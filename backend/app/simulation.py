"""Defensive what-if simulation.

The baseline Environment is never mutated: every simulation runs on a deep copy.
"""
from __future__ import annotations

from typing import Any

from .analysis import analyze, legitimate_reach
from .models import (ApplyMfa, ApplySegmentation, DisableRelationship, Environment, Privilege, ReducePrivilege,
                     Relationship, RemoveRelationship, RelType, SimAction)

IMPACT_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}
REVERSIBLE_KINDS = {"disable_relationship", "apply_mfa", "reduce_privilege"}


class SimulationError(ValueError):
    """Invalid simulation request (unknown id, no-op action)."""


def _rel(env: Environment, rel_id: str) -> Relationship:
    for r in env.relationships:
        if r.id == rel_id:
            return r
    raise SimulationError(f"unknown relationship: {rel_id}")


def _has_asset(env: Environment, asset_id: str) -> None:
    if not any(a.id == asset_id for a in env.assets):
        raise SimulationError(f"unknown asset: {asset_id}")


def _impact_of(r: Relationship, action_kind: str) -> dict[str, Any]:
    if r.business_critical:
        level = "high"
    elif r.legitimate_use:
        level = "medium"
    else:
        level = "low"
    # MFA keeps the access (users enrol), so a business-critical edge is rated one step lower. A privilege reduction does
    # NOT get that discount: whether the lower privilege still supports the business function is unknowable here (e.g.
    # write -> read on an order-processing link), so it stays "high" (audit finding F3, docs/TECHNICAL_VALIDATION.md).
    if action_kind == "apply_mfa" and level == "high":
        level = "medium"
    return {"relationship_id": r.id, "source": r.source, "target": r.target, "action": action_kind,
            "level": level, "legitimate_use": r.legitimate_use, "legitimate_use_ar": r.legitimate_use_ar,
            "business_critical": r.business_critical, "reversible": action_kind in REVERSIBLE_KINDS}


def apply_actions(env: Environment, actions: list[SimAction]) -> tuple[Environment, list[dict[str, Any]]]:
    """Apply actions to an isolated copy and return (copy, impacts).

    Copy-on-write: the copy gets its own relationship *list*, and a relationship object is cloned the first time an
    action needs to change it. Objects of the input environment are therefore never mutated (tests assert this), and
    large environments are not deep-copied for every simulated action. Assets are never modified by any action.
    """
    sim = env.model_copy(update={"relationships": list(env.relationships)})
    owned: set[str] = set()

    def own(rel_id: str) -> Relationship:
        for i, r in enumerate(sim.relationships):
            if r.id == rel_id:
                if rel_id not in owned:
                    r = r.model_copy()
                    sim.relationships[i] = r
                    owned.add(rel_id)
                return r
        raise SimulationError(f"unknown relationship: {rel_id}")

    impacts: list[dict[str, Any]] = []
    for act in actions:
        if isinstance(act, RemoveRelationship):
            r = _rel(sim, act.relationship_id)
            impacts.append(_impact_of(r, act.kind))
            sim.relationships = [x for x in sim.relationships if x.id != r.id]
        elif isinstance(act, DisableRelationship):
            r = own(act.relationship_id)
            if r.disabled:
                raise SimulationError(f"{r.id}: already disabled")
            r.disabled = True
            impacts.append(_impact_of(r, act.kind))
        elif isinstance(act, ReducePrivilege):
            r = own(act.relationship_id)
            if r.privilege not in (Privilege.admin, Privilege.write):
                raise SimulationError(f"{r.id}: privilege already minimal")
            r.privilege = Privilege.read
            impacts.append(_impact_of(r, act.kind))
        elif isinstance(act, ApplyMfa):
            _has_asset(sim, act.asset_id)
            # sorted: output must not depend on the order relationships happen to be listed in the input
            hit_ids = sorted(r.id for r in sim.relationships
                             if r.target == act.asset_id and r.type in (RelType.can_login, RelType.has_credentials))
            if not hit_ids:
                raise SimulationError(f"{act.asset_id}: no login/credential relationships to protect")
            for rid in hit_ids:
                r = own(rid)
                r.mfa_required = True
                impacts.append(_impact_of(r, act.kind))
        elif isinstance(act, ApplySegmentation):
            _has_asset(sim, act.asset_id)
            seg = sorted((r for r in sim.relationships
                          if r.target == act.asset_id and r.type is RelType.network_access), key=lambda r: r.id)
            if not seg:
                raise SimulationError(f"{act.asset_id}: no network paths to segment")
            for r in seg:
                impacts.append(_impact_of(r, act.kind))
            gone = {r.id for r in seg}
            sim.relationships = [r for r in sim.relationships if r.id not in gone]
    # No whole-model re-validation here: every action only removes relationships or flips flags/enum values on
    # relationships that already passed validation, so references cannot become inconsistent (and re-validating
    # thousands of relationships per simulated action dominated runtime on large environments).
    return sim, impacts


def simulate(env: Environment, actions: list[SimAction], baseline: dict[str, Any] | None = None,
             reach_before: dict[str, set[str]] | None = None) -> dict[str, Any]:
    before = baseline or analyze(env)
    sim_env, impacts = apply_actions(env, actions)
    after = analyze(sim_env)

    b_paths = {p["id"]: p for p in before["paths"]}
    a_paths = {p["id"]: p for p in after["paths"]}
    eliminated = [pid for pid in b_paths if pid not in a_paths]
    remaining = [pid for pid in a_paths if pid in b_paths]
    mitigated = [pid for pid in remaining if a_paths[pid]["score"] < b_paths[pid]["score"]]
    introduced = [pid for pid in a_paths if pid not in b_paths]  # should always be empty

    residual = []
    for pid in remaining:
        p = a_paths[pid]
        residual.append({
            "path_id": pid, "target": p["target"], "score": p["score"], "severity": p["severity"],
            "classification": p["classification"], "score_before": b_paths[pid]["score"],
            "reasons": [{"code": "still_reaches_sensitive_asset", "params": {"target": p["target"]}}]
            + ([{"code": "still_validated", "params": {}}] if p["classification"] == "validated" else []),
        })
    residual.sort(key=lambda x: (-x["score"], x["path_id"]))

    reach_b = reach_before if reach_before is not None else legitimate_reach(env)
    reach_a = legitimate_reach(sim_env)
    lost = [{"identity": ident, "asset": a}
            for ident, assets in sorted(reach_b.items())
            for a in sorted(assets - reach_a.get(ident, set()))]

    # Exact set of assets touched: endpoints of every changed relationship, plus identities/assets that lost reach.
    affected: list[str] = []
    for i in impacts:
        for aid in (i["source"], i["target"]):
            if aid not in affected:
                affected.append(aid)
    for l in lost:
        for aid in (l["identity"], l["asset"]):
            if aid not in affected:
                affected.append(aid)

    level = max((i["level"] for i in impacts), key=lambda lv: IMPACT_ORDER[lv], default="none")
    if lost and IMPACT_ORDER[level] < IMPACT_ORDER["medium"]:
        level = "medium"

    sb, sa = before["summary"], after["summary"]
    pct = round(100 * (sb["posture_score"] - sa["posture_score"]) / sb["posture_score"], 1) if sb["posture_score"] else 0.0
    return {
        "actions": [a.model_dump() for a in actions],
        "before": sb,
        "after": sa,
        "risk_reduction_pct": pct,  # change in posture index (mean of worst path per sensitive asset)
        "path_score_reduction_pct": round(
            100 * (sb["total_path_score"] - sa["total_path_score"]) / sb["total_path_score"], 1)
        if sb["total_path_score"] else 0.0,  # change in summed path scores
        "paths_eliminated": eliminated,
        "paths_mitigated": mitigated,
        "paths_remaining": remaining,
        "paths_introduced": introduced,
        "before_paths": before["paths"],
        "after_paths": after["paths"],
        "residual_risks": residual,
        "operational_impact": {
            "level": level,
            "affected_relationships": impacts,
            "affected_assets": affected,
            "lost_access": lost,
            "fully_reversible": bool(impacts) and all(i["reversible"] for i in impacts),
        },
        "note": "Simulation ran on an isolated copy; the baseline environment was not modified.",
    }
