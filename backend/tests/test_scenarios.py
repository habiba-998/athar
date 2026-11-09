"""The shipped synthetic scenarios: they must match their builders, import cleanly, agree with the independent oracle,
be deterministic, and keep producing the documented results (golden values, pinned from real runs)."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.analysis import analyze
from app.data.demo import build_demo_environment
from app.data.scenario_harbor import build_harbor_environment
from app.data.scenario_meridian import build_meridian_environment
from app.models import DisableRelationship, Environment, RemoveRelationship
from app.recommendations import recommend_ex
from app.simulation import simulate
from tests.test_validation import assert_matches_oracle, fingerprint

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = {"acme-sample": build_demo_environment, "harbor-logistics": build_harbor_environment,
             "meridian-enterprise": build_meridian_environment}
client = TestClient(main.app)


@pytest.mark.parametrize("name", SCENARIOS)
def test_committed_json_matches_the_builder(name):
    on_disk = json.loads((ROOT / "scenarios" / f"{name}.json").read_text(encoding="utf-8"))
    assert on_disk == json.loads(json.dumps(SCENARIOS[name]().model_dump(mode="json")))


@pytest.mark.parametrize("name", SCENARIOS)
def test_each_scenario_imports_through_the_api_and_reanalyses(name):
    payload = json.loads((ROOT / "scenarios" / f"{name}.json").read_text(encoding="utf-8"))
    r = client.put("/api/environment", json=payload)
    assert r.status_code == 200, r.text
    assert client.get("/api/analysis").json()["summary"]["attack_paths"] == analyze(SCENARIOS[name]())["summary"]["attack_paths"]


@pytest.mark.parametrize("name", SCENARIOS)
def test_scenarios_agree_with_the_independent_oracle(name):
    assert_matches_oracle(SCENARIOS[name]())


def test_scenarios_are_entirely_synthetic_and_bilingual():
    for build in SCENARIOS.values():
        env = build()
        assert env.synthetic is True
        assert all(a.name_ar.strip() for a in env.assets)
        # every recorded legitimate use has an Arabic text too (otherwise the Arabic UI would say "none recorded")
        assert all((r.legitimate_use is None) == (r.legitimate_use_ar is None) for r in env.relationships)


# ----------------------------------------------------------------------------- Harbor: realism of the model

def paths_of(env: Environment):
    return {tuple(p["nodes"]): p for p in analyze(env)["paths"]}


def test_harbor_has_multiple_identities_privilege_levels_servers_databases_and_sensitive_resources():
    env = build_harbor_environment()
    by_type: dict[str, int] = {}
    for a in env.assets:
        by_type[a.type.value] = by_type.get(a.type.value, 0) + 1
    assert by_type["user"] >= 6 and by_type["service_account"] >= 3 and by_type["server"] >= 6
    assert by_type["database"] >= 4 and by_type["cloud"] >= 3 and by_type["control"] >= 3
    assert {r.privilege.value for r in env.relationships} == {"none", "read", "write", "admin"}
    assert {r.evidence.value for r in env.relationships} == {"validated", "inferred", "theoretical"}
    assert sum(1 for a in env.assets if a.compromised) == 2                      # two assumed-breach starting points
    assert any(a.exposure.value == "internet" for a in env.assets)


@pytest.mark.parametrize("route", [
    # a phished helpdesk account reaches PII through the stale bastion permission and an application service account
    ("u-lina", "grp-helpdesk", "jump-host", "api-orders", "svc-app", "db-customers"),
    # ... or the most privileged identity via credentials held on the directory server, then the cloud admin role
    ("u-lina", "grp-helpdesk", "jump-host", "dc-01", "u-khalid-it", "role-cloud-admin"),
    # ... or through CI/CD: credentials left on the runner, then an over-privileged deploy role
    ("u-lina", "grp-helpdesk", "jump-host", "ci-runner", "svc-ci", "role-cloud-admin"),
    # the internet-facing portal reaches the data lake through the orders tier and the batch server
    ("web-ext", "api-orders", "app-batch", "s3-datalake"),
    # ... and customer PII through a direct database connection
    ("web-ext", "db-customers"),
])
def test_harbor_contains_the_documented_realistic_attack_routes(route):
    assert route in paths_of(build_harbor_environment())


def test_harbor_legitimate_access_does_not_create_attack_paths_by_itself():
    """Honest users (DBA, HR, Finance, Executive) are not compromised, so their routes must not appear as attack paths."""
    sources = {p["source"] for p in analyze(build_harbor_environment())["paths"]}
    assert sources == {"u-lina", "web-ext"}


# ----------------------------------------------------------------------------- Harbor: golden results (pinned from real runs)

def test_harbor_baseline_golden_values():
    s = analyze(build_harbor_environment())["summary"]
    assert (s["attack_paths"], s["validated_paths"], s["paths_truncated"]) == (42, 12, False)
    assert s["severity_distribution"] == {"critical": 5, "high": 25, "medium": 12, "low": 0}
    assert (s["max_path_score"], s["posture_score"], s["total_path_score"]) == (88.0, 67.3, 2399.4)
    assert s["compromised_sensitive_assets"] == []


def test_harbor_the_top_recommendation_is_the_stale_helpdesk_bastion_permission():
    env = build_harbor_environment()
    recs, partial = recommend_ex(env, analyze(env))
    assert partial is False
    top = recs[0]
    assert top["id"] == "rec-remove_relationship-r02" and top["paths_eliminated"] == 37
    assert top["tradeoff"] == "low" and top["operational_impact"]["lost_access"] == []
    assert top["requires_human_approval"] is True


def test_harbor_removing_the_stale_permission_golden_before_after_and_residual():
    env = build_harbor_environment()
    res = simulate(env, [RemoveRelationship(relationship_id="r02")])
    assert (res["before"]["attack_paths"], res["after"]["attack_paths"]) == (42, 5)
    assert (res["before"]["posture_score"], res["after"]["posture_score"]) == (67.3, 22.8)
    assert (res["before"]["total_path_score"], res["after"]["total_path_score"]) == (2399.4, 349.7)
    assert res["operational_impact"]["level"] == "low" and res["operational_impact"]["lost_access"] == []
    assert res["operational_impact"]["fully_reversible"] is False
    # residual risk is entirely the internet-facing portal, and the top residual is a business-critical link
    after = {tuple(p["nodes"]): p["score"] for p in res["after_paths"]}
    assert set(after) == {("web-ext", "api-orders"), ("web-ext", "api-orders", "db-orders"), ("web-ext", "api-orders", "svc-app", "db-customers"),
                          ("web-ext", "api-orders", "app-batch", "s3-datalake"), ("web-ext", "db-customers")}
    assert after[("web-ext", "api-orders")] == 88.0
    # the same change expressed as a reversible disable has the identical security effect
    dis = simulate(env, [DisableRelationship(relationship_id="r02")])
    assert dis["after"] == res["after"] and dis["operational_impact"]["fully_reversible"] is True


def test_harbor_is_deterministic_across_processes_with_different_hash_seeds():
    script = ("import sys, hashlib; sys.path.insert(0, {b!r});"
              "from app.data.scenario_harbor import build_harbor_environment as b;"
              "from tests.test_validation import fingerprint;"
              "print(hashlib.sha256(fingerprint(b()).encode()).hexdigest())").format(b=str(ROOT / "backend"))
    outs = []
    for seed in ("0", "7", "99999"):
        r = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True, cwd=ROOT / "backend", timeout=180,
                           env={**os.environ, "PYTHONHASHSEED": seed, "ATHAR_DB": ":memory:"})
        assert r.returncode == 0, r.stderr[-600:]
        outs.append(r.stdout.strip())
    assert len(set(outs)) == 1
    assert outs[0] == hashlib.sha256(fingerprint(build_harbor_environment()).encode()).hexdigest()   # and equals the in-process result
