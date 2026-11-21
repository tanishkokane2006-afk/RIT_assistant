"""
Access control and token management for RIT Assistant v3.
Features:
- Atomic guest usage tracking (5-query limit) using SQLite with BEGIN IMMEDIATE transactions.
- Concurrent thread safety.
- Signed institute tokens with HMAC-SHA256 and constant-time comparison.
- Institute users (email ending in config.INSTITUTE_DOMAINS) have unlimited queries.
- CLI: python -m backend.access issue user@ritindia.edu
"""

import argparse
import hashlib
import hmac
import logging
import sqlite3
import sys
import time
from pathlib import Path
from typing import Tuple, Optional

import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backend.access")

def make_token(email: str, ttl_seconds: int = config.TOKEN_TTL_SECONDS, secret: str = config.TOKEN_SECRET) -> str:
    """Generate an HMAC-SHA256 signed token for an institute email."""
    email_clean = email.strip().lower()
    expiry = int(time.time()) + ttl_seconds
    payload = f"{email_clean}:{expiry}"
    sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"

def verify_token(token: Optional[str], secret: str = config.TOKEN_SECRET) -> Optional[str]:
    """
    Verify an HMAC-SHA256 signed token.
    Checks: signature integrity (constant-time), expiry, and institute domain.
    Returns verified email if valid, or None.
    """
    if not token or not token.strip():
        return None

    parts = token.strip().split(":")
    if len(parts) != 3:
        return None

    email, expiry_str, provided_sig = parts[0], parts[1], parts[2]

    # Verify expiry
    try:
        expiry = int(expiry_str)
        if time.time() > expiry:
            logger.info("Token expired for email: %s", email)
            return None
    except ValueError:
        return None

    # Verify signature with constant-time comparison
    payload = f"{email}:{expiry_str}"
    expected_sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(provided_sig, expected_sig):
        logger.warning("Tampered or invalid token signature for email: %s", email)
        return None

    # Verify institute domain
    domain = email.split("@")[-1].lower() if "@" in email else ""
    if domain not in config.INSTITUTE_DOMAINS:
        logger.warning("Token domain '%s' not in institute domains: %s", domain, config.INSTITUTE_DOMAINS)
        return None

    return email

class AccessControl:
    def __init__(self, db_path: Path = config.DB_PATH, guest_limit: int = config.GUEST_LIMIT):
        config.ensure_directories()
        self.db_path = db_path
        self.guest_limit = guest_limit
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0, isolation_level=None)
        return conn

    def _init_db(self):
        """Initialize usage table."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usage (
                user_id TEXT PRIMARY KEY,
                count INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.close()

    def consume(self, user_id: str, institute: bool = False) -> Tuple[bool, Optional[int]]:
        """
        Atomically consume query quota.
        - Institute users: unlimited, returns (True, None).
        - Guest users: tracked with BEGIN IMMEDIATE up to guest_limit.
        Returns: (allowed, remaining)
        """
        if institute:
            return True, None

        user_clean = user_id.strip()
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # BEGIN IMMEDIATE prevents concurrent readers from acquiring write locks
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute("SELECT count FROM usage WHERE user_id = ?", (user_clean,))
            row = cursor.fetchone()

            current_count = row[0] if row else 0

            if current_count >= self.guest_limit:
                cursor.execute("COMMIT")
                return False, 0

            new_count = current_count + 1
            cursor.execute(
                "INSERT OR REPLACE INTO usage (user_id, count) VALUES (?, ?)",
                (user_clean, new_count)
            )
            cursor.execute("COMMIT")
            remaining = max(0, self.guest_limit - new_count)
            return True, remaining
        except Exception as e:
            cursor.execute("ROLLBACK")
            logger.error("Database error in access.consume: %s", e)
            raise e
        finally:
            conn.close()

    def get_remaining(self, user_id: str, institute: bool = False) -> Tuple[bool, Optional[int]]:
        """Check status and remaining queries without incrementing."""
        if institute:
            return True, None

        user_clean = user_id.strip()
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT count FROM usage WHERE user_id = ?", (user_clean,))
        row = cursor.fetchone()
        conn.close()

        current_count = row[0] if row else 0
        remaining = max(0, self.guest_limit - current_count)
        return current_count < self.guest_limit, remaining

access_control = AccessControl()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Access control token management CLI")
    subparsers = parser.add_subparsers(dest="subcommand")

    issue_p = subparsers.add_parser("issue", help="Issue an institute access token")
    issue_p.add_argument("email", help="Institute email address (e.g. user@ritindia.edu)")
    issue_p.add_argument("--ttl", type=int, default=config.TOKEN_TTL_SECONDS, help="TTL in seconds")

    args = parser.parse_args()
    if args.subcommand == "issue":
        token = make_token(args.email, ttl_seconds=args.ttl)
        verified = verify_token(token)
        if not verified:
            print(f"Warning: Domain for '{args.email}' is not in config.INSTITUTE_DOMAINS ({config.INSTITUTE_DOMAINS}).")
        print(f"Issued Token for {args.email}:\n{token}")
    else:
        parser.print_help()
