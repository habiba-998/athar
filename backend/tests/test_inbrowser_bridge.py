"""The static build runs this backend inside the browser through frontend/src/inbrowser/bridge.py (an ASGI bridge). These tests run
the same bridge under CPython and require it to behave exactly like the real HTTP application, and the static build's pieces to be
consistent. (The WebAssembly side is covered by the Playwright suite against the real static build.)"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
BRIDGE = ROOT / "frontend" / "src" / "inbrowser" / "bridge.py"


def _run(script_lines: list[str]) -> dict:
    env = {**{k: v for k, v in os.environ.items() if not k.startswith("ATHAR_")}, "ATHAR_DB": ":memory:"}
    r = subprocess.run([sys.executable, "-I", "-c", "\n".join(script_lines)], capture_output=True, text=True, cwd=BACKEND, timeout=180, env=env)
    assert r.returncode == 0, r.stderr[-800:]
    return json.loads(r.stdout.strip().splitlines()[-1])


SCRIPT = [
    "import asyncio, importlib.util, json, sys",
    f"sys.path.insert(0, {str(BACKEND)!r})",
    f"spec = importlib.util.spec_from_file_location('bridge', {str(BRIDGE)!r}); b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)",
    f"b.install({str(BACKEND)!r})",
    "from fastapi.testclient import TestClient",
    "import app.main as m",
    "http = TestClient(m.app)",
    "def via(method, url, body=None):",
    "    r = json.loads(asyncio.run(b.handle(method, url, '{}', json.dumps(body) if body is not None else None)))",
    "    return r['status'], json.loads(r['body']) if r['body'] else None, r['headers']",
    "out = {}",
    "for url in ['/api/health', '/api/auth/status', '/api/analysis', '/api/environment', '/api/recommendations', '/api/scoring-config', '/api/evidence', '/api/services', '/api/plans', '/api/nope']:",
    "    s, d, _ = via('GET', url); h = http.get(url)",
    "    out[url] = [s == h.status_code, d == h.json()]",
    "act = {'actions': [{'kind': 'remove_relationship', 'relationship_id': 'r03'}]}",
    "s, d, hdr = via('POST', '/api/simulate', act); h = http.post('/api/simulate', json=act)",
    "out['simulate'] = [s == h.status_code == 200, d['ephemeral'] is True and d['after'] == h.json()['after'], 'content-security-policy' in hdr]",
    "s, d, _ = via('PUT', '/api/environment', {}); out['write'] = [s, d]",
    "s, d, _ = via('GET', '/api/sensitivity?trials=2'); out['sens'] = [s, d['trials']]",
    "s, d, _ = via('GET', '/api/plans/plan-minimal/report?lang=ar'); out['report'] = [s, d['markdown'][:2]]",
    "print(json.dumps(out))",
]


def test_the_bridge_answers_exactly_like_the_http_application():
    out = _run(SCRIPT)
    for url, (same_status, same_body) in ((u, v) for u, v in out.items() if u.startswith("/api/")):
        assert same_status and same_body, url
    assert out["simulate"] == [True, True, True]
    assert out["write"] == [403, {"error": "read_only_demo"}]            # the in-browser engine is always the read-only demo
    assert out["sens"] == [200, 16] and out["report"] == [200, "# "]          # visitors get the cached default sensitivity run (16 trials)


def test_the_bridge_never_lets_a_visitor_become_an_administrator():
    out = _run(SCRIPT[:-1] + [
        "s, d, _ = asyncio.run(b.handle('POST', '/api/environment/reset', json.dumps({'x-athar-token': 'anything'}), '{}')), 0, 0",
        "r = json.loads(s)",
        "print(json.dumps({'status': r['status'], 'body': json.loads(r['body'])}))"])
    assert out == {"status": 403, "body": {"error": "read_only_demo"}}


def test_the_static_build_assets_are_consistent():
    prep = (ROOT / "frontend" / "scripts" / "prepare-pyodide.mjs").read_text(encoding="utf-8")
    worker = (ROOT / "frontend" / "src" / "inbrowser" / "worker.ts").read_text(encoding="utf-8")
    pkg = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    # the packages the worker loads are the roots the preparation script bundles, and the Pyodide version is pinned exactly
    loaded = set(__import__("re").search(r"loadPackage\(\[([^\]]+)\]", worker).group(1).replace("'", "").replace(" ", "").split(","))
    roots = set(__import__("re").search(r"ROOTS = \[([^\]]+)\]", prep).group(1).replace("'", "").replace(" ", "").split(","))
    assert loaded == roots
    assert pkg["dependencies"]["pyodide"] == "314.0.7"
    assert "build:static" in pkg["scripts"] and "--mode static" in pkg["scripts"]["build:static"]
    headers = json.loads((ROOT / "frontend" / "static-headers.json").read_text(encoding="utf-8"))
    csp = headers["Content-Security-Policy"]
    assert "'wasm-unsafe-eval'" in csp and "'unsafe-eval'" not in csp.replace("'wasm-unsafe-eval'", "") and "frame-ancestors 'none'" in csp
    assert "connect-src 'self'" in csp and "http" not in csp                                   # no third-party origin is ever contacted
    assert "http://" not in worker and "https://" not in worker                                 # the runtime is self-hosted: no URL at all


def test_the_netlify_configuration_builds_exactly_the_tested_static_site():
    import tomllib
    cfg = tomllib.loads((ROOT / "netlify.toml").read_text(encoding="utf-8"))
    assert cfg["build"]["base"] == "frontend" and cfg["build"]["publish"] == "dist-static"
    assert cfg["build"]["command"] == "npm ci && npm run build:static"                  # the same command CI runs
    assert cfg["build"]["environment"]["NODE_VERSION"] == "22"
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "dist-static/" in ignore and "static-assets/" in ignore                      # generated files are never committed
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "npm run build:static" in ci and "--static" in ci                              # CI builds and verifies the same artifact
