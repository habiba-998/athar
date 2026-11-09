"""Sensitivity analysis of the heuristic scoring assumptions.

The scoring weights are documented ASSUMPTIONS, not calibrated values. This module measures how much ATHAR's outputs
move when those assumptions are wrong: (1) joint random perturbation of every weight within +-spread (seeded, so the same
request always gives the same answer) and (2) a one-at-a-time sweep showing which single assumption matters most.
It reports ranges and rank stability; it does not turn scores into probabilities and does not make the weights correct.
"""
from __future__ import annotations

import random
import statistics
from typing import Any

from .analysis import analyze, severity_for, use_config
from .models import ScoringConfig
from .recommendations import recommend_ex

DEFAULT_TRIALS = 16
MAX_TRIALS = 60
DEFAULT_SPREAD = 0.30
MAX_SPREAD = 0.50
DEFAULT_SEED = 1109
TOP_RECS = 10
TOP_PATHS = 20

PARAMS = ("evidence_observed", "evidence_inferred", "evidence_theoretical", "privilege_read", "privilege_write",
          "mfa_factor", "length_penalty", "exposure_bonus")
_BOUNDS = {"evidence_observed": (0.05, 1.0), "evidence_inferred": (0.05, 1.0), "evidence_theoretical": (0.05, 1.0),
           "privilege_read": (0.05, 1.0), "privilege_write": (0.05, 1.0), "mfa_factor": (0.05, 1.0),
           "length_penalty": (0.0, 0.5), "exposure_bonus": (1.0, 1.5)}


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def perturb(base: ScoringConfig, rnd: random.Random, spread: float) -> ScoringConfig:
    """Jointly scale every weight by an independent factor in [1-spread, 1+spread], preserving the ordering constraints."""
    f = lambda: rnd.uniform(1 - spread, 1 + spread)  # noqa: E731
    inferred = _clip(base.evidence_inferred * f(), 0.05, 1.0)
    theoretical = _clip(base.evidence_theoretical * f(), 0.05, inferred)
    read = _clip(base.privilege_read * f(), 0.05, 1.0)
    write = _clip(base.privilege_write * f(), read, 1.0)
    mfa = _clip(base.mfa_factor * f(), 0.05, 1.0)
    length = _clip(base.length_penalty * f(), 0.0, 0.5)
    exposure = _clip(base.exposure_bonus * f(), 1.0, 1.5)
    observed = _clip(base.evidence_observed * f(), inferred, 1.0)   # drawn last
    return ScoringConfig(evidence_observed=observed, evidence_inferred=inferred, evidence_theoretical=theoretical,
                         privilege_read=read, privilege_write=write, mfa_factor=mfa, length_penalty=length,
                         exposure_bonus=exposure)


def scale_one(base: ScoringConfig, name: str, factor: float) -> ScoringConfig:
    """Scale a single weight, clamped to its valid range and to its neighbours in the ordering constraints."""
    lo, hi = _BOUNDS[name]
    if name == "evidence_theoretical":
        hi = base.evidence_inferred
    elif name == "evidence_inferred":
        lo, hi = base.evidence_theoretical, base.evidence_observed
    elif name == "evidence_observed":
        lo = base.evidence_inferred
    elif name == "privilege_read":
        hi = base.privilege_write
    elif name == "privilege_write":
        lo = base.privilege_read
    value = round(_clip(getattr(base, name) * factor, lo, hi), 6)
    return base.model_copy(update={name: value})


def _snapshot(env, cfg: ScoringConfig) -> dict[str, Any]:
    with use_config(cfg):
        a = analyze(env)
        recs, _ = recommend_ex(env, a)
    return {"scores": {p["id"]: p["score"] for p in a["paths"]}, "order": [p["id"] for p in a["paths"]],
            "recs": [r["id"] for r in recs[:TOP_RECS]], "posture": a["summary"]["posture_score"]}


def _indicator(width: float) -> str:
    return "low" if width < 5 else ("medium" if width < 15 else "high")


def run_sensitivity(env, base_cfg: ScoringConfig, trials: int = DEFAULT_TRIALS, spread: float = DEFAULT_SPREAD,
                    seed: int = DEFAULT_SEED) -> dict[str, Any]:
    trials = max(1, min(trials, MAX_TRIALS))
    spread = max(0.01, min(spread, MAX_SPREAD))
    base = _snapshot(env, base_cfg)
    rnd = random.Random(seed)
    snaps = [_snapshot(env, perturb(base_cfg, rnd, spread)) for _ in range(trials)]

    ranks_by_path: dict[str, list[int]] = {pid: [] for pid in base["order"]}
    scores_by_path: dict[str, list[float]] = {pid: [base["scores"][pid]] for pid in base["order"]}
    for s in snaps:
        assert set(s["scores"]) == set(base["scores"]), "the attack-path set must not depend on the weights"
        for i, pid in enumerate(s["order"]):
            ranks_by_path[pid].append(i + 1)
            scores_by_path[pid].append(s["scores"][pid])
    paths = []
    for i, pid in enumerate(base["order"][:TOP_PATHS]):
        sc = scores_by_path[pid]
        sevs = {severity_for(x) for x in sc}
        paths.append({"id": pid, "rank": i + 1, "baseline": base["scores"][pid], "min": min(sc), "max": max(sc),
                      "median": round(statistics.median(sc), 1), "rank_min": min(ranks_by_path[pid]),
                      "rank_max": max(ranks_by_path[pid]), "severity_can_change": len(sevs) > 1,
                      "indicator": _indicator(max(sc) - min(sc))})

    recs = []
    for i, rid in enumerate(base["recs"]):
        pos = [s["recs"].index(rid) + 1 for s in snaps if rid in s["recs"]]
        present = 100 * len(pos) / trials
        top3 = 100 * sum(1 for p in pos if p <= 3) / trials
        stability = "stable" if top3 >= 90 else ("moderate" if top3 >= 60 else "sensitive")
        recs.append({"id": rid, "baseline_rank": i + 1, "rank_min": min(pos) if pos else None,
                     "rank_max": max(pos) if pos else None, "presence_pct": round(present, 1),
                     "top1_pct": round(100 * sum(1 for p in pos if p == 1) / trials, 1),
                     "top3_pct": round(top3, 1), "stability": stability})

    # One-at-a-time: which single assumption moves the posture index the most?
    params = []
    for name in PARAMS:
        lo_cfg, hi_cfg = scale_one(base_cfg, name, 1 - spread), scale_one(base_cfg, name, 1 + spread)
        lo, hi = _snapshot(env, lo_cfg), _snapshot(env, hi_cfg)
        params.append({"name": name, "baseline": getattr(base_cfg, name),
                       "low_value": getattr(lo_cfg, name), "high_value": getattr(hi_cfg, name),
                       "posture_at_low": lo["posture"], "posture_at_high": hi["posture"],
                       "posture_swing": round(abs(hi["posture"] - lo["posture"]), 1),
                       "top_recommendation_changes": (lo["recs"][:1] != base["recs"][:1]) or (hi["recs"][:1] != base["recs"][:1])})
    params.sort(key=lambda p: (-p["posture_swing"], p["name"]))

    postures = [s["posture"] for s in snaps] + [base["posture"]]
    return {
        "method": "seeded_joint_perturbation_and_one_at_a_time",
        "trials": trials, "spread": spread, "seed": seed,
        "config": base_cfg.model_dump(),
        "posture": {"baseline": base["posture"], "min": min(postures), "max": max(postures)},
        "paths": paths,
        "recommendations": recs,
        "parameters": params,
        "top_recommendation_unchanged_pct": round(100 * sum(1 for s in snaps if s["recs"][:1] == base["recs"][:1]) / trials, 1),
        "highest_path_unchanged_pct": round(100 * sum(1 for s in snaps if s["order"][:1] == base["order"][:1]) / trials, 1),
        "not_a_probability": True,
        "note": "Ranges describe how much the heuristic index moves if the assumptions change; they are not confidence intervals.",
    }
