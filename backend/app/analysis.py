"""Deterministic graph analysis: attack-path discovery and transparent risk scoring.

Nothing here is probabilistic or learned. A "score" is a reproducible 0-100
heuristic index computed from the factors returned alongside it. It is NOT a
probability of compromise.
"""
from __future__ import annotations

import hashlib
import math
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from typing import Any

import networkx as nx

from .models import (EVIDENCE_RANK, Asset, AssetType, Environment, Evidence, Privilege, Relationship, RelType,
                     ScoringConfig)

# ---- scoring assumptions live in ScoringConfig (models.py); the default is the documented baseline ----
DEFAULT_CONFIG = ScoringConfig()
_ACTIVE: ContextVar[ScoringConfig] = ContextVar("athar_scoring_config", default=DEFAULT_CONFIG)


def active_config() -> ScoringConfig:
    return _ACTIVE.get()


@contextmanager
def use_config(config: ScoringConfig | None) -> Iterator[ScoringConfig]:
    """Run analysis under `config` (None keeps the current one). Context-local, so concurrent requests cannot interfere."""
    cfg = config if config is not None else _ACTIVE.get()
    token = _ACTIVE.set(cfg)
    try:
        yield cfg
    finally:
        _ACTIVE.reset(token)


SENSITIVE_MIN_CRITICALITY = 4
SENSITIVE_TYPES = (AssetType.server, AssetType.database, AssetType.cloud, AssetType.identity_provider)
MAX_HOPS = 6
MAX_PATHS = 500
STEP_BUDGET = 400_000      # max edge expansions per analysis; exceeding it marks the result truncated (deterministic)
SEVERITY_BANDS = [(70.0, "critical"), (50.0, "high"), (30.0, "medium"), (0.0, "low")]
SEVERITIES = ["critical", "high", "medium", "low"]


def severity_for(score: float) -> str:
    for threshold, name in SEVERITY_BANDS:
        if score >= threshold:
            return name
    return "low"


@lru_cache(maxsize=256)
def _tables(cfg: ScoringConfig) -> tuple[dict[Evidence, float], dict[Privilege, float]]:
    return cfg.evidence_weights(), cfg.privilege_weights()


def edge_weight(rel: Relationship, cfg: ScoringConfig | None = None) -> float:
    c = cfg or _ACTIVE.get()
    ev, pv = _tables(c)
    w = ev[rel.evidence] * pv[rel.privilege]
    return w * (c.mfa_factor if rel.mfa_required else 1.0)


def weight_reasons(rel: Relationship, cfg: ScoringConfig | None = None) -> list[str]:
    """Which attributes of a relationship lower its weight below 1 (the reasons it is a 'weak' or 'strong' link)."""
    c = cfg or _ACTIVE.get()
    ev, pv = _tables(c)
    out = []
    if ev[rel.evidence] < 1.0:
        out.append(f"evidence:{rel.evidence.value}")
    if pv[rel.privilege] < 1.0:
        out.append(f"privilege:{rel.privilege.value}")
    if rel.mfa_required:
        out.append("mfa")
    return out


def weakest_evidence(rels: list[Relationship]) -> Evidence:
    """Weakest-link evidence class of a chain of relationships."""
    return min((r.evidence for r in rels), key=lambda e: EVIDENCE_RANK[e])


def build_graph(env: Environment) -> nx.DiGraph:
    """Directed graph of traversable relationships (controls/`protects` and disabled edges excluded)."""
    g: nx.DiGraph = nx.DiGraph()
    for a in env.assets:
        g.add_node(a.id, asset=a)
    for r in env.relationships:
        if r.type is RelType.protects or r.disabled:
            continue
        g.add_edge(r.source, r.target, rel=r)
    return g


def sensitive_targets(env: Environment) -> list[Asset]:
    return [
        a for a in env.assets
        if a.criticality >= SENSITIVE_MIN_CRITICALITY
        and a.type in SENSITIVE_TYPES
    ]


def path_id(nodes: list[str]) -> str:
    return "p-" + hashlib.sha1("->".join(nodes).encode()).hexdigest()[:10]


def _score_path(by_id: dict[str, Asset], nodes: list[str], rels: list[Relationship]) -> dict[str, Any]:
    cfg = _ACTIVE.get()
    target = by_id[nodes[-1]]
    weights = [edge_weight(r, cfg) for r in rels]
    ease = math.prod(weights) ** (1 / len(weights))
    length_f = 1 / (1 + cfg.length_penalty * (len(rels) - 1))
    exposed = any(by_id[n].exposure.value == "internet" for n in nodes)
    exposure_f = cfg.exposure_bonus if exposed else 1.0
    crit_n = target.criticality / 5
    score = min(100.0, round(100 * crit_n * ease * length_f * exposure_f, 1))
    classification = weakest_evidence(rels).value        # weakest link: theoretical < inferred < observed < validated
    # Driver analysis: which hop holds the path back (lowest weight; first on ties) and why.
    weakest_i = min(range(len(rels)), key=lambda i: (weights[i], i))
    factors = [
        {"code": "target_criticality", "value": round(crit_n, 3), "detail": {"criticality": target.criticality}},
        {"code": "ease", "value": round(ease, 3), "detail": {"edge_weights": [round(w, 3) for w in weights]}},
        {"code": "length", "value": round(length_f, 3), "detail": {"hops": len(rels)}},
        {"code": "exposure", "value": exposure_f, "detail": {"internet_exposed": exposed}},
    ]
    # Reducers are factors below 1 ordered strongest-first; the exposure bonus is the only factor above 1.
    reducers = sorted((f for f in factors if f["value"] < 1.0), key=lambda f: (f["value"], f["code"]))  # type: ignore[operator]
    return {
        "score": score, "severity": severity_for(score), "classification": classification, "factors": factors,
        "weakest_hop": {"relationship_id": rels[weakest_i].id, "weight": round(weights[weakest_i], 3),
                        "reasons": weight_reasons(rels[weakest_i], cfg)},
        "drivers": [f["code"] for f in reducers],
        "hop_weights": [round(w, 3) for w in weights],
    }


class _BudgetExceeded(Exception):
    pass


def _distance_to(g: nx.DiGraph, target: str) -> dict[str, int]:
    """Hop distance from every node to `target` (reverse BFS, limited to MAX_HOPS)."""
    dist = {target: 0}
    frontier = [target]
    for d in range(1, MAX_HOPS + 1):
        nxt: list[str] = []
        for v in frontier:
            for u in g.predecessors(v):
                if u not in dist:
                    dist[u] = d
                    nxt.append(u)
        frontier = nxt
        if not frontier:
            break
    return dist


def _simple_paths(g: nx.DiGraph, s: str, t: str, dist: dict[str, int], budget: list[int]):
    """Yield every simple path s -> t with at most MAX_HOPS edges.

    Unlike a plain DFS, a branch is only entered if `t` is still reachable within the remaining hops
    (precomputed reverse distances), so effort is proportional to the output rather than to dead ends.
    `budget[0]` counts edge expansions; exhausting it raises _BudgetExceeded (deterministic, not time-based).
    """
    if dist.get(s, MAX_HOPS + 1) > MAX_HOPS:
        return
    path = [s]
    on_path = {s}
    stack = [iter(g.successors(s))]
    while stack:
        n = next(stack[-1], None)
        if n is None:
            stack.pop()
            on_path.discard(path.pop())
            continue
        budget[0] -= 1
        if budget[0] < 0:
            raise _BudgetExceeded
        if n == t:
            if len(path) <= MAX_HOPS:
                yield [*path, t]
            continue
        if n in on_path:
            continue
        d = dist.get(n)
        if d is None or len(path) + d > MAX_HOPS:
            continue
        path.append(n)
        on_path.add(n)
        stack.append(iter(g.successors(n)))


def find_attack_paths(env: Environment) -> list[dict[str, Any]]:
    return enumerate_attack_paths(env)[0]


def enumerate_attack_paths(env: Environment) -> tuple[list[dict[str, Any]], bool]:
    """Return (paths, truncated). `truncated` is True when the global MAX_PATHS cap stopped enumeration,
    in which case the result is knowingly incomplete and callers must say so."""
    g = build_graph(env)
    by_id = {a.id: a for a in env.assets}
    sources = [a.id for a in env.assets if a.compromised]
    # An asset that is already assumed compromised cannot be "reached": paths to it are moot (see analyze()).
    targets = [a.id for a in sensitive_targets(env) if not a.compromised]
    out: list[dict[str, Any]] = []
    truncated = False
    budget = [STEP_BUDGET]
    dists = {t: _distance_to(g, t) for t in targets}
    for s in sources:
        for t in targets:
            if s == t:
                continue
            if truncated:
                break
            found: list[list[str]] = []
            try:
                for nodes in _simple_paths(g, s, t, dists[t], budget):
                    found.append(nodes)
                    if len(found) > MAX_PATHS - len(out):  # one more than fits: proves the cap really cuts results
                        break
            except _BudgetExceeded:
                truncated = True                           # keep what was found before the budget ran out
            for nodes in found:
                if len(out) >= MAX_PATHS:
                    truncated = True
                    break
                rels: list[Relationship] = [g.edges[u, v]["rel"] for u, v in zip(nodes, nodes[1:])]
                scored = _score_path(by_id, nodes, rels)
                out.append({
                    "id": path_id(nodes),
                    "source": s,
                    "target": t,
                    "nodes": nodes,
                    "relationship_ids": [r.id for r in rels],
                    "steps": [
                        {"relationship_id": r.id, "from": r.source, "to": r.target, "type": r.type.value,
                         "privilege": r.privilege.value, "evidence": r.evidence.value, "mfa_required": r.mfa_required,
                         "confidence": r.effective_confidence, "evidence_source": r.evidence_source,
                         "validation": r.validation}
                        for r in rels
                    ],
                    **scored,
                })
    out.sort(key=lambda p: (-p["score"], p["id"]))
    return out, truncated


def unjustified_access_findings(env: Environment) -> list[dict[str, Any]]:
    """Rule: privileged/sensitive-reaching edges with no recorded business justification."""
    out = []
    by_id = {a.id: a for a in env.assets}
    for r in env.relationships:
        if r.type in (RelType.protects, RelType.member_of) or r.legitimate_use or r.disabled:
            continue
        tgt = by_id[r.target]
        if r.privilege in (Privilege.admin, Privilege.write) or tgt.criticality >= SENSITIVE_MIN_CRITICALITY:
            sev = "high" if r.privilege is Privilege.admin else "medium"
            out.append({"id": f"f-unjustified-{r.id}", "kind": "unjustified_access", "severity": sev,
                        "relationship_id": r.id, "source": r.source, "target": r.target,
                        "privilege": r.privilege.value, "evidence": r.evidence.value})
    return out


def analyze(env: Environment, config: ScoringConfig | None = None) -> dict[str, Any]:
    with use_config(config):
        return _analyze(env)


def _analyze(env: Environment) -> dict[str, Any]:
    paths, truncated = enumerate_attack_paths(env)
    sensitive = sensitive_targets(env)
    # Sensitive assets that are themselves assumed compromised are reported, but excluded from the posture mean:
    # they have no attack path to score, and counting them as 0 would make the posture look BETTER the more assets
    # are already breached (audit finding F1, docs/TECHNICAL_VALIDATION.md).
    owned = sorted(t.id for t in sensitive if t.compromised)
    worst: dict[str, float] = {t.id: 0.0 for t in sensitive if not t.compromised}
    for p in paths:
        worst[p["target"]] = max(worst[p["target"]], p["score"])
    posture = round(sum(worst.values()) / len(worst), 1) if worst else 0.0
    dist = {s: 0 for s in SEVERITIES}
    ev_dist = {e.value: 0 for e in sorted(Evidence, key=lambda e: -EVIDENCE_RANK[e])}
    for p in paths:
        dist[p["severity"]] += 1
        ev_dist[p["classification"]] += 1
    findings = [
        {"id": f"f-{p['id']}", "kind": "attack_path", "severity": p["severity"], "path_id": p["id"],
         "target": p["target"], "score": p["score"], "classification": p["classification"]}
        for p in paths[:10]
    ] + unjustified_access_findings(env)
    rank = {s: i for i, s in enumerate(SEVERITIES)}
    findings.sort(key=lambda f: (rank[f["severity"]], -f.get("score", 0), f["id"]))
    assets = [a for a in env.assets if a.type is not AssetType.control]
    return {
        "paths": paths,
        "findings": findings,
        "worst_by_target": worst,
        "summary": {
            "total_assets": len(assets),
            "critical_assets": sum(1 for a in assets if a.criticality >= SENSITIVE_MIN_CRITICALITY),
            "attack_paths": len(paths),
            "paths_truncated": truncated,  # True => enumeration hit MAX_PATHS; results are knowingly incomplete
            "compromised_sensitive_assets": owned,  # already-breached sensitive assets: not scored, always surfaced
            "validated_paths": ev_dist["validated"],
            "evidence_distribution": ev_dist,   # paths per weakest-link class (validated/observed/inferred/theoretical)
            "max_path_score": max((p["score"] for p in paths), default=0.0),
            "total_path_score": round(sum(p["score"] for p in paths), 1),
            "posture_score": posture,
            "severity_distribution": dist,
        },
    }


def legitimate_reach(env: Environment) -> dict[str, set[str]]:
    """Assets reachable from each non-compromised identity (used to estimate disruption)."""
    g = build_graph(env)
    return {
        a.id: set(nx.descendants(g, a.id))
        for a in env.assets
        if a.type in (AssetType.user, AssetType.service_account) and not a.compromised
    }
