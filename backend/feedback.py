"""
Feedback, Suggestions, UI Configuration, and Admin System for RIT Assistant v3.
Features:
- GET /ui-config: Public UI settings (institute name, limits, contacts, etc.)
- GET /auth/me: Token validation returning masked identity.
- POST /feedback: Answer-level or general user feedback.
- POST /suggestions: User-suggested questions and unanswered question reports.
- Admin dashboard APIs (protected by RIT_ADMIN_KEY):
  - GET /admin/submissions
  - PATCH /admin/submissions/{id}
  - GET /admin/export.csv (CSV-injection safe, UTF-8 with BOM)
  - GET /admin/top-questions (Normalised grouping)
- CLI support: python -m backend.feedback purge --days N
"""

import argparse
import codecs
import csv
import datetime
import hmac
import io
import json
import logging
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import Response as FastApiResponse
from pydantic import BaseModel, Field

import config
from backend.access import verify_token

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backend.feedback")

router = APIRouter()

# --------------------------------------------------------------------------
# Database Initialization
# --------------------------------------------------------------------------
def get_db_connection() -> sqlite3.Connection:
    config.ensure_directories()
    config.FEEDBACK_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(config.FEEDBACK_DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_feedback_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'new',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            user_type TEXT NOT NULL,
            rating INTEGER,
            category TEXT,
            text TEXT,
            query TEXT,
            answer TEXT,
            mode TEXT,
            sources_json TEXT,
            contact_email TEXT,
            admin_note TEXT
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_sub_kind ON submissions(kind)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_sub_status ON submissions(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_sub_created ON submissions(created_at)")
    conn.commit()
    conn.close()

init_feedback_db()

# --------------------------------------------------------------------------
# In-Memory Rate Limiting (5 submissions per hour per user)
# --------------------------------------------------------------------------
_rate_limit_lock = threading.Lock()
_user_submission_timestamps: Dict[str, List[float]] = {}
SUBMISSION_LIMIT_PER_HOUR = 5

def check_submission_rate_limit(user_key: str):
    now = time.time()
    one_hour_ago = now - 3600.0
    with _rate_limit_lock:
        timestamps = _user_submission_timestamps.get(user_key, [])
        valid_timestamps = [t for t in timestamps if t > one_hour_ago]
        if len(valid_timestamps) >= SUBMISSION_LIMIT_PER_HOUR:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Submission rate limit reached ({SUBMISSION_LIMIT_PER_HOUR} submissions per hour). Please try again later."
            )
        valid_timestamps.append(now)
        _user_submission_timestamps[user_key] = valid_timestamps

# --------------------------------------------------------------------------
# Text Sanitization and Email Validation
# --------------------------------------------------------------------------
def sanitize_text(val: Optional[str]) -> Optional[str]:
    """Strip control characters while preserving standard whitespace (newlines, tabs)."""
    if val is None:
        return None
    # Strip chars < 32 except \t (9), \n (10), \r (13); also strip \x7f (127)
    cleaned = "".join(c for c in val if (ord(c) >= 32 or c in ("\n", "\r", "\t")) and ord(c) != 127)
    return cleaned.strip()

def validate_email_format(email: Optional[str]) -> Optional[str]:
    if not email:
        return None
    email_clean = email.strip()
    if not email_clean:
        return None
    if len(email_clean) > 120:
        raise HTTPException(status_code=422, detail="Contact email exceeds 120 characters.")
    if not re.match(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", email_clean):
        raise HTTPException(status_code=422, detail="Invalid email format.")
    return email_clean

def get_submission_user(request: Request) -> Tuple[str, str]:
    """Resolve (user_key, user_type: 'guest'|'institute')."""
    token_header = request.headers.get("X-Institute-Token")
    if token_header:
        email = verify_token(token_header)
        if email:
            return email, "institute"

    guest_id = request.cookies.get("guest_id")
    if not guest_id:
        guest_id = f"guest_{uuid.uuid4().hex[:12]}"
    return guest_id, "guest"

# --------------------------------------------------------------------------
# Public Pydantic Models
# --------------------------------------------------------------------------
class UIConfigResponse(BaseModel):
    institute_name: str
    assistant_name: str
    guest_limit: int
    max_query_chars: int
    support_email: str
    privacy_url: str
    data_updated: Optional[str] = None

class AuthMeResponse(BaseModel):
    authenticated: bool
    masked_email: str
    unlimited: bool

class FeedbackPayload(BaseModel):
    kind: str = Field(..., description="'answer' or 'general'")
    rating: Optional[int] = Field(None, ge=1, le=5)
    category: Optional[str] = Field(None, max_length=100)
    text: Optional[str] = Field(None, max_length=1000)
    query: Optional[str] = Field(None, max_length=500)
    answer: Optional[str] = Field(None, max_length=2000)
    mode: Optional[str] = Field(None, max_length=50)
    sources: Optional[List[str]] = Field(None)
    contact_email: Optional[str] = Field(None, max_length=120)
    hp: Optional[str] = Field(None, description="Honeypot field (must be empty)")

class SuggestionPayload(BaseModel):
    question: str = Field(..., min_length=1, max_length=300)
    details: Optional[str] = Field(None, max_length=500)
    category: Optional[str] = Field(None, max_length=100)
    contact_email: Optional[str] = Field(None, max_length=120)
    kind: Optional[str] = Field("suggestion", description="'suggestion' or 'unanswered'")
    hp: Optional[str] = Field(None, description="Honeypot field (must be empty)")

class AdminSubmissionPatch(BaseModel):
    status: Optional[str] = Field(None, description="'new', 'in_review', 'done', 'declined'")
    admin_note: Optional[str] = Field(None, max_length=2000)

# --------------------------------------------------------------------------
# Endpoints: UI Config & Auth Verification
# --------------------------------------------------------------------------
@router.get("/ui-config", response_model=UIConfigResponse)
def get_ui_config():
    """Public UI configuration values."""
    data_updated = "2024-25 / 2025-26 Academic Data"
    if config.EMB_PATH.exists():
        try:
            mtime = config.EMB_PATH.stat().st_mtime
            dt = datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc)
            data_updated = dt.strftime("%b %Y (Indexed)")
        except Exception:
            pass

    return UIConfigResponse(
        institute_name=config.INSTITUTE_NAME,
        assistant_name=config.ASSISTANT_NAME,
        guest_limit=config.GUEST_LIMIT,
        max_query_chars=config.MAX_QUERY_CHARS,
        support_email=config.SUPPORT_EMAIL,
        privacy_url=config.PRIVACY_URL,
        data_updated=data_updated
    )

@router.get("/auth/me", response_model=AuthMeResponse)
def auth_me(request: Request):
    """Validate institute token and return masked identity."""
    token = request.headers.get("X-Institute-Token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing institute token.")

    email = verify_token(token)
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid, expired, or untrusted institute token.")

    # Mask email: e.g. "s***@ritindia.edu"
    parts = email.split("@")
    user_part = parts[0]
    domain_part = parts[1] if len(parts) > 1 else ""
    if len(user_part) <= 1:
        masked_user = f"{user_part}***"
    else:
        masked_user = f"{user_part[0]}***"
    masked_email = f"{masked_user}@{domain_part}"

    return AuthMeResponse(
        authenticated=True,
        masked_email=masked_email,
        unlimited=True
    )

# --------------------------------------------------------------------------
# Endpoints: Feedback & Suggestions
# --------------------------------------------------------------------------
@router.post("/feedback")
def submit_feedback(payload: FeedbackPayload, request: Request):
    """Submit general or answer-specific feedback."""
    if payload.hp:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid submission.")

    allowed_kinds = {"answer", "general"}
    if payload.kind not in allowed_kinds:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Kind must be 'answer' or 'general'.")

    user_key, user_type = get_submission_user(request)
    check_submission_rate_limit(user_key)

    contact_email = validate_email_format(payload.contact_email)
    sub_id = f"sub_{uuid.uuid4().hex[:12]}"
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    internal_kind = "answer_feedback" if payload.kind == "answer" else "general_feedback"

    sources_json = json.dumps(payload.sources) if payload.sources else None

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO submissions (
            id, kind, status, created_at, updated_at, user_type, rating,
            category, text, query, answer, mode, sources_json, contact_email, admin_note
        ) VALUES (?, ?, 'new', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
    """, (
        sub_id,
        internal_kind,
        now_iso,
        now_iso,
        user_type,
        payload.rating,
        sanitize_text(payload.category),
        sanitize_text(payload.text),
        sanitize_text(payload.query),
        sanitize_text(payload.answer),
        sanitize_text(payload.mode),
        sources_json,
        contact_email
    ))
    conn.commit()
    conn.close()

    logger.info("New feedback submission: id=%s kind=%s user_type=%s", sub_id, internal_kind, user_type)
    return {"status": "ok", "id": sub_id}

@router.post("/suggestions")
def submit_suggestion(payload: SuggestionPayload, request: Request):
    """Submit suggested questions or unanswerable query alerts."""
    if payload.hp:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid submission.")

    allowed_kinds = {"suggestion", "unanswered"}
    kind = payload.kind or "suggestion"
    if kind not in allowed_kinds:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Kind must be 'suggestion' or 'unanswered'.")

    q_clean = sanitize_text(payload.question)
    if not q_clean:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Question cannot be empty.")

    user_key, user_type = get_submission_user(request)
    check_submission_rate_limit(user_key)

    contact_email = validate_email_format(payload.contact_email)
    sub_id = f"sub_{uuid.uuid4().hex[:12]}"
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO submissions (
            id, kind, status, created_at, updated_at, user_type, rating,
            category, text, query, answer, mode, sources_json, contact_email, admin_note
        ) VALUES (?, ?, 'new', ?, ?, ?, NULL, ?, ?, ?, NULL, NULL, NULL, ?, NULL)
    """, (
        sub_id,
        kind,
        now_iso,
        now_iso,
        user_type,
        sanitize_text(payload.category),
        sanitize_text(payload.details),
        q_clean,
        contact_email
    ))
    conn.commit()
    conn.close()

    logger.info("New question suggestion: id=%s kind=%s user_type=%s", sub_id, kind, user_type)
    return {"status": "ok", "id": sub_id}

# --------------------------------------------------------------------------
# Admin Authentication & Endpoints
# --------------------------------------------------------------------------
def verify_admin_key(x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key")) -> str:
    """Verify admin key constant-time. Returns 404 if disabled, 401 if invalid."""
    if not config.ADMIN_KEY or len(config.ADMIN_KEY) < 16:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin interface is not configured or enabled."
        )

    if not x_admin_key or not hmac.compare_digest(x_admin_key.strip(), config.ADMIN_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin authentication key."
        )

    return config.ADMIN_KEY

@router.get("/admin/submissions")
def admin_get_submissions(
    kind: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    q: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: str = Depends(verify_admin_key)
):
    """Retrieve submissions with filtering, search, and metric counts."""
    conn = get_db_connection()
    c = conn.cursor()

    # Calculate counts by kind and status
    c.execute("SELECT kind, count(*) FROM submissions GROUP BY kind")
    by_kind = {r[0]: r[1] for r in c.fetchall()}

    c.execute("SELECT status, count(*) FROM submissions GROUP BY status")
    by_status = {r[0]: r[1] for r in c.fetchall()}

    where_clauses = []
    params: List[Any] = []

    if kind:
        where_clauses.append("kind = ?")
        params.append(kind)
    if status_filter:
        where_clauses.append("status = ?")
        params.append(status_filter)
    if q:
        search_pattern = f"%{q.strip()}%"
        where_clauses.append("(query LIKE ? OR text LIKE ? OR contact_email LIKE ? OR admin_note LIKE ?)")
        params.extend([search_pattern, search_pattern, search_pattern, search_pattern])

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    # Total matching count
    c.execute(f"SELECT count(*) FROM submissions {where_sql}", params)
    total = c.fetchone()[0]

    # Query rows
    sql = f"""
        SELECT id, kind, status, created_at, updated_at, user_type, rating,
               category, text, query, answer, mode, sources_json, contact_email, admin_note
        FROM submissions {where_sql}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """
    c.execute(sql, params + [limit, offset])
    rows = c.fetchall()
    conn.close()

    items = []
    for r in rows:
        item = dict(r)
        if item.get("sources_json"):
            try:
                item["sources"] = json.loads(item["sources_json"])
            except Exception:
                item["sources"] = []
        else:
            item["sources"] = []
        items.append(item)

    return {
        "items": items,
        "total": total,
        "counts": {
            "by_kind": by_kind,
            "by_status": by_status
        }
    }

@router.patch("/admin/submissions/{sub_id}")
def admin_patch_submission(
    sub_id: str,
    payload: AdminSubmissionPatch,
    _: str = Depends(verify_admin_key)
):
    """Update submission status or admin note."""
    allowed_statuses = {"new", "in_review", "done", "declined"}
    if payload.status is not None and payload.status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Status must be one of {sorted(allowed_statuses)}"
        )

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM submissions WHERE id = ?", (sub_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found.")

    updates = []
    params = []
    if payload.status is not None:
        updates.append("status = ?")
        params.append(payload.status)
    if payload.admin_note is not None:
        updates.append("admin_note = ?")
        params.append(sanitize_text(payload.admin_note))

    if updates:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        updates.append("updated_at = ?")
        params.append(now_iso)
        params.append(sub_id)

        sql = f"UPDATE submissions SET {', '.join(updates)} WHERE id = ?"
        c.execute(sql, params)
        conn.commit()

    c.execute("SELECT * FROM submissions WHERE id = ?", (sub_id,))
    updated = dict(c.fetchone())
    conn.close()
    return updated

def escape_csv_cell(val: Any) -> str:
    """Protect against CSV formula injection by prefixing formula trigger chars with a single quote."""
    if val is None:
        return ""
    s = str(val).strip()
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{s}"
    return s

@router.get("/admin/export.csv")
def admin_export_csv(
    kind: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    _: str = Depends(verify_admin_key)
):
    """Export submissions as UTF-8 CSV with BOM and CSV injection defense."""
    conn = get_db_connection()
    c = conn.cursor()

    where_clauses = []
    params: List[Any] = []
    if kind:
        where_clauses.append("kind = ?")
        params.append(kind)
    if status_filter:
        where_clauses.append("status = ?")
        params.append(status_filter)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    c.execute(f"SELECT * FROM submissions {where_sql} ORDER BY created_at DESC", params)
    rows = c.fetchall()
    conn.close()

    fields = [
        "id", "kind", "status", "created_at", "updated_at", "user_type",
        "rating", "category", "text", "query", "answer", "mode",
        "sources_json", "contact_email", "admin_note"
    ]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(fields)

    for r in rows:
        row_dict = dict(r)
        safe_row = [escape_csv_cell(row_dict.get(k)) for k in fields]
        writer.writerow(safe_row)

    # Encode with UTF-8 BOM
    csv_bytes = codecs.BOM_UTF8 + output.getvalue().encode("utf-8")

    return FastApiResponse(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=\"rit_assistant_submissions.csv\"",
            "X-Robots-Tag": "noindex"
        }
    )

@router.get("/admin/top-questions")
def admin_top_questions(_: str = Depends(verify_admin_key)):
    """Group suggestions and unanswered queries by normalised question text with frequencies."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT id, kind, query, text, created_at, status
        FROM submissions
        WHERE kind IN ('suggestion', 'unanswered') AND query IS NOT NULL
        ORDER BY created_at DESC
    """)
    rows = c.fetchall()
    conn.close()

    groups: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        q_raw = r["query"] or ""
        # Normalise question: lowercase, alphanumeric and spaces only
        norm_q = re.sub(r"[^a-z0-9\s]", "", q_raw.lower()).strip()
        if not norm_q:
            continue

        if norm_q not in groups:
            groups[norm_q] = {
                "normalised_question": norm_q,
                "sample_question": q_raw,
                "count": 0,
                "kinds": set(),
                "statuses": set(),
                "latest_date": r["created_at"],
                "ids": []
            }

        g = groups[norm_q]
        g["count"] += 1
        g["kinds"].add(r["kind"])
        g["statuses"].add(r["status"])
        g["ids"].append(r["id"])

    # Convert sets to sorted lists and sort groups by count descending
    result = []
    for g in groups.values():
        g["kinds"] = sorted(list(g["kinds"]))
        g["statuses"] = sorted(list(g["statuses"]))
        result.append(g)

    result.sort(key=lambda x: x["count"], reverse=True)
    return {"top_questions": result}

# --------------------------------------------------------------------------
# CLI Maintenance Support: Purge
# --------------------------------------------------------------------------
def purge_old_submissions(days: int = config.FEEDBACK_RETENTION_DAYS) -> int:
    """Purge submissions older than N days."""
    cutoff_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    cutoff_iso = cutoff_dt.isoformat()

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM submissions WHERE created_at < ?", (cutoff_iso,))
    purged = c.rowcount
    conn.commit()
    conn.close()
    logger.info("Purged %d submissions older than %d days (before %s)", purged, days, cutoff_iso)
    return purged

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage feedback submissions.")
    subparsers = parser.add_subparsers(dest="subcommand")

    purge_parser = subparsers.add_parser("purge", help="Purge submissions older than N days")
    purge_parser.add_argument("--days", type=int, default=config.FEEDBACK_RETENTION_DAYS, help="Retention period in days")

    args = parser.parse_args()
    if args.subcommand == "purge":
        count = purge_old_submissions(days=args.days)
        print(f"Successfully purged {count} submissions older than {args.days} days.")
    else:
        parser.print_help()
