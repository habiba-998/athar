"""The mutation list must stay in sync with the source: a stale pattern would silently stop testing anything."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location("mutation_check", ROOT / "scripts" / "mutation_check.py")
    mod = importlib.util.module_from_spec(spec)                    # type: ignore[arg-type]
    spec.loader.exec_module(mod)                                   # type: ignore[union-attr]
    return mod


def test_every_mutation_pattern_matches_the_current_source_exactly_once_and_ids_are_unique():
    mod = _load()
    ids = [m[0] for m in mod.MUTATIONS]
    assert len(ids) == len(set(ids)) >= 13
    for mid, _desc, rel, old, new, selection in mod.MUTATIONS:
        text = (ROOT / "backend" / rel).read_text(encoding="utf-8")
        assert text.count(old) >= 1, f"{mid}: pattern no longer found in {rel}"
        assert old != new, mid
        assert " -k " in selection, mid


def test_the_sources_are_not_currently_mutated():
    mod = _load()
    for mid, _d, rel, old, new, _s in mod.MUTATIONS:
        assert new not in (ROOT / "backend" / rel).read_text(encoding="utf-8") or new in old, mid
