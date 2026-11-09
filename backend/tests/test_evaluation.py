"""The evaluation and sensitivity scripts: reproducible, internally consistent, and the committed results are current."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def results():
    ev = load("evaluate")
    return ev, ev.evaluate()


def test_evaluation_is_reproducible_and_the_committed_results_are_current(results):
    ev, first = results
    again = ev.evaluate()
    assert json.dumps(first, sort_keys=True) == json.dumps(again, sort_keys=True)
    committed = json.loads((ROOT / "docs" / "evaluation" / "results.json").read_text(encoding="utf-8"))
    assert json.dumps(first, sort_keys=True) == json.dumps(committed, sort_keys=True), "run scripts/evaluate.py and commit docs/evaluation/*"
    assert (ROOT / "docs" / "evaluation" / "RESULTS.md").read_text(encoding="utf-8") == ev.md(first)


def test_remediation_curves_never_get_worse_and_start_from_the_baseline(results):
    _, res = results
    for sc in res["scenarios"].values():
        for plan in ("greedy_all_actions", "greedy_remove_only", "greedy_business_safe"):
            paths = [sc["baseline"]["attack_paths"]] + [s["paths"] for s in sc[plan]]
            assert paths == sorted(paths, reverse=True), (plan, paths)
            totals = [sc["baseline"]["total_path_score"]] + [s["total_score"] for s in sc[plan]]
            assert totals == sorted(totals, reverse=True)
            # cumulative operational cost is monotone as well
            lost = [s["cum_lost_access_pairs"] for s in sc[plan]]
            assert lost == sorted(lost)


def test_the_business_safe_plan_never_takes_a_high_impact_step_and_keeps_a_residual(results):
    _, res = results
    for key, sc in res["scenarios"].items():
        assert all(s["step_impact"] != "high" for s in sc["greedy_business_safe"]), key
        assert sc["greedy_business_safe"][-1]["paths"] > 0, f"{key}: if nothing remained, the business-safe plan would not need qualifying"
        assert sc["residual_business_safe"], key
        # while the unconstrained plan reaches zero only by touching business-critical access
        assert sc["greedy_all_actions"][-1]["paths"] == 0
        assert sc["greedy_all_actions"][-1]["cum_business_critical_touched"] >= 1


def test_athar_is_never_better_than_the_exhaustive_optimum_and_beats_random_and_static_choices(results):
    _, res = results
    for key, sc in res["scenarios"].items():
        for c in sc["comparison"]:
            if c["optimal"]:
                assert c["optimal"]["remaining"] <= c["athar"]["remaining"], (key, c["k"])      # sanity: nothing beats the optimum
            assert c["athar"]["remaining"] <= c["random"]["remaining_mean"], (key, c["k"])
            assert c["athar"]["remaining"] <= c["static_frequency"]["remaining"], (key, c["k"])


def test_min_cut_is_a_lower_bound_on_the_removals_needed_to_cut_every_path(results):
    _, res = results
    for key, sc in res["scenarios"].items():
        steps_to_zero = next(s["step"] for s in sc["greedy_remove_only"] if s["paths"] == 0)
        assert 1 <= sc["min_cut"] <= steps_to_zero, key


def test_sensitivity_script_runs_and_the_path_set_never_depends_on_the_weights(monkeypatch):
    sens = load("sensitivity")
    monkeypatch.setattr(sens, "TRIALS", 6)                       # the script itself asserts the path set is weight-independent
    rows = sens.run_one("test", sens.build_demo_environment())
    assert any("Kendall" in r for r in rows)
    # the active configuration is back to the documented defaults afterwards
    import app.analysis as an
    cfg = an.active_config()
    assert cfg.mfa_factor == 0.35 and cfg.exposure_bonus == 1.1 and cfg.length_penalty == 0.1


def test_kendall_tau_b_is_correct_on_known_cases():
    k = load("sensitivity").kendall_tau_b
    assert k([1, 2, 3, 4], [1, 2, 3, 4]) == 1.0
    assert k([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0
    assert k([1, 1, 1], [1, 2, 3]) == 1.0                         # no ordered pairs in x: defined as 1.0 here (nothing to disagree about)
    assert round(k([1, 2, 3, 4, 5], [1, 3, 2, 4, 5]), 3) == 0.8   # one discordant pair out of ten
