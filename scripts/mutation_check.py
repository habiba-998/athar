"""Mutation testing of the security- and decision-critical code, reproducible and CI-friendly.

Each entry injects ONE defect into a source file (exact text replacement), runs the tests that must notice it, and restores
the file (also on crash). A mutant that SURVIVES, or a pattern that no longer matches the source (a stale entry), fails the
run, so the list cannot rot silently. Run from the repository root:

    python scripts/mutation_check.py            # all mutants (about 2 minutes)
    python scripts/mutation_check.py M17 M20    # selected mutants
    python scripts/mutation_check.py --list

The mutants are hand-chosen, not generated: they target the properties the documentation claims (Pareto relation, evidence
weakest-link, demo read-only enforcement, proxy trust, RTO honesty, ...). This is NOT a statistical mutation score.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")

# (id, description, file, exact text to replace, replacement, pytest selection "path -k expr")
MUTATIONS = [
    ('M12', 'plans.dominates uses < instead of <= (strict everywhere)', 'app/plans.py', 'return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))',
     'return all(x < y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))', 'tests/test_intelligence.py -k "ParetoRelation"'),
    ('M13', 'plans.dominates drops the strictly-better requirement', 'app/plans.py', 'return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))',
     'return all(x <= y for x, y in zip(a, b))', 'tests/test_intelligence.py -k "ParetoRelation"'),
    ('M14', 'confidence can be high without a sensitivity run', 'app/narrative.py', 'return ("low" if strong_share < 0.25 else "medium"), reasons',
     'return ("low" if strong_share < 0.25 else "high" if strong_share >= 0.6 else "medium"), reasons', 'tests/test_intelligence.py -k "confidence"'),
    ('M15', 'real-world validation accepted on synthetic data', 'app/models.py', 'if r.validation == "real_world":', 'if False:', 'tests/test_intelligence.py -k "real_world"'),
    ('M16', 'path class uses the strongest hop instead of the weakest', 'app/analysis.py', 'return min((r.evidence for r in rels), key=lambda e: EVIDENCE_RANK[e])',
     'return max((r.evidence for r in rels), key=lambda e: EVIDENCE_RANK[e])', 'tests/test_intelligence.py -k "weakest_link"'),
    ('M17', 'proxy handling trusts the forgeable left-most address', 'app/security.py', 'return parts[-1]', 'return parts[0]',
     'tests/test_production.py -k "forged or rightmost or follow_the_trusted"'),
    ('M18', 'demo mode lets PUT through as if it were a read', 'app/security.py', 'reading = request.method in ("GET", "HEAD")', 'reading = request.method in ("GET", "HEAD", "PUT")',
     'tests/test_production.py -k "every_write_is_refused"'),
    ('M19', 'unknown recovery time is treated as within the objective', 'app/business.py', 'elif hours is None:\n            rto = "unknown"', 'elif hours is None:\n            rto = "within"',
     'tests/test_intelligence.py -k "rto_exceeded_and_unknown"'),
    ('M20', 'plan suggestion ignores high operational impact', 'app/plans.py', 'and p["operational"]["level"] != "high" and p["business"]["critical_services_interrupted"] == 0]',
     'and p["business"]["critical_services_interrupted"] == 0]', 'tests/test_intelligence.py -k "suggestion or favoured"'),
    ('M21', 'min-cut ignores business criticality when weighting', 'app/plans.py', 'return 1000 * level_cost + 1', 'return 1',
     'tests/test_intelligence.py -k "brute_force_optimum"'),
    ('M22', 'perturbation no longer keeps observed >= inferred', 'app/sensitivity.py', 'observed = _clip(base.evidence_observed * f(), inferred, 1.0)', 'observed = _clip(base.evidence_observed * f(), 0.05, 1.0)',
     'tests/test_intelligence.py -k "valid_ordered_configuration"'),
    ('M23', 'public-demo simulation is persisted', 'app/main.py', 'if request.state.ephemeral:\n        # Public read-only demo', 'if False:\n        # Public read-only demo',
     'tests/test_production.py -k "never_persisted"'),
    ('M24', 'weights table cache ignores the active config', 'app/analysis.py', 'c = cfg or _ACTIVE.get()\n    ev, pv = _tables(c)\n    w = ev[rel.evidence]', 'c = cfg or _ACTIVE.get()\n    ev, pv = _tables(DEFAULT_CONFIG)\n    w = ev[rel.evidence]',
     'tests/test_validation.py -k "random_scoring_configurations"'),
]


SELECTION_TIMEOUT = 900


def pytest_command(selection: str) -> list[str]:
    path, _, expr = selection.partition(" -k ")
    return [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", path.strip(), "-k", expr.strip().strip('"')]


def run_one(mutation) -> str:
    mid, _desc, rel, old, new, selection = mutation
    path = os.path.join(BACKEND, rel.replace("/", os.sep))
    with open(path, encoding="utf-8", newline="") as f:
        original = f.read()
    if old not in original:
        return "STALE"
    try:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(original.replace(old, new, 1))
        r = subprocess.run(pytest_command(selection), cwd=BACKEND, capture_output=True, text=True, timeout=SELECTION_TIMEOUT)
        return "CAUGHT" if r.returncode != 0 else "SURVIVED"
    finally:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(original)


def main(argv: list[str]) -> int:
    if "--list" in argv:
        for m in MUTATIONS:
            print(f"{m[0]}  {m[1]}")
        return 0
    wanted = [a for a in argv if not a.startswith("-")]
    todo = [m for m in MUTATIONS if not wanted or m[0] in wanted]
    results = []
    for m in todo:
        status = run_one(m)
        results.append((m[0], m[1], status))
        print(f"{m[0]:4} {status:8} {m[1]}", flush=True)
    bad = [r for r in results if r[2] != "CAUGHT"]
    print(f"\n{len(results) - len(bad)} of {len(results)} mutants caught" + (f"; NOT caught: {', '.join(b[0] + ' ' + b[2] for b in bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
