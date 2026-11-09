"""Documentation drift guard: the competition documents quote numbers and enumerate features; fail if they stop matching reality."""
from __future__ import annotations

import json
from pathlib import Path

from app.analysis import analyze
from app.data.scenario_harbor import build_harbor_environment
from app.models import RelType
from app.recommendations import recommend

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
DELIVERABLES = ["PRODUCT_OVERVIEW", "TECHNICAL_VALIDATION", "EVALUATION", "FRAMEWORK_MAPPING", "THREAT_MODEL", "CLAIMS", "COMPETITION_DEMO",
                "REMAINING_WORK", "ARCHITECTURE", "SECURITY", "DATA_MODEL", "DEMO", "DEPLOYMENT"]


def read(name: str) -> str:
    return (DOCS / f"{name}.md").read_text(encoding="utf-8")


def test_all_competition_deliverables_exist_and_are_substantial():
    for d in DELIVERABLES:
        assert len(read(d)) > 800, d
    for f in ("RESULTS.md", "SENSITIVITY.md", "results.json"):
        assert (DOCS / "evaluation" / f).stat().st_size > 500, f
    assert (ROOT / "scenarios" / "README.md").exists()


def test_framework_mapping_covers_every_relationship_type_and_action_kind():
    text = read("FRAMEWORK_MAPPING")
    for rt in RelType:
        if rt is not RelType.protects:                       # controls are explained in prose, not traversed
            assert f"`{rt.value}`" in text, f"relationship type {rt.value} missing from the ATT&CK table"
    for kind in ("remove_relationship", "disable_relationship", "reduce_privilege", "apply_mfa", "apply_segmentation"):
        assert kind in text, kind
    for must_say in ("not certified", "does **not** detect", "confirm each ID"):
        assert must_say.lower().replace("*", "") in text.lower().replace("*", ""), must_say


def test_evaluation_document_quotes_the_numbers_the_evaluation_actually_produced():
    res = json.loads((DOCS / "evaluation" / "results.json").read_text(encoding="utf-8"))["scenarios"]
    text = read("EVALUATION")
    h, a = res["harbor-logistics"], res["acme-sample"]
    expect = [
        f"{h['baseline']['attack_paths']} attack paths, posture {h['baseline']['posture_score']}",
        f"**{h['baseline']['attack_paths']} → {h['greedy_all_actions'][0]['paths']}**", f"{h['baseline']['posture_score']} → {h['greedy_all_actions'][0]['posture']}",
        f"{a['baseline']['attack_paths']} → {a['greedy_all_actions'][0]['paths']}",
        f"**{h['min_cut']}** in both", "highest path " + str(h["baseline"]["max_path_score"]),
    ]
    low = text.lower()
    for e in expect:
        assert e.lower() in low, f"EVALUATION.md no longer contains: {e}"
    plain = text.replace("**", "")
    # the comparison tables: ATHAR / static / random mean / exhaustive optimum, for k = 1..3, in both scenarios
    for sc, name in ((h, "Harbor"), (a, "Acme")):
        cmp_ = sc["comparison"]
        line = next((ln for ln in plain.splitlines() if ln.startswith(f"| {name} | 1 / 2 / 3 |")), None)
        assert line, f"{name} comparison row missing"
        cells = [c.strip() for c in line.strip("|").split("|")]            # scenario | k | ATHAR | static | random | optimum
        assert cells[2] == " / ".join(str(c["athar"]["remaining"]) for c in cmp_), f"{name}: ATHAR cell {cells[2]!r}"
        assert cells[3] == " / ".join(str(c["static_frequency"]["remaining"]) for c in cmp_), f"{name}: static cell {cells[3]!r}"
        assert cells[5] == " / ".join(str(c["optimal"]["remaining"]) for c in cmp_), f"{name}: optimum cell {cells[5]!r}"
        for c in cmp_:
            assert str(c["random"]["remaining_mean"]) in cells[4], f"{name}: random mean {c['random']['remaining_mean']} missing"
    # residual risk of the business-safe plan (what the document says cannot be cut)
    assert str(h["residual_business_safe"][0]["score"]) in plain and str(h["residual_business_safe"][1]["score"]) in plain
    assert str(a["residual_business_safe"][0]["score"]) in plain


def test_demo_script_quotes_engine_values():
    env = build_harbor_environment()
    a = analyze(env)
    recs = recommend(env, a)
    text = read("COMPETITION_DEMO") + read("PRODUCT_OVERVIEW")
    assert f"{recs[0]['priority']:,}" in text                       # "2,049.7"
    assert f"{a['summary']['attack_paths']} attack paths" in text.replace("**", "")
    assert str(a["summary"]["posture_score"]) in text and str(a["summary"]["max_path_score"]) in text
    assert f"{recs[0]['paths_eliminated']} of {a['summary']['attack_paths']}" in text


def test_claims_register_states_the_hard_limits():
    text = read("CLAIMS").lower()
    for phrase in ("not claimed", "predicts", "real-world validation", "compliance", "replacement for"):
        assert phrase in text, phrase


# ---------------------------------------------------------------------------- advanced-intelligence sprint documents

import re  # noqa: E402


def test_deployment_doc_exists_and_never_claims_a_live_url():
    text = read("DEPLOYMENT")
    assert len(text) > 800 and "not deployed" in text.lower()
    assert "REPLACE_WITH_YOUR_API_ORIGIN" in text                       # placeholders, never a guessed URL
    urls = re.findall(r"https://[A-Za-z0-9.\-]+\.[a-z]{2,}", text)
    allowed = {"https://render.com", "https://github.com", "https://api.example.org", "https://example.org"}
    assert all(u in allowed or u.startswith(("https://<",)) for u in urls), urls
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Deployment status: not deployed" in readme


def test_every_environment_variable_the_code_reads_is_documented_in_the_architecture_reference():
    section = read("ARCHITECTURE").split("## Environment variable reference", 1)[1]
    used = set()
    for f in (ROOT / "backend" / "app").glob("*.py"):
        used |= set(re.findall(r"\b(ATHAR_[A-Z_]+|ANTHROPIC_API_KEY)\b", f.read_text(encoding="utf-8")))
    used -= {"ATHAR_"}
    missing = sorted(v for v in used if v not in section)
    assert not missing, f"undocumented environment variables: {missing}"


def test_demo_script_numbers_match_the_generated_meridian_results():
    res = json.loads((DOCS / "evaluation" / "meridian.json").read_text(encoding="utf-8"))
    text = read("COMPETITION_DEMO").replace("**", "")
    b, s = res["baseline"], res["sensitivity"]
    plans = {p["strategy"]: p for p in res["plans"]}
    for needle in (f"{b['attack_paths']} attack paths", f"posture {b['posture_score']}", f"highest path {b['max_path_score']}",
                   f"{res['top_recommendation']['paths_eliminated']} of {b['attack_paths']}",
                   f"{s['posture']['min']} to {s['posture']['max']}", f"{s['top_recommendation_unchanged_pct']}%", f"{s['highest_path_unchanged_pct']}%",
                   f"{plans['reversible']['paths_after']}** paths".replace("**", ""), f"{plans['reversible']['posture_after']}"):
        assert needle in text, f"COMPETITION_DEMO.md no longer contains: {needle}"
    assert plans["max_reduction"]["paths_after"] == 0 and plans["max_reduction"]["impact"] == "high"
    assert res["suggested_plan"] != "plan-max-reduction"
    assert res["evidence"]["by_validation"]["real_world"] == 0


def test_meridian_results_file_is_current():
    import importlib.util
    spec = importlib.util.spec_from_file_location("meridian_report", ROOT / "scripts" / "meridian_report.py")
    mod = importlib.util.module_from_spec(spec)                         # type: ignore[arg-type]
    spec.loader.exec_module(mod)                                        # type: ignore[union-attr]
    assert mod.build() == json.loads((DOCS / "evaluation" / "meridian.json").read_text(encoding="utf-8"))


def test_arabic_speaking_notes_and_the_one_sentence_story_are_present():
    text = read("COMPETITION_DEMO")
    assert "understanding, comparing, and validating defensive decisions before implementing them" in text
    assert "الملاحظات بالعربية" in text
    for stamp in ("0:00 - 0:40", "0:40 - 1:30", "1:30 - 2:30", "2:30 - 3:30", "3:30 - 4:30", "4:30 - 5:20", "5:20 - 6:00"):
        assert stamp in text, stamp
    assert "Offline / failure fallback" in text


def test_framework_mapping_records_the_verified_version_and_references():
    text = read("FRAMEWORK_MAPPING")
    assert "v20.1" in text and "Stealth" in text and "SP 800-207" in text and "Sheyner" in text and "Phillips" in text
