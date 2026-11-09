"""Defensive plan generation and multi-objective (Pareto) comparison.

A *plan* is an ordered list of defensive actions. Several plans are generated with deliberately different priorities
(smallest change, business-safe, reversible-only, balanced, maximum reduction, minimum-disruption complete cut) and each
is evaluated by the same deterministic simulation. Plans are then compared on four objectives that are all minimised:

    paths remaining, residual posture index, disruption cost, implementation effort

A plan is *Pareto-optimal* among the generated plans when no other generated plan is at least as good on every objective
and strictly better on one. That is a statement about THESE plans only: the generators are greedy heuristics (except the
weighted minimum cut, which is exact for its own objective), so no claim of global optimality is made anywhere.
ATHAR never executes a plan; it only prepares it for human review.
"""
from __future__ import annotations

from typing import Any

import networkx as nx
from pydantic import TypeAdapter

from .analysis import analyze, build_graph, legitimate_reach
from .business import approvals_for, effort_of, service_impact
from .models import Environment, RemoveRelationship, SimAction
from .recommendations import disruption_cost, recommend_ex
from .simulation import IMPACT_ORDER, apply_actions, simulate

ADAPTER: TypeAdapter[SimAction] = TypeAdapter(SimAction)
OBJECTIVES = ("paths_after", "posture_after", "disruption_cost", "effort")
ALL_KINDS = {"remove_relationship", "disable_relationship", "reduce_privilege", "apply_mfa", "apply_segmentation"}
REVERSIBLE_ONLY = {"disable_relationship", "reduce_privilege", "apply_mfa"}
MAX_STEPS = 8

# strategy id -> (kinds allowed, highest operational-impact level a single step may have, max steps)
STRATEGIES: dict[str, tuple[set[str], str, int]] = {
    "minimal": (ALL_KINDS, "medium", 1),
    "business_safe": (ALL_KINDS, "low", MAX_STEPS),
    "reversible": (REVERSIBLE_ONLY, "medium", MAX_STEPS),
    "balanced": (ALL_KINDS, "medium", 4),
    "max_reduction": (ALL_KINDS, "high", MAX_STEPS),
}
STRATEGY_ORDER = ["minimal", "business_safe", "reversible", "balanced", "max_reduction", "min_cut"]


def dominates(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    """`a` Pareto-dominates `b` (all objectives minimised): no worse everywhere, strictly better somewhere."""
    return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))


def pareto_front(vectors: dict[str, tuple[float, ...]]) -> dict[str, list[str]]:
    """Map each id to the sorted list of ids that dominate it (empty list => Pareto-optimal)."""
    return {i: sorted(j for j, vj in vectors.items() if j != i and dominates(vj, vi)) for i, vi in vectors.items()}


def _greedy(env: Environment, kinds: set[str], max_level: str, max_steps: int) -> list[SimAction]:
    """Repeatedly take the best-ranked recommendation (re-ranked on the updated environment) that fits the constraints."""
    chosen: list[SimAction] = []
    cur = env
    for _ in range(max_steps):
        a = analyze(cur)
        if a["summary"]["attack_paths"] == 0:
            break
        recs, _ = recommend_ex(cur, a)
        pick = next((r for r in recs if r["action"]["kind"] in kinds
                     and IMPACT_ORDER[r["tradeoff"]] <= IMPACT_ORDER[max_level]), None)
        if pick is None:
            break
        action = ADAPTER.validate_python(pick["action"])
        chosen.append(action)
        cur, _ = apply_actions(cur, [action])
    return chosen


def _cut_capacity(env_rel) -> int:
    """Weight of removing a relationship in the minimum cut, lexicographic: first the disruption cost the recommender
    assigns to a removal (3 if business-critical, 1 if it has a recorded legitimate use, else 0), then the number of removals."""
    level_cost = 3 if env_rel.business_critical else (1 if env_rel.legitimate_use else 0)
    return 1000 * level_cost + 1


def min_cut_actions(env: Environment, analysis: dict[str, Any]) -> list[SimAction]:
    """Removals of minimum total weight that disconnect every compromised asset from every attacked target.

    Exact (max-flow = min-cut) for "least summed removal disruption, then fewest removals" on the full graph; the engine's
    hop limit is ignored, so some cut edges may not lie on any hop-limited path - those are dropped, which keeps the cut
    complete. It only considers removals (no reversible actions) and ignores the lost-access term of the disruption cost, so
    other plans can beat it on the plan-level disruption cost; it is NOT optimal for posture, effort or reversibility, and
    it cuts business-critical access if that is the cheapest complete cut. Edges are inserted in id order so the result
    does not depend on input ordering.
    """
    if not analysis["paths"]:
        return []
    g = build_graph(env)
    h: nx.DiGraph = nx.DiGraph()
    for u, v, d in sorted(g.edges(data=True), key=lambda e: e[2]["rel"].id):
        h.add_edge(u, v, capacity=_cut_capacity(d["rel"]), rid=d["rel"].id)
    for s in sorted(a.id for a in env.assets if a.compromised):
        h.add_edge("__S__", s)                                  # no capacity attribute => infinite
    for t in sorted({p["target"] for p in analysis["paths"]}):
        h.add_edge(t, "__T__")
    if "__S__" not in h or "__T__" not in h or not nx.has_path(h, "__S__", "__T__"):
        return []
    _, (reach, _non) = nx.minimum_cut(h, "__S__", "__T__")
    on_path = {rid for p in analysis["paths"] for rid in p["relationship_ids"]}
    ids = sorted(h[u][v]["rid"] for u in reach for v in h[u] if v not in reach and "rid" in h[u][v])
    return [RemoveRelationship(relationship_id=rid) for rid in ids if rid in on_path]


def _canon(actions: list[SimAction]) -> tuple[str, ...]:
    return tuple(sorted(a.model_dump_json() for a in actions))


def _evaluate(env: Environment, analysis: dict[str, Any], reach: dict[str, set[str]], plan_id: str, strategy: str,
              actions: list[SimAction]) -> dict[str, Any]:
    base = analysis["summary"]
    if actions:
        res = simulate(env, actions, baseline=analysis, reach_before=reach)
        after, op = res["after"], res["operational_impact"]
        residual_paths = res["after_paths"]
        eliminated, mitigated = len(res["paths_eliminated"]), len(res["paths_mitigated"])
    else:
        after = base
        op = {"level": "none", "affected_relationships": [], "affected_assets": [], "lost_access": [], "fully_reversible": True}
        residual_paths = analysis["paths"]
        eliminated = mitigated = 0
    business = service_impact(env, op["affected_relationships"])
    cost = round(disruption_cost(op), 1)
    posture_before, posture_after = base["posture_score"], after["posture_score"]
    return {
        "id": plan_id,
        "strategy": strategy,
        "actions": [a.model_dump() for a in actions],
        "metrics": {
            "paths_before": base["attack_paths"], "paths_after": after["attack_paths"],
            "paths_eliminated": eliminated, "paths_mitigated": mitigated,
            "posture_before": posture_before, "posture_after": posture_after,
            "posture_reduction_pct": round(100 * (posture_before - posture_after) / posture_before, 1) if posture_before else 0.0,
            "max_residual_score": after["max_path_score"],
            "residual_validated": after["validated_paths"],
            "residual_evidence": after["evidence_distribution"],
            "residual_severity": after["severity_distribution"],
        },
        "residual_top": [{"path_id": p["id"], "nodes": p["nodes"], "target": p["target"], "score": p["score"],
                          "severity": p["severity"], "classification": p["classification"]} for p in residual_paths[:5]],
        "operational": {
            "level": op["level"], "affected_assets": op["affected_assets"], "lost_access": len(op["lost_access"]),
            "fully_reversible": bool(op["fully_reversible"]),
            "touches_business_critical": any(i["business_critical"] for i in op["affected_relationships"]),
            "affected_relationships": [i["relationship_id"] for i in op["affected_relationships"]],
        },
        "business": business,
        "disruption_cost": cost,
        "effort": effort_of(actions),
        "approvals": approvals_for(actions, op, business),
        "objectives": [after["attack_paths"], posture_after, cost, effort_of(actions)],
        "requires_human_approval": True,
    }


def generate_plans(env: Environment, analysis: dict[str, Any]) -> dict[str, Any]:
    """Generate, evaluate and compare plans for the environment under the ACTIVE scoring configuration."""
    reach = legitimate_reach(env)
    candidates: list[tuple[str, list[SimAction]]] = []
    for sid in STRATEGY_ORDER:
        if sid == "min_cut":
            acts = min_cut_actions(env, analysis)
        else:
            kinds, level, steps = STRATEGIES[sid]
            acts = _greedy(env, kinds, level, steps)
        candidates.append((sid, acts))

    plans: list[dict[str, Any]] = [_evaluate(env, analysis, reach, "plan-status-quo", "status_quo", [])]
    seen: dict[tuple[str, ...], dict[str, Any]] = {(): plans[0]}
    for sid, acts in candidates:
        key = _canon(acts)
        if not acts:
            continue
        if key in seen:                       # an identical action set from another strategy: keep one, remember both
            seen[key].setdefault("also_strategies", []).append(sid)
            continue
        plan = _evaluate(env, analysis, reach, f"plan-{sid.replace('_', '-')}", sid, acts)
        seen[key] = plan
        plans.append(plan)

    dominated = pareto_front({p["id"]: tuple(p["objectives"]) for p in plans})
    for p in plans:
        p["pareto"] = {"optimal": not dominated[p["id"]], "dominated_by": dominated[p["id"]]}

    # A SUGGESTED starting point for the human reviewer: among Pareto-optimal plans with a real change that is not rated
    # "high" operational impact and does not interrupt a critical service, take the lowest residual posture.
    eligible = [p for p in plans if p["pareto"]["optimal"] and p["actions"]
                and p["operational"]["level"] != "high" and p["business"]["critical_services_interrupted"] == 0]
    eligible.sort(key=lambda p: (p["metrics"]["posture_after"], p["disruption_cost"], p["effort"], p["id"]))
    suggested = eligible[0]["id"] if eligible else None
    return {
        "plans": plans,
        "objectives": list(OBJECTIVES),
        "suggested_plan_id": suggested,
        "suggestion_rule": "lowest_residual_posture_among_pareto_plans_without_high_impact_or_critical_service_interruption",
        "optimality_claim": "none: plans come from greedy heuristics and one exact weighted cut; Pareto status is relative to the generated plans only",
        "partial": bool(analysis["summary"].get("paths_truncated")),
    }
