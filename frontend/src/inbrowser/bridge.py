"""ATHAR in the browser: an in-process ASGI bridge around the unchanged FastAPI backend (backend/app).

In the static build the backend source is loaded into Pyodide (CPython compiled to WebAssembly) inside a Web Worker, and every
`/api/...` call of the frontend is turned into an ASGI request to the very same `app.main:app` that the server deployment runs.
Nothing is re-implemented: routing, validation, the demo-mode guard, scoring, plans, sensitivity and explanations are the same code.

The module also runs under ordinary CPython (the tests compare it with the real HTTP application).
"""
import json
import os
import sys
import traceback
from urllib.parse import urlsplit

_app = None


def _patch_threadpool():
    """WebAssembly has no threads: "sync" endpoints run inline instead of in anyio's thread pool."""
    import anyio.to_thread
    import fastapi.dependencies.utils
    import fastapi.routing
    import starlette.concurrency
    import starlette.routing

    async def run_sync(func, *args, **kwargs):
        return func(*args)

    async def inline(func, *args, **kwargs):
        return func(*args, **kwargs)

    anyio.to_thread.run_sync = run_sync
    for mod in (starlette.concurrency, fastapi.routing, starlette.routing, fastapi.dependencies.utils):
        if hasattr(mod, "run_in_threadpool"):
            mod.run_in_threadpool = inline


def install(backend_dir=None):
    """Import the backend once. Always the read-only public demo, with an in-memory database and no secrets."""
    global _app
    if backend_dir and backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    os.environ.setdefault("ATHAR_MODE", "demo")
    os.environ.setdefault("ATHAR_DB", ":memory:")
    os.environ.setdefault("ATHAR_LOG_LEVEL", "ERROR")           # the browser console is not a log shipper
    for name in ("ATHAR_RATE_READ", "ATHAR_RATE_WRITE", "ATHAR_RATE_EXPLAIN"):
        os.environ.setdefault(name, "1000000")                  # one visitor, one browser: nobody to rate-limit
    if sys.platform == "emscripten":
        _patch_threadpool()
    import app.main as m
    _app = m.app
    return m.app.title


async def handle(method, url, headers_json="{}", body=None):
    """Run one request through the application and return a JSON document {status, headers, body}."""
    if _app is None:
        install()
    parts = urlsplit(url)
    raw = body.encode("utf-8") if body else b""
    headers = [(k.lower().encode(), str(v).encode()) for k, v in json.loads(headers_json).items()]
    headers += [(b"host", b"athar.local"), (b"content-length", str(len(raw)).encode())]
    if raw and not any(k == b"content-type" for k, _ in headers):
        headers.append((b"content-type", b"application/json"))      # the API only speaks JSON
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method.upper(), "path": parts.path,
             "raw_path": parts.path.encode(), "query_string": parts.query.encode(), "headers": headers,
             "client": ("127.0.0.1", 0), "server": ("athar.local", 443), "scheme": "https"}
    sent = []
    state = {"done": False}

    async def receive():
        if not state["done"]:
            state["done"] = True
            return {"type": "http.request", "body": raw, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    try:
        await _app(scope, receive, send)
    except Exception:                                           # the app answers 500 itself; this only guards the bridge
        traceback.print_exc()
        return json.dumps({"status": 500, "headers": {}, "body": json.dumps({"error": "internal_error"})})
    start = next(m for m in sent if m["type"] == "http.response.start")
    data = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return json.dumps({"status": start["status"], "headers": {k.decode(): v.decode() for k, v in start["headers"]},
                       "body": data.decode("utf-8", "replace")})
