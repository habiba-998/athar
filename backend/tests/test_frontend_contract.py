"""The browser talks to the backend ONLY through the calls in frontend/src/api.ts. This test pins that contract: every call exists on
the FastAPI app with the same HTTP method, nothing is hard-coded to a host, and vercel.json routes every one of them to the backend."""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.main import app

ROOT = Path(__file__).resolve().parents[2]
API_TS = (ROOT / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")


def frontend_calls() -> list[tuple[str, str]]:
    """(method, path) for every entry of the `api` object: path = static part up to a template placeholder or query string."""
    body = API_TS[API_TS.index("export const api = {"):]
    entries = re.split(r"\n  (?=\w+: )", body)[1:]
    calls = []
    for e in entries:
        m = re.search(r"[`']((?:/api/)[^`'$?]*)", e)
        if not m:
            continue
        method = (re.search(r"json\('(\w+)'", e) or [None, "GET"])[1]
        calls.append((method, m.group(1)))
    return calls


def route_matches(method: str, path: str) -> bool:
    for r in app.routes:
        rp = getattr(r, "path", "")
        methods = getattr(r, "methods", None) or set()
        pattern = "^" + re.sub(r"\{[^}]+\}", "[^/]+", rp.replace("{full_path:path}", ".*")) + "$"
        if method not in methods:
            continue
        if path.endswith("/"):                      # the frontend wrote `/api/x/${id}...`: compare on the static prefix, then a parameter
            if rp.startswith(path) and rp[len(path):].startswith("{"):
                return True
        elif re.match(pattern, path):
            return True
    return False


def test_the_contract_parser_actually_finds_the_calls():
    calls = frontend_calls()
    assert len(calls) >= 25 and ("GET", "/api/analysis") in calls and ("POST", "/api/simulate") in calls and ("PUT", "/api/scoring-config") in calls
    assert ("DELETE", "/api/relationships/") in calls or any(m == "DELETE" for m, _ in calls)


def test_every_frontend_call_exists_on_the_backend_with_the_same_method():
    missing = [(m, p) for m, p in frontend_calls() if not route_matches(m, p)]
    assert not missing, missing


def test_vercel_routes_every_frontend_call_to_the_backend_service():
    cfg = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    first = cfg["rewrites"][0]
    for _m, p in frontend_calls():
        assert re.match("^" + first["source"] + "$", p) and first["destination"] == {"service": "backend"}, p


def test_the_backend_exposes_nothing_outside_api_except_the_optional_static_catch_all_and_docs():
    outside = {getattr(r, "path", "") for r in app.routes if not getattr(r, "path", "").startswith("/api")}
    assert outside <= {"/{full_path:path}", "/docs", "/openapi.json", "/docs/oauth2-redirect", "/redoc", ""}, outside


def test_no_frontend_source_hard_codes_a_host():
    for f in (ROOT / "frontend" / "src").glob("*.ts*"):
        if f.name.endswith(".test.ts"):
            continue
        text = f.read_text(encoding="utf-8")
        assert not re.search(r"https?://(localhost|127\.0\.0\.1|0\.0\.0\.0)", text), f.name
        assert "fetch(" not in text or f.name == "api.ts", f"{f.name} must go through api.ts"


def test_the_contract_check_can_fail():
    """Guard against a vacuous test: wrong method or unknown path must NOT match."""
    assert not route_matches("GET", "/api/definitely-not-a-route")
    assert not route_matches("POST", "/api/analysis")           # exists, but only for GET
    assert not route_matches("DELETE", "/api/plans/")
