"""Tests for access control and guest rate limiter (5-query limit)."""

import tempfile
from pathlib import Path

import config
from backend.access import AccessControl, make_token, verify_token


def test_guest_5_query_limit():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = Path(tmpdir) / "test_access.db"
        manager = AccessControl(db_path=test_db, guest_limit=5)
        guest_id = "test_guest_123"

        # Check initial status
        allowed, remaining = manager.get_remaining(guest_id)
        assert allowed is True
        assert remaining == 5

        # First 5 queries should succeed
        for i in range(1, 6):
            allowed, remaining = manager.consume(guest_id)
            assert allowed is True
            assert remaining == 5 - i

        # 6th query must be rejected
        allowed, remaining = manager.consume(guest_id)
        assert allowed is False
        assert remaining == 0

        # Status should show 0 remaining
        allowed, remaining = manager.get_remaining(guest_id)
        assert allowed is False
        assert remaining == 0


def test_institute_unlimited():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = Path(tmpdir) / "test_access.db"
        manager = AccessControl(db_path=test_db, guest_limit=5)
        user_id = "faculty@ritindia.edu"

        # 10 queries should all succeed without decrements
        for _ in range(10):
            allowed, remaining = manager.consume(user_id, institute=True)
            assert allowed is True
            assert remaining is None

        allowed, remaining = manager.get_remaining(user_id, institute=True)
        assert allowed is True
        assert remaining is None


def test_token_issuance_and_verification():
    # Valid token
    token = make_token("student@ritindia.edu", ttl_seconds=3600)
    email = verify_token(token)
    assert email == "student@ritindia.edu"

    # Expired token
    expired_token = make_token("student@ritindia.edu", ttl_seconds=-10)
    assert verify_token(expired_token) is None

    # Tampered token
    parts = token.split(":")
    tampered = f"{parts[0]}:{parts[1]}:{'0' * len(parts[2])}"
    assert verify_token(tampered) is None

    # Invalid domain
    foreign_token = make_token("hacker@otherdomain.com", ttl_seconds=3600)
    assert verify_token(foreign_token) is None


if __name__ == "__main__":
    test_guest_5_query_limit()
    test_institute_unlimited()
    test_token_issuance_and_verification()
    print("test_access: ALL PASSED")
