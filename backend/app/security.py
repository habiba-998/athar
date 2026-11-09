"""Request guard: body-size limit, rate limiting and access control for the two supported modes.

ATHAR_MODE=local  (default)  - a private instance.
    * If ATHAR_API_TOKEN is set, every /api request (except health and auth status) must send the same value in the
      `X-ATHAR-Token` header (constant-time comparison).
    * If it is not set, the API only accepts connections from the local machine.
ATHAR_MODE=demo              - a PUBLIC, READ-ONLY demonstration of synthetic data.
    * Anyone may read (GET) and may run the two stateless computations POST /api/simulate and POST /api/explain, whose
      results are NOT persisted (no shared audit rows can be created by visitors).
    * Every other write (import, edit, reset, undo, scoring configuration, scenario activation) is refused with 403
      `read_only_demo` unless the request carries the administrator token (ATHAR_ADMIN_TOKEN) in `X-ATHAR-Token`.
    * With no ATHAR_ADMIN_TOKEN configured the demo is read-only for everybody.
This is a demo-grade control, not a substitute for real authentication, accounts, roles or SSO (see docs/SECURITY.md).
"""
from __future__ import annotations

import hmac
import os
import threading
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse

LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}  # "testclient" is Starlette's in-process test host
PUBLIC_PATHS = {"/api/health", "/api/ready", "/api/auth/status"}
EXPENSIVE_PATHS = {"/api/explain", "/api/sensitivity", "/api/plans"}
DEMO_OPEN_POSTS = {"/api/simulate", "/api/explain"}   # stateless in demo mode: computed, never persisted
MIN_SECRET_LENGTH = 16
WINDOW_SECONDS = 60.0


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except ValueError:
        return default


def mode() -> str:
    return "demo" if os.environ.get("ATHAR_MODE", "local").strip().lower() == "demo" else "local"


def is_demo() -> bool:
    return mode() == "demo"


def trust_proxy() -> bool:
    return os.environ.get("ATHAR_TRUST_PROXY", "").strip() == "1"


def client_ip(request: Request) -> str:
    """The client address. X-Forwarded-For is honoured ONLY when ATHAR_TRUST_PROXY=1, which must be set only behind exactly one
    trusted reverse proxy that appends the address it saw. The RIGHT-MOST entry is that proxy's observation; entries to its
    left are client-supplied and can be forged, so they are ignored. Without the flag the header is never trusted, otherwise a
    caller could spoof it to dodge rate limits or to look like loopback."""
    if trust_proxy():
        parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if parts:
            return parts[-1]
    return request.client.host if request.client else "unknown"


def is_https(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    return trust_proxy() and request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https"


def secret_problems() -> list[str]:
    """Configuration problems with the tokens; a public demo must not start with weak or colliding secrets."""
    out = []
    tok, adm = os.environ.get("ATHAR_API_TOKEN", ""), os.environ.get("ATHAR_ADMIN_TOKEN", "")
    for name, val in (("ATHAR_API_TOKEN", tok), ("ATHAR_ADMIN_TOKEN", adm)):
        if val and len(val) < MIN_SECRET_LENGTH:
            out.append(f"{name} is shorter than {MIN_SECRET_LENGTH} characters")
    if tok and adm and hmac.compare_digest(tok.encode(), adm.encode()):
        out.append("ATHAR_API_TOKEN and ATHAR_ADMIN_TOKEN must differ")
    return out


class RateLimiter:
    """In-memory sliding window per (client, bucket)."""

    def __init__(self, read: int | None = None, write: int | None = None, explain: int | None = None) -> None:
        self.limits = {"read": read or _int_env("ATHAR_RATE_READ", 300),
                       "write": write or _int_env("ATHAR_RATE_WRITE", 90),
                       "explain": explain or _int_env("ATHAR_RATE_EXPLAIN", 40)}
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    @staticmethod
    def bucket(method: str, path: str) -> str:
        if path in EXPENSIVE_PATHS or path.endswith("/explanation") or path.endswith("/report"):
            return "explain"                         # CPU-heavy or AI-backed endpoints share the small bucket
        return "read" if method in ("GET", "HEAD", "OPTIONS") else "write"

    def check(self, client: str, method: str, path: str) -> float | None:
        """Return None if allowed, else seconds until the client may retry."""
        b = self.bucket(method, path)
        limit, now = self.limits[b], time.monotonic()
        with self._lock:
            q = self._hits[(client, b)]
            while q and now - q[0] > WINDOW_SECONDS:
                q.popleft()
            if len(q) >= limit:
                return max(1.0, WINDOW_SECONDS - (now - q[0]))
            q.append(now)
            if len(self._hits) > 5000:  # bound memory under many distinct clients
                for k in [k for k, v in self._hits.items() if not v][:1000]:
                    del self._hits[k]
        return None


def max_body() -> int:
    return _int_env("ATHAR_MAX_BODY", 1_048_576)


def token_required() -> bool:
    """Whether a token is needed to READ. In demo mode reading is public, so this is False there."""
    return (not is_demo()) and bool(os.environ.get("ATHAR_API_TOKEN"))


def admin_configured() -> bool:
    return bool(os.environ.get("ATHAR_ADMIN_TOKEN"))


def _token_ok(request: Request, expected: str | None) -> bool:
    if not expected:
        return False
    supplied = request.headers.get("x-athar-token", "")
    return hmac.compare_digest(supplied.encode(), expected.encode())


def is_admin(request: Request) -> bool:
    return _token_ok(request, os.environ.get("ATHAR_ADMIN_TOKEN"))


def authorised(request: Request) -> bool:
    """Local mode access rule (kept for backwards compatibility and the tests)."""
    expected = os.environ.get("ATHAR_API_TOKEN")
    if expected:
        return _token_ok(request, expected)
    return client_ip(request) in LOOPBACK


def reject(status: int, code: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": code}, headers=headers)


def auth_status() -> dict[str, object]:
    return {"token_required": token_required(), "mode": mode(), "read_only": is_demo(),
            "admin_token_supported": is_demo() and admin_configured()}


async def guard(request: Request, call_next, limiter: RateLimiter):
    path = request.url.path
    request.state.ephemeral = False
    request.state.admin = False
    if not path.startswith("/api") or request.method == "OPTIONS":
        return await call_next(request)  # CORS preflight and the static single-page app
    if request.method in ("POST", "PUT", "PATCH"):
        length = request.headers.get("content-length")
        if length is None:
            return reject(411, "length_required")
        if not length.isdigit() or int(length) > max_body():
            return reject(413, "payload_too_large")
    wait = limiter.check(client_ip(request), request.method, path)
    if wait is not None:
        return reject(429, "rate_limited", {"Retry-After": str(int(wait))})
    if path in PUBLIC_PATHS:
        return await call_next(request)
    if is_demo():
        admin = is_admin(request)
        request.state.admin = admin
        reading = request.method in ("GET", "HEAD")
        if not (admin or reading or (request.method == "POST" and path in DEMO_OPEN_POSTS)):
            return reject(403, "read_only_demo" if not admin_configured() or "x-athar-token" not in request.headers else "invalid_admin_token")
        request.state.ephemeral = not admin          # visitors never create audit rows or persistent state
        return await call_next(request)
    if not authorised(request):
        if token_required():
            return reject(401, "invalid_or_missing_token")
        return reject(403, "local_only")
    request.state.admin = True
    return await call_next(request)
