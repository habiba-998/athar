"""Evaluation harness: measurable remediation scenarios on the shipped synthetic environments.

Run from the backend folder:   python ../scripts/evaluate.py
Writes docs/evaluation/RESULTS.md and docs/evaluation/results.json. Every number is computed by the engine in this
repository on the synthetic scenarios in ../scenarios; nothing is estimated, sampled from real data, or hand-edited.
The only randomness is the seeded random-removal baseline. The whole evaluation is run twice and must be identical.

What it measures, per scenario
  1. Baseline: attack paths, evidence classes, severity, posture, worst path per sensitive asset.
  2. Remediation curve: ATHAR's recommendations applied one at a time (re-recommended after each step),
     with paths, validated paths, posture, residual risk, operational impact and reversibility after every step.
  3. Quality of the recommendations (only within the model): the same number of removals chosen by
       - ATHAR (greedy, remove-only so the comparison is like-for-like),
       - a naive static heuristic (remove the relationships that appear on the most paths),
       - random relationships that lie on attack paths (seeded, 500 trials: a deliberately favourable random baseline),
       - the exhaustive optimum for small k (best possible reduction in remaining paths),
     and the minimum number of removals that would cut every path (graph min-cut) versus the steps ATHAR needed.
Limits: "optimal" and "random" are relative to the model's own path set; this does not measure real-world risk.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import os
import random
import statistics
import sys
from pathlib import Path

os.environ.setdefault("ATHAR_DB", ":memory:")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))

import networkx as nx  # noqa: E402
from pydantic import TypeAdapter  # noqa: E402

from app.analysis import SENSITIVE_TYPES, analyze, build_graph, legitimate_reach  # noqa: E402
from app.data.demo import build_demo_environment  # noqa: E402
from app.data.scenario_harbor import build_harbor_environment  # noqa: E402
from app.models import AssetType, Environment, RemoveRelationship, SimAction  # noqa: E402
from app.recommendations import recommend_ex  # noqa: E402
from app.simulation import apply_actions, simulate  # noqa: E402

ADAPTER = TypeAdapter(SimAction)
SCENARIOS = {"acme-sample": ("Acme Synthetic Corp (sample, 15 assets)", build_demo_environment),
             "harbor-logistics": ("Harbor Synthetic Logistics (34 assets)", build_harbor_environment)}
MAX_STEPS = 8
RANDOM_TRIALS = 500
RANDOM_SEED = 20261109
OUT = HERE.parent / "docs" / "evaluation"


# ----------------------------------------------------------------------------- helpers
def name(env: Environment, aid: str) -> str:
    return next(a.name for a in env.assets if a.id == aid)


def describe(env: Environment, action: dict) -> str:
    rels = {r.id: r for r in env.relationships}
    if "relationship_id" in action:
        r = rels[action["relationship_id"]]
        return f"{action['kind']} {r.id}: {name(env, r.source)} -[{r.type.value}]-> {name(env, r.target)}"
    return f"{action['kind']}: {name(env, action['asset_id'])}"


def summary(a: dict) -> dict:
    s = a["summary"]
    return {k: s[k] for k in ("attack_paths", "validated_paths", "posture_score", "total_path_score", "max_path_score", "severity_distribution")}


def lost_pairs(base: Environment, cur: Environment) -> int:
    rb, rc = legitimate_reach(base), legitimate_reach(cur)
    return sum(len(rb[i] - rc.get(i, set())) for i in rb)


def bc_touched(base: Environment, cur: Environment) -> int:
    """Business-critical relationships that no longer exist or are disabled/MFA-constrained/downgraded in `cur`."""
    now = {r.id: r for r in cur.relationships}
    n = 0
    for r in base.relationships:
        if not r.business_critical:
            continue
        c = now.get(r.id)
        if c is None or c.disabled != r.disabled or c.mfa_required != r.mfa_required or c.privilege != r.privilege:
            n += 1
    return n


def greedy(base: Environment, kinds: set[str] | None, business_safe: bool = False) -> tuple[list[dict], Environment]:
    """Apply ATHAR's top recommendation (optionally restricted to action kinds), re-analyse, repeat.

    `business_safe` refuses any step whose operational impact is "high" (it touches a business-critical relationship),
    which is how a real team would have to operate: eliminating every path by cutting business-critical access is not a
    defence, so the residual risk of the business-safe plan is the number that matters.
    Returns (steps, final environment).
    """
    cur, steps = base, []
    for i in range(1, MAX_STEPS + 1):
        a = analyze(cur)
        if a["summary"]["attack_paths"] == 0:
            break
        recs, _ = recommend_ex(cur, a)
        pick = next((r for r in recs if (kinds is None or r["action"]["kind"] in kinds) and not (business_safe and r["tradeoff"] == "high")), None)
        if pick is None:
            break
        action = ADAPTER.validate_python(pick["action"])
        nxt, _ = apply_actions(cur, [action])
        res = simulate(cur, [action], baseline=a)
        after = analyze(nxt)
        steps.append({
            "step": i, "action": describe(cur, pick["action"]), "kind": pick["action"]["kind"],
            "paths": after["summary"]["attack_paths"], "validated": after["summary"]["validated_paths"],
            "posture": after["summary"]["posture_score"], "total_score": after["summary"]["total_path_score"],
            "step_impact": res["operational_impact"]["level"], "step_reversible": res["operational_impact"]["fully_reversible"],
            "cum_lost_access_pairs": lost_pairs(base, nxt), "cum_business_critical_touched": bc_touched(base, nxt),
        })
        cur = nxt
    return steps, cur


# ---- fast, exact evaluation of removal sets (removal never creates paths or changes surviving scores: tests/test_validation.py)
class PathIndex:
    def __init__(self, env: Environment):
        a = analyze(env)
        self.env = env
        self.paths = [(frozenset(p["relationship_ids"]), p["score"], p["target"]) for p in a["paths"]]
        self.targets = list(a["worst_by_target"])
        self.on_path = sorted({rid for ids, _, _ in self.paths for rid in ids})
        self.freq = {rid: sum(rid in ids for ids, _, _ in self.paths) for rid in self.on_path}

    def after(self, removed: frozenset[str]) -> tuple[int, float, float]:
        alive = [(s, t) for ids, s, t in self.paths if not (ids & removed)]
        worst = {t: 0.0 for t in self.targets}
        for s, t in alive:
            worst[t] = max(worst[t], s)
        posture = round(sum(worst.values()) / len(worst), 1) if worst else 0.0
        return len(alive), round(sum(s for s, _ in alive), 1), posture

    def lost(self, removed: frozenset[str]) -> int:
        cur, _ = apply_actions(self.env, [RemoveRelationship(relationship_id=r) for r in sorted(removed)])
        return lost_pairs(self.env, cur)

    def bc(self, removed: frozenset[str]) -> int:
        rels = {r.id: r for r in self.env.relationships}
        return sum(rels[r].business_critical for r in removed)


def min_cut_size(env: Environment) -> int:
    """Smallest number of relationships whose removal disconnects every compromised source from every sensitive target
    (any path length; the engine's 6-hop limit is ignored, so this is an upper bound on what the hop-limited model needs)."""
    g = build_graph(env)
    h = nx.DiGraph()
    for u, v, d in g.edges(data=True):
        h.add_edge(u, v, capacity=1)
    sources = [a.id for a in env.assets if a.compromised]
    targets = [a.id for a in env.assets if a.criticality >= 4 and a.type in SENSITIVE_TYPES and not a.compromised]
    for s in sources:
        h.add_edge("__S__", s)          # no capacity attribute => infinite
    for t in targets:
        h.add_edge(t, "__T__")
    if "__S__" not in h or "__T__" not in h or not nx.has_path(h, "__S__", "__T__"):
        return 0
    return int(nx.minimum_cut_value(h, "__S__", "__T__"))


def compare(env: Environment, idx: PathIndex, greedy_removes: list[dict]) -> list[dict]:
    rows = []
    rnd = random.Random(RANDOM_SEED)
    freq_order = sorted(idx.on_path, key=lambda r: (-idx.freq[r], r))
    for k in range(1, min(len(greedy_removes), 4) + 1):
        athar = frozenset(s["action"].split(" ")[1].rstrip(":") for s in greedy_removes[:k])
        static = frozenset(freq_order[:k])
        samples = [frozenset(rnd.sample(idx.on_path, min(k, len(idx.on_path)))) for _ in range(RANDOM_TRIALS)]
        rem = [idx.after(s)[0] for s in samples]
        lost = [idx.lost(s) for s in samples[:100]]
        row = {
            "k": k,
            "athar": {"remaining": idx.after(athar)[0], "posture": idx.after(athar)[2], "lost_access": idx.lost(athar), "business_critical": idx.bc(athar)},
            "static_frequency": {"remaining": idx.after(static)[0], "posture": idx.after(static)[2], "lost_access": idx.lost(static), "business_critical": idx.bc(static)},
            "random": {"remaining_mean": round(statistics.mean(rem), 1), "remaining_min": min(rem), "remaining_max": max(rem),
                       "remaining_median": statistics.median(rem), "lost_access_mean": round(statistics.mean(lost), 2)},
            "optimal": None,
        }
        combos = math.comb(len(idx.on_path), k)
        if combos <= 60000:
            best = min((idx.after(frozenset(c))[0], idx.after(frozenset(c))[1], idx.bc(frozenset(c)), tuple(sorted(c))) for c in itertools.combinations(idx.on_path, k))
            bs = frozenset(best[3])
            row["optimal"] = {"remaining": best[0], "posture": idx.after(bs)[2], "lost_access": idx.lost(bs), "business_critical": idx.bc(bs), "combinations_checked": combos}
        rows.append(row)
    return rows


# ----------------------------------------------------------------------------- run
def evaluate() -> dict:
    out: dict = {"max_steps": MAX_STEPS, "random_trials": RANDOM_TRIALS, "random_seed": RANDOM_SEED, "scenarios": {}}
    for key, (title, build) in SCENARIOS.items():
        env = build()
        a = analyze(env)
        idx = PathIndex(env)
        classes: dict[str, int] = {}
        for p in a["paths"]:
            classes[p["classification"]] = classes.get(p["classification"], 0) + 1
        g_all, final_all = greedy(env, None)
        g_rm, _ = greedy(env, {"remove_relationship"})
        g_safe, final_safe = greedy(env, None, business_safe=True)
        out["scenarios"][key] = {
            "title": title, "assets": len(env.assets), "relationships": len(env.relationships),
            "baseline": {**summary(a), "classes": classes, "worst_by_target": dict(sorted(a["worst_by_target"].items(), key=lambda kv: (-kv[1], kv[0]))),
                         "compromised_sources": [x.id for x in env.assets if x.compromised],
                         "relationships_on_attack_paths": len(idx.on_path)},
            "greedy_all_actions": g_all,
            "greedy_remove_only": g_rm,
            "greedy_business_safe": g_safe,
            "comparison": compare(env, idx, g_rm),
            "min_cut": min_cut_size(env),
            "residual_after_all_actions": _residual(env, final_all),
            "residual_business_safe": _residual(env, final_safe),
        }
    return out


def _residual(env: Environment, final: Environment) -> list[dict]:
    """What is still reachable after a plan (top 8 by score), named from the original environment."""
    return [{"route": " > ".join(name(env, n) for n in p["nodes"]), "score": p["score"], "severity": p["severity"], "evidence": p["classification"]}
            for p in analyze(final)["paths"][:8]]


# ----------------------------------------------------------------------------- markdown
def md(res: dict) -> str:
    L: list[str] = []
    L += ["# Evaluation results", "",
          "_Generated by `scripts/evaluate.py` from the scenarios in `scenarios/`. Every number below is computed by this repository's engine; "
          "re-running the script reproduces them exactly (the script runs the whole evaluation twice and fails if the results differ). "
          "All data is synthetic, so these results describe the model's behaviour on invented environments, not real-world risk._", ""]
    for key, sc in res["scenarios"].items():
        b = sc["baseline"]
        L += [f"## {sc['title']}", "",
              f"{sc['assets']} assets, {sc['relationships']} relationships; assumed-breach starting points: {', '.join(f'`{x}`' for x in b['compromised_sources'])}. "
              f"{b['relationships_on_attack_paths']} relationships lie on at least one attack path.", "",
              "### 1. Baseline", "",
              "| Metric | Value |", "|---|---|",
              f"| Attack paths | {b['attack_paths']} (validated {b['classes'].get('validated', 0)}, inferred {b['classes'].get('inferred', 0)}, theoretical {b['classes'].get('theoretical', 0)}) |",
              f"| Severity (critical / high / medium / low) | {' / '.join(str(b['severity_distribution'][k]) for k in ('critical', 'high', 'medium', 'low'))} |",
              f"| Posture index | {b['posture_score']} |", f"| Highest path score | {b['max_path_score']} |", f"| Summed path score | {b['total_path_score']} |", "",
              "Worst path per sensitive asset:", "", "| Sensitive asset | Worst path score |", "|---|---|"]
        L += [f"| `{t}` | {s} |" for t, s in b["worst_by_target"].items()]
        for title, steps in (("ATHAR recommendations applied one at a time (all action types)", sc["greedy_all_actions"]),
                             ("Same, restricted to remove-permission actions", sc["greedy_remove_only"]),
                             ("BUSINESS-SAFE plan: all action types, but any step with high operational impact is refused", sc["greedy_business_safe"])):
            L += ["", f"### 2. Remediation curve: {title}", "",
                  "| Step | Change applied | Paths | Validated | Posture | Σ score | Step impact | Reversible | Cum. lost access | Cum. business-critical touched |", "|---|---|---|---|---|---|---|---|---|---|"]
            L += [f"| 0 | (baseline) | {b['attack_paths']} | {b['validated_paths']} | {b['posture_score']} | {b['total_path_score']} | | | 0 | 0 |"]
            L += [f"| {s['step']} | {s['action']} | {s['paths']} | {s['validated']} | {s['posture']} | {s['total_score']} | {s['step_impact']} | {'yes' if s['step_reversible'] else 'no'} | {s['cum_lost_access_pairs']} | {s['cum_business_critical_touched']} |" for s in steps]
        L += ["", "Residual attack paths after the all-action plan (top by score). Note that reaching zero may require cutting business-critical access (see the *Step impact* and *Cum. business-critical touched* columns above):", ""]
        L += ([f"- {r['route']}: {r['score']} ({r['severity']}, {r['evidence']})" for r in sc["residual_after_all_actions"]] or ["- none"])
        L += ["", "**Residual risk of the business-safe plan** (what remains if no business-critical access may be cut), top by score:", ""]
        L += ([f"- {r['route']}: {r['score']} ({r['severity']}, {r['evidence']})" for r in sc["residual_business_safe"]] or ["- none"])
        L += ["", "### 3. Quality of the choices (same number of removals, model-internal)", "",
              "| k | ATHAR remaining | static-frequency remaining | random mean [min–max] | optimal remaining | ATHAR lost access | optimal lost access | ATHAR business-critical removed |", "|---|---|---|---|---|---|---|---|"]
        for c in sc["comparison"]:
            o = c["optimal"]
            L += [f"| {c['k']} | {c['athar']['remaining']} | {c['static_frequency']['remaining']} | {c['random']['remaining_mean']} [{c['random']['remaining_min']}–{c['random']['remaining_max']}] | "
                  f"{o['remaining'] if o else 'n/a'} | {c['athar']['lost_access']} | {o['lost_access'] if o else 'n/a'} | {c['athar']['business_critical']} |"]
        steps_rm = sc["greedy_remove_only"]
        zero = next((s['step'] for s in steps_rm if s['paths'] == 0), None)
        L += ["", f"Minimum number of relationship removals that would cut **every** path (graph min-cut, any length): **{sc['min_cut']}**. "
              f"ATHAR remove-only greedy reached zero paths in: {zero if zero else 'not within ' + str(res['max_steps']) + ' steps'}.", ""]
    L += ["## How to read this", "",
          "- *Remaining* is the number of attack paths left after the changes; lower is better. *Lost access* counts (identity, asset) pairs of legitimate identities that lose reachability.",
          "- *Optimal* is found by exhaustive search over relationships on attack paths (minimum remaining paths, ties broken by lower summed remaining score then fewer business-critical relationships). It is only computed where the search is small.",
          "- *Random* picks relationships uniformly among those lying on attack paths (a favourable baseline: random over all relationships would do worse).",
          "- These comparisons show how well ATHAR's ranking performs *inside its own model*. They are not a measurement of real-world risk reduction.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    first = evaluate()
    second = evaluate()
    blob1, blob2 = json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True)
    if blob1 != blob2:
        sys.exit("NON-DETERMINISTIC: two runs of the evaluation differ")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(first, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    (OUT / "RESULTS.md").write_text(md(first), encoding="utf-8", newline="\n")
    print("evaluation complete; two runs identical; sha256 =", hashlib.sha256(blob1.encode()).hexdigest()[:16])
    for key, sc in first["scenarios"].items():
        b = sc["baseline"]
        print(f"{key}: baseline {b['attack_paths']} paths, posture {b['posture_score']}; all-action plan: "
              + " -> ".join(str(s["paths"]) for s in sc["greedy_all_actions"]) + "; business-safe plan: "
              + " -> ".join(str(s["paths"]) for s in sc["greedy_business_safe"]) + f"; min-cut {sc['min_cut']}")
