"""Independent re-derivation of attack paths and scores from the raw /api/environment data.

Start the backend on port 8000 first, then run:  python scripts/verify_independent.py
It uses its own DFS and scoring formula (no NetworkX, no app code) and compares with /api/analysis, then checks
that simulations never change the server's environment, plus input validation and CORS. NOTE: it posts simulations
and explanations, so run it against a throw-away database (set ATHAR_DB) and a high rate limit.
"""
import json, math, sys, time
import httpx

B = "http://127.0.0.1:8000"
P = B  # no proxy in this run
results = []

def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))

c = httpx.Client(timeout=15)
for _ in range(40):
    try:
        if c.get(B + "/api/health").status_code == 200 and c.get(P + "/api/health").status_code == 200:
            break
    except Exception:
        time.sleep(0.5)

for path in ["/api/health", "/api/environment", "/api/analysis", "/api/recommendations", "/api/activity"]:
    r = c.get(B + path)
    check(f"GET {path}", r.status_code == 200, f"{r.status_code}, {len(r.content)} bytes")
    check(f"GET {path} via frontend proxy", c.get(P + path).status_code == 200)
    check(f"headers {path}", r.headers.get("x-content-type-options") == "nosniff" and r.headers.get("cache-control") == "no-store")

env = c.get(B + "/api/environment").json()
base = c.get(B + "/api/analysis").json()
check("environment flagged synthetic", env["synthetic"] is True)

# ---- independent recomputation of paths and scores (no networkx, own DFS)
assets = {a["id"]: a for a in env["assets"]}
adj = {}
rels = {}
for r in env["relationships"]:
    if r["type"] == "protects":
        continue
    adj.setdefault(r["source"], []).append(r["target"])
    rels[(r["source"], r["target"])] = r
EV = {"validated": 1.0, "inferred": 0.7, "theoretical": 0.4}
PV = {"none": 1.0, "read": 0.7, "write": 0.85, "admin": 1.0}
def ew(r): return EV[r["evidence"]] * PV[r["privilege"]] * (0.35 if r["mfa_required"] else 1.0)
sources = [a for a in assets if assets[a]["compromised"]]
targets = [a for a, v in assets.items() if v["criticality"] >= 4 and v["type"] in ("server", "database", "cloud")]
found = {}
def dfs(node, tgt, trail):
    if node == tgt and len(trail) > 1:
        found[tuple(trail)] = True
        return
    if len(trail) > 6:
        return
    for n in adj.get(node, []):
        if n not in trail:
            dfs(n, tgt, trail + [n])
for s in sources:
    for t in targets:
        dfs(s, t, [s])
api_paths = {tuple(p["nodes"]): p for p in base["paths"]}
check("independent DFS finds identical path set", set(found) == set(api_paths), f"{len(found)} vs {len(api_paths)}")
bad = 0
for nodes, p in api_paths.items():
    w = [ew(rels[(u, v)]) for u, v in zip(nodes, nodes[1:])]
    ease = math.prod(w) ** (1 / len(w))
    lf = 1 / (1 + 0.1 * (len(w) - 1))
    ef = 1.1 if any(assets[n]["exposure"] == "internet" for n in nodes) else 1.0
    exp = min(100.0, round(100 * assets[nodes[-1]]["criticality"] / 5 * ease * lf * ef, 1))
    bad += abs(exp - p["score"]) > 1e-9
check("independent score recomputation matches every path", bad == 0, f"{len(api_paths)} paths, {bad} mismatches")
check("paths sorted by score desc", [p["score"] for p in base["paths"]] == sorted((p["score"] for p in base["paths"]), reverse=True))
s = base["summary"]
check("summary counts consistent", s["attack_paths"] == len(base["paths"]) and sum(s["severity_distribution"].values()) == len(base["paths"]))

# ---- simulation
snap_env, snap_base = json.dumps(env, sort_keys=True), json.dumps(base, sort_keys=True)
sim = c.post(B + "/api/simulate", json={"actions": [{"kind": "remove_relationship", "relationship_id": "r03"}]}).json()
check("simulate r03: paths 20->11", sim["before"]["attack_paths"] == 20 and sim["after"]["attack_paths"] == 11, f"{sim['before']['attack_paths']}->{sim['after']['attack_paths']}")
check("simulate r03: eliminated paths all contained r03", all("r03" in base["paths"][[p['id'] for p in base['paths']].index(i)]["relationship_ids"] for i in sim["paths_eliminated"]))
check("simulate r03: no path introduced", sim["paths_introduced"] == [])
check("simulate r03: residual risks to customer DB remain", any(r["target"] == "db-customers" for r in sim["residual_risks"]))
check("simulate r03: impact low (no legit use)", sim["operational_impact"]["level"] == "low")
# independent: after paths == baseline paths minus those using r03
expected_after = {tuple(p["nodes"]) for p in base["paths"] if "r03" not in p["relationship_ids"]}
check("after-paths == baseline minus paths through r03", {tuple(p["nodes"]) for p in sim["after_paths"]} == expected_after)
check("environment unchanged after simulation", json.dumps(c.get(B + "/api/environment").json(), sort_keys=True) == snap_env)
check("analysis unchanged after simulation", json.dumps(c.get(B + "/api/analysis").json(), sort_keys=True) == snap_base)
for acts, label in [
    ([{"kind": "apply_mfa", "asset_id": "web-portal"}], "mfa"),
    ([{"kind": "apply_segmentation", "asset_id": "app-server"}], "segmentation"),
    ([{"kind": "reduce_privilege", "relationship_id": "r03", "to": "read"}], "reduce_privilege"),
    ([{"kind": "remove_relationship", "relationship_id": "r03"}, {"kind": "remove_relationship", "relationship_id": "r08"}], "multi"),
]:
    r = c.post(B + "/api/simulate", json={"actions": acts})
    check(f"simulate {label} 200", r.status_code == 200, f"after={r.json()['after']['attack_paths']} reduction={r.json()['risk_reduction_pct']}%")
check("environment still unchanged after all sims", json.dumps(c.get(B + "/api/environment").json(), sort_keys=True) == snap_env)

# ---- validation / errors
for body, name in [
    ({"actions": [{"kind": "remove_relationship", "relationship_id": "nope"}]}, "unknown id -> 422"),
    ({"actions": [{"kind": "remove_relationship", "relationship_id": "<script>alert(1)</script>"}]}, "XSS id -> 422"),
    ({"actions": [{"kind": "remove_relationship", "relationship_id": "r1' OR '1'='1"}]}, "SQLi id -> 422"),
    ({"actions": []}, "empty -> 422"),
    ({"actions": [{"kind": "delete_all"}]}, "unknown kind -> 422"),
    ({"actions": [{"kind": "remove_relationship", "relationship_id": "r03"}] * 21}, "21 actions -> 422"),
    ({}, "missing actions -> 422"),
]:
    r = c.post(B + "/api/simulate", json=body)
    check("simulate " + name, r.status_code == 422, str(r.status_code))
r = c.post(B + "/api/simulate", content=b"{not json", headers={"content-type": "application/json"})
check("malformed JSON -> 422", r.status_code == 422)
check("GET on POST route -> 405", c.get(B + "/api/simulate").status_code == 405)
check("unknown route -> 404", c.get(B + "/api/nope").status_code == 404)

# ---- explain
pid = base["paths"][0]["id"]
for lang in ("en", "ar"):
    r = c.post(B + "/api/explain", json={"kind": "path", "id": pid, "lang": lang}).json()
    check(f"explain path {lang}", bool(r["template_explanation"]) and r["ai_explanation"] is None and r["ai_status"] == "ai_disabled")
check("explain Arabic text contains Arabic", any("؀" <= ch <= "ۿ" for ch in c.post(B + "/api/explain", json={"kind": "path", "id": pid, "lang": "ar"}).json()["template_explanation"]))
recs = c.get(B + "/api/recommendations").json()
check("recommendations all need human approval", recs and all(r["requires_human_approval"] for r in recs), f"{len(recs)} recs")
check("recommendation explain 200", c.post(B + "/api/explain", json={"kind": "recommendation", "id": recs[0]["id"]}).status_code == 200)
check("explain unknown path -> 404", c.post(B + "/api/explain", json={"kind": "path", "id": "p-x"}).status_code == 404)
check("explain bad lang -> 422", c.post(B + "/api/explain", json={"kind": "path", "id": pid, "lang": "fr"}).status_code == 422)
# CORS
r = c.options(B + "/api/simulate", headers={"origin": "http://evil.example", "access-control-request-method": "POST"})
check("CORS rejects foreign origin", "access-control-allow-origin" not in r.headers)
r = c.options(B + "/api/simulate", headers={"origin": "http://localhost:5173", "access-control-request-method": "POST"})
check("CORS allows dev origin", r.headers.get("access-control-allow-origin") == "http://localhost:5173")
act = c.get(B + "/api/activity").json()
check("activity log records simulations", sum(a["kind"] == "simulation_run" for a in act) >= 5, f"{len(act)} events")

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
