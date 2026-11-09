"""Access control, rate limiting, CORS, request-size limits and headers."""
import pytest
from fastapi.testclient import TestClient

from app import main
from app.security import RateLimiter

client = TestClient(main.app)
ORIGIN = "http://localhost:5173"


def test_local_only_mode_rejects_non_loopback_clients():
    remote = TestClient(main.app, client=("203.0.113.9", 4444))
    assert remote.get("/api/analysis").status_code == 403
    assert remote.get("/api/analysis").json() == {"error": "local_only"}
    assert remote.get("/api/health").status_code == 200        # health stays public
    for host in ("127.0.0.1", "::1"):
        assert TestClient(main.app, client=(host, 1)).get("/api/analysis").status_code == 200


def test_token_mode(monkeypatch):
    monkeypatch.setenv("ATHAR_API_TOKEN", "s3cret-demo-token")
    remote = TestClient(main.app, client=("203.0.113.9", 4444))
    assert client.get("/api/analysis").status_code == 401
    assert client.get("/api/analysis", headers={"x-athar-token": "wrong"}).status_code == 401
    assert client.get("/api/analysis", headers={"x-athar-token": ""}).status_code == 401
    ok = {"x-athar-token": "s3cret-demo-token"}
    assert client.get("/api/analysis", headers=ok).status_code == 200
    assert remote.get("/api/analysis", headers=ok).status_code == 200          # token replaces the loopback rule
    assert client.post("/api/simulate", json={"actions": [{"kind": "remove_relationship", "relationship_id": "r03"}]}).status_code == 401
    assert client.put("/api/environment", json={}).status_code == 401
    assert client.get("/api/health").status_code == 200
    status = client.get("/api/auth/status").json()
    assert status["token_required"] is True and status["mode"] == "local" and status["read_only"] is False


def test_token_never_echoed(monkeypatch):
    monkeypatch.setenv("ATHAR_API_TOKEN", "s3cret-demo-token")
    r = client.get("/api/analysis", headers={"x-athar-token": "nope"})
    assert "s3cret" not in r.text and "s3cret" not in str(r.headers)


def test_rate_limit_returns_429_with_retry_after():
    main.limiter = RateLimiter(read=3, write=2, explain=1)
    codes = [client.get("/api/analysis").status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    r = client.get("/api/analysis")
    assert r.json() == {"error": "rate_limited"} and int(r.headers["retry-after"]) >= 1


def test_rate_limit_buckets_are_independent_and_per_client():
    main.limiter = RateLimiter(read=2, write=1, explain=1)
    body = {"actions": [{"kind": "remove_relationship", "relationship_id": "r03"}]}
    assert client.post("/api/simulate", json=body).status_code == 200
    assert client.post("/api/simulate", json=body).status_code == 429          # write bucket exhausted
    assert client.get("/api/analysis").status_code == 200                      # read bucket unaffected
    other = TestClient(main.app, client=("127.0.0.1", 9))
    assert other.post("/api/simulate", json=body).status_code == 200           # different client, own budget


def test_explain_has_its_own_stricter_bucket():
    main.limiter = RateLimiter(read=100, write=100, explain=1)
    pid = client.get("/api/analysis").json()["paths"][0]["id"]
    assert client.post("/api/explain", json={"kind": "path", "id": pid}).status_code == 200
    assert client.post("/api/explain", json={"kind": "path", "id": pid}).status_code == 429


def test_unauthenticated_requests_are_still_rate_limited():
    main.limiter = RateLimiter(read=2, write=2, explain=2)
    remote = TestClient(main.app, client=("203.0.113.9", 4444))
    assert [remote.get("/api/analysis").status_code for _ in range(3)] == [403, 403, 429]


def test_cors_allows_only_configured_origins():
    ok = client.options("/api/simulate", headers={"origin": ORIGIN, "access-control-request-method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == ORIGIN
    bad = client.options("/api/simulate", headers={"origin": "http://evil.example",
                                                   "access-control-request-method": "POST"})
    assert "access-control-allow-origin" not in bad.headers
    assert client.get("/api/analysis", headers={"origin": "http://evil.example"}).headers.get(
        "access-control-allow-origin") is None
    assert "*" not in main._origins()


def test_cors_headers_present_on_guard_rejections(monkeypatch):
    monkeypatch.setenv("ATHAR_API_TOKEN", "t")
    r = client.get("/api/analysis", headers={"origin": ORIGIN})
    assert r.status_code == 401 and r.headers.get("access-control-allow-origin") == ORIGIN


def test_cors_origin_env_is_sanitised(monkeypatch):
    monkeypatch.setenv("ATHAR_CORS_ORIGINS", "*, https://good.example ,javascript:alert(1),http://*.evil")
    assert main._origins() == ["https://good.example"]


def test_security_headers_on_success_and_error_responses():
    for r in (client.get("/api/analysis"), client.get("/api/nope"),
              client.post("/api/simulate", json={})):
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["cache-control"] == "no-store"
        assert r.headers["referrer-policy"] == "no-referrer"


def test_internal_errors_do_not_leak_details(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("secret internal path C:\\very\\secret")
    monkeypatch.setattr(main, "simulate", boom)
    safe = TestClient(main.app, raise_server_exceptions=False)
    r = safe.post("/api/simulate", json={"actions": [{"kind": "remove_relationship", "relationship_id": "r03"}]})
    assert r.status_code == 500 and r.json() == {"error": "internal_error"} and "secret" not in r.text


@pytest.mark.parametrize("path", ["/api/assets/../../etc/passwd", "/api/assets/%2e%2e%2fsecret",
                                  "/api/relationships/x'; DROP TABLE activity;--"])
def test_path_parameters_are_treated_as_data(path):
    r = client.delete(path)
    assert r.status_code in (404, 405, 422)
    assert client.get("/api/activity").status_code == 200   # database still intact


def test_html_in_names_is_stored_verbatim_not_executed_by_api():
    # The API is JSON-only; escaping is the UI's job (React). Verify it round-trips as inert data.
    a = {"id": "xss-1", "name": "<img src=x onerror=alert(1)>", "name_ar": "x", "type": "server"}
    assert client.post("/api/assets", json=a).status_code == 200
    r = client.get("/api/environment")
    assert r.headers["content-type"].startswith("application/json")
    assert any(x["name"] == a["name"] for x in r.json()["assets"])
