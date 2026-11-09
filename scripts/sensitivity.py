"""Sensitivity analysis of the scoring weights.

ATHAR's weights (evidence, privilege, MFA, length, exposure) are documented modelling ASSUMPTIONS, not calibrated
values. This script asks: if those assumptions were wrong by up to +-30%, would ATHAR's conclusions change?

Run from the backend folder:  python ../scripts/sensitivity.py
Writes docs/evaluation/SENSITIVITY.md. Seeded and reproducible.

Method: in each trial every weight is multiplied by an independent factor drawn from U(0.7, 1.3) (then clipped to its
valid range; theoretical <= inferred <= validated = 1.0 is preserved). The attack-path SET never changes (it depends
only on the graph), so the ranking of the same paths is compared with the baseline ranking:
  * Kendall tau-b between baseline and perturbed scores (1.0 = identical ordering),
  * whether the single highest-scoring path is unchanged, and the overlap of the top-3,
  * whether ATHAR's #1 recommendation is unchanged, and the overlap of the top-3 recommendations.
"""
from __future__ import annotations

import itertools
import os
import random
import statistics
import sys
from pathlib import Path

os.environ.setdefault("ATHAR_DB", ":memory:")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))

import app.analysis as an  # noqa: E402
from app.data.demo import build_demo_environment  # noqa: E402
from app.data.scenario_harbor import build_harbor_environment  # noqa: E402
from app.models import ScoringConfig  # noqa: E402
from app.recommendations import recommend  # noqa: E402

TRIALS = 200
SPREAD = 0.30
SEED = 1109
BASE = an.DEFAULT_CONFIG


def clip(x, lo, hi):
    return max(lo, min(hi, x))


def perturb(rnd: random.Random) -> ScoringConfig:
    f = lambda: rnd.uniform(1 - SPREAD, 1 + SPREAD)  # noqa: E731
    inferred = clip(BASE.evidence_inferred * f(), 0.05, 1.0)
    theoretical = clip(BASE.evidence_theoretical * f(), 0.05, inferred)          # keep theoretical <= inferred <= validated
    read = clip(BASE.privilege_read * f(), 0.05, 1.0)
    write = clip(BASE.privilege_write * f(), read, 1.0)                           # the model requires read <= write
    mfa = clip(BASE.mfa_factor * f(), 0.05, 1.0)
    length = clip(BASE.length_penalty * f(), 0.0, 0.5)
    exposure = clip(BASE.exposure_bonus * f(), 1.0, 1.5)
    observed = clip(BASE.evidence_observed * f(), inferred, 1.0)                  # drawn last: earlier draws stay identical
    return ScoringConfig(evidence_observed=observed, evidence_inferred=inferred, evidence_theoretical=theoretical,
                         privilege_read=read, privilege_write=write, mfa_factor=mfa, length_penalty=length, exposure_bonus=exposure)


def kendall_tau_b(x: list[float], y: list[float]) -> float:
    n = len(x)
    conc = disc = tx = ty = 0
    for i, j in itertools.combinations(range(n), 2):
        dx, dy = x[i] - x[j], y[i] - y[j]
        if dx == 0 and dy == 0:
            continue
        if dx == 0:
            tx += 1
        elif dy == 0:
            ty += 1
        elif dx * dy > 0:
            conc += 1
        else:
            disc += 1
    denom = ((conc + disc + tx) * (conc + disc + ty)) ** 0.5
    return (conc - disc) / denom if denom else 1.0


def snapshot(env, cfg: ScoringConfig):
    with an.use_config(cfg):
        a = an.analyze(env)
        scores = {p["id"]: p["score"] for p in a["paths"]}
        order = [p["id"] for p in a["paths"]]
        recs = [r["id"] for r in recommend(env, a)]
        return scores, order, recs, a["summary"]["posture_score"]


def run_one(title: str, env) -> list[str]:
    base_scores, base_order, base_recs, base_posture = snapshot(env, BASE)
    ids = sorted(base_scores)
    rnd = random.Random(SEED)
    taus, top1, top3, rec1, rec3, postures = [], 0, [], 0, [], []
    for _ in range(TRIALS):
        scores, order, recs, posture = snapshot(env, perturb(rnd))
        assert set(scores) == set(base_scores), "path set must not depend on weights"
        taus.append(kendall_tau_b([base_scores[i] for i in ids], [scores[i] for i in ids]))
        top1 += order[0] == base_order[0]
        top3.append(len(set(order[:3]) & set(base_order[:3])) / 3)
        rec1 += recs[0] == base_recs[0]
        rec3.append(len(set(recs[:3]) & set(base_recs[:3])) / 3)
        postures.append(posture)
    q =lambda xs, p: sorted(xs)[int(p * (len(xs) - 1))]  # noqa: E731
    return [f"### {title}", "",
            f"{len(base_scores)} attack paths; baseline posture {base_posture}; {TRIALS} trials, weights varied by up to ±{int(SPREAD * 100)}%.", "",
            "| Question | Result |", "|---|---|",
            f"| Ordering of all paths vs baseline (Kendall τ-b) | mean {statistics.mean(taus):.3f}, 5th percentile {q(taus, 0.05):.3f}, worst {min(taus):.3f} |",
            f"| Highest-scoring path unchanged | {100 * top1 / TRIALS:.0f}% of trials |",
            f"| Top-3 paths: average overlap with baseline | {100 * statistics.mean(top3):.0f}% |",
            f"| ATHAR's #1 recommendation unchanged | {100 * rec1 / TRIALS:.0f}% of trials (`{base_recs[0]}`) |",
            f"| Top-3 recommendations: average overlap | {100 * statistics.mean(rec3):.0f}% |",
            f"| Posture index range across trials | {min(postures)} – {max(postures)} (baseline {base_posture}) |", ""]


if __name__ == "__main__":
    out = ["# Sensitivity of the scoring weights", "",
           "_Generated by `scripts/sensitivity.py` (seeded, reproducible). The scoring weights are modelling assumptions, so this measures how much "
           "ATHAR's rankings and recommendations depend on them. It does not make the weights correct._", ""]
    for title, build in (("Acme Synthetic Corp (sample)", build_demo_environment), ("Harbor Synthetic Logistics", build_harbor_environment)):
        out += run_one(title, build())
    out += ["## Reading this", "",
            "- The set of attack paths is fixed by the graph; only their *scores and ranking* depend on the weights.",
            "- τ-b of 1.0 means the ordering is identical; values around 0.75–0.85 mean moderate re-ordering between similar paths.",
            "- The stability of the **#1 recommendation** measures whether the *structural* conclusion (which relationship is the chokepoint) survives different weights. "
            "That conclusion comes from the graph, so it is expected to be more robust than the numbers.",
            "- **Absolute values are assumption-dependent.** The posture index and the identity of the single highest-scoring path can move noticeably with the weights "
            "(see the ranges above). Compare scores only within one scoring configuration, treat them as a prioritisation aid rather than a measurement, "
            "and calibrate the weights on real data before relying on absolute values.",
            "- Robustness here is a property of two synthetic environments; it is not evidence that the weights match real attacker behaviour.", ""]
    path = HERE.parent / "docs" / "evaluation" / "SENSITIVITY.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out), encoding="utf-8", newline="\n")
    print("\n".join(out))
