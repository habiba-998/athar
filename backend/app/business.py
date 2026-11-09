"""Business-impact intelligence: which business services depend on the access a defensive change would touch.

Everything here is derived from data the author declared (services, `supports_services`, `business_critical`,
`recovery_hours`, `rto_hours`). ATHAR does not observe real dependencies or measure real outage cost: the output is a
triage aid for a human approver. Security and business needs are reported side by side; nothing in this module prefers
"eliminate every path" over keeping a service running.
"""
from __future__ import annotations

from typing import Any

from .models import Environment, Relationship, SimAction

# Relative implementation effort per action (abstract units, documented assumption, not hours).
EFFORT = {"disable_relationship": 1, "remove_relationship": 1, "reduce_privilege": 2, "apply_mfa": 3, "apply_segmentation": 4}

# How a defensive action affects a service that relies on the touched relationship.
EFFECT_OF_ACTION = {"remove_relationship": "interrupted", "disable_relationship": "interrupted",
                    "apply_segmentation": "interrupted", "reduce_privilege": "degraded", "apply_mfa": "friction"}
EFFECT_WEIGHT = {"interrupted": 1.0, "degraded": 0.5, "friction": 0.15}
EFFECT_ORDER = {"friction": 0, "degraded": 1, "interrupted": 2}
ROLLBACK_KINDS = {"disable_relationship", "reduce_privilege", "apply_mfa"}  # reversible: undone by re-enabling / restoring


def effort_of(actions: list[SimAction]) -> int:
    return sum(EFFORT[a.kind] for a in actions)


def service_dependencies(env: Environment, analysis: dict[str, Any]) -> list[dict[str, Any]]:
    """For every declared service: the relationships it relies on, and which of them currently sit on attack paths."""
    on_path: dict[str, int] = {}
    for p in analysis["paths"]:
        for rid in p["relationship_ids"]:
            on_path[rid] = on_path.get(rid, 0) + 1
    rels_by_service: dict[str, list[Relationship]] = {s.id: [] for s in env.services}
    for r in env.relationships:
        for sid in r.supports_services:
            rels_by_service[sid].append(r)
    out = []
    for s in sorted(env.services, key=lambda s: s.id):
        rels = sorted(rels_by_service[s.id], key=lambda r: r.id)
        out.append({
            "id": s.id, "name": s.name, "name_ar": s.name_ar, "criticality": s.criticality, "rto_hours": s.rto_hours,
            "description": s.description, "description_ar": s.description_ar,
            "access_requirements": [
                {"relationship_id": r.id, "source": r.source, "target": r.target, "type": r.type.value,
                 "privilege": r.privilege.value, "legitimate_use": r.legitimate_use, "legitimate_use_ar": r.legitimate_use_ar,
                 "business_critical": r.business_critical, "disabled": r.disabled,
                 "attack_paths_through": on_path.get(r.id, 0), "recovery_hours": r.recovery_hours}
                for r in rels],
            "exposed_dependencies": sum(1 for r in rels if on_path.get(r.id, 0) > 0),
        })
    return out


def service_impact(env: Environment, impacts: list[dict[str, Any]]) -> dict[str, Any]:
    """Services affected by a simulated change, given its `operational_impact.affected_relationships`.

    `recovery`: `rollback` for reversible actions (re-enable / restore); for removals and segmentation the declared
    `recovery_hours` of the relationship (the worst across the service's touched relationships), or `unknown`.
    `rto_status` compares that to the service's declared RTO; `unknown` is never silently treated as fine.
    """
    rels = {r.id: r for r in env.relationships}
    svc = {s.id: s for s in env.services}
    per: dict[str, dict[str, Any]] = {}
    for imp in impacts:
        r = rels.get(imp["relationship_id"])
        if r is None:
            continue
        effect = EFFECT_OF_ACTION[imp["action"]]
        for sid in r.supports_services:
            d = per.setdefault(sid, {"effect": effect, "relationships": set(), "rollback": True, "hours": [], "unknown": False})
            if EFFECT_ORDER[effect] > EFFECT_ORDER[d["effect"]]:
                d["effect"] = effect
            d["relationships"].add(r.id)
            if imp["action"] not in ROLLBACK_KINDS:
                d["rollback"] = False
                if r.recovery_hours is None:
                    d["unknown"] = True
                else:
                    d["hours"].append(r.recovery_hours)
    rows = []
    for sid in sorted(per):
        s, d = svc[sid], per[sid]
        if d["effect"] == "friction" or (d["rollback"] and not d["unknown"]):
            recovery, hours = "rollback", 0.0
        elif d["unknown"]:
            recovery, hours = "unknown", None
        else:
            recovery, hours = "reprovision", max(d["hours"]) if d["hours"] else 0.0
        if d["effect"] == "friction":
            rto = "not_applicable"
        elif hours is None:
            rto = "unknown"
        else:
            rto = "exceeds" if hours > s.rto_hours else "within"
        rows.append({"service_id": sid, "name": s.name, "name_ar": s.name_ar, "criticality": s.criticality,
                     "rto_hours": s.rto_hours, "effect": d["effect"], "relationships": sorted(d["relationships"]),
                     "recovery": recovery, "recovery_hours": hours, "rto_status": rto})
    rows.sort(key=lambda x: (-x["criticality"], -EFFECT_ORDER[x["effect"]], x["service_id"]))
    total = sum(s.criticality / 5 for s in env.services)
    index = 100 * sum(r["criticality"] / 5 * EFFECT_WEIGHT[r["effect"]] for r in rows) / total if total else 0.0
    return {
        "services": rows,
        "business_impact_index": round(index, 1),   # 0-100 share of service criticality affected (weighted by effect)
        "services_interrupted": sum(1 for r in rows if r["effect"] == "interrupted"),
        "critical_services_interrupted": sum(1 for r in rows if r["effect"] == "interrupted" and r["criticality"] >= 4),
        "rto_exceeded": sum(1 for r in rows if r["rto_status"] == "exceeds"),
        "rto_unknown": sum(1 for r in rows if r["rto_status"] == "unknown"),
        "services_declared": len(env.services),
    }


def approvals_for(actions: list[SimAction], operational: dict[str, Any], business: dict[str, Any]) -> list[dict[str, Any]]:
    """Which human sign-offs a change would need. ATHAR never applies changes: this is a checklist for the people who do."""
    if not actions:
        return []
    why_service = []
    if business["services"]:
        why_service.append("services_affected")
    if any(i["business_critical"] for i in operational["affected_relationships"]):
        why_service.append("business_critical_access")
    if operational["lost_access"]:
        why_service.append("legitimate_access_lost")
    why_board = []
    if operational["level"] == "high":
        why_board.append("high_operational_impact")
    if not operational["fully_reversible"]:
        why_board.append("not_fully_reversible")
    if business["rto_exceeded"] or business["rto_unknown"]:
        why_board.append("recovery_vs_rto")
    out = [{"role": "security_owner", "why": ["every_change_requires_human_approval"]}]
    if why_service:
        out.append({"role": "service_owner", "why": why_service})
    if why_board:
        out.append({"role": "change_board", "why": why_board})
    return out
