"""Live checks against REAL uvicorn processes (not the in-process test client).

Run with the backend's Python:   python scripts/verify_live.py [--with-network]
It starts/stops its own servers on port 8200 with throw-away databases. It checks: persistence across a real
process restart, token mode, rate limits, body-size/chunked-upload rejection and AI fallbacks.
`--with-network` additionally sends ONE request (synthetic facts, a deliberately fake API key) to
api.anthropic.com to prove the AI fallback against a real failing endpoint; without the flag nothing leaves the machine.
"""
import os, subprocess, sys, tempfile, time, json
import httpx

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
WITH_NETWORK = "--with-network" in sys.argv
PY = sys.executable
PORT = 8200
BASE = f"http://127.0.0.1:{PORT}"
results = []

def check(name, ok, detail=""):
    ok = bool(ok)
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))

def start(extra_env):
    env = {**os.environ, **extra_env}
    for k in ("ATHAR_API_TOKEN", "ATHAR_AI_PROVIDER", "ANTHROPIC_API_KEY"):
        if k not in extra_env:
            env.pop(k, None)
    p = subprocess.Popen([PY, "-m", "uvicorn", "app.main:app", "--port", str(PORT), "--log-level", "warning"],
                         cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            if httpx.get(BASE + "/api/health", timeout=1).status_code == 200:
                return p
        except Exception:
            time.sleep(0.3)
    p.kill()
    raise RuntimeError("server did not start")

def stop(p):
    p.terminate()
    try:
        p.wait(8)
    except Exception:
        p.kill()
    time.sleep(0.5)

db = os.path.join(tempfile.mkdtemp(prefix="athar-live-"), "live.db")
body = {"actions": [{"kind": "remove_relationship", "relationship_id": "r03"}]}

# ---- 1. default (local-only) mode, persistence across a real process restart
p = start({"ATHAR_DB": db})
c = httpx.Client(base_url=BASE, timeout=10)
check("starts and serves health", c.get("/api/health").json()["synthetic_data"] is True)
check("loopback client allowed in local-only mode", c.get("/api/analysis").status_code == 200)
check("DELETE r05 ok", c.delete("/api/relationships/r05").status_code == 200)
sim = c.post("/api/simulate", json=body).json()
check("simulation recorded with id+timestamp", sim["record_id"] >= 1 and sim["recorded_at"].endswith("+00:00"))
paths_edited = c.get("/api/analysis").json()["summary"]["attack_paths"]
meta = c.get("/api/environment/meta").json()
check("environment is custom after edit", meta["is_sample"] is False and meta["can_undo"] is True)
# chunked upload has no Content-Length -> must be refused (cannot bypass the size limit)
r = c.put("/api/environment", content=(chunk for chunk in [b'{"a":', b'1}']))
check("chunked body without Content-Length rejected (411)", r.status_code == 411, str(r.status_code))
r = c.put("/api/environment", content=b"x" * (1_048_576 + 10), headers={"content-type": "application/json"})
check("oversize body rejected (413)", r.status_code == 413, str(r.status_code))
stop(p)

p = start({"ATHAR_DB": db})
c = httpx.Client(base_url=BASE, timeout=10)
env = c.get("/api/environment").json()
check("edit survived real process restart", all(r["id"] != "r05" for r in env["relationships"]))
check("analysis identical after restart", c.get("/api/analysis").json()["summary"]["attack_paths"] == paths_edited)
hist = c.get("/api/simulations").json()
check("simulation history survived restart", len(hist) == 1 and hist[0]["id"] == sim["record_id"] and hist[0]["current_environment"] is True)
rec = c.get(f"/api/simulations/{sim['record_id']}").json()
check("stored evidence intact after restart", rec["before_paths"] and rec["after_paths"][0]["factors"], f"{len(rec['before_paths'])} paths")
acts = [a["kind"] for a in c.get("/api/activity?limit=200").json()]
check("activity history survived restart", "relationship_deleted" in acts and "simulation_run" in acts and acts.count("environment_loaded") == 2)
check("explanations table queryable", c.get("/api/explanations").status_code == 200)
check("reset restores sample", c.post("/api/environment/reset").json()["is_sample"] is True)
stop(p)

# ---- 2. token mode on a real server
p = start({"ATHAR_DB": db, "ATHAR_API_TOKEN": "live-token-123"})
c = httpx.Client(base_url=BASE, timeout=10)
check("token mode: no token -> 401", c.get("/api/analysis").status_code == 401)
check("token mode: wrong token -> 401", c.get("/api/analysis", headers={"x-athar-token": "nope"}).status_code == 401)
check("token mode: correct token -> 200", c.get("/api/analysis", headers={"x-athar-token": "live-token-123"}).status_code == 200)
check("token mode: write without token -> 401", c.post("/api/simulate", json=body).status_code == 401)
check("token mode: write with token -> 200", c.post("/api/simulate", json=body, headers={"x-athar-token": "live-token-123"}).status_code == 200)
check("token mode: health + auth status stay public", c.get("/api/health").status_code == 200 and c.get("/api/auth/status").json().get("token_required") is True)
r = c.get("/api/analysis", headers={"origin": "http://localhost:5173"})
check("401 still carries CORS header for the UI origin", r.headers.get("access-control-allow-origin") == "http://localhost:5173")
check("foreign origin gets no CORS header", c.get("/api/analysis", headers={"origin": "http://evil.example", "x-athar-token": "live-token-123"}).headers.get("access-control-allow-origin") is None)
stop(p)

# ---- 3. real rate limiting
p = start({"ATHAR_DB": db, "ATHAR_RATE_READ": "5", "ATHAR_RATE_WRITE": "3", "ATHAR_RATE_EXPLAIN": "2"})
c = httpx.Client(base_url=BASE, timeout=10)
codes = [c.get("/api/analysis").status_code for _ in range(8)]
# the readiness probe in start() already spent >=1 of the 5 allowed read requests (health is rate-limited too)
first_429 = codes.index(429)
check("read limit enforced on real server (limit 5 incl. readiness probe)",
      4 <= first_429 <= 5 and all(x == 200 for x in codes[:first_429]) and all(x == 429 for x in codes[first_429:]), str(codes))
r = c.get("/api/analysis")
check("429 has Retry-After", r.status_code == 429 and int(r.headers["retry-after"]) >= 1)
wcodes = [c.post("/api/simulate", json=body).status_code for _ in range(5)]
check("write limit enforced independently", wcodes == [200, 200, 200, 429, 429], str(wcodes))
stop(p)

# ---- 4. AI misconfiguration on a real server never breaks explanations
p = start({"ATHAR_DB": db, "ATHAR_AI_PROVIDER": "anthropic"})   # provider but no key
c = httpx.Client(base_url=BASE, timeout=10)
pid = c.get("/api/analysis").json()["paths"][0]["id"]
j = c.post("/api/explain", json={"kind": "path", "id": pid, "lang": "ar"}).json()
check("provider without key -> ai_not_configured + deterministic text", j["ai_status"] == "ai_not_configured" and j["ai_explanation"] is None and j["template_explanation"])
stop(p)
if WITH_NETWORK:
    p = start({"ATHAR_DB": db, "ATHAR_AI_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "sk-fake-key-for-offline-check"})
    c = httpx.Client(base_url=BASE, timeout=30)
    t0 = time.time()
    j = c.post("/api/explain", json={"kind": "path", "id": pid}).json()
    check("fake key reaches the real API and fails safely (ai_unavailable, deterministic text intact)",
          j["ai_explanation"] is None and j["ai_status"] == "ai_unavailable" and j["template_explanation"], f"{time.time()-t0:.1f}s")
    stop(p)
else:
    print("SKIP network AI-fallback check (pass --with-network to run it)")

print(f"\n{sum(results)}/{len(results)} live checks passed")
sys.exit(0 if all(results) else 1)
