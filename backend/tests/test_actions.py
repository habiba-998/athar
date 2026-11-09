"""Every defensive action: isolation, effect, impact and error handling."""
import pytest
from fastapi.testclient import TestClient

from app import main
from app.analysis import analyze
from app.data.demo import build_demo_environment
from app.models import (ApplyMfa, ApplySegmentation, DisableRelationship, ReducePrivilege, RemoveRelationship)
from app.simulation import SimulationError, apply_actions, simulate

client = TestClient(main.app)

ALL_ACTIONS = [
    RemoveRelationship(relationship_id="r03"),
    DisableRelationship(relationship_id="r03"),
    ReducePrivilege(relationship_id="r03"),
    ApplyMfa(asset_id="web-portal"),
    ApplySegmentation(asset_id="app-server"),
]


@pytest.fixture()
def env():
    return build_demo_environment()


@pytest.mark.parametrize("action", ALL_ACTIONS, ids=lambda a: a.kind)
def test_each_action_runs_on_an_isolated_copy(env, action):
    before = env.model_dump()
    sim_env, _ = apply_actions(env, [action])
    assert env.model_dump() == before            # input untouched
    assert sim_env is not env and sim_env.model_dump() != before   # the copy did change
    res = simulate(env, [action])
    assert env.model_dump() == before
    assert res["paths_introduced"] == []
    assert res["after"]["total_path_score"] < res["before"]["total_path_score"]


@pytest.mark.parametrize("action", ALL_ACTIONS, ids=lambda a: a.kind)
def test_each_action_via_api_leaves_server_state_untouched(action):
    h, env_json, analysis = main.state.hash, client.get("/api/environment").json(), client.get("/api/analysis").json()
    r = client.post("/api/simulate", json={"actions": [action.model_dump()]})
    assert r.status_code == 200
    assert main.state.hash == h
    assert client.get("/api/environment").json() == env_json
    assert client.get("/api/analysis").json() == analysis


def test_remove_vs_disable_are_distinct(env):
    removed, _ = apply_actions(env, [RemoveRelationship(relationship_id="r03")])
    disabled, _ = apply_actions(env, [DisableRelationship(relationship_id="r03")])
    assert all(r.id != "r03" for r in removed.relationships)                 # gone
    kept = next(r for r in disabled.relationships if r.id == "r03")          # still present, flagged
    assert kept.disabled is True
    # same attack-surface effect...
    assert {p["id"] for p in analyze(removed)["paths"]} == {p["id"] for p in analyze(disabled)["paths"]}
    # ...but different reversibility reporting
    rem = simulate(env, [RemoveRelationship(relationship_id="r03")])["operational_impact"]
    dis = simulate(env, [DisableRelationship(relationship_id="r03")])["operational_impact"]
    assert rem["fully_reversible"] is False and rem["affected_relationships"][0]["reversible"] is False
    assert dis["fully_reversible"] is True and dis["affected_relationships"][0]["reversible"] is True


def test_disabled_relationship_is_not_traversable_and_not_a_finding(env):
    sim_env, _ = apply_actions(env, [DisableRelationship(relationship_id="r03")])
    a = analyze(sim_env)
    assert all("r03" not in p["relationship_ids"] for p in a["paths"])
    assert all(f.get("relationship_id") != "r03" for f in a["findings"])


def test_disable_twice_is_rejected(env):
    with pytest.raises(SimulationError):
        simulate(env, [DisableRelationship(relationship_id="r03"), DisableRelationship(relationship_id="r03")])


def test_remove_then_remove_same_edge_is_rejected(env):
    with pytest.raises(SimulationError):
        simulate(env, [RemoveRelationship(relationship_id="r03"), RemoveRelationship(relationship_id="r03")])


def test_exact_affected_assets_for_removal(env):
    imp = simulate(env, [RemoveRelationship(relationship_id="r03")])["operational_impact"]
    assert imp["affected_assets"] == ["emp-sara", "jump-host"]
    assert [i["relationship_id"] for i in imp["affected_relationships"]] == ["r03"]
    assert imp["lost_access"] == [] and imp["level"] == "low"


def test_exact_affected_assets_for_segmentation(env):
    imp = simulate(env, [ApplySegmentation(asset_id="app-server")])["operational_impact"]
    # network_access edges into app-server are r08 (web-portal) and r18 (jump-host)
    assert {i["relationship_id"] for i in imp["affected_relationships"]} == {"r08", "r18"}
    assert set(imp["affected_assets"]) >= {"web-portal", "jump-host", "app-server"}
    assert imp["level"] == "high"  # r08 is business critical


def test_mfa_on_asset_without_login_edges_raises(env):
    with pytest.raises(SimulationError):
        simulate(env, [ApplyMfa(asset_id="app-server")])


def test_mfa_flags_only_target_edges(env):
    sim_env, impacts = apply_actions(env, [ApplyMfa(asset_id="web-portal")])
    flagged = {r.id for r in sim_env.relationships if r.mfa_required}
    assert flagged == {"r01"} == {i["relationship_id"] for i in impacts}
    assert all(i["reversible"] for i in impacts)


def test_reduce_privilege_downgrades_only_that_edge(env):
    sim_env, _ = apply_actions(env, [ReducePrivilege(relationship_id="r03")])
    changed = {r.id for r, o in zip(sim_env.relationships, env.relationships) if r.privilege != o.privilege}
    assert changed == {"r03"}
    assert next(r for r in sim_env.relationships if r.id == "r03").privilege.value == "read"


def test_actions_compose_in_order(env):
    res = simulate(env, [RemoveRelationship(relationship_id="r03"), ApplyMfa(asset_id="web-portal"),
                         ReducePrivilege(relationship_id="r06")])
    single = simulate(env, [RemoveRelationship(relationship_id="r03")])
    assert res["after"]["total_path_score"] < single["after"]["total_path_score"]
    assert [i["action"] for i in res["operational_impact"]["affected_relationships"]] == [
        "remove_relationship", "apply_mfa", "reduce_privilege"]


def test_business_critical_disable_is_high_impact_but_reversible(env):
    imp = simulate(env, [DisableRelationship(relationship_id="r09")])["operational_impact"]
    assert imp["level"] == "high" and imp["fully_reversible"] is True


def test_f3_privilege_reduction_on_a_business_critical_relationship_is_not_downgraded_to_medium(env):
    """Audit finding F3: write->read on an order-processing link can break it, so it must stay 'high' impact.
    MFA, by contrast, keeps the access (users enrol), so it is rated one step lower."""
    r09 = next(r for r in env.relationships if r.id == "r09")
    assert r09.business_critical and r09.privilege.value == "write"
    assert simulate(env, [ReducePrivilege(relationship_id="r09")])["operational_impact"]["level"] == "high"
    assert simulate(env, [ApplyMfa(asset_id="web-portal")])["operational_impact"]["level"] == "medium"   # r01 is business critical
    assert simulate(env, [RemoveRelationship(relationship_id="r09")])["operational_impact"]["level"] == "high"


def test_disable_is_offered_as_a_recommendation_with_lower_cost(env):
    recs = {r["id"]: r for r in main.state.recs}
    # r04 has a recorded legitimate use, so both options are offered; disable is cheaper (reversible)
    rm, dis = recs.get("rec-remove_relationship-r04"), recs.get("rec-disable_relationship-r04")
    all_recs = {r["id"] for r in main.state.recs}
    assert any(i.startswith("rec-disable_relationship-") for i in all_recs)
    if rm and dis:
        assert dis["disruption_cost"] < rm["disruption_cost"]


def test_api_rejects_disable_of_unknown_relationship():
    r = client.post("/api/simulate", json={"actions": [{"kind": "disable_relationship", "relationship_id": "zzz"}]})
    assert r.status_code == 422
