"""Unit and integration tests for FastAPI App (Task E).
Tests:
- 5 guest calls succeed, 6th returns HTTP 429
- Institute token allows unlimited queries
- Invalid token returns HTTP 401
- Empty or oversized query returns HTTP 422
- GET /health returns valid status and metadata
- GET /usage reports quota correctly
"""

import tempfile
import uuid
from pathlib import Path
from fastapi.testclient import TestClient

import config
from backend.access import make_token
from backend.app import app

client = TestClient(app)

def test_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["model"] == config.MODEL_NAME

def test_query_validation():
    # Empty query
    res = client.post("/chat", json={"query": ""})
    assert res.status_code == 422

    # Whitespace only
    res = client.post("/chat", json={"query": "   "})
    assert res.status_code == 422

    # Oversized query (> 500 chars)
    oversized = "a" * (config.MAX_QUERY_CHARS + 10)
    res = client.post("/chat", json={"query": oversized})
    assert res.status_code == 422

def test_guest_rate_limiting():
    # Create isolated client with custom guest cookie
    guest_cookie = {"guest_id": f"test_client_guest_{uuid.uuid4().hex[:8]}"}

    # First 5 calls succeed
    for i in range(1, 6):
        res = client.post("/chat", json={"query": "What is RIT?"}, cookies=guest_cookie)
        assert res.status_code == 200, f"Query {i} failed: {res.text}"
        data = res.json()
        assert data["remaining"] == 5 - i

    # 6th call must return 429 Too Many Requests
    res = client.post("/chat", json={"query": "What is RIT?"}, cookies=guest_cookie)
    assert res.status_code == 429
    assert "limit reached" in res.json()["detail"].lower()

def test_institute_token_auth():
    # 1. Invalid token returns 401
    res = client.post(
        "/chat",
        json={"query": "What is RIT?"},
        headers={"X-Institute-Token": "invalid_fake_token"}
    )
    assert res.status_code == 401

    # 2. Valid token allows unlimited queries
    valid_token = make_token("student@ritindia.edu", ttl_seconds=3600)
    headers = {"X-Institute-Token": valid_token}

    for _ in range(7):
        res = client.post("/chat", json={"query": "What is RIT?"}, headers=headers)
        assert res.status_code == 200
        assert res.json()["remaining"] is None

def test_usage_endpoint():
    uid = f"usage_test_{uuid.uuid4().hex[:8]}"
    guest_cookie = {"guest_id": uid}
    res = client.get("/usage", cookies=guest_cookie)
    assert res.status_code == 200
    data = res.json()
    assert data["user_id"] == uid
    assert data["is_institute"] is False
    assert data["allowed"] is True

    valid_token = make_token("faculty@ritindia.edu", ttl_seconds=3600)
    res = client.get("/usage", headers={"X-Institute-Token": valid_token})
    assert res.status_code == 200
    data = res.json()
    assert data["is_institute"] is True
    assert data["remaining"] is None

if __name__ == "__main__":
    test_health_endpoint()
    test_query_validation()
    test_guest_rate_limiting()
    test_institute_token_auth()
    test_usage_endpoint()
    print("test_api: ALL PASSED")
