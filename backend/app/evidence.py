"""Evidence explorer data: provenance of every relationship, summarised honestly.

All fields are DECLARED by whoever supplied the environment. ATHAR displays them, counts them and weights them in the
heuristic score, but never verifies, refreshes or upgrades them. In this MVP the environments are synthetic, so the
count of real-world-validated relationships is always zero by construction (the model rejects that value).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import EVIDENCE_RANK, Environment, RelType

STALE_AFTER_DAYS = 180


def evidence_overview(env: Environment, analysis: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    on_path: dict[str, int] = {}
    for p in analysis["paths"]:
        for rid in p["relationship_ids"]:
            on_path[rid] = on_path.get(rid, 0) + 1
    rows = []
    for r in sorted(env.relationships, key=lambda r: r.id):
        if r.type is RelType.protects:
            continue
        age = None
        if r.collected_at is not None:
            at = r.collected_at if r.collected_at.tzinfo else r.collected_at.replace(tzinfo=timezone.utc)
            age = max(0, (now - at).days)
        rows.append({
            "id": r.id, "source": r.source, "target": r.target, "type": r.type.value, "privilege": r.privilege.value,
            "evidence": r.evidence.value, "confidence": r.effective_confidence, "evidence_source": r.evidence_source,
            "collected_at": r.collected_at.isoformat() if r.collected_at else None, "age_days": age,
            "stale": age is not None and age > STALE_AFTER_DAYS, "validation": r.validation,
            "rationale": r.rationale, "rationale_ar": r.rationale_ar, "disabled": r.disabled,
            "attack_paths_through": on_path.get(r.id, 0),
        })
    by_evidence = {e.value: 0 for e in sorted(EVIDENCE_RANK, key=lambda e: -EVIDENCE_RANK[e])}
    by_validation: dict[str, int] = {"none": 0, "synthetic_exercise": 0, "real_world": 0}
    by_source: dict[str, int] = {}
    for x in rows:
        by_evidence[x["evidence"]] += 1
        by_validation[x["validation"]] += 1
        by_source[x["evidence_source"]] = by_source.get(x["evidence_source"], 0) + 1
    return {
        "relationships": rows,
        "summary": {
            "total": len(rows), "by_evidence": by_evidence, "by_validation": by_validation,
            "by_source": dict(sorted(by_source.items())),
            "undated": sum(1 for x in rows if x["collected_at"] is None), "stale": sum(1 for x in rows if x["stale"]),
            "stale_after_days": STALE_AFTER_DAYS,
            "on_attack_paths": sum(1 for x in rows if x["attack_paths_through"] > 0),
            "weak_on_paths": sum(1 for x in rows if x["attack_paths_through"] > 0 and x["evidence"] in ("inferred", "theoretical")),
        },
        "honesty": {"synthetic": True, "real_world_validated": 0, "declared_not_verified": True,
                    "classes": ["validated", "observed", "inferred", "theoretical"]},
    }
