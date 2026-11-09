"""Vercel entrypoint: exposes the ATHAR FastAPI application as a serverless function.

Vercel serves the built single-page app (frontend/dist) as static files and routes /api/* here (see vercel.json), so the app
and the API share one origin: no CORS and no API base URL are needed. The deployment is the PUBLIC READ-ONLY DEMO:

* writes are refused (no ATHAR_ADMIN_TOKEN is configured, so nobody can write); simulations are computed but not stored;
* the filesystem is read-only except /tmp, and every function instance has its own memory, so nothing could be shared or
  persisted reliably anyway. State is rebuilt from the synthetic sample on every cold start (stateless by design).

Defaults below are NON-secret and can be overridden in the Vercel project settings. No secret is required.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("ATHAR_MODE", "demo")
os.environ.setdefault("ATHAR_DB", "/tmp/athar.db")          # the only writable location in a serverless function
os.environ.setdefault("ATHAR_TRUST_PROXY", "1")              # exactly one trusted proxy hop: Vercel sets X-Forwarded-For
os.environ.setdefault("ATHAR_HSTS", "1")
os.environ.setdefault("ATHAR_LOG_LEVEL", "INFO")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.main import app  # noqa: E402,F401  (Vercel looks for an ASGI application named `app`)
