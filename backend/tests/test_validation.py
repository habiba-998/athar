"""Technical validation of the analysis engine (see docs/TECHNICAL_VALIDATION.md).

Three independent kinds of evidence:
  1. ORACLE      - a from-the-specification reimplementation that shares no code with app.analysis, compared on random
                   environments and the shipped scenarios.
  2. METAMORPHIC - properties that must hold for ANY environment (e.g. removing a relationship never adds a path).
  3. DETERMINISM - same input => same output, regardless of input ordering and of Python's hash randomisation.
"""
from __future__ import annotations

import copy
import json
import math
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest

from app.analysis import analyze
from app.data.demo import build_demo_environment
from app.models import (ApplyMfa, ApplySegmentation, Asset, DisableRelationship, Environment, ReducePrivilege,
                        Relationship, RemoveRelationship, ScoringConfig)
from app.recommendations import recommend
from app.simulation import simulate

BACKEND = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------- generators


def random_env(seed: int, n: int | None = None, density: float = 2.2) -> Environment:
    """Random but valid environment exercising every scoring input (types, criticality, exposure, evidence, privilege, MFA)."""
    rnd = random.Random(seed)
    n = n or rnd.randint(5, 11)
    kinds = ["user", "service_account", "group", "server", "database", "cloud", "identity_provider"]
    assets = [Asset(id=f"a{i}", name=f"A{i}", name_ar=f"أ{i}", type=rnd.choice(kinds), criticality=rnd.randint(1, 5),
                    exposure=rnd.choice(["internet", "internal", "restricted"]), compromised=(i < rnd.randint(1, 2)))
              for i in range(n)]
    pairs: set[tuple[int, int]] = set()
    rels: list[Relationship] = []
    target = min(int(n * density), n * (n - 1))
    while len(rels) < target:
        s, t = rnd.sample(range(n), 2)
        if (s, t) in pairs:
            continue
        pairs.add((s, t))
        rels.append(Relationship(
            id=f"r{len(rels)}", source=f"a{s}", target=f"a{t}", type=rnd.choice(["can_login", "read_access", "trusts", "network_access", "admin_access"]),
            privilege=rnd.choice(["none", "read", "write", "admin"]), evidence=rnd.choice(["validated", "observed", "inferred", "theoretical"]),
            mfa_required=rnd.random() < 0.15, disabled=rnd.random() < 0.08,
            legitimate_use="use" if rnd.random() < 0.5 else None, business_critical=rnd.random() < 0.3))
    return Environment(name="rnd", assets=assets, relationships=rels)


SEEDS = range(60)

# --------------------------------------------------------------------------- 1. oracle (independent of app.analysis)

# Constants are re-stated here from the specification on purpose: importing them from the engine would make the
# oracle silently follow any change (or bug) in the engine instead of checking it.
EV = {"validated": 1.0, "observed": 0.85, "inferred": 0.7, "theoretical": 0.4}
PV = {"none": 1.0, "read": 0.7, "write": 0.85, "admin": 1.0}
SPEC = {"ev": EV, "pv": PV, "mfa": 0.35, "length": 0.1, "exposure": 1.1}
RANK = {"theoretical": 0, "inferred": 1, "observed": 2, "validated": 3}      # weakest link decides the class
SENSITIVE_TYPES = ("server", "database", "cloud", "identity_provider")
SPEC_MAX_HOPS = 6


def oracle(env: Environment, spec: dict | None = None) -> dict:
    """Spec: docs/ARCHITECTURE.md 'Path search and scoring'. Plain recursive DFS, no pruning, no networkx."""
    sp = spec or SPEC
    EV_, PV_ = sp["ev"], sp["pv"]
    A = {a.id: a for a in env.assets}
    adj: dict[str, list[Relationship]] = {}
    for r in env.relationships:
        if r.type.value == "protects" or r.disabled:
            continue
        adj.setdefault(r.source, []).append(r)
    sources = [a.id for a in env.assets if a.compromised]
    targets = [a.id for a in env.assets if a.criticality >= 4 and a.type.value in SENSITIVE_TYPES and not a.compromised]
    paths: dict[tuple[str, ...], tuple[float, str]] = {}

    def dfs(node: str, tgt: str, trail: list[str], used: list[Relationship]) -> None:
        for r in adj.get(node, []):
            if r.target in trail:
                continue
            if len(used) + 1 > SPEC_MAX_HOPS:
                continue
            nxt_trail, nxt_used = trail + [r.target], used + [r]
            if r.target == tgt:
                w = [EV_[x.evidence.value] * PV_[x.privilege.value] * (sp["mfa"] if x.mfa_required else 1.0) for x in nxt_used]
                ease = math.prod(w) ** (1 / len(w))
                length = 1 / (1 + sp["length"] * (len(w) - 1))
                exposure = sp["exposure"] if any(A[n].exposure.value == "internet" for n in nxt_trail) else 1.0
                score = min(100.0, round(100 * (A[tgt].criticality / 5) * ease * length * exposure, 1))
                cls = min((x.evidence.value for x in nxt_used), key=lambda e: RANK[e])
                paths[tuple(nxt_trail)] = (score, cls)
            else:
                dfs(r.target, tgt, nxt_trail, nxt_used)

    for s in sources:
        for t in targets:
            if s != t:
                dfs(s, t, [s], [])
    worst = {t: 0.0 for t in targets}
    for nodes, (score, _) in paths.items():
        worst[nodes[-1]] = max(worst[nodes[-1]], score)
    return {
        "paths": paths,
        "posture": round(sum(worst.values()) / len(worst), 1) if worst else 0.0,
        "total": round(sum(s for s, _ in paths.values()), 1),
        "validated": sum(1 for _, c in paths.values() if c == "validated"),
    }


def assert_matches_oracle(env: Environment, config=None, spec: dict | None = None) -> None:
    got, want = analyze(env, config), oracle(env, spec)
    assert not got["summary"]["paths_truncated"]
    assert {tuple(p["nodes"]): (p["score"], p["classification"]) for p in got["paths"]} == want["paths"]
    s = got["summary"]
    assert (s["posture_score"], s["total_path_score"], s["validated_paths"], s["attack_paths"]) == (
        want["posture"], want["total"], want["validated"], len(want["paths"]))
    assert sum(s["severity_distribution"].values()) == len(want["paths"])


@pytest.mark.parametrize("seed", SEEDS)
def test_engine_matches_independent_oracle_on_random_environments(seed):
    assert_matches_oracle(random_env(seed))


def test_hop_limit_matches_the_specification_exactly():
    """A chain of 9 assets: reachability must stop at exactly 6 hops, as documented (not 5, not 7)."""
    assets = [Asset(id=f"c{i}", name=f"C{i}", name_ar=f"س{i}", type="server", criticality=5, compromised=(i == 0)) for i in range(9)]
    rels = [Relationship(id=f"k{i}", source=f"c{i}", target=f"c{i+1}", type="network_access", evidence="validated") for i in range(8)]
    got = {p["nodes"][-1] for p in analyze(Environment(name="chain", assets=assets, relationships=rels))["paths"]}
    assert got == {"c1", "c2", "c3", "c4", "c5", "c6"}


def test_the_random_environments_actually_exercise_the_engine():
    """Guard against vacuous passes: the oracle comparison is only meaningful if there are paths to compare."""
    results = [analyze(random_env(s)) for s in SEEDS]
    counts = [r["summary"]["attack_paths"] for r in results]
    classes = {p["classification"] for r in results for p in r["paths"]}
    assert sum(counts) >= 200 and sum(c >= 5 for c in counts) >= 15
    assert classes == {"validated", "observed", "inferred", "theoretical"}


def random_spec(seed: int) -> tuple[ScoringConfig, dict]:
    """A random valid scoring configuration and the same numbers as an oracle spec (re-derived, not read from the engine)."""
    r = random.Random(seed)
    theo = r.uniform(0.1, 0.5)
    inf = r.uniform(theo, 0.8)
    obs = r.uniform(inf, 1.0)
    read = r.uniform(0.3, 0.8)
    write = r.uniform(read, 1.0)
    mfa, length, expo = r.uniform(0.1, 0.9), r.uniform(0.0, 0.3), r.uniform(1.0, 1.4)
    cfg = ScoringConfig(evidence_observed=obs, evidence_inferred=inf, evidence_theoretical=theo, privilege_read=read,
                        privilege_write=write, mfa_factor=mfa, length_penalty=length, exposure_bonus=expo)
    spec = {"ev": {"validated": 1.0, "observed": obs, "inferred": inf, "theoretical": theo},
            "pv": {"none": 1.0, "read": read, "write": write, "admin": 1.0}, "mfa": mfa, "length": length, "exposure": expo}
    return cfg, spec


@pytest.mark.parametrize("seed", range(25))
def test_engine_matches_oracle_under_random_scoring_configurations(seed):
    """Configurable weights: the engine and the independent oracle agree for arbitrary valid configurations."""
    cfg, spec = random_spec(seed)
    assert_matches_oracle(random_env(seed), cfg, spec)


def test_engine_matches_independent_oracle_on_demo_environment():
    assert_matches_oracle(build_demo_environment())


def test_posture_is_the_mean_of_the_worst_path_per_sensitive_target():
    a = analyze(build_demo_environment())
    worst: dict[str, float] = {}
    for p in a["paths"]:
        worst[p["target"]] = max(worst.get(p["target"], 0.0), p["score"])
    targets = [x for x in build_demo_environment().assets if x.criticality >= 4 and x.type.value in SENSITIVE_TYPES]
    assert a["summary"]["posture_score"] == round(sum(worst.get(t.id, 0.0) for t in targets) / len(targets), 1)


# --------------------------------------------------------------------------- audit finding F1

def _owned_env() -> Environment:
    assets = [Asset(id="s", name="S", name_ar="س", type="user", compromised=True),
              Asset(id="srv", name="Owned server", name_ar="خ", type="server", criticality=4, compromised=True),
              Asset(id="db", name="DB", name_ar="ق", type="database", criticality=5)]
    rels = [Relationship(id="x1", source="s", target="db", type="read_access", privilege="read", evidence="validated")]
    return Environment(name="owned", assets=assets, relationships=rels)


def test_f1_already_compromised_sensitive_assets_do_not_dilute_the_posture():
    s = analyze(_owned_env())["summary"]
    # one scored target (db): posture equals its worst path, NOT half of it
    assert s["posture_score"] == s["max_path_score"] == 70.0
    assert s["compromised_sensitive_assets"] == ["srv"]


def test_f1_no_paths_are_reported_to_an_already_compromised_asset():
    env = _owned_env()
    env.relationships.append(Relationship(id="x2", source="s", target="srv", type="admin_access", privilege="admin", evidence="validated"))
    a = analyze(env)
    assert all(p["target"] != "srv" for p in a["paths"])
    assert a["summary"]["compromised_sensitive_assets"] == ["srv"]


def test_f1_more_breached_assets_never_improve_the_posture():
    base = _owned_env()
    base.assets[1].compromised = False                      # srv uncompromised and unreachable: scores 0, dilutes the mean
    p_unreached = analyze(base)["summary"]["posture_score"]
    p_owned = analyze(_owned_env())["summary"]["posture_score"]
    assert p_owned >= p_unreached                           # marking it compromised must not lower the posture


# --------------------------------------------------------------------------- 2. metamorphic properties

def _paths(env: Environment) -> dict[str, float]:
    a = analyze(env)
    assert not a["summary"]["paths_truncated"]
    return {p["id"]: p["score"] for p in a["paths"]}


@pytest.mark.parametrize("seed", SEEDS)
def test_removing_a_relationship_never_adds_paths_or_raises_scores(seed):
    env = random_env(seed)
    before, b_sum = _paths(env), analyze(env)["summary"]
    for rel in env.relationships[:6]:
        sim = env.model_copy(update={"relationships": [r for r in env.relationships if r.id != rel.id]})
        after, a_sum = _paths(sim), analyze(sim)["summary"]
        assert set(after) <= set(before)
        assert all(after[k] == before[k] for k in after)                # surviving paths keep their exact score
        assert a_sum["posture_score"] <= b_sum["posture_score"] and a_sum["total_path_score"] <= b_sum["total_path_score"]


@pytest.mark.parametrize("seed", SEEDS)
def test_adding_a_relationship_never_removes_paths(seed):
    env = random_env(seed)
    before = _paths(env)
    ids = [a.id for a in env.assets]
    have = {(r.source, r.target) for r in env.relationships}
    rnd = random.Random(seed)
    for _ in range(20):
        s, t = rnd.sample(ids, 2)
        if (s, t) not in have:
            bigger = env.model_copy(update={"relationships": [*env.relationships, Relationship(id="new", source=s, target=t, type="trusts", privilege="read", evidence="theoretical")]})
            after = _paths(bigger)
            assert set(before) <= set(after)
            assert all(after[k] == before[k] for k in before)
            return


@pytest.mark.parametrize("seed", SEEDS)
def test_stronger_evidence_or_privilege_never_lowers_a_score_and_mfa_never_raises_one(seed):
    env = random_env(seed)
    base = _paths(env)
    rel = next((r for r in env.relationships if not r.disabled and r.type.value != "protects"), None)
    if rel is None:
        return
    idx = env.relationships.index(rel)

    def with_rel(**changes):
        rels = list(env.relationships)
        rels[idx] = Relationship.model_validate({**rels[idx].model_dump(), **changes})   # validated: enums, not raw strings
        return env.model_copy(update={"relationships": rels})

    for ev, nxt in (("theoretical", "inferred"), ("inferred", "observed"), ("observed", "validated")):
        if rel.evidence.value == ev:
            up = _paths(with_rel(evidence=nxt))
            assert set(up) == set(base) and all(up[k] >= base[k] for k in base)
    for pv, nxt in (("none", "none"), ("read", "write"), ("write", "admin")):
        if rel.privilege.value == pv and nxt != pv:
            up = _paths(with_rel(privilege=nxt))
            assert set(up) == set(base) and all(up[k] >= base[k] for k in base)
    if not rel.mfa_required:
        down = _paths(with_rel(mfa_required=True))
        assert set(down) == set(base) and all(down[k] <= base[k] for k in base)


@pytest.mark.parametrize("seed", SEEDS)
def test_disable_and_remove_have_the_same_security_effect(seed):
    env = random_env(seed)
    for rel in [r for r in env.relationships if not r.disabled][:3]:
        a = simulate(env, [RemoveRelationship(relationship_id=rel.id)])
        b = simulate(env, [DisableRelationship(relationship_id=rel.id)])
        assert a["paths_eliminated"] == b["paths_eliminated"] and a["after"] == b["after"]
        assert a["operational_impact"]["lost_access"] == b["operational_impact"]["lost_access"]


@pytest.mark.parametrize("seed", SEEDS)
def test_independent_removals_commute(seed):
    env = random_env(seed)
    ids = [r.id for r in env.relationships]
    if len(ids) < 2:
        return
    x, y = ids[0], ids[len(ids) // 2]
    if x == y:
        return
    ab = simulate(env, [RemoveRelationship(relationship_id=x), RemoveRelationship(relationship_id=y)])
    ba = simulate(env, [RemoveRelationship(relationship_id=y), RemoveRelationship(relationship_id=x)])
    assert ab["after"] == ba["after"] and ab["paths_eliminated"] == ba["paths_eliminated"]
    assert ab["operational_impact"]["lost_access"] == ba["operational_impact"]["lost_access"]


@pytest.mark.parametrize("seed", SEEDS)
def test_simulation_accounting_is_consistent_and_never_introduces_paths(seed):
    env = random_env(seed)
    base = analyze(env)
    rels = [r for r in env.relationships if not r.disabled][:2]
    if not rels:
        return
    actions = [RemoveRelationship(relationship_id=rels[0].id)]
    if len(rels) > 1:
        actions.append(ReducePrivilege(relationship_id=rels[1].id)) if rels[1].privilege.value in ("write", "admin") else None
    res = simulate(env, actions)
    before_ids = {p["id"] for p in base["paths"]}
    assert set(res["paths_eliminated"]) | set(res["paths_remaining"]) == before_ids
    assert not set(res["paths_eliminated"]) & set(res["paths_remaining"])
    assert res["paths_introduced"] == []
    assert res["after"]["attack_paths"] == len(res["paths_remaining"])
    assert set(res["paths_mitigated"]) <= set(res["paths_remaining"])


def test_isolation_the_live_environment_is_bit_identical_after_every_action_kind():
    env = build_demo_environment()
    snap = json.dumps(env.model_dump(mode="json"), sort_keys=True)
    for act in (RemoveRelationship(relationship_id="r03"), DisableRelationship(relationship_id="r03"), ReducePrivilege(relationship_id="r03"),
                ApplyMfa(asset_id="web-portal"), ApplySegmentation(asset_id="app-server")):
        simulate(env, [act])
        assert json.dumps(env.model_dump(mode="json"), sort_keys=True) == snap


# --------------------------------------------------------------------------- 3. determinism

def fingerprint(env: Environment) -> str:
    """Everything a user can see, serialised canonically."""
    a = analyze(env)
    recs = recommend(env, a)
    sims = {r["id"]: simulate(env, [r_action(r)], baseline=a) for r in recs[:3]}
    return json.dumps({"analysis": a, "recs": recs, "sims": sims}, sort_keys=True, default=str)


def r_action(rec: dict):
    from pydantic import TypeAdapter
    from app.models import SimAction
    return TypeAdapter(SimAction).validate_python(rec["action"])


def test_repeated_runs_are_identical():
    env = build_demo_environment()
    assert fingerprint(env) == fingerprint(env) == fingerprint(build_demo_environment())


@pytest.mark.parametrize("seed", range(25))
def test_results_do_not_depend_on_the_order_of_assets_and_relationships(seed):
    env = random_env(seed)
    a = analyze(env)
    if a["summary"]["paths_truncated"]:
        pytest.skip("truncation is order-dependent by design (documented)")
    rnd = random.Random(seed + 1000)
    assets, rels = list(env.assets), list(env.relationships)
    rnd.shuffle(assets)
    rnd.shuffle(rels)
    shuffled = Environment(name=env.name, assets=assets, relationships=rels)
    b = analyze(shuffled)
    strip = lambda x: json.dumps({k: x[k] for k in ("paths", "summary", "worst_by_target")}, sort_keys=True, default=str)  # noqa: E731
    assert strip(a) == strip(b)
    assert [f["id"] for f in a["findings"]] == [f["id"] for f in b["findings"]]
    assert recommend(env, a) == recommend(shuffled, b)


SCRIPT = """
import json, sys
sys.path.insert(0, {backend!r})
from app.data.demo import build_demo_environment
from tests.test_validation import fingerprint
import hashlib
print(hashlib.sha256(fingerprint(build_demo_environment()).encode()).hexdigest())
"""


def test_output_is_identical_across_processes_with_different_hash_seeds():
    """Python randomises str hashing per process; any hidden dependence on set/dict ordering would show up here."""
    outs = []
    for seed in ("0", "1", "424242"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "ATHAR_DB": ":memory:"}
        r = subprocess.run([sys.executable, "-I", "-c", SCRIPT.format(backend=str(BACKEND))], capture_output=True, text=True, env=env, cwd=BACKEND, timeout=120)
        assert r.returncode == 0, r.stderr[-800:]
        outs.append(r.stdout.strip())
    assert len(set(outs)) == 1 and len(outs[0]) == 64
