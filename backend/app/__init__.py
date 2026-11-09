"""ATHAR backend package.

Platform defaults: Vercel sets VERCEL=1 for builds and functions. There the deployment is the PUBLIC READ-ONLY DEMO, whose
serverless functions have a read-only filesystem (only /tmp is writable) and no state shared between instances. So, unless the
project settings say otherwise, a Vercel function runs in demo mode with a /tmp database, trusts the single Vercel proxy hop
for client addresses and sends HSTS. No secret is involved: without ATHAR_ADMIN_TOKEN nobody can write.
"""
import os

if os.environ.get("VERCEL"):
    os.environ.setdefault("ATHAR_MODE", "demo")
    os.environ.setdefault("ATHAR_DB", "/tmp/athar.db")
    os.environ.setdefault("ATHAR_TRUST_PROXY", "1")
    os.environ.setdefault("ATHAR_HSTS", "1")
