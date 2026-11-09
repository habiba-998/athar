"""Production readiness: the two access modes, secrets, headers, proxy handling, static serving, logging and deployment files."""
from __future__ import annotations

import io
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import logging_setup, main, security
from app.security import RateLimiter, secret_problems

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
ADMIN = "admin-token-0123456789-abcdef"
remote = TestClient(main.app, client=("203.0.113.9", 4000))      # a non-loopback visitor
local = TestClient(main.app)                                       # Starlette's in-process host counts as loopback


@pytest.fixture
def demo(monkeypatch):
    monkeypatch.setenv("ATHAR_MODE", "demo")
    monkeypatch.setenv("ATHAR_ADMIN_TOKEN", ADMIN)


def counts() -> tuple[int, int, int, str]:
    return (len(local.get("/api/activity?limit=200").json()), len(local.get("/api/simulations?limit=100").json()),
            len(local.get("/api/explanations?limit=100").json()), local.get("/api/environment/meta").json()["hash"])


# ============================================================================ local mode (default)

class TestLocalMode:
    def test_default_mode_is_local_and_remote_visitors_are_refused(self):
        assert security.mode() == "local"
        r = remote.get("/api/analysis")
        assert r.status_code == 403 and r.json() == {"error": "local_only"}
        assert local.get("/api/analysis").status_code == 200

    def test_auth_status_describes_the_mode(self):
        s = local.get("/api/auth/status").json()
        assert s == {"token_required": False, "mode": "local", "read_only": False, "admin_token_supported": False}

    def test_a_forged_forwarded_header_cannot_turn_a_remote_visitor_into_loopback(self):
        r = remote.get("/api/analysis", headers={"X-Forwarded-For": "127.0.0.1"})
        assert r.status_code == 403                                           # the header is ignored unless a proxy is trusted

    def test_behind_a_trusted_proxy_only_the_rightmost_address_counts(self, monkeypatch):
        monkeypatch.setenv("ATHAR_TRUST_PROXY", "1")
        assert remote.get("/api/analysis", headers={"X-Forwarded-For": "127.0.0.1, 203.0.113.9"}).status_code == 403   # left part is forgeable
        assert remote.get("/api/analysis", headers={"X-Forwarded-For": "203.0.113.9, 127.0.0.1"}).status_code == 200  # proxy saw loopback

    def test_rate_limits_follow_the_trusted_client_address_not_the_forgeable_part(self, monkeypatch):
        main.limiter = RateLimiter(read=2, write=50, explain=50)
        monkeypatch.setenv("ATHAR_TRUST_PROXY", "1")
        monkeypatch.setenv("ATHAR_MODE", "demo")
        codes = [remote.get("/api/health", headers={"X-Forwarded-For": f"10.0.0.{i}, 198.51.100.7"}).status_code for i in range(5)]
        assert codes[:2] == [200, 200] and 429 in codes[2:]                     # varying the forged prefix does not reset the window
        other = remote.get("/api/health", headers={"X-Forwarded-For": "198.51.100.8"}).status_code
        assert other == 200                                                    # a different real client has its own window


# ============================================================================ demo mode (public, read-only)

WRITES = [("PUT", "/api/environment", "env"), ("POST", "/api/environment/reset", {}), ("POST", "/api/environment/undo", {}),
          ("PUT", "/api/scoring-config", {}), ("POST", "/api/scoring-config/reset", {}), ("POST", "/api/attack-scenarios/x/activate", {}),
          ("POST", "/api/assets", {}), ("PUT", "/api/assets/a", {}), ("DELETE", "/api/assets/a", None),
          ("POST", "/api/relationships", {}), ("PUT", "/api/relationships/r", {}), ("DELETE", "/api/relationships/r01", None)]


class TestDemoMode:
    def test_status_exposes_mode_without_secrets(self, demo):
        s = remote.get("/api/auth/status").json()
        assert s == {"token_required": False, "mode": "demo", "read_only": True, "admin_token_supported": True}
        assert ADMIN not in json.dumps(s) and ADMIN not in remote.get("/api/health").text

    def test_visitors_can_read_everything_without_a_token(self, demo):
        for p in ("/api/analysis", "/api/environment", "/api/recommendations", "/api/plans", "/api/scoring-config", "/api/evidence",
                  "/api/services", "/api/attack-scenarios", "/api/activity", "/api/simulations", "/api/environment/meta", "/api/ai/status"):
            assert remote.get(p).status_code == 200, p

    @pytest.mark.parametrize("method,path,body", WRITES)
    def test_every_write_is_refused_for_visitors_and_changes_nothing(self, demo, method, path, body):
        before = counts()
        payload = local.get("/api/environment").json() if body == "env" else body
        r = remote.request(method, path, json=payload)
        assert r.status_code == 403 and r.json()["error"] == "read_only_demo"
        assert counts() == before

    def test_demo_without_an_admin_token_is_read_only_for_everybody(self, monkeypatch):
        monkeypatch.setenv("ATHAR_MODE", "demo")
        assert remote.get("/api/auth/status").json()["admin_token_supported"] is False
        assert remote.post("/api/environment/reset", json={}, headers={"X-ATHAR-Token": "anything-at-all-1234"}).status_code == 403

    def test_a_wrong_admin_token_is_refused_distinctly(self, demo):
        r = remote.post("/api/environment/reset", json={}, headers={"X-ATHAR-Token": ADMIN + "x"})
        assert r.status_code == 403 and r.json()["error"] == "invalid_admin_token"

    def test_the_admin_token_unlocks_writes_which_are_then_audited(self, demo):
        before = counts()
        r = remote.post("/api/environment/reset", json={}, headers={"X-ATHAR-Token": ADMIN})
        assert r.status_code == 200
        latest = local.get("/api/activity?limit=1").json()[0]               # the audit log is capped, so compare the newest row, not a count
        assert latest["kind"] == "environment_reset"
        sim = remote.post("/api/simulate", json={"actions": [{"kind": "disable_relationship", "relationship_id": "r03"}]},
                          headers={"X-ATHAR-Token": ADMIN}).json()
        assert sim["ephemeral"] is False and isinstance(sim["record_id"], int)

    def test_simulation_for_visitors_is_computed_but_never_persisted(self, demo):
        before = counts()
        r = remote.post("/api/simulate", json={"actions": [{"kind": "remove_relationship", "relationship_id": "r03"}]})
        assert r.status_code == 200
        j = r.json()
        assert j["ephemeral"] is True and j["record_id"] is None and j["after"]["attack_paths"] < j["before"]["attack_paths"]
        assert counts() == before

    def test_explanations_for_visitors_use_templates_only_and_are_not_stored(self, demo, monkeypatch):
        monkeypatch.setenv("ATHAR_AI_PROVIDER", "anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
        path_id = local.get("/api/analysis").json()["paths"][0]["id"]
        before = counts()
        r = remote.post("/api/explain", json={"kind": "path", "id": path_id, "lang": "en"}).json()
        assert r["ai_explanation"] is None and r["ai_status"] == "ai_disabled" and r["template_explanation"]
        assert counts() == before

    def test_visitors_cannot_force_new_sensitivity_computations(self, demo):
        r = remote.get("/api/sensitivity?trials=3&spread=0.1&seed=99").json()
        assert r["trials"] == 16 and r["seed"] == 1109 and r["spread"] == 0.3      # parameters ignored: one cached default run

    def test_plan_reports_and_sensitivity_leave_no_audit_rows_for_visitors(self, demo):
        before = counts()
        plans = remote.get("/api/plans").json()
        assert remote.get(f"/api/plans/{plans['plans'][1]['id']}/report?lang=ar").status_code == 200
        remote.get("/api/sensitivity")
        assert counts() == before

    def test_bodies_are_still_size_limited_and_length_checked(self, demo, monkeypatch):
        monkeypatch.setenv("ATHAR_MAX_BODY", "50")
        r = remote.post("/api/simulate", content=b"x" * 200, headers={"Content-Type": "application/json"})
        assert r.status_code == 413

    def test_demo_rate_limits_apply_to_visitors(self, demo):
        main.limiter = RateLimiter(read=3, write=3, explain=1)
        assert [remote.get("/api/plans").status_code for _ in range(3)].count(429) == 2


# ============================================================================ secrets and start-up

class TestSecrets:
    def test_weak_or_colliding_secrets_are_reported(self, monkeypatch):
        monkeypatch.setenv("ATHAR_API_TOKEN", "short")
        monkeypatch.setenv("ATHAR_ADMIN_TOKEN", "short")
        problems = secret_problems()
        assert any("ATHAR_API_TOKEN" in p for p in problems) and any("ATHAR_ADMIN_TOKEN" in p for p in problems)
        monkeypatch.setenv("ATHAR_API_TOKEN", ADMIN)
        monkeypatch.setenv("ATHAR_ADMIN_TOKEN", ADMIN)
        assert any("must differ" in p for p in secret_problems())

    def test_strong_distinct_secrets_have_no_problems(self, monkeypatch):
        monkeypatch.setenv("ATHAR_API_TOKEN", ADMIN)
        monkeypatch.setenv("ATHAR_ADMIN_TOKEN", ADMIN[::-1])
        assert secret_problems() == []

    @staticmethod
    def _import(env: dict[str, str]) -> subprocess.CompletedProcess:
        script = (f"import json,sys; sys.path.insert(0, {str(BACKEND)!r}); import app.main as m; "
                  "print(json.dumps({'docs': m.app.docs_url, 'openapi': m.app.openapi_url, 'mode': m.security.mode()}))")
        return subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True, cwd=BACKEND, timeout=120,
                              env={**{k: v for k, v in os.environ.items() if not k.startswith("ATHAR_")}, "ATHAR_DB": ":memory:", **env})

    def test_a_public_demo_refuses_to_start_with_a_weak_secret(self):
        r = self._import({"ATHAR_MODE": "demo", "ATHAR_ADMIN_TOKEN": "tooshort"})
        assert r.returncode != 0 and "weak secrets" in r.stderr and "tooshort" not in r.stderr

    def test_a_demo_with_strong_secrets_starts_with_the_api_docs_disabled(self):
        r = self._import({"ATHAR_MODE": "demo", "ATHAR_ADMIN_TOKEN": ADMIN})
        assert r.returncode == 0, r.stderr[-400:]
        assert json.loads(r.stdout.strip().splitlines()[-1]) == {"docs": None, "openapi": None, "mode": "demo"}

    def test_a_demo_can_opt_in_to_the_docs(self):
        r = self._import({"ATHAR_MODE": "demo", "ATHAR_ADMIN_TOKEN": ADMIN, "ATHAR_DOCS": "1"})
        assert json.loads(r.stdout.strip().splitlines()[-1])["docs"] == "/docs"

    def test_local_mode_keeps_the_docs(self):
        assert json.loads(self._import({}).stdout.strip().splitlines()[-1])["docs"] == "/docs"

    def test_unknown_mode_values_fall_back_to_local(self, monkeypatch):
        monkeypatch.setenv("ATHAR_MODE", "production")
        assert security.mode() == "local" and not security.is_demo()


# ============================================================================ headers

class TestHeaders:
    def test_security_headers_on_every_api_response(self):
        for r in (local.get("/api/health"), local.get("/api/nope"), remote.get("/api/analysis")):          # success, 404, 403
            h = r.headers
            assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY" and h["referrer-policy"] == "no-referrer"
            assert "frame-ancestors 'none'" in h["content-security-policy"] and "default-src 'self'" in h["content-security-policy"]
            assert re.fullmatch(r"[0-9a-f]{12}", h["x-request-id"]) and h["cache-control"] == "no-store"
            assert "camera=()" in h["permissions-policy"] and h["cross-origin-opener-policy"] == "same-origin"

    def test_csp_is_strict(self):
        csp = local.get("/api/health").headers["content-security-policy"]
        assert "script-src 'self';" in csp and "object-src 'none'" in csp and "base-uri 'none'" in csp
        assert "unsafe-eval" not in csp and "*" not in csp and "script-src 'self' 'unsafe-inline'" not in csp

    def test_csp_connect_extension_accepts_only_plain_https_origins(self, monkeypatch):
        monkeypatch.setenv("ATHAR_CSP_CONNECT", "https://api.example.org http://insecure.example https://*.evil.example javascript:alert(1)")
        csp = main._csp()
        assert "https://api.example.org" in csp and "insecure" not in csp and "evil" not in csp and "javascript" not in csp

    def test_hsts_only_over_https_or_when_forced(self, monkeypatch):
        assert "strict-transport-security" not in local.get("/api/health").headers
        assert "strict-transport-security" not in local.get("/api/health", headers={"X-Forwarded-Proto": "https"}).headers   # header untrusted
        monkeypatch.setenv("ATHAR_TRUST_PROXY", "1")
        assert "max-age=31536000" in local.get("/api/health", headers={"X-Forwarded-Proto": "https"}).headers["strict-transport-security"]
        monkeypatch.delenv("ATHAR_TRUST_PROXY")
        monkeypatch.setenv("ATHAR_HSTS", "1")
        assert "includeSubDomains" in local.get("/api/health").headers["strict-transport-security"]
        assert "strict-transport-security" in TestClient(main.app, base_url="https://testserver").get("/api/health").headers

    def test_health_and_readiness_reveal_nothing_sensitive(self, demo):
        h = remote.get("/api/health").json()
        assert set(h) == {"status", "synthetic_data", "version", "mode"}
        assert remote.get("/api/ready").json() == {"ready": True}

    def test_internal_errors_stay_opaque_and_carry_headers(self, monkeypatch):
        def boom(*_a, **_k):
            raise RuntimeError("secret internal detail /etc/passwd")
        monkeypatch.setattr(main.state, "plans", boom)
        r = TestClient(main.app, raise_server_exceptions=False).get("/api/plans")
        assert r.status_code == 500 and r.json() == {"error": "internal_error"} and "passwd" not in r.text


# ============================================================================ single-page app serving

def test_static_serving_rules(tmp_path):
    dist = tmp_path / "site" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text('<!doctype html><div id="root"></div><script src="/assets/app-abc123.js"></script>', encoding="utf-8")
    (dist / "assets" / "app-abc123.js").write_text("console.log('hi')", encoding="utf-8")
    (tmp_path / "site" / "secret.txt").write_text("TOP-SECRET", encoding="utf-8")
    script = (
        f"import sys, json; sys.path.insert(0, {str(BACKEND)!r}); from fastapi.testclient import TestClient; import app.main as m; c = TestClient(m.app); out = {{}}\n"
        "def rec(k, r): out[k] = [r.status_code, r.headers.get('cache-control'), r.headers.get('content-type'), r.text[:60]]\n"
        "rec('root', c.get('/')); rec('asset', c.get('/assets/app-abc123.js')); rec('route', c.get('/environment/edit'))\n"
        "rec('api404', c.get('/api/nope')); rec('api_root', c.get('/api')); rec('dots', c.get('/../secret.txt'))\n"
        "rec('head', c.head('/')); rec('enc', c.get('/assets/..%2f..%2fsecret.txt')); rec('enc2', c.get('/%2e%2e/secret.txt')); rec('health', c.get('/api/health'))\n"
        "print(json.dumps(out))")
    r = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True, cwd=BACKEND, timeout=120,
                       env={**{k: v for k, v in os.environ.items() if not k.startswith("ATHAR_")}, "ATHAR_DB": ":memory:",
                            "ATHAR_STATIC_DIR": str(dist)})
    assert r.returncode == 0, r.stderr[-500:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["root"][0] == 200 and 'id="root"' in out["root"][3] and out["root"][1] == "no-cache"
    assert out["asset"][0] == 200 and "immutable" in out["asset"][1] and "console.log" in out["asset"][3]
    assert out["route"][0] == 200 and 'id="root"' in out["route"][3]                      # client-side routes fall back to the app shell
    assert out["api404"][0] == 404 and out["api404"][2].startswith("application/json") and out["api_root"][0] == 404
    for k in ("dots", "enc", "enc2"):
        assert "TOP-SECRET" not in out[k][3], k                                             # nothing outside the build folder is ever served
    assert out["health"][0] == 200
    assert out["head"][0] == 200                                                              # uptime monitors often probe with HEAD


# ============================================================================ structured logging

class TestLogging:
    @pytest.fixture
    def stream(self):
        buf = io.StringIO()
        h = logging.StreamHandler(buf)
        h.setFormatter(logging_setup.JsonFormatter())
        logging_setup.LOGGER.addHandler(h)
        yield buf
        logging_setup.LOGGER.removeHandler(h)

    def test_one_json_line_per_request_without_secrets_or_addresses(self, stream, demo):
        remote.get("/api/analysis?secret=query-value", headers={"X-ATHAR-Token": ADMIN})
        remote.post("/api/environment/reset", json={"k": "body-value"})
        lines = [json.loads(x) for x in stream.getvalue().splitlines() if x.strip()]
        reqs = [x for x in lines if x["msg"] == "request"]
        assert len(reqs) == 2 and reqs[0]["status"] == 200 and reqs[1]["status"] == 403
        for x in reqs:
            assert {"ts", "level", "request_id", "method", "path", "status", "ms", "client", "mode"} <= set(x)
            assert re.fullmatch(r"[0-9a-f]{8}", x["client"])
        raw = stream.getvalue()
        assert ADMIN not in raw and "203.0.113.9" not in raw and "query-value" not in raw and "body-value" not in raw

    def test_the_formatter_never_emits_tracebacks(self):
        try:
            raise ValueError("sensitive detail")
        except ValueError:
            rec = logging.LogRecord("athar", logging.ERROR, "f", 1, "failed", None, sys.exc_info())
        out = json.loads(logging_setup.JsonFormatter().format(rec))
        assert out["error_type"] == "ValueError" and "sensitive" not in json.dumps(out) and "Traceback" not in json.dumps(out)


# ============================================================================ deployment files

class TestDeploymentFiles:
    def test_dockerfile_is_multistage_non_root_with_healthcheck_and_no_secrets(self):
        d = (ROOT / "deploy" / "Dockerfile").read_text(encoding="utf-8")
        assert "AS web" in d and "AS run" in d and "USER athar" in d and "HEALTHCHECK" in d and "requirements.prod.txt" in d
        assert "ATHAR_MODE=demo" in d
        assert not re.search(r"ATHAR_(ADMIN|API)_TOKEN=[A-Za-z0-9_\-]{8,}", d)              # no literal secret baked into the image
        ignore = (ROOT / "deploy" / "Dockerfile.dockerignore").read_text(encoding="utf-8")
        assert ".env" in ignore and "!.env.example" in ignore and "node_modules" in ignore

    def test_vercel_services_config_declares_both_services_and_routes_api_before_the_catch_all(self):
        v = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        fe = v["services"]["frontend"]
        assert fe["root"] == "frontend/" and (ROOT / "frontend" / "index.html").is_file()
        assert (fe["installCommand"], fe["buildCommand"], fe["outputDirectory"]) == ("npm ci", "npm run build", "dist")   # explicit, not defaults
        assert json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))["scripts"]["build"].endswith("vite build")
        be = v["services"]["backend"]
        assert be["root"] == "backend/" and be["framework"] == "fastapi" and be["entrypoint"] == "app.main:app"
        assert (BACKEND / "app" / "main.py").is_file()                                   # the entrypoint module exists under the service root
        assert v["rewrites"][0] == {"source": "/api/(.*)", "destination": {"service": "backend"}}      # most specific first
        assert v["rewrites"][-1] == {"source": "/(.*)", "destination": {"service": "frontend"}}
        assert set(v["services"]) == {"frontend", "backend"} and len(v["rewrites"]) == 2        # no duplicate services, no extra routes
        for invalid_with_services in ("builds", "functions", "buildCommand", "installCommand", "outputDirectory", "framework", "headers", "routes"):
            assert invalid_with_services not in v, invalid_with_services                  # build/runtime/header rules live inside a service
        hdr = {h["key"]: h["value"] for h in fe["headers"][0]["headers"]}
        assert "frame-ancestors 'none'" in hdr["Content-Security-Policy"] and "connect-src 'self'" in hdr["Content-Security-Policy"]
        assert hdr["Strict-Transport-Security"].startswith("max-age=") and hdr["X-Content-Type-Options"] == "nosniff"
        text = json.dumps(v)
        assert "localhost" not in text and "127.0.0.1" not in text and not re.search(r"(?i)token|secret|password", text)
        assert (BACKEND / ".python-version").read_text(encoding="utf-8").strip() == "3.12"
        assert "vercel" not in (BACKEND / "pyproject.toml").read_text(encoding="utf-8")        # one place declares the entrypoint: vercel.json

    def test_vercel_sees_exactly_one_python_app_and_one_dependency_manifest(self):
        """Why the import once reported several FastAPI apps is unknown (the error text was not available); the repository now
        contains exactly one ASGI application, one Python project root for Vercel, and no stray entrypoint shims."""
        apps = [p for p in ROOT.rglob("*.py") if "FastAPI(" in p.read_text(encoding="utf-8", errors="ignore")
                and not {"node_modules", "tests", ".venv", "__pycache__"} & set(p.relative_to(ROOT).parts)]
        assert [p.relative_to(ROOT).as_posix() for p in apps] == ["backend/app/main.py"]
        assert not (ROOT / "api").exists() and not (ROOT / "requirements.txt").exists() and not (ROOT / "frontend" / "vercel.json").exists()
        assert not (ROOT / ".python-version").exists()                                            # a root Python marker could read as a third app
        assert not (ROOT / "pyproject.toml").exists() and not (ROOT / "Dockerfile").exists()      # a root Dockerfile could read as another app

    def test_the_backend_runtime_requirements_equal_the_audited_production_pins(self):
        parse = lambda p: dict(l.strip().split("==") for l in p.read_text(encoding="utf-8").splitlines() if "==" in l and not l.startswith("#"))  # noqa: E731
        assert parse(BACKEND / "requirements.txt") == parse(BACKEND / "requirements.prod.txt")
        assert not ({"pytest", "mypy", "coverage", "httpx"} & set(parse(BACKEND / "requirements.txt")))

    def test_on_vercel_the_backend_defaults_to_the_read_only_demo_without_any_secret(self):
        base = {k: v for k, v in os.environ.items() if not k.startswith("ATHAR_")}
        probe = "; ".join(["import sys, json, os", f"sys.path.insert(0, {str(BACKEND)!r})", "import app",
                           "print(json.dumps({k: os.environ.get(k) for k in ('ATHAR_MODE', 'ATHAR_DB', 'ATHAR_TRUST_PROXY', 'ATHAR_HSTS', 'ATHAR_ADMIN_TOKEN', 'ATHAR_API_TOKEN')}))"])
        run = lambda env: json.loads(subprocess.run([sys.executable, "-I", "-c", probe], capture_output=True, text=True, cwd=BACKEND, timeout=60, env=env).stdout.strip().splitlines()[-1])  # noqa: E731
        on = run({**base, "VERCEL": "1"})
        assert on == {"ATHAR_MODE": "demo", "ATHAR_DB": "/tmp/athar.db", "ATHAR_TRUST_PROXY": "1", "ATHAR_HSTS": "1", "ATHAR_ADMIN_TOKEN": None, "ATHAR_API_TOKEN": None}
        assert all(v is None for v in run(base).values())                                  # nothing changes off Vercel
        assert run({**base, "VERCEL": "1", "ATHAR_MODE": "local"})["ATHAR_MODE"] == "local"  # project settings win

    def test_the_vercel_runtime_serves_the_read_only_demo(self):
        parts = ["import sys, json", f"sys.path.insert(0, {str(BACKEND)!r})", "from fastapi.testclient import TestClient", "import app.main as m",
                 "c = TestClient(m.app); r = c.get('/api/auth/status').json()", "w = c.put('/api/environment', json={})",
                 "s = c.post('/api/simulate', json={'actions': [{'kind': 'remove_relationship', 'relationship_id': 'r03'}]})",
                 "print(json.dumps({'status': r, 'write': [w.status_code, w.json()], 'sim': [s.status_code, s.json().get('ephemeral')], 'docs': m.app.docs_url}))"]
        r = subprocess.run([sys.executable, "-I", "-c", "; ".join(parts)], capture_output=True, text=True, cwd=BACKEND, timeout=120,
                           env={**{k: v for k, v in os.environ.items() if not k.startswith("ATHAR_")}, "VERCEL": "1", "ATHAR_DB": ":memory:"})
        assert r.returncode == 0, r.stderr[-500:]
        out = json.loads(r.stdout.strip().splitlines()[-1])
        assert out["status"]["mode"] == "demo" and out["status"]["read_only"] is True and out["status"]["admin_token_supported"] is False
        assert out["write"] == [403, {"error": "read_only_demo"}] and out["sim"] == [200, True] and out["docs"] is None

    def test_vercel_config_has_security_headers_and_a_placeholder_for_the_api_origin(self):
        v = json.loads((ROOT / "deploy" / "vercel.frontend-only.json").read_text(encoding="utf-8"))
        hdrs = {h["key"]: h["value"] for h in v["headers"][0]["headers"]}
        assert "frame-ancestors 'none'" in hdrs["Content-Security-Policy"] and hdrs["X-Content-Type-Options"] == "nosniff"
        assert "REPLACE_WITH_YOUR_API_ORIGIN" in hdrs["Content-Security-Policy"]           # never a guessed URL
        assert v["outputDirectory"] == "dist"

    def test_env_example_has_no_values_for_secrets_and_lists_every_variable_the_code_reads(self):
        ex = (ROOT / ".env.example").read_text(encoding="utf-8")
        assert re.search(r"^ATHAR_API_TOKEN=$", ex, re.M) and re.search(r"^ATHAR_ADMIN_TOKEN=$", ex, re.M) and re.search(r"^ANTHROPIC_API_KEY=$", ex, re.M)
        used = set()
        for f in (BACKEND / "app").glob("*.py"):
            used |= set(re.findall(r"\b(ATHAR_[A-Z_]+|ANTHROPIC_API_KEY)\b", f.read_text(encoding="utf-8")))
        used -= {"ATHAR_"}
        missing = sorted(v for v in used if not re.search(rf"^{v}=", ex, re.M))
        assert not missing, f"variables read by the code but missing from .env.example: {missing}"

    def test_the_runtime_requirements_are_a_pinned_subset_of_the_lock(self):
        parse = lambda p: dict(l.strip().split("==") for l in (BACKEND / p).read_text(encoding="utf-8").splitlines() if "==" in l and not l.startswith("#"))  # noqa: E731
        lock, prod = parse("requirements.lock.txt"), parse("requirements.prod.txt")
        assert prod and all(lock.get(k) == v for k, v in prod.items())
        assert not ({"pytest", "mypy", "coverage", "httpx", "pluggy"} & set(prod))
        assert {"fastapi", "uvicorn", "networkx", "pydantic", "starlette"} <= set(prod)

    def test_no_secret_shaped_strings_are_committed(self):
        patterns = [re.compile(p) for p in (r"sk-ant-[A-Za-z0-9_-]{16,}", r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----", r"AKIA[0-9A-Z]{16}",
                                            r"ghp_[A-Za-z0-9]{30,}", r"xox[bap]-[A-Za-z0-9-]{20,}")]
        skip = {"node_modules", "dist", "data", "__pycache__", ".mypy_cache", ".pytest_cache", "test-results", "playwright-report", "tests"}
        hits = []
        for p in ROOT.rglob("*"):
            if p.is_file() and not (skip & set(p.relative_to(ROOT).parts)) and p.suffix in {".py", ".md", ".json", ".yaml", ".yml", ".ts", ".tsx", ".txt", ".example", ".html", ".css", ""}:
                try:
                    text = p.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                hits += [f"{p.relative_to(ROOT)}: {pat.pattern}" for pat in patterns if pat.search(text)]
        assert not hits, hits

    def test_the_frontend_build_contains_no_loopback_or_private_addresses(self):
        dist = ROOT / "frontend" / "dist"
        if not (dist / "index.html").exists():
            pytest.skip("frontend not built")
        blob = "".join(p.read_text(encoding="utf-8", errors="ignore") for p in dist.rglob("*") if p.suffix in {".js", ".html", ".css"})
        bad = re.findall(r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+)[:/\d]*", blob)
        assert not bad, sorted(set(bad))
        assert "ATHAR_ADMIN_TOKEN" not in blob and "ANTHROPIC_API_KEY" not in blob


class TestHttpsAndCors:
    def test_plain_http_behind_a_trusted_proxy_is_redirected_when_forced(self, monkeypatch):
        monkeypatch.setenv("ATHAR_FORCE_HTTPS", "1")
        monkeypatch.setenv("ATHAR_TRUST_PROXY", "1")
        r = local.get("/api/analysis?x=1", headers={"X-Forwarded-Proto": "http", "Host": "demo.example.org"}, follow_redirects=False)
        assert r.status_code == 308 and r.headers["location"] == "https://demo.example.org/api/analysis?x=1"
        assert local.get("/api/analysis", headers={"X-Forwarded-Proto": "https"}).status_code == 200
        assert local.get("/api/health", headers={"X-Forwarded-Proto": "http"}).status_code == 200      # probes are exempt
        assert local.get("/api/ready", headers={"X-Forwarded-Proto": "http"}).status_code == 200

    def test_the_redirect_needs_both_flags_and_ignores_a_forged_header_otherwise(self, monkeypatch):
        monkeypatch.setenv("ATHAR_TRUST_PROXY", "1")                        # force flag off
        assert local.get("/api/analysis", headers={"X-Forwarded-Proto": "http"}, follow_redirects=False).status_code == 200
        monkeypatch.delenv("ATHAR_TRUST_PROXY")
        monkeypatch.setenv("ATHAR_FORCE_HTTPS", "1")                        # proxy not trusted: header is attacker-controlled, ignore it
        assert local.get("/api/analysis", headers={"X-Forwarded-Proto": "http"}, follow_redirects=False).status_code == 200

    def test_cors_defaults_to_no_cross_origin_callers_in_demo_mode(self, monkeypatch):
        assert "http://localhost:5173" in main._origins()                    # local development default
        monkeypatch.setenv("ATHAR_MODE", "demo")
        assert main._origins() == []
        monkeypatch.setenv("ATHAR_CORS_ORIGINS", "https://app.example.org")
        assert main._origins() == ["https://app.example.org"]

    def test_a_foreign_origin_gets_no_cors_headers_and_no_wildcard_is_ever_returned(self, demo):
        for origin in ("https://evil.example", "null"):          # (CORS middleware is configured at import time, so the demo default is covered by test_cors_defaults…)
            r = remote.get("/api/analysis", headers={"Origin": origin})
            assert "access-control-allow-origin" not in r.headers, origin
        pre = remote.options("/api/environment", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "PUT"})
        assert "access-control-allow-origin" not in pre.headers
