"""Write the shipped synthetic scenarios to ../scenarios/*.json (importable through the Environment tab).

Run from the backend folder:  python ../scripts/export_scenarios.py
A test (tests/test_scenarios.py) fails if the committed JSON no longer matches the builders, so the files cannot drift.
"""
import json
import os
import sys

os.environ.setdefault("ATHAR_DB", ":memory:")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

from app.data.demo import build_demo_environment  # noqa: E402
from app.data.scenario_harbor import build_harbor_environment  # noqa: E402
from app.data.scenario_meridian import build_meridian_environment  # noqa: E402

OUT = os.path.join(HERE, "..", "scenarios")
os.makedirs(OUT, exist_ok=True)
for name, env in (("acme-sample", build_demo_environment()), ("harbor-logistics", build_harbor_environment()),
                  ("meridian-enterprise", build_meridian_environment())):
    path = os.path.join(OUT, f"{name}.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(env.model_dump(mode="json"), f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    print(f"wrote {os.path.relpath(path)}: {len(env.assets)} assets, {len(env.relationships)} relationships")
