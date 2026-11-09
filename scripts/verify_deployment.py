"""Verify a DEPLOYED ATHAR instance from the outside, over the network, with the standard library only.

    python scripts/verify_deployment.py https://your-deployment.example
    python scripts/verify_deployment.py http://127.0.0.1:8000 --allow-insecure-local     # rehearsal against a local server
    python scripts/verify_deployment.py https://... --json report.json --admin-token-env ATHAR_ADMIN_TOKEN

What it checks (each line is PASS / FAIL / SKIP; exit status is non-zero if anything fails):
  * the URL is https (public deployments only) and its TLS certificate validates against the system trust store
  * /api/health, /api/ready, mode == demo, read-only flag
  * security headers on the page and on API responses (CSP, nosniff, frame, referrer, HSTS)
  * the single-page app is served and refers to no localhost / loopback address and contains no secret-looking strings
  * read endpoints work (analysis, plans, scoring config, evidence, services) and return synthetic data
  * writes are REFUSED without the administrator token (import, edit, reset, scoring change) with 403
  * stateless simulation works and is not persisted
  * unknown API paths return JSON without stack traces; the interactive docs are off
  * a cross-origin request from an unlisted origin receives no CORS allowance
  * response time of a read request

It never prints a token. The administrator token (optional) is read from an environment variable whose NAME you pass.
It only sends ordinary requests to the URL you give it: no scanning, fuzzing or exploitation.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 20
SECRET_PATTERNS = [r"sk-ant-[A-Za-z0-9_-]{10,}", r"ATHAR_ADMIN_TOKEN\s*[:=]\s*[\"'][^\"']{8,}", r"ANTHROPIC_API_KEY\s*[:=]\s*[\"'][^\"']{8,}",
                   r"-----BEGIN (RSA |EC )?PRIVATE KEY-----"]
LOCAL_PATTERN = re.compile(r"(?:https?:)?//(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+)(?::\d+)?", re.I)


class Resp:
    def __init__(self, status: int, headers: dict[str, str], body: bytes):
        self.status, self.headers, self.body = status, {k.lower(): v for k, v in headers.items()}, body

    def json(self):
        return json.loads(self.body.decode("utf-8", "replace"))

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", "replace")


def request(url: str, method: str = "GET", body: bytes | None = None, headers: dict[str, str] | None = None) -> Resp:
    req = urllib.request.Request(url, data=body, method=method, headers={"User-Agent": "athar-deployment-check/1.0", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:                # default context: certificate IS verified
            return Resp(r.status, dict(r.headers), r.read(5_000_000))
    except urllib.error.HTTPError as e:
        return Resp(e.code, dict(e.headers), e.read(1_000_000))


class Report:
    def __init__(self) -> None:
        self.rows: list[dict[str, str]] = []

    def add(self, status: str, name: str, detail: str = "") -> None:
        self.rows.append({"status": status, "check": name, "detail": detail})
        print(f"{status:5} {name}" + (f"  -  {detail}" if detail else ""))

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.add("PASS" if ok else "FAIL", name, detail)
        return ok

    @property
    def failed(self) -> int:
        return sum(1 for r in self.rows if r["status"] == "FAIL")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", help="base URL of the deployment, e.g. https://example.org")
    ap.add_argument("--allow-insecure-local", action="store_true", help="permit http:// for a loopback rehearsal (not a deployment check)")
    ap.add_argument("--json", metavar="FILE", help="also write the results as JSON")
    ap.add_argument("--admin-token-env", metavar="VAR", help="name of an environment variable holding the administrator token (optional)")
    args = ap.parse_args()

    base = args.url.rstrip("/")
    u = urllib.parse.urlparse(base)
    rep = Report()
    host = u.hostname or ""
    is_loopback = host in ("localhost", "127.0.0.1", "::1")

    if u.scheme != "https":
        if args.allow_insecure_local and is_loopback:
            rep.add("SKIP", "https", "loopback rehearsal: this is NOT a public deployment check")
        else:
            rep.check("url uses https", False, "a public deployment must be https; use --allow-insecure-local only for a loopback rehearsal")
            return finish(rep, args)
    else:
        if is_loopback:
            rep.check("public host", False, "a loopback address is not a public deployment")
            return finish(rep, args)
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((host, u.port or 443), timeout=TIMEOUT) as s, ctx.wrap_socket(s, server_hostname=host) as t:
                cert = t.getpeercert()
            rep.check("tls certificate validates", True, f"expires {cert.get('notAfter')}")
        except (OSError, ssl.SSLError) as e:
            rep.check("tls certificate validates", False, type(e).__name__)
            return finish(rep, args)

    try:
        health = request(f"{base}/api/health")
    except (urllib.error.URLError, OSError) as e:
        rep.check("server reachable", False, type(e).__name__)
        return finish(rep, args)
    rep.check("health", health.status == 200 and health.json().get("status") == "ok", f"HTTP {health.status}")
    rep.check("readiness", request(f"{base}/api/ready").status == 200)
    auth = request(f"{base}/api/auth/status").json()
    rep.check("public demo mode, read-only", auth.get("mode") == "demo" and auth.get("read_only") is True, f"mode={auth.get('mode')}")
    rep.check("no token needed to read", auth.get("token_required") is False)

    page = request(f"{base}/")
    html = page.text
    rep.check("single-page app is served", page.status == 200 and 'id="root"' in html, f"HTTP {page.status}")
    for hname, want in (("content-security-policy", "default-src 'self'"), ("x-content-type-options", "nosniff"), ("x-frame-options", "DENY"),
                        ("referrer-policy", "no-referrer")):
        rep.check(f"page header {hname}", want in page.headers.get(hname, ""))
    if u.scheme == "https":
        rep.check("page header strict-transport-security", "max-age=" in page.headers.get("strict-transport-security", ""))
    api = request(f"{base}/api/analysis")
    rep.check("api header content-security-policy", "default-src" in api.headers.get("content-security-policy", ""))
    rep.check("api responses are not cacheable", "no-store" in api.headers.get("cache-control", ""))

    # the shipped bundle: no loopback/LAN addresses, no secrets
    assets = sorted(set(re.findall(r'(?:src|href)="(/assets/[^"]+\.(?:js|css))"', html)))
    blob = html
    for a in assets[:12]:
        blob += request(base + a).text
    rep.check("bundle references found", bool(assets), f"{len(assets)} asset files")
    local = sorted(set(LOCAL_PATTERN.findall(blob)))
    # w3.org / reactjs.org style namespace URLs are fine; only loopback/private addresses matter here
    rep.check("bundle contains no localhost or private-network address", not local, ", ".join(local[:3]))
    leaks = [p for p in SECRET_PATTERNS if re.search(p, blob)]
    rep.check("bundle contains no secret-looking strings", not leaks)

    t0 = time.perf_counter()
    analysis = request(f"{base}/api/analysis")
    ms = 1000 * (time.perf_counter() - t0)
    rep.check("analysis readable", analysis.status == 200 and analysis.json()["summary"]["attack_paths"] >= 1)
    rep.check("read latency under 3 s", ms < 3000, f"{ms:.0f} ms")
    for path in ("/api/environment", "/api/plans", "/api/scoring-config", "/api/evidence", "/api/services", "/api/recommendations"):
        r = request(base + path)
        rep.check(f"GET {path}", r.status == 200, f"HTTP {r.status}")
    env = request(f"{base}/api/environment").json()
    rep.check("environment is flagged synthetic", env.get("synthetic") is True)

    body = json.dumps(env).encode()
    for method, path, payload in (("PUT", "/api/environment", body), ("POST", "/api/environment/reset", b"{}"),
                                  ("POST", "/api/environment/undo", b"{}"), ("PUT", "/api/scoring-config", b"{}"),
                                  ("POST", "/api/attack-scenarios/x/activate", b"{}"), ("POST", "/api/assets", b"{}"),
                                  ("DELETE", "/api/relationships/r01", None)):
        r = request(base + path, method, payload, {"Content-Type": "application/json"} if payload is not None else None)
        rep.check(f"{method} {path} refused without admin token", r.status in (401, 403), f"HTTP {r.status}")
    rep.check("environment unchanged after refused writes", request(f"{base}/api/environment").json() == env)

    first = env["relationships"][0]["id"]
    sim = request(f"{base}/api/simulate", "POST", json.dumps({"actions": [{"kind": "disable_relationship", "relationship_id": first}]}).encode(),
                  {"Content-Type": "application/json"})
    ok = sim.status == 200 and sim.json().get("ephemeral") is True and sim.json().get("record_id") is None
    rep.check("stateless simulation works and is not persisted", ok, f"HTTP {sim.status}")

    nf = request(f"{base}/api/definitely-not-a-route")
    rep.check("unknown API path returns JSON, no stack trace", nf.status == 404 and "Traceback" not in nf.text and nf.headers.get("content-type", "").startswith("application/json"))
    docs, spec = request(f"{base}/docs"), request(f"{base}/openapi.json")
    rep.check("interactive API docs are disabled", "swagger" not in docs.text.lower() and '"openapi"' not in spec.text[:2000])
    cors = request(f"{base}/api/analysis", "GET", None, {"Origin": "https://not-allowed.invalid"})
    rep.check("cross-origin request from an unlisted origin gets no CORS allowance", "access-control-allow-origin" not in cors.headers)
    pre = request(f"{base}/api/environment", "OPTIONS", None, {"Origin": "https://not-allowed.invalid", "Access-Control-Request-Method": "PUT"})
    rep.check("cross-origin preflight is not allowed", "access-control-allow-origin" not in pre.headers)

    if args.admin_token_env:
        tok = os.environ.get(args.admin_token_env, "")
        if not tok:
            rep.add("SKIP", "admin token checks", f"environment variable {args.admin_token_env} is empty")
        else:
            bad = request(f"{base}/api/environment/reset", "POST", b"{}", {"X-ATHAR-Token": tok + "x", "Content-Type": "application/json"})
            rep.check("wrong admin token is refused", bad.status in (401, 403))
            good = request(f"{base}/api/scoring-config", "GET", None, {"X-ATHAR-Token": tok})
            rep.check("admin token accepted for reads", good.status == 200)
    else:
        rep.add("SKIP", "admin token checks", "not requested (--admin-token-env)")
    return finish(rep, args)


def finish(rep: Report, args) -> int:
    passed = sum(1 for r in rep.rows if r["status"] == "PASS")
    print(f"\n{passed} passed, {rep.failed} failed, {sum(1 for r in rep.rows if r['status'] == 'SKIP')} skipped")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"url": args.url, "results": rep.rows, "failed": rep.failed}, f, indent=2)
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
