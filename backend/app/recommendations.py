"""Recommendations are derived by simulating each candidate defensive action.

Expected risk reduction therefore comes from the same deterministic engine as
the analysis; nothing is estimated by a model. Every recommendation requires
human approval: ATHAR never executes changes.
"""
from __future__ import annotations

from typing import Any

from .analysis import legitimate_reach
from .models import (ApplyMfa, ApplySegmentation, DisableRelationship, Environment, Privilege, ReducePrivilege,
                     RemoveRelationship, RelType, SimAction)
from .simulation import SimulationError, simulate

COST = {"high": 3.0, "medium": 1.0, "low": 0.0, "none": 0.0}
MAX_RECOMMENDATIONS = 10
MAX_CANDIDATES = 60        # candidate actions simulated for large environments (bounds worst-case latency; flagged when hit)
SMALL_ENV_RELATIONSHIPS = 200
SMALL_ENV_CANDIDATES = 150  # small environments simulate quickly, so they get a higher cap. Deterministic in the input size.


def candidate_cap(env: Environment) -> int:
    return SMALL_ENV_CANDIDATES if len(env.relationships) <= SMALL_ENV_RELATIONSHIPS else MAX_CANDIDATES
REVERSIBLE_DISCOUNT = 0.75  # reversible actions cost 25% less disruption than irreversible ones (documented assumption)


def _candidates(env: Environment, analysis: dict[str, Any]) -> list[SimAction]:
    # Relationships on the most attack paths first (ties by id): deterministic, and the likeliest to matter
    # if the evaluation cap below has to cut the list.
    counts: dict[str, int] = {}
    for p in analysis["paths"]:
        for rid in p["relationship_ids"]:
            counts[rid] = counts.get(rid, 0) + 1
    rel_ids = sorted(counts, key=lambda rid: (-counts[rid], rid))
    rels = {r.id: r for r in env.relationships}
    out: list[SimAction] = []
    seen_assets: set[tuple[str, str]] = set()
    for rid in rel_ids:
        r = rels[rid]
        out.append(RemoveRelationship(relationship_id=rid))
        if r.legitimate_use:
            out.append(DisableRelationship(relationship_id=rid))  # reversible alternative where access has a use
        if r.privilege in (Privilege.admin, Privilege.write):
            out.append(ReducePrivilege(relationship_id=rid))
        if r.type in (RelType.can_login, RelType.has_credentials) and not r.mfa_required:
            key = ("mfa", r.target)
            if key not in seen_assets:
                seen_assets.add(key)
                out.append(ApplyMfa(asset_id=r.target))
        if r.type is RelType.network_access:
            key = ("seg", r.target)
            if key not in seen_assets:
                seen_assets.add(key)
                out.append(ApplySegmentation(asset_id=r.target))
    return out


def disruption_cost(impact: dict[str, Any]) -> float:
    """Relationship-level disruption cost of a simulated change (documented assumption, see ARCHITECTURE.md)."""
    return sum(COST[i["level"]] * (REVERSIBLE_DISCOUNT if i["reversible"] else 1.0)
               for i in impact["affected_relationships"]) + 0.5 * len(impact["lost_access"])


def _key(a: SimAction) -> str:
    return f"rec-{a.kind}-{getattr(a, 'relationship_id', None) or getattr(a, 'asset_id', '')}"


def recommend(env: Environment, analysis: dict[str, Any]) -> list[dict[str, Any]]:
    return recommend_ex(env, analysis)[0]


def recommend_ex(env: Environment, analysis: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    """Return (recommendations, partial). `partial` is True when the candidate list was cut at MAX_CANDIDATES
    or the underlying path enumeration was truncated: the ranking is then over a subset of possible actions."""
    recs = []
    base_total = analysis["summary"]["total_path_score"]
    candidates = _candidates(env, analysis)
    cap = candidate_cap(env)
    partial = len(candidates) > cap or bool(analysis["summary"].get("paths_truncated"))
    reach_before = legitimate_reach(env)  # identical for every candidate: compute once
    for act in candidates[:cap]:
        try:
            res = simulate(env, [act], baseline=analysis, reach_before=reach_before)
        except SimulationError:
            continue
        gain = base_total - res["after"]["total_path_score"]
        if gain <= 0:
            continue
        impact = res["operational_impact"]
        cost = disruption_cost(impact)
        recs.append({
            "id": _key(act),
            "action": act.model_dump(),
            "risk_reduction_pct": res["risk_reduction_pct"],
            "path_score_reduction_pct": res["path_score_reduction_pct"],
            "path_score_reduction": round(gain, 1),
            "paths_eliminated": len(res["paths_eliminated"]),
            "paths_mitigated": len(res["paths_mitigated"]),
            "paths_remaining": len(res["paths_remaining"]),
            "operational_impact": impact,
            "disruption_cost": round(cost, 1),
            "priority": round(gain / (1 + cost), 2),
            "tradeoff": impact["level"],
            "rationale": [
                {"code": "reduces_path_risk", "params": {"eliminated": len(res["paths_eliminated"]),
                                                          "mitigated": len(res["paths_mitigated"])}},
                {"code": f"impact_{impact['level']}", "params": {}},
            ],
            "requires_human_approval": True,
        })
    recs.sort(key=lambda r: (-r["priority"], r["id"]))
    return recs[:MAX_RECOMMENDATIONS], partial
