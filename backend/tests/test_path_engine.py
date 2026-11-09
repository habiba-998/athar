"""The pruned DFS must return exactly the paths NetworkX's reference all_simple_paths would, and stay bounded."""
import random
import time

import networkx as nx
import pytest

import app.analysis as an
from app.analysis import MAX_HOPS, analyze, build_graph, enumerate_attack_paths, sensitive_targets
from app.data.demo import build_demo_environment
from app.models import Asset, Environment, Relationship

TYPES = ["user", "service_account", "group", "server", "database", "cloud"]


def random_env(seed: int, n: int, e: int, sources: int = 1) -> Environment:
    rnd = random.Random(seed)
    assets = [Asset(id=f"a{i}", name=f"A{i}", name_ar=f"أ{i}", type=rnd.choice(TYPES), criticality=rnd.randint(1, 5),
                    compromised=i < sources) for i in range(n)]
    pairs: set[tuple[int, int]] = set()
    rels: list[Relationship] = []
    while len(rels) < e:
        s, t = rnd.sample(range(n), 2)
        if (s, t) not in pairs:
            pairs.add((s, t))
            rels.append(Relationship(id=f"r{len(rels)}", source=f"a{s}", target=f"a{t}", type="read_access",
                                     privilege="read", evidence=rnd.choice(["validated", "inferred", "theoretical"]),
                                     disabled=rnd.random() < 0.1))
    return Environment(name="rnd", assets=assets, relationships=rels)


def reference_paths(env: Environment) -> set[tuple[str, ...]]:
    g = build_graph(env)
    out = set()
    for s in (a.id for a in env.assets if a.compromised):
        for t in (a.id for a in sensitive_targets(env) if not a.compromised):
            if s != t:
                out |= {tuple(p) for p in nx.all_simple_paths(g, s, t, cutoff=MAX_HOPS)}
    return out


@pytest.mark.parametrize("seed", range(40))
def test_matches_networkx_reference_on_random_graphs(seed):
    rnd = random.Random(seed)
    n = rnd.randint(4, 14)
    env = random_env(seed, n, rnd.randint(n, min(n * (n - 1), 3 * n)), sources=rnd.randint(1, 2))
    paths, truncated = enumerate_attack_paths(env)
    if truncated:                                   # only compare complete enumerations
        pytest.skip("truncated sample")
    assert {tuple(p["nodes"]) for p in paths} == reference_paths(env)
    assert len({p["id"] for p in paths}) == len(paths)               # no duplicates


def test_matches_reference_on_the_demo_environment():
    env = build_demo_environment()
    assert {tuple(p["nodes"]) for p in analyze(env)["paths"]} == reference_paths(env)


def test_hop_limit_is_respected_exactly():
    # a chain of 8 assets: the end is 7 hops away, beyond MAX_HOPS=6
    assets = [Asset(id=f"c{i}", name=f"C{i}", name_ar=f"س{i}", type="server", criticality=5, compromised=(i == 0)) for i in range(8)]
    rels = [Relationship(id=f"k{i}", source=f"c{i}", target=f"c{i+1}", type="network_access") for i in range(7)]
    env = Environment(name="chain", assets=assets, relationships=rels)
    ends = {p["nodes"][-1] for p in analyze(env)["paths"]}
    assert "c6" in ends and "c7" not in ends
    assert max(len(p["steps"]) for p in analyze(env)["paths"]) == MAX_HOPS


def test_dead_ends_do_not_cost_time():
    """A huge irrelevant fan-out must not slow the search: the pruned DFS never enters branches that cannot reach a target."""
    assets = [Asset(id="s", name="S", name_ar="س", type="user", compromised=True),
              Asset(id="t", name="T", name_ar="ت", type="database", criticality=5)]
    assets += [Asset(id=f"x{i}", name=f"X{i}", name_ar=f"س{i}", type="server", criticality=1) for i in range(300)]
    rels = [Relationship(id="direct", source="s", target="t", type="read_access", privilege="read")]
    k = 0
    for i in range(300):                                   # dense dead-end mesh hanging off the source
        rels.append(Relationship(id=f"d{k}", source="s", target=f"x{i}", type="network_access")); k += 1
        for j in (i + 1, i + 2, i + 3):
            if j < 300:
                rels.append(Relationship(id=f"d{k}", source=f"x{i}", target=f"x{j}", type="network_access")); k += 1
    env = Environment(name="mesh", assets=assets, relationships=rels)
    t0 = time.time()
    a = analyze(env)
    assert time.time() - t0 < 1.0
    assert [p["nodes"] for p in a["paths"]] == [["s", "t"]] and a["summary"]["paths_truncated"] is False


def test_step_budget_truncates_deterministically_and_keeps_partial_results(monkeypatch):
    env = random_env(3, 60, 300)
    monkeypatch.setattr(an, "STEP_BUDGET", 50)
    p1, t1 = enumerate_attack_paths(env)
    p2, t2 = enumerate_attack_paths(env)
    assert t1 is True and t2 is True
    assert [p["id"] for p in p1] == [p["id"] for p in p2]            # same inputs -> same partial result


def test_recommendations_are_capped_flagged_partial_and_ordered_by_path_frequency():
    from app.recommendations import MAX_CANDIDATES, _candidates, recommend_ex
    env = random_env(5, 120, 1500)
    a = analyze(env)
    cands = _candidates(env, a)
    assert len(cands) > MAX_CANDIDATES
    recs, partial = recommend_ex(env, a)
    assert partial is True and len(recs) <= 10
    # first candidate is the relationship that sits on the most attack paths
    counts: dict[str, int] = {}
    for p in a["paths"]:
        for rid in p["relationship_ids"]:
            counts[rid] = counts.get(rid, 0) + 1
    assert counts[cands[0].relationship_id] == max(counts.values())
    assert recommend_ex(env, a)[0] == recs                       # deterministic


def test_demo_recommendations_are_not_partial():
    from app.recommendations import recommend_ex
    env = build_demo_environment()
    assert recommend_ex(env, analyze(env))[1] is False


def _machine_slowness() -> float:
    """How much slower than the development machine's nominal speed this process currently runs (>= 1).

    A fixed pure-Python reference loop (about 0.15 s nominal) is timed in the SAME process, so the factor includes coverage
    tracing and CPU throttling or contention. It lets the bound below follow the machine's speed without being loosened:
    an algorithmic regression is a >10x slowdown, which a 3x throttled machine does not explain.
    """
    t0 = time.perf_counter()
    acc = 0
    for i in range(1_500_000):
        acc += i * i % 7
    return max(1.0, min(6.0, (time.perf_counter() - t0) / 0.15))


def test_worst_case_import_through_the_api_stays_responsive():
    from fastapi.testclient import TestClient
    from app import main
    env = random_env(11, 500, 5000)
    before = _machine_slowness()
    t0 = time.time()
    main.state.replace(env, "environment_imported", {})          # same path as PUT /api/environment, minus the 1 MB body cap
    elapsed = time.time() - t0
    slowness = max(before, _machine_slowness())                   # the slower of the two samples: throttling can start mid-run
    meta = TestClient(main.app).get("/api/environment/meta").json()
    # Intent: bounded, not hung. Measured 8-9 s plain and 23-26 s under coverage (stable over repeated imports in one process);
    # before the pruned search this size did not finish in 150 s. The 90 s bound is the nominal-machine bound and is only
    # scaled up (at most 6x) by a measured slowdown of the machine itself, never by the size of the observed time.
    bound = 90 * slowness
    assert elapsed < bound, f"import+analysis+recommendations took {elapsed:.1f}s (bound {bound:.0f}s, machine slowness x{slowness:.1f})"
    assert meta["recommendations_partial"] is True and meta["paths_truncated"] is True
    assert len(main.state.recs) <= 10


def test_worst_case_validator_limits_finish_quickly():
    """500 assets / 5000 relationships is the largest environment the model accepts; analysis must stay bounded."""
    env = random_env(11, 500, 5000)
    t0 = time.time()
    a = analyze(env)
    elapsed = time.time() - t0
    assert elapsed < 10, f"analysis took {elapsed:.1f}s"
    assert len(a["paths"]) <= an.MAX_PATHS
