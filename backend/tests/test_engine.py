import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.analysis import analyze, severity_for
from app.data.demo import build_demo_environment
from app.main import app
from app.models import (ApplyMfa, ApplySegmentation, Environment, Evidence, ReducePrivilege, RemoveRelationship,
                        SimulationRequest)
from app.recommendations import recommend
from app.simulation import SimulationError, simulate

client = TestClient(app)


@pytest.fixture()
def env() -> Environment:
    return build_demo_environment()


# ---------------------------------------------------------------- paths & risk
def test_demo_reaches_sensitive_database_from_compromised_account(env):
    a = analyze(env)
    routes = [p["nodes"] for p in a["paths"] if p["target"] == "db-customers"]
    assert ["emp-sara", "jump-host", "backup-server", "db-customers"] in routes
    assert ["emp-sara", "web-portal", "app-server", "db-customers"] in routes
    assert all(p["nodes"][0] == "emp-sara" for p in a["paths"])


def test_paths_are_simple_and_follow_real_edges(env):
    rels = {(r.source, r.target) for r in env.relationships}
    for p in analyze(env)["paths"]:
        assert len(set(p["nodes"])) == len(p["nodes"])
        assert all((u, v) in rels for u, v in zip(p["nodes"], p["nodes"][1:]))


def test_scoring_is_reproducible_and_hand_checkable(env):
    p = next(p for p in analyze(env)["paths"]
             if p["nodes"] == ["emp-sara", "jump-host", "backup-server", "db-customers"])
    # edges: r03 validated*admin=1.0, r07 1.0, r10 validated*read=0.7 -> ease=0.7**(1/3)
    expected = round(100 * (5 / 5) * (0.7 ** (1 / 3)) * (1 / 1.2), 1)
    assert p["score"] == expected
    assert p["classification"] == "validated"
    assert analyze(env)["paths"] == analyze(build_demo_environment())["paths"]


def test_theoretical_evidence_is_distinguished(env):
    a = analyze(env)
    vault = [p for p in a["paths"] if p["target"] == "secrets-vault"]
    assert vault and all(p["classification"] == "theoretical" for p in vault)
    # same route with the theoretical hop upgraded to validated must score strictly higher
    upgraded = env.model_copy(deep=True)
    next(r for r in upgraded.relationships if r.id == "r14").evidence = Evidence.validated
    up = {p["id"]: p["score"] for p in analyze(upgraded)["paths"]}
    assert all(up[p["id"]] > p["score"] for p in vault)


def test_severity_bands():
    assert [severity_for(s) for s in (75, 55, 35, 5)] == ["critical", "high", "medium", "low"]


def test_summary_metrics_come_from_data(env):
    s = analyze(env)["summary"]
    assert s["attack_paths"] == len(analyze(env)["paths"])
    assert sum(s["severity_distribution"].values()) == s["attack_paths"]
    assert s["total_assets"] == 15 and s["critical_assets"] == 7


def test_unjustified_access_finding_for_stale_admin_login(env):
    kinds = {(f["kind"], f.get("relationship_id")) for f in analyze(env)["findings"]}
    assert ("unjustified_access", "r03") in kinds


def _dense_env(n: int) -> Environment:
    """Complete directed graph: the number of simple paths explodes, forcing the global path cap."""
    from app.models import Asset, Relationship
    assets = [Asset(id=f"n{i}", name=f"N{i}", name_ar=f"ن{i}", type="server", criticality=5, compromised=(i == 0))
              for i in range(n)]
    rels = [Relationship(id=f"e{i}-{j}", source=f"n{i}", target=f"n{j}", type="network_access", evidence="validated")
            for i in range(n) for j in range(n) if i != j]
    return Environment(name="dense", assets=assets, relationships=rels)


def test_path_cap_is_global_and_reported_not_silent():
    from app.analysis import MAX_PATHS
    a = analyze(_dense_env(9))
    assert a["summary"]["paths_truncated"] is True
    assert len(a["paths"]) == MAX_PATHS                        # exactly the cap, never above it
    assert a["summary"]["attack_paths"] == MAX_PATHS


def test_small_environments_are_never_flagged_truncated(env):
    assert analyze(env)["summary"]["paths_truncated"] is False


def test_path_count_exactly_at_cap_is_not_reported_as_truncated(monkeypatch, env):
    import app.analysis as an
    monkeypatch.setattr(an, "MAX_PATHS", 20)                    # the demo has exactly 20 paths
    assert analyze(env)["summary"]["paths_truncated"] is False and analyze(env)["summary"]["attack_paths"] == 20
    monkeypatch.setattr(an, "MAX_PATHS", 19)
    s = analyze(env)["summary"]
    assert s["paths_truncated"] is True and s["attack_paths"] == 19


# ---------------------------------------------------------------- simulation
def test_simulation_never_mutates_baseline(env):
    snapshot = env.model_dump()
    simulate(env, [RemoveRelationship(relationship_id="r03"), ApplyMfa(asset_id="web-portal"),
                   ReducePrivilege(relationship_id="r06")])
    assert env.model_dump() == snapshot


def test_removing_excessive_permission_before_after(env):
    res = simulate(env, [RemoveRelationship(relationship_id="r03")])
    assert res["paths_eliminated"]                         # jump-host routes gone
    assert res["paths_remaining"]                          # residual risk remains (portal/app route)
    assert res["after"]["attack_paths"] < res["before"]["attack_paths"]
    assert res["paths_introduced"] == []
    assert res["risk_reduction_pct"] >= 0
    assert res["operational_impact"]["level"] == "low"     # no recorded legitimate use
    assert any(r["target"] == "db-customers" for r in res["residual_risks"])


def test_business_critical_removal_flags_high_impact_and_lost_access(env):
    res = simulate(env, [RemoveRelationship(relationship_id="r09")])
    assert res["operational_impact"]["level"] == "high"   # r09 is business critical
    # redundancy: svc-deploy still reaches the DB transitively via the backup trust, so no lost reach
    assert {"identity": "svc-deploy", "asset": "db-customers"} not in res["operational_impact"]["lost_access"]
    # removing HR's only route genuinely disrupts a legitimate identity
    res = simulate(env, [RemoveRelationship(relationship_id="r17")])
    assert {"identity": "emp-omar", "asset": "db-hr"} in res["operational_impact"]["lost_access"]


def test_mfa_mitigates_without_eliminating(env):
    res = simulate(env, [ApplyMfa(asset_id="web-portal")])
    assert res["paths_mitigated"] and not res["paths_eliminated"]
    assert res["after"]["total_path_score"] < res["before"]["total_path_score"]


def test_segmentation_and_privilege_reduction(env):
    assert simulate(env, [ApplySegmentation(asset_id="app-server")])["paths_eliminated"]
    assert simulate(env, [ReducePrivilege(relationship_id="r03")])["paths_mitigated"]


@pytest.mark.parametrize("action", [
    RemoveRelationship(relationship_id="nope"),
    ReducePrivilege(relationship_id="r05"),     # already minimal
    ApplyMfa(asset_id="db-hr"),                 # no login edges
    ApplySegmentation(asset_id="missing"),
])
def test_invalid_simulations_raise(env, action):
    with pytest.raises(SimulationError):
        simulate(env, [action])


def test_recommendations_are_simulated_and_need_approval(env):
    recs = recommend(env, analyze(env))
    assert recs and all(r["requires_human_approval"] for r in recs)
    assert all(r["path_score_reduction"] > 0 for r in recs)
    assert [r["priority"] for r in recs] == sorted((r["priority"] for r in recs), reverse=True)
    top = {r["id"] for r in recs[:3]}
    assert "rec-remove_relationship-r03" in top or "rec-reduce_privilege-r03" in top


# ---------------------------------------------------------------- validation
def test_model_rejects_bad_input():
    with pytest.raises(ValidationError):
        RemoveRelationship(relationship_id="<script>")
    with pytest.raises(ValidationError):
        SimulationRequest(actions=[])
    with pytest.raises(ValidationError):
        SimulationRequest(actions=[{"kind": "rm_rf", "relationship_id": "r1"}])
    env = build_demo_environment().model_dump()
    env["relationships"].append({**env["relationships"][0], "id": "dup"})
    with pytest.raises(ValidationError):
        Environment.model_validate(env)


# ---------------------------------------------------------------- API
def test_api_read_endpoints():
    assert client.get("/api/health").json()["synthetic_data"] is True
    assert client.get("/api/environment").json()["synthetic"] is True
    assert client.get("/api/analysis").json()["summary"]["attack_paths"] > 0
    assert client.get("/api/recommendations").json()
    r = client.get("/api/activity")
    assert r.json() and r.headers["x-content-type-options"] == "nosniff"


def test_api_simulate_ok_and_baseline_unchanged():
    before = client.get("/api/analysis").json()
    r = client.post("/api/simulate", json={"actions": [{"kind": "remove_relationship", "relationship_id": "r03"}]})
    assert r.status_code == 200 and r.json()["paths_eliminated"]
    assert client.get("/api/analysis").json() == before
    assert client.get("/api/activity").json()[0]["kind"] == "simulation_run"


@pytest.mark.parametrize("payload,code", [
    ({"actions": [{"kind": "remove_relationship", "relationship_id": "zzz"}]}, 422),
    ({"actions": [{"kind": "remove_relationship", "relationship_id": "x'; DROP TABLE"}]}, 422),
    ({"actions": []}, 422),
    ({"actions": [{"kind": "remove_relationship", "relationship_id": "r03", "extra": 1}]}, 422),
    ({}, 422),
])
def test_api_simulate_rejects_bad_requests(payload, code):
    assert client.post("/api/simulate", json=payload).status_code == code


def test_api_explain_separates_evidence_from_ai():
    pid = client.get("/api/analysis").json()["paths"][0]["id"]
    for lang in ("en", "ar"):
        r = client.post("/api/explain", json={"kind": "path", "id": pid, "lang": lang}).json()
        assert r["evidence"]["route"] and r["template_explanation"]
        assert r["ai_explanation"] is None and r["ai_status"] == "ai_disabled"  # AI is opt-in
    assert client.post("/api/explain", json={"kind": "path", "id": "p-nope"}).status_code == 404
    rec = client.get("/api/recommendations").json()[0]["id"]
    assert client.post("/api/explain", json={"kind": "recommendation", "id": rec}).status_code == 200
    assert client.post("/api/explain", json={"kind": "path", "id": "x", "lang": "fr"}).status_code == 422
