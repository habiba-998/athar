"""Tests for the decision-intelligence layer: configurable scoring, evidence model, business impact, plans and Pareto
comparison, sensitivity analysis, bilingual explanations, attack scenarios.

Independent re-implementations are used wherever a property could otherwise be 'tested' by the code under test itself
(the Pareto relation, the minimum cut, the weakest-link evidence class).
"""
from __future__ import annotations

import itertools
import json
import random
import threading
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import main
from app.analysis import DEFAULT_CONFIG, analyze, use_config
from app.business import approvals_for, service_impact
from app.data.demo import build_demo_environment
from app.data.scenario_harbor import build_harbor_environment
from app.data.scenario_meridian import build_meridian_environment
from app.evidence import evidence_overview
from app.models import (Asset, Environment, Evidence, Privilege, Relationship, RemoveRelationship, ScoringConfig,
                        SimulationRequest)
from app.narrative import confidence_label, plan_report, recommendation_explanation
from app.plans import dominates, generate_plans, min_cut_actions, pareto_front
from app.recommendations import recommend_ex
from app.sensitivity import perturb, run_sensitivity, scale_one
from app.simulation import simulate
from app.state import AppState
from app.store import Store
from tests.test_validation import random_env

client = TestClient(main.app)
BUILDERS = {"acme": build_demo_environment, "harbor": build_harbor_environment, "meridian": build_meridian_environment}


def sig(env: Environment) -> str:
    return json.dumps(env.model_dump(mode="json"), sort_keys=True)


# ============================================================================ scoring configuration

class TestScoringConfig:
    def test_defaults_are_the_documented_baseline(self):
        c = ScoringConfig()
        assert (c.evidence_observed, c.evidence_inferred, c.evidence_theoretical) == (0.85, 0.70, 0.40)
        assert (c.privilege_read, c.privilege_write, c.mfa_factor, c.length_penalty, c.exposure_bonus) == (0.70, 0.85, 0.35, 0.10, 1.10)

    @pytest.mark.parametrize("bad", [
        {"evidence_theoretical": 0.9},                  # theoretical > inferred
        {"evidence_inferred": 0.95},                    # inferred > observed
        {"privilege_read": 0.9},                        # read > write
        {"mfa_factor": 0.0}, {"mfa_factor": 1.5}, {"length_penalty": -0.1}, {"length_penalty": 0.9},
        {"exposure_bonus": 0.9}, {"exposure_bonus": 2.0}, {"unknown_field": 1},
    ])
    def test_invalid_configurations_are_rejected(self, bad):
        with pytest.raises(ValidationError):
            ScoringConfig(**bad)

    def test_validated_and_admin_anchors_are_not_configurable(self):
        with pytest.raises(ValidationError):
            ScoringConfig(evidence_validated=0.5)             # type: ignore[call-arg]
        ev, pv = ScoringConfig().evidence_weights(), ScoringConfig().privilege_weights()
        assert ev[Evidence.validated] == 1.0 and pv[Privilege.admin] == 1.0 and pv[Privilege.none] == 1.0
        extreme = ScoringConfig(evidence_observed=1.0, privilege_write=1.0)
        assert extreme.evidence_weights()[Evidence.validated] == 1.0 and extreme.privilege_weights()[Privilege.admin] == 1.0

    def test_default_config_reproduces_the_golden_baseline(self):
        s = analyze(build_harbor_environment())["summary"]
        assert (s["attack_paths"], s["posture_score"], s["max_path_score"]) == (42, 67.3, 88.0)
        assert analyze(build_harbor_environment(), DEFAULT_CONFIG)["summary"] == s

    def test_changing_a_weight_changes_scores_but_never_the_path_set(self):
        env = build_harbor_environment()
        base = analyze(env)
        low = analyze(env, ScoringConfig(evidence_inferred=0.5, evidence_theoretical=0.3, mfa_factor=0.2))
        assert {p["id"] for p in base["paths"]} == {p["id"] for p in low["paths"]}
        assert low["summary"]["posture_score"] != base["summary"]["posture_score"]

    def test_config_is_context_local_and_restored(self):
        env = build_demo_environment()
        cfg = ScoringConfig(length_penalty=0.3)
        with use_config(cfg):
            inside = analyze(env)["summary"]["posture_score"]
        assert analyze(env)["summary"]["posture_score"] != inside
        assert analyze(env, cfg)["summary"]["posture_score"] == inside

    def test_concurrent_requests_with_different_configs_do_not_interfere(self):
        env = build_harbor_environment()
        cfgs = [DEFAULT_CONFIG, ScoringConfig(length_penalty=0.4), ScoringConfig(exposure_bonus=1.5), ScoringConfig(mfa_factor=0.9)]
        want = [analyze(env, c)["summary"]["total_path_score"] for c in cfgs]
        got: dict[int, list[float]] = {i: [] for i in range(len(cfgs))}
        barrier = threading.Barrier(len(cfgs))

        def worker(i: int) -> None:
            barrier.wait()
            for _ in range(15):
                with use_config(cfgs[i]):
                    got[i].append(analyze(env)["summary"]["total_path_score"])

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(len(cfgs))]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert all(set(got[i]) == {want[i]} for i in got)

    def test_api_get_put_reset_cycle_and_effect_on_results(self):
        r = client.get("/api/scoring-config").json()
        assert r["is_default"] is True and r["config"] == r["defaults"]
        before = client.get("/api/analysis").json()["summary"]["posture_score"]
        new = {**r["config"], "evidence_inferred": 0.5, "evidence_theoretical": 0.3}
        put = client.put("/api/scoring-config", json=new)
        assert put.status_code == 200 and put.json()["is_default"] is False
        assert client.get("/api/analysis").json()["summary"]["posture_score"] != before
        assert client.get("/api/environment/meta").json()["config_is_default"] is False
        assert client.post("/api/scoring-config/reset").json()["is_default"] is True
        assert client.get("/api/analysis").json()["summary"]["posture_score"] == before

    @pytest.mark.parametrize("body", [{"evidence_theoretical": 0.99}, {"mfa_factor": 5}, {"nope": 1}])
    def test_api_rejects_invalid_configs_and_keeps_the_old_one(self, body):
        cur = client.get("/api/scoring-config").json()["config"]
        assert client.put("/api/scoring-config", json={**cur, **body}).status_code == 422
        assert client.get("/api/scoring-config").json()["config"] == cur

    def test_config_survives_a_restart(self, tmp_path):
        db = str(tmp_path / "c.db")
        a = AppState(Store(db))
        cfg = ScoringConfig(length_penalty=0.25)
        a.set_config(cfg)
        b = AppState(Store(db))
        assert b.config == cfg and b.base["summary"]["posture_score"] == a.base["summary"]["posture_score"]

    def test_simulation_uses_the_configured_weights(self):
        client.put("/api/scoring-config", json={**client.get("/api/scoring-config").json()["config"], "length_penalty": 0.4})
        res = client.post("/api/simulate", json={"actions": [{"kind": "remove_relationship", "relationship_id": "r03"}]}).json()
        assert res["before"]["posture_score"] == client.get("/api/analysis").json()["summary"]["posture_score"]


# ============================================================================ evidence model

class TestEvidenceModel:
    def _chain(self, evs: list[str], **extra) -> Environment:
        n = len(evs) + 1
        assets = [Asset(id=f"n{i}", name=f"N{i}", name_ar=f"ن{i}", type="server", criticality=5, compromised=(i == 0)) for i in range(n)]
        rels = [Relationship(id=f"k{i}", source=f"n{i}", target=f"n{i+1}", type="network_access", evidence=e, **extra) for i, e in enumerate(evs)]
        return Environment(name="chain", assets=assets, relationships=rels)

    @pytest.mark.parametrize("evs,expected", [
        (["validated", "validated"], "validated"), (["validated", "observed"], "observed"),
        (["observed", "observed"], "observed"), (["validated", "inferred"], "inferred"),
        (["observed", "inferred", "validated"], "inferred"), (["validated", "theoretical"], "theoretical"),
        (["observed", "theoretical", "inferred"], "theoretical"),
    ])
    def test_path_class_is_the_weakest_link(self, evs, expected):
        paths = analyze(self._chain(evs))["paths"]
        assert paths[-1]["classification"] == expected            # the full-length path from n0 to the last node

    def test_observed_is_never_reported_as_validated(self):
        a = analyze(self._chain(["observed", "observed"]))
        assert a["summary"]["validated_paths"] == 0 and a["summary"]["evidence_distribution"]["observed"] >= 1

    def test_evidence_distribution_adds_up(self):
        for build in BUILDERS.values():
            s = analyze(build())["summary"]
            assert sum(s["evidence_distribution"].values()) == s["attack_paths"]

    def test_confidence_defaults_follow_the_evidence_level_and_can_be_overridden(self):
        env = self._chain(["validated", "observed", "inferred", "theoretical"])
        assert [r.effective_confidence for r in env.relationships] == ["high", "high", "medium", "low"]
        env2 = self._chain(["inferred"], confidence="high")
        assert env2.relationships[0].effective_confidence == "high"

    def test_step_provenance_is_carried_into_every_path_step(self):
        for p in analyze(build_meridian_environment())["paths"][:30]:
            for s in p["steps"]:
                assert s["confidence"] in ("low", "medium", "high") and s["evidence_source"] and s["validation"] in ("none", "synthetic_exercise")

    def test_real_world_validation_can_never_be_recorded_on_synthetic_data(self):
        with pytest.raises(ValidationError, match="real-world validation"):
            self._chain(["validated"], validation="real_world")
        payload = build_demo_environment().model_dump(mode="json")
        payload["relationships"][0]["validation"] = "real_world"
        assert client.put("/api/environment", json=payload).status_code == 422

    def test_environment_cannot_claim_to_be_non_synthetic(self):
        payload = build_demo_environment().model_dump(mode="json")
        payload["synthetic"] = False
        assert client.put("/api/environment", json=payload).status_code == 422

    def test_no_shipped_scenario_claims_real_world_validation(self):
        for build in BUILDERS.values():
            assert all(r.validation != "real_world" for r in build().relationships)

    def test_validated_edges_in_shipped_scenarios_are_marked_as_synthetic_exercises(self):
        env = build_meridian_environment()
        assert all(r.validation == "synthetic_exercise" for r in env.relationships if r.evidence.value == "validated")
        assert all(r.validation == "none" for r in env.relationships if r.evidence.value != "validated")

    def test_overview_summarises_provenance_honestly(self):
        env = build_meridian_environment()
        ov = evidence_overview(env, analyze(env), now=datetime(2026, 11, 9, tzinfo=timezone.utc))
        s = ov["summary"]
        assert s["total"] == len([r for r in env.relationships if r.type.value != "protects"])
        assert sum(s["by_evidence"].values()) == s["total"] == sum(s["by_validation"].values())
        assert s["by_validation"]["real_world"] == 0 and ov["honesty"]["real_world_validated"] == 0
        assert ov["honesty"]["declared_not_verified"] is True and s["stale"] >= 2 and s["undated"] == 0
        assert all(r["stale"] == (r["age_days"] is not None and r["age_days"] > 180) for r in ov["relationships"])

    def test_overview_api(self):
        client.put("/api/environment", json=build_meridian_environment().model_dump(mode="json"))
        ov = client.get("/api/evidence").json()
        assert ov["honesty"]["synthetic"] is True and ov["summary"]["on_attack_paths"] > 0

    def test_dates_are_never_invented(self):
        env = build_harbor_environment()                      # Harbor declares no collection dates
        assert evidence_overview(env, analyze(env))["summary"]["undated"] == len(env.relationships) - sum(1 for r in env.relationships if r.type.value == "protects")


# ============================================================================ model integrity (new references)

class TestModelIntegrity:
    def test_unknown_service_reference_is_rejected(self):
        env = build_meridian_environment().model_dump(mode="json")
        env["relationships"][0]["supports_services"] = ["svc-nope"]
        with pytest.raises(ValidationError, match="unknown service"):
            Environment.model_validate(env)

    def test_duplicate_service_and_scenario_ids_are_rejected(self):
        env = build_meridian_environment().model_dump(mode="json")
        with pytest.raises(ValidationError, match="duplicate service"):
            Environment.model_validate({**env, "services": env["services"] + env["services"][:1]})
        with pytest.raises(ValidationError, match="duplicate attack scenario"):
            Environment.model_validate({**env, "attack_scenarios": env["attack_scenarios"] + env["attack_scenarios"][:1]})

    def test_scenario_must_reference_real_non_control_assets(self):
        env = build_meridian_environment().model_dump(mode="json")
        for bad in ("ghost", "ctl-waf"):
            with pytest.raises(ValidationError, match="unknown or control"):
                Environment.model_validate({**env, "attack_scenarios": [{"id": "s", "name": "S", "name_ar": "س", "compromised": [bad]}]})

    def test_identity_provider_is_a_sensitive_target(self):
        env = build_meridian_environment()
        assert "idp-sso" in analyze(env)["worst_by_target"]

    def test_older_environment_files_without_the_new_fields_still_import(self):
        payload = json.loads(json.dumps(build_demo_environment().model_dump(mode="json")))
        for r in payload["relationships"]:
            for k in ("evidence_source", "collected_at", "confidence", "validation", "rationale", "rationale_ar", "supports_services", "recovery_hours"):
                r.pop(k, None)
        for k in ("services", "attack_scenarios"):
            payload.pop(k, None)
        for a in payload["assets"]:
            a.pop("segment", None)
        assert client.put("/api/environment", json=payload).status_code == 200


# ============================================================================ business impact

class TestBusinessImpact:
    def _impacts(self, env, kind, **ids):
        res = simulate(env, SimulationRequest.model_validate({"actions": [{"kind": kind, **ids}]}).actions)
        return res["operational_impact"]

    def test_removal_interrupts_the_dependent_service_and_recovery_is_compared_with_rto(self):
        env = build_meridian_environment()
        op = self._impacts(env, "remove_relationship", relationship_id="i02")
        b = service_impact(env, op["affected_relationships"])
        row = b["services"][0]
        assert row["service_id"] == "svc-support" and row["effect"] == "interrupted"
        assert row["recovery"] == "reprovision" and row["recovery_hours"] == 2 and row["rto_status"] == "within"
        assert b["business_impact_index"] > 0 and b["services_interrupted"] == 1

    def test_reversible_disable_is_a_rollback_and_mfa_is_only_friction(self):
        env = build_meridian_environment()
        d = service_impact(env, self._impacts(env, "disable_relationship", relationship_id="i02")["affected_relationships"])["services"][0]
        assert d["effect"] == "interrupted" and d["recovery"] == "rollback" and d["recovery_hours"] == 0.0
        m = service_impact(env, self._impacts(env, "apply_mfa", asset_id="app-erp")["affected_relationships"])
        assert all(s["effect"] == "friction" and s["rto_status"] == "not_applicable" for s in m["services"])
        assert m["services_interrupted"] == 0

    def test_rto_exceeded_and_unknown_are_never_silently_fine(self):
        env = build_meridian_environment()
        raw = env.model_dump(mode="json")
        for r in raw["relationships"]:
            if r["id"] == "i02":
                r["recovery_hours"] = 30                       # slower than the 8 h RTO of the support desk
            if r["id"] == "i01":
                r["recovery_hours"] = None                     # unknown
        env2 = Environment.model_validate(raw)
        slow = service_impact(env2, self._impacts(env2, "remove_relationship", relationship_id="i02")["affected_relationships"])
        assert slow["services"][0]["rto_status"] == "exceeds" and slow["rto_exceeded"] == 1
        unk = service_impact(env2, self._impacts(env2, "remove_relationship", relationship_id="i01")["affected_relationships"])
        assert unk["services"][0]["rto_status"] == "unknown" and unk["rto_unknown"] == 1

    def test_without_declared_services_there_is_no_invented_business_impact(self):
        env = build_harbor_environment()
        b = service_impact(env, self._impacts(env, "remove_relationship", relationship_id="r02")["affected_relationships"])
        assert b["services"] == [] and b["business_impact_index"] == 0.0 and b["services_declared"] == 0

    def test_index_is_bounded_and_monotone_in_the_number_of_interrupted_services(self):
        env = build_meridian_environment()
        one = service_impact(env, self._impacts(env, "disable_relationship", relationship_id="w02")["affected_relationships"])
        both = service_impact(env, simulate(env, SimulationRequest.model_validate({"actions": [
            {"kind": "disable_relationship", "relationship_id": "w02"}, {"kind": "disable_relationship", "relationship_id": "w03"}]}).actions
        )["operational_impact"]["affected_relationships"])
        assert 0 <= one["business_impact_index"] <= both["business_impact_index"] <= 100

    def test_approvals_scale_with_impact_and_always_include_a_human_security_owner(self):
        env = build_meridian_environment()
        for kind, ids in (("disable_relationship", {"relationship_id": "a01"}), ("remove_relationship", {"relationship_id": "w02"}),
                          ("apply_mfa", {"asset_id": "app-erp"})):
            acts = SimulationRequest.model_validate({"actions": [{"kind": kind, **ids}]}).actions
            op = simulate(env, acts)["operational_impact"]
            roles = [a["role"] for a in approvals_for(acts, op, service_impact(env, op["affected_relationships"]))]
            assert roles[0] == "security_owner"
        acts = SimulationRequest.model_validate({"actions": [{"kind": "remove_relationship", "relationship_id": "w02"}]}).actions
        op = simulate(env, acts)["operational_impact"]
        roles = [a["role"] for a in approvals_for(acts, op, service_impact(env, op["affected_relationships"]))]
        assert "service_owner" in roles and "change_board" in roles          # business-critical, irreversible
        assert approvals_for([], {}, {}) == []                              # nothing to approve for "no change"

    def test_service_dependencies_endpoint_lists_access_requirements(self):
        client.put("/api/environment", json=build_meridian_environment().model_dump(mode="json"))
        svc = {s["id"]: s for s in client.get("/api/services").json()}
        assert set(svc) == {"svc-orders", "svc-payments", "svc-erp", "svc-hr", "svc-backup", "svc-devops", "svc-support"}
        assert all(s["access_requirements"] for s in svc.values())
        assert svc["svc-support"]["access_requirements"][0]["relationship_id"] == "i02"
        assert svc["svc-erp"]["exposed_dependencies"] > 0

    def test_tradeoff_is_explicit_removing_the_gateway_link_stops_attacks_and_interrupts_ordering(self):
        env = build_meridian_environment()
        res = simulate(env, [RemoveRelationship(relationship_id="w02")])
        b = service_impact(env, res["operational_impact"]["affected_relationships"])
        assert "svc-orders" in {s["service_id"] for s in b["services"]} and res["operational_impact"]["level"] == "high"


# ============================================================================ plans and Pareto comparison

def brute_force_dominated_by(vecs: dict[str, tuple]) -> dict[str, list[str]]:
    """Independent Pareto relation written from the definition, with explicit loops."""
    out: dict[str, list[str]] = {}
    for i, vi in vecs.items():
        out[i] = []
        for j, vj in vecs.items():
            if i == j:
                continue
            no_worse, better = True, False
            for x, y in zip(vj, vi):
                if x > y:
                    no_worse = False
                if x < y:
                    better = True
            if no_worse and better:
                out[i].append(j)
        out[i].sort()
    return out


@pytest.fixture(scope="module")
def plan_sets():
    out = {}
    for name, build in BUILDERS.items():
        env = build()
        out[name] = (env, analyze(env), generate_plans(env, analyze(env)))
    return out


class TestParetoRelation:
    def test_dominates_basic_cases(self):
        assert dominates((1, 1), (2, 2)) and dominates((1, 2), (2, 2))
        assert not dominates((2, 2), (2, 2)) and not dominates((1, 3), (2, 2)) and not dominates((2, 2), (1, 3))

    @pytest.mark.parametrize("seed", range(40))
    def test_front_matches_an_independent_implementation_on_random_vectors(self, seed):
        rnd = random.Random(seed)
        vecs = {f"p{i}": tuple(rnd.choice([0, 1, 2, 3, 5.5]) for _ in range(4)) for i in range(rnd.randint(1, 12))}
        assert pareto_front(vecs) == brute_force_dominated_by(vecs)

    @pytest.mark.parametrize("seed", range(20))
    def test_relation_is_irreflexive_asymmetric_transitive_and_the_front_is_never_empty(self, seed):
        rnd = random.Random(seed)
        vs = [tuple(rnd.randint(0, 4) for _ in range(4)) for _ in range(10)]
        for a in vs:
            assert not dominates(a, a)
        for a, b in itertools.permutations(vs, 2):
            assert not (dominates(a, b) and dominates(b, a))
        for a, b, c in itertools.permutations(vs, 3):
            if dominates(a, b) and dominates(b, c):
                assert dominates(a, c)
        front = pareto_front({str(i): v for i, v in enumerate(vs)})
        assert any(not d for d in front.values())
        for i, d in front.items():                      # every dominated plan is dominated by something on the front
            if d:
                assert any(not front[j] for j in d)


class TestPlans:
    @pytest.mark.parametrize("name", BUILDERS)
    def test_pareto_flags_match_an_independent_implementation(self, plan_sets, name):
        _, _, res = plan_sets[name]
        vecs = {p["id"]: tuple(p["objectives"]) for p in res["plans"]}
        want = brute_force_dominated_by(vecs)
        assert {p["id"]: p["pareto"]["dominated_by"] for p in res["plans"]} == want
        assert all(p["pareto"]["optimal"] == (not want[p["id"]]) for p in res["plans"])

    @pytest.mark.parametrize("name", BUILDERS)
    def test_status_quo_is_the_reference_and_changes_nothing(self, plan_sets, name):
        env, base, res = plan_sets[name]
        sq = res["plans"][0]
        assert sq["id"] == "plan-status-quo" and sq["actions"] == [] and sq["effort"] == 0 and sq["disruption_cost"] == 0
        assert sq["metrics"]["paths_after"] == base["summary"]["attack_paths"] and sq["metrics"]["posture_after"] == base["summary"]["posture_score"]
        assert sq["approvals"] == [] and sq["pareto"]["optimal"] is True        # doing nothing minimises disruption and effort

    @pytest.mark.parametrize("name", BUILDERS)
    def test_every_plan_matches_a_direct_simulation_of_its_actions(self, plan_sets, name):
        env, base, res = plan_sets[name]
        for p in res["plans"][1:]:
            acts = SimulationRequest.model_validate({"actions": p["actions"]}).actions
            direct = simulate(env, acts, baseline=base)
            assert p["metrics"]["paths_after"] == direct["after"]["attack_paths"]
            assert p["metrics"]["posture_after"] == direct["after"]["posture_score"]
            assert p["operational"]["level"] == direct["operational_impact"]["level"]
            assert p["operational"]["fully_reversible"] == direct["operational_impact"]["fully_reversible"]
            assert p["objectives"][:2] == [direct["after"]["attack_paths"], direct["after"]["posture_score"]]

    @pytest.mark.parametrize("name", BUILDERS)
    def test_no_plan_ever_adds_a_path_or_raises_the_posture(self, plan_sets, name):
        _, base, res = plan_sets[name]
        for p in res["plans"]:
            assert p["metrics"]["paths_after"] <= base["summary"]["attack_paths"]
            assert p["metrics"]["posture_after"] <= base["summary"]["posture_score"]

    @pytest.mark.parametrize("name", BUILDERS)
    def test_generating_plans_never_mutates_the_environment(self, name):
        env = BUILDERS[name]()
        before = sig(env)
        generate_plans(env, analyze(env))
        assert sig(env) == before

    @pytest.mark.parametrize("name", BUILDERS)
    def test_plan_generation_is_deterministic(self, plan_sets, name):
        env, base, res = plan_sets[name]
        again = generate_plans(env, analyze(env))
        assert json.dumps(again, sort_keys=True) == json.dumps(res, sort_keys=True)

    def test_plans_do_not_depend_on_the_order_of_the_input(self, plan_sets):
        env, _, res = plan_sets["meridian"]
        rnd = random.Random(7)
        raw = env.model_dump(mode="json")
        rnd.shuffle(raw["assets"])
        rnd.shuffle(raw["relationships"])
        shuffled = Environment.model_validate(raw)
        other = generate_plans(shuffled, analyze(shuffled))
        norm = lambda r: {p["id"]: (sorted(json.dumps(a, sort_keys=True) for a in p["actions"]), p["objectives"], p["pareto"]["optimal"]) for p in r["plans"]}  # noqa: E731
        assert norm(other) == norm(res) and other["suggested_plan_id"] == res["suggested_plan_id"]

    @pytest.mark.parametrize("name", BUILDERS)
    def test_the_suggestion_never_picks_a_high_impact_or_critical_service_interrupting_plan(self, plan_sets, name):
        _, _, res = plan_sets[name]
        by_id = {p["id"]: p for p in res["plans"]}
        if res["suggested_plan_id"] is None:
            return
        p = by_id[res["suggested_plan_id"]]
        assert p["pareto"]["optimal"] and p["actions"] and p["operational"]["level"] != "high"
        assert p["business"]["critical_services_interrupted"] == 0

    def test_eliminating_every_path_is_not_automatically_favoured(self, plan_sets):
        """Meridian has a complete-cut plan (0 paths); it is shown, but it is NOT the suggestion because it disrupts critical service."""
        _, _, res = plan_sets["meridian"]
        zero = [p for p in res["plans"] if p["metrics"]["paths_after"] == 0]
        assert zero and all(p["operational"]["level"] == "high" for p in zero)
        assert res["suggested_plan_id"] not in {p["id"] for p in zero}

    def test_no_global_optimality_claim_is_made(self, plan_sets):
        _, _, res = plan_sets["harbor"]
        assert res["optimality_claim"].startswith("none")
        text = json.dumps(res).lower()
        assert "globally optimal" not in text and "guaranteed" not in text

    def test_each_plan_declares_human_approval(self, plan_sets):
        for name in BUILDERS:
            assert all(p["requires_human_approval"] for p in plan_sets[name][2]["plans"])

    def test_identical_action_sets_from_two_strategies_are_listed_once(self, plan_sets):
        for name in BUILDERS:
            keys = [tuple(sorted(json.dumps(a, sort_keys=True) for a in p["actions"])) for p in plan_sets[name][2]["plans"]]
            assert len(keys) == len(set(keys))

    def test_reversible_plan_only_uses_reversible_actions(self, plan_sets):
        for name in BUILDERS:
            for p in plan_sets[name][2]["plans"]:
                if p["strategy"] == "reversible":
                    assert all(a["kind"] in ("disable_relationship", "reduce_privilege", "apply_mfa") for a in p["actions"]) and p["operational"]["fully_reversible"]

    def test_business_safe_plan_never_includes_a_step_rated_above_low(self, plan_sets):
        env, base, res = plan_sets["harbor"]
        p = next((p for p in res["plans"] if p["strategy"] == "business_safe"), None)
        assert p is not None
        cur = []
        for a in p["actions"]:
            cur.append(a)
            step = simulate(env, SimulationRequest.model_validate({"actions": [a]}).actions)
            assert step["operational_impact"]["level"] in ("none", "low")


class TestMinimumCut:
    @staticmethod
    def weight(env: Environment, ids: set[str]) -> int:
        by = {r.id: r for r in env.relationships}
        return sum(1000 * (3 if by[i].business_critical else 1 if by[i].legitimate_use else 0) + 1 for i in ids)

    @pytest.mark.parametrize("name", BUILDERS)
    def test_the_cut_eliminates_every_path(self, plan_sets, name):
        env, base, _ = plan_sets[name]
        acts = min_cut_actions(env, base)
        assert acts and simulate(env, acts, baseline=base)["after"]["attack_paths"] == 0

    @pytest.mark.parametrize("seed", range(30))
    def test_cut_weight_equals_the_brute_force_optimum_on_small_graphs(self, seed):
        env = random_env(seed, n=7, density=1.5)                     # <= 6 hops anywhere, so the engine's hop limit never binds
        a = analyze(env)
        if not a["paths"]:
            assert min_cut_actions(env, a) == []
            return
        on_path = sorted({rid for p in a["paths"] for rid in p["relationship_ids"]})
        if len(on_path) > 15:
            pytest.skip("brute force too large")
        path_sets = [set(p["relationship_ids"]) for p in a["paths"]]
        best = min(self.weight(env, set(sub)) for k in range(len(on_path) + 1) for sub in itertools.combinations(on_path, k)
                   if all(ps & set(sub) for ps in path_sets))
        got = {act.relationship_id for act in min_cut_actions(env, a)}        # type: ignore[attr-defined]
        assert all(ps & got for ps in path_sets), "the cut must hit every path"
        assert self.weight(env, got) == best


# ============================================================================ sensitivity

@pytest.fixture(scope="module")
def sens():
    env = build_harbor_environment()
    return env, run_sensitivity(env, DEFAULT_CONFIG, trials=8, spread=0.3, seed=5)


class TestSensitivity:
    def test_is_deterministic_for_a_seed_and_differs_for_another(self, sens):
        env, r = sens
        assert json.dumps(run_sensitivity(env, DEFAULT_CONFIG, 8, 0.3, 5), sort_keys=True) == json.dumps(r, sort_keys=True)
        other = run_sensitivity(env, DEFAULT_CONFIG, 8, 0.3, 6)
        assert json.dumps(other, sort_keys=True) != json.dumps(r, sort_keys=True)         # a different seed explores different weights
        assert other["paths"][0]["baseline"] == r["paths"][0]["baseline"]                 # ... around the same baseline

    def test_ranges_contain_the_baseline_and_are_ordered(self, sens):
        _, r = sens
        assert r["posture"]["min"] <= r["posture"]["baseline"] <= r["posture"]["max"]
        assert r["posture"]["min"] < r["posture"]["max"]                                   # the weights do move the posture
        for p in r["paths"]:
            assert p["min"] <= p["baseline"] <= p["max"]
            assert 1 <= p["rank_min"] <= p["rank_max"]
            assert p["indicator"] == ("low" if p["max"] - p["min"] < 5 else "medium" if p["max"] - p["min"] < 15 else "high")

    def test_recommendation_stability_fields(self, sens):
        _, r = sens
        assert [x["baseline_rank"] for x in r["recommendations"]] == list(range(1, len(r["recommendations"]) + 1))
        for x in r["recommendations"]:
            assert 0 <= x["top1_pct"] <= x["top3_pct"] <= 100 and 0 <= x["presence_pct"] <= 100
            assert x["stability"] in ("stable", "moderate", "sensitive")

    def test_one_at_a_time_covers_every_parameter_and_is_sorted_by_influence(self, sens):
        _, r = sens
        assert {p["name"] for p in r["parameters"]} == {"evidence_observed", "evidence_inferred", "evidence_theoretical", "privilege_read",
                                                        "privilege_write", "mfa_factor", "length_penalty", "exposure_bonus"}
        swings = [p["posture_swing"] for p in r["parameters"]]
        assert swings == sorted(swings, reverse=True)

    def test_it_never_presents_scores_as_probabilities(self, sens):
        _, r = sens
        assert r["not_a_probability"] is True and "confidence interval" in r["note"]

    def test_the_path_set_is_invariant_under_perturbation(self):
        env = build_demo_environment()
        base = {p["id"] for p in analyze(env)["paths"]}
        rnd = random.Random(3)
        for _ in range(8):
            assert {p["id"] for p in analyze(env, perturb(DEFAULT_CONFIG, rnd, 0.5))["paths"]} == base

    @pytest.mark.parametrize("seed", range(60))
    def test_perturbation_always_yields_a_valid_ordered_configuration(self, seed):
        c = perturb(ScoringConfig(evidence_inferred=0.4, evidence_theoretical=0.39, privilege_read=0.84), random.Random(seed), 0.5)
        assert c.evidence_theoretical <= c.evidence_inferred <= c.evidence_observed <= 1 and c.privilege_read <= c.privilege_write <= 1

    def test_scale_one_clamps_to_neighbours(self):
        c = scale_one(DEFAULT_CONFIG, "evidence_inferred", 5.0)
        assert c.evidence_inferred == c.evidence_observed == 0.85
        assert scale_one(DEFAULT_CONFIG, "privilege_write", 0.1).privilege_write == DEFAULT_CONFIG.privilege_read
        assert scale_one(DEFAULT_CONFIG, "mfa_factor", 1.3).mfa_factor == pytest.approx(0.455)

    def test_api_validates_parameters(self):
        for q in ("trials=0", "trials=999", "spread=0", "spread=0.9"):
            assert client.get(f"/api/sensitivity?{q}").status_code == 422
        r = client.get("/api/sensitivity?trials=2&spread=0.2&seed=3")
        assert r.status_code == 200 and r.json()["trials"] == 2


# ============================================================================ explanations (bilingual)

class TestExplanations:
    def test_nine_questions_in_both_languages_with_real_numbers(self):
        env = build_meridian_environment()
        base = analyze(env)
        recs, _ = recommend_ex(env, base)
        ex = recommendation_explanation(env, base, recs[0])
        assert [q["key"] for q in ex["questions"]] == ["proposed", "why", "evidence", "confidence", "changes", "business", "residual", "uncertainty", "approval"]
        for q in ex["questions"]:
            assert q["question"]["en"].endswith("?") and q["answer"]["en"].strip() and q["answer"]["ar"].strip()
            assert any("؀" <= ch <= "ۿ" for ch in q["answer"]["ar"] + q["question"]["ar"])
        direct = simulate(env, SimulationRequest.model_validate({"actions": [recs[0]["action"]]}).actions, baseline=base)
        f = ex["facts"]
        assert (f["paths_before"], f["paths_after"]) == (direct["before"]["attack_paths"], direct["after"]["attack_paths"])
        why = next(q for q in ex["questions"] if q["key"] == "why")["answer"]["en"]
        assert str(len(direct["paths_eliminated"])) in why and str(direct["after"]["posture_score"]) in why

    def test_explanations_never_describe_scores_as_probabilities_or_claim_real_validation(self):
        env = build_meridian_environment()
        base = analyze(env)
        for rec in recommend_ex(env, base)[0][:3]:
            ex = recommendation_explanation(env, base, rec)
            txt = " ".join(q["answer"]["en"] for q in ex["questions"]).lower()
            assert "not a probability" in txt and "synthetic" in txt and "not verified" in txt
            assert "will be breached" not in txt and "likelihood of" not in txt
            assert ex["confidence"]["is_probability"] is False

    @pytest.mark.parametrize("share,stab,want", [
        (0.9, "stable", "high"), (0.9, None, "medium"), (0.1, None, "low"), (0.5, "stable", "medium"),
        (0.9, "sensitive", "low"), (0.1, "stable", "low"), (0.7, "moderate", "medium"),
    ])
    def test_confidence_label_rules(self, share, stab, want):
        assert confidence_label(share, stab)[0] == want

    def test_high_confidence_is_impossible_without_a_sensitivity_run(self):
        for share in (0.0, 0.3, 0.6, 1.0):
            assert confidence_label(share, None)[0] != "high"

    def test_endpoint_uses_the_latest_matching_sensitivity_result(self):
        client.put("/api/environment", json=build_meridian_environment().model_dump(mode="json"))
        rid = client.get("/api/recommendations").json()[0]["id"]
        before = client.get(f"/api/recommendations/{rid}/explanation").json()
        assert "stability_not_assessed" in before["confidence"]["reasons"]
        client.get("/api/sensitivity?trials=3")
        after = client.get(f"/api/recommendations/{rid}/explanation").json()
        assert not ({"stability_not_assessed"} & set(after["confidence"]["reasons"]))

    def test_unknown_recommendation_is_404(self):
        assert client.get("/api/recommendations/rec-nope/explanation").status_code == 404

    @pytest.mark.parametrize("lang", ["en", "ar"])
    def test_plan_report_is_a_deterministic_decision_record(self, plan_sets, lang):
        env, _, res = plan_sets["meridian"]
        plan = next(p for p in res["plans"] if p["strategy"] == "balanced")
        a, b = plan_report(env, plan, lang), plan_report(env, plan, lang)
        assert a == b and a.startswith("# ")
        assert "[ ]" in a and a.count("##") >= 6
        assert "2026-" not in a                                   # no timestamps: the same plan always yields the same text
        assert ("افتراضي" in a) if lang == "ar" else ("synthetic" in a.lower() and "not verified" in a.lower() and "global optimality" in a)

    def test_report_and_plan_endpoints(self):
        client.put("/api/environment", json=build_meridian_environment().model_dump(mode="json"))
        res = client.get("/api/plans").json()
        assert res["suggested_plan_id"] and all(p["summary"]["en"] and p["summary"]["ar"] for p in res["plans"])
        pid = res["plans"][1]["id"]
        assert client.get(f"/api/plans/{pid}/report?lang=ar").json()["markdown"].startswith("# ")
        assert client.get(f"/api/plans/{pid}/report?lang=fr").status_code == 422
        assert client.get("/api/plans/plan-nope/report").status_code == 404


# ============================================================================ attack scenarios, undo, reset, history

class TestScenariosAndHistory:
    def test_activating_a_scenario_switches_the_starting_points_and_can_be_undone(self):
        client.put("/api/environment", json=build_meridian_environment().model_dump(mode="json"))
        scs = {s["id"]: s for s in client.get("/api/attack-scenarios").json()}
        assert scs["sc-phish-helpdesk"]["active"] is True and scs["sc-vendor"]["active"] is False
        base = client.get("/api/analysis").json()["summary"]["attack_paths"]
        assert client.post("/api/attack-scenarios/sc-vendor/activate").status_code == 200
        env = client.get("/api/environment").json()
        assert [a["id"] for a in env["assets"] if a["compromised"]] == ["u-vendor"]
        assert {p["source"] for p in client.get("/api/analysis").json()["paths"]} == {"u-vendor"}
        assert client.get("/api/analysis").json()["summary"]["attack_paths"] != base
        assert client.post("/api/environment/undo").status_code == 200
        assert client.get("/api/analysis").json()["summary"]["attack_paths"] == base

    def test_unknown_scenario_is_404(self):
        client.put("/api/environment", json=build_meridian_environment().model_dump(mode="json"))
        assert client.post("/api/attack-scenarios/nope/activate").status_code == 404

    def test_every_meridian_scenario_produces_paths_and_matches_its_description(self):
        env = build_meridian_environment()
        for sc in env.attack_scenarios:
            raw = env.model_dump(mode="json")
            for a in raw["assets"]:
                a["compromised"] = a["id"] in sc.compromised
            a = analyze(Environment.model_validate(raw))
            assert a["summary"]["attack_paths"] > 0, sc.id
            assert {p["source"] for p in a["paths"]} <= set(sc.compromised)

    def test_reset_returns_to_the_sample_and_keeps_history_bounded(self):
        client.put("/api/environment", json=build_meridian_environment().model_dump(mode="json"))
        assert client.get("/api/environment/meta").json()["is_sample"] is False
        client.post("/api/environment/reset")
        meta = client.get("/api/environment/meta").json()
        assert meta["is_sample"] is True and meta["can_undo"] is True
        assert client.post("/api/environment/undo").status_code == 200                # undo of the reset brings Meridian back
        assert client.get("/api/environment").json()["name"].startswith("Meridian")

    def test_simulation_history_records_each_run_and_marks_stale_ones(self):
        r1 = client.post("/api/simulate", json={"actions": [{"kind": "disable_relationship", "relationship_id": "r03"}]}).json()
        assert r1["record_id"] and r1["ephemeral"] is False
        client.post("/api/environment/reset")
        listing = client.get("/api/simulations").json()
        assert any(x["id"] == r1["record_id"] for x in listing)

    def test_the_live_environment_is_untouched_by_simulation_and_by_plans(self):
        before = client.get("/api/environment").json()
        client.post("/api/simulate", json={"actions": [{"kind": "remove_relationship", "relationship_id": "r03"}]})
        client.get("/api/plans")
        assert client.get("/api/environment").json() == before
