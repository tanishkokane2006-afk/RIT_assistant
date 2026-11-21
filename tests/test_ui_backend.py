"""
Integration and unit tests for UI backend endpoints:
- GET /ui-config: Public configuration values
- GET /usage: Unchanged contract with additive 'unlimited' field
- GET /auth/me: Token validation returning masked identity
- POST /feedback: Answer-level and general feedback, validation, honeypot, rate limiting
- POST /suggestions: User question suggestions, unanswered alerts, validation, honeypot
- Admin dashboard endpoints:
  - 404 when RIT_ADMIN_KEY is not configured
  - 401 when X-Admin-Key is missing or incorrect
  - 200 and valid data when X-Admin-Key matches
  - GET /admin/submissions: counts, filtering, search
  - PATCH /admin/submissions/{id}: status update and admin notes
  - GET /admin/export.csv: UTF-8 BOM, formula injection defense, X-Robots-Tag
  - GET /admin/top-questions: normalised grouping and frequencies
- CLI purge command: python -m backend.feedback purge --days N
- Security headers and CSP compliance on all HTTP responses
"""

import codecs
import csv
import io
import time
import uuid
from fastapi.testclient import TestClient

import config
from backend.access import make_token
from backend.app import app
from backend.feedback import (
    escape_csv_cell,
    purge_old_submissions,
    init_feedback_db,
    get_db_connection,
)

client = TestClient(app)


def test_ui_config_endpoint():
    res = client.get("/ui-config")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["institute_name"] == config.INSTITUTE_NAME
    assert data["assistant_name"] == config.ASSISTANT_NAME
    assert data["guest_limit"] == config.GUEST_LIMIT
    assert data["max_query_chars"] == config.MAX_QUERY_CHARS
    assert data["support_email"] == config.SUPPORT_EMAIL
    assert data["privacy_url"] == config.PRIVACY_URL
    assert "data_updated" in data
    assert data["data_updated"] is not None


def test_usage_unlimited_field():
    # Guest user
    guest_cookie = {"guest_id": f"guest_ui_{uuid.uuid4().hex[:8]}"}
    res = client.get("/usage", cookies=guest_cookie)
    assert res.status_code == 200
    data = res.json()
    assert data["unlimited"] is False
    assert data["is_institute"] is False
    assert isinstance(data["remaining"], int)

    # Institute user
    token = make_token("faculty@ritindia.edu", ttl_seconds=3600)
    res_inst = client.get("/usage", headers={"X-Institute-Token": token})
    assert res_inst.status_code == 200
    data_inst = res_inst.json()
    assert data_inst["unlimited"] is True
    assert data_inst["is_institute"] is True
    assert data_inst["remaining"] is None


def test_auth_me_endpoint():
    # 1. Missing token -> 401
    res = client.get("/auth/me")
    assert res.status_code == 401

    # 2. Invalid token -> 401
    res = client.get("/auth/me", headers={"X-Institute-Token": "invalid_fake_token"})
    assert res.status_code == 401

    # 3. Valid standard email token
    token = make_token("student123@ritindia.edu", ttl_seconds=3600)
    res = client.get("/auth/me", headers={"X-Institute-Token": token})
    assert res.status_code == 200
    data = res.json()
    assert data["authenticated"] is True
    assert data["masked_email"] == "s***@ritindia.edu"
    assert data["unlimited"] is True

    # 4. Valid single-letter username token
    token_short = make_token("x@ritindia.edu", ttl_seconds=3600)
    res_short = client.get("/auth/me", headers={"X-Institute-Token": token_short})
    assert res_short.status_code == 200
    assert res_short.json()["masked_email"] == "x***@ritindia.edu"


def test_feedback_submission():
    user_cookie = {"guest_id": f"guest_fb_{uuid.uuid4().hex[:8]}"}

    # 1. Honeypot rejection
    res_hp = client.post(
        "/feedback",
        json={"kind": "general", "text": "spam", "hp": "bot_content"},
        cookies=user_cookie
    )
    assert res_hp.status_code == 422

    # 2. Invalid kind
    res_bad = client.post(
        "/feedback",
        json={"kind": "invalid_kind", "text": "test"},
        cookies=user_cookie
    )
    assert res_bad.status_code == 422

    # 3. Invalid contact email
    res_bad_email = client.post(
        "/feedback",
        json={"kind": "general", "text": "test", "contact_email": "not-an-email"},
        cookies=user_cookie
    )
    assert res_bad_email.status_code == 422

    # 4. Valid answer feedback
    res_ans = client.post(
        "/feedback",
        json={
            "kind": "answer",
            "rating": 5,
            "query": "What is the intake for CSE?",
            "answer": "The intake is 120 seats.",
            "mode": "structured",
            "sources": ["https://ritindia.edu/intake"],
            "text": "Very accurate and quick answer."
        },
        cookies=user_cookie
    )
    assert res_ans.status_code == 200
    data_ans = res_ans.json()
    assert data_ans["status"] == "ok"
    assert data_ans["id"].startswith("sub_")

    # 5. Valid general feedback with institute token
    inst_token = make_token("prof@ritindia.edu", ttl_seconds=3600)
    res_gen = client.post(
        "/feedback",
        json={
            "kind": "general",
            "rating": 4,
            "category": "suggestion",
            "text": "Add a dark mode toggle button in chat header.",
            "contact_email": "prof@ritindia.edu"
        },
        headers={"X-Institute-Token": inst_token}
    )
    assert res_gen.status_code == 200
    assert res_gen.json()["status"] == "ok"


def test_feedback_rate_limit():
    rate_limit_cookie = {"guest_id": f"guest_rate_{uuid.uuid4().hex[:8]}"}

    # 5 submissions within an hour should succeed
    for i in range(5):
        res = client.post(
            "/feedback",
            json={"kind": "general", "text": f"Feedback number {i+1}"},
            cookies=rate_limit_cookie
        )
        assert res.status_code == 200, f"Submission {i+1} failed"

    # 6th submission must be rejected with HTTP 429
    res_blocked = client.post(
        "/feedback",
        json={"kind": "general", "text": "Feedback number 6"},
        cookies=rate_limit_cookie
    )
    assert res_blocked.status_code == 429
    assert "rate limit reached" in res_blocked.json()["detail"].lower()


def test_suggestions_submission():
    sugg_cookie = {"guest_id": f"guest_sugg_{uuid.uuid4().hex[:8]}"}

    # 1. Honeypot check
    res_hp = client.post(
        "/suggestions",
        json={"question": "What sports facilities exist?", "hp": "spam_bot"},
        cookies=sugg_cookie
    )
    assert res_hp.status_code == 422

    # 2. Empty question
    res_empty = client.post(
        "/suggestions",
        json={"question": "   "},
        cookies=sugg_cookie
    )
    assert res_empty.status_code == 422

    # 3. Valid question suggestion
    res_ok = client.post(
        "/suggestions",
        json={
            "question": "Can I get hostel details for direct second year students?",
            "details": "Specifically looking for boys hostel fees and rules.",
            "category": "campus",
            "contact_email": "applicant@gmail.com"
        },
        cookies=sugg_cookie
    )
    assert res_ok.status_code == 200
    assert res_ok.json()["status"] == "ok"
    assert res_ok.json()["id"].startswith("sub_")

    # 4. Valid unanswered report
    res_unans = client.post(
        "/suggestions",
        json={
            "kind": "unanswered",
            "question": "Where is the student photocopy center located?",
            "category": "campus"
        },
        cookies=sugg_cookie
    )
    assert res_unans.status_code == 200
    assert res_unans.json()["status"] == "ok"


def test_admin_api():
    # Save original config
    orig_key = config.ADMIN_KEY
    test_admin_key = "test_admin_secret_key_12345"

    try:
        # 1. When ADMIN_KEY is not configured or < 16 chars -> 404
        config.ADMIN_KEY = None
        res_disabled = client.get("/admin/submissions")
        assert res_disabled.status_code == 404

        config.ADMIN_KEY = "too_short"
        res_short = client.get("/admin/submissions")
        assert res_short.status_code == 404

        # Enable admin key
        config.ADMIN_KEY = test_admin_key

        # 2. Missing admin key -> 401
        res_no_auth = client.get("/admin/submissions")
        assert res_no_auth.status_code == 401

        # 3. Wrong admin key -> 401
        res_wrong = client.get("/admin/submissions", headers={"X-Admin-Key": "wrong_key_12345678"})
        assert res_wrong.status_code == 401

        # 4. Correct admin key -> 200
        admin_headers = {"X-Admin-Key": test_admin_key}
        res_subs = client.get("/admin/submissions", headers=admin_headers)
        assert res_subs.status_code == 200
        data = res_subs.json()
        assert "items" in data
        assert "total" in data
        assert "counts" in data
        assert "by_kind" in data["counts"]
        assert "by_status" in data["counts"]

        # 5. Insert test submission and test PATCH /admin/submissions/{id}
        test_item_id = None
        if data["items"]:
            test_item_id = data["items"][0]["id"]
        else:
            # Create a suggestion first
            res_s = client.post("/suggestions", json={"question": "Test question for patch"})
            test_item_id = res_s.json()["id"]

        # Patch status and admin note
        res_patch = client.patch(
            f"/admin/submissions/{test_item_id}",
            json={"status": "in_review", "admin_note": "Reviewed by IT admin."},
            headers=admin_headers
        )
        assert res_patch.status_code == 200
        patch_data = res_patch.json()
        assert patch_data["status"] == "in_review"
        assert patch_data["admin_note"] == "Reviewed by IT admin."

        # Invalid status patch -> 422
        res_bad_status = client.patch(
            f"/admin/submissions/{test_item_id}",
            json={"status": "non_existent_status"},
            headers=admin_headers
        )
        assert res_bad_status.status_code == 422

        # Non-existent ID patch -> 404
        res_bad_id = client.patch(
            "/admin/submissions/sub_nonexistent999",
            json={"status": "done"},
            headers=admin_headers
        )
        assert res_bad_id.status_code == 404

        # 6. Test GET /admin/top-questions
        # Create identical suggestions to test grouping
        common_q = "What is the fee for OBC category?"
        client.post("/suggestions", json={"question": common_q})
        client.post("/suggestions", json={"question": "What is the fee for OBC category?"})

        res_top = client.get("/admin/top-questions", headers=admin_headers)
        assert res_top.status_code == 200
        top_data = res_top.json()
        assert "top_questions" in top_data
        assert isinstance(top_data["top_questions"], list)
        found = any("what is the fee for obc category" in item["normalised_question"] for item in top_data["top_questions"])
        assert found, "Top questions grouping should contain common question"

        # 7. Test CSV export with UTF-8 BOM and formula injection defense
        # Submit a potentially dangerous formula
        client.post("/suggestions", json={"question": "=1+1", "details": "@cmd.exe"})

        res_csv = client.get("/admin/export.csv", headers=admin_headers)
        assert res_csv.status_code == 200
        assert res_csv.headers["content-type"].startswith("text/csv")
        assert res_csv.headers.get("x-robots-tag") == "noindex"

        content = res_csv.content
        assert content.startswith(codecs.BOM_UTF8), "Export CSV must start with UTF-8 BOM"

        # Read CSV rows to verify formula escaping
        text_content = content.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text_content))
        header = next(reader)
        assert "query" in header

        # Check escape_csv_cell function directly
        assert escape_csv_cell("=SUM(A1:A10)") == "'=SUM(A1:A10)"
        assert escape_csv_cell("+12345") == "'+12345"
        assert escape_csv_cell("-command") == "'-command"
        assert escape_csv_cell("@danger") == "'@danger"
        assert escape_csv_cell("Regular text") == "Regular text"

    finally:
        config.ADMIN_KEY = orig_key


def test_cli_purge():
    # Insert dummy old submission
    conn = get_db_connection()
    c = conn.cursor()
    old_id = "sub_old_test_dummy"
    c.execute("""
        INSERT OR REPLACE INTO submissions (
            id, kind, status, created_at, updated_at, user_type, rating,
            category, text, query, answer, mode, sources_json, contact_email, admin_note
        ) VALUES (?, 'suggestion', 'new', '2020-01-01T00:00:00+00:00', '2020-01-01T00:00:00+00:00', 'guest', NULL,
                 NULL, NULL, 'old question', NULL, NULL, NULL, NULL, NULL)
    """, (old_id,))
    conn.commit()
    conn.close()

    # Purge submissions older than 100 days
    purged = purge_old_submissions(days=100)
    assert purged >= 1, "Should have purged at least the 2020 dummy submission"

    # Verify old row deleted
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM submissions WHERE id = ?", (old_id,))
    row = c.fetchone()
    conn.close()
    assert row is None, "Old submission must be purged"


def test_security_headers_and_csp():
    # Test on /health
    res_health = client.get("/health")
    assert res_health.status_code == 200
    headers = res_health.headers
    assert "default-src 'self'" in headers.get("content-security-policy", "")
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("referrer-policy") == "no-referrer"

    # Test /admin route headers
    res_admin = client.get("/admin")
    assert res_admin.status_code == 200
    assert res_admin.headers.get("x-robots-tag") == "noindex"
    assert "default-src 'self'" in res_admin.headers.get("content-security-policy", "")

    # Test static / route headers
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert "default-src 'self'" in res_root.headers.get("content-security-policy", "")


if __name__ == "__main__":
    test_ui_config_endpoint()
    test_usage_unlimited_field()
    test_auth_me_endpoint()
    test_feedback_submission()
    test_feedback_rate_limit()
    test_suggestions_submission()
    test_admin_api()
    test_cli_purge()
    test_security_headers_and_csp()
    print("test_ui_backend: ALL PASSED")
