"""Rough scaling benchmark for the analysis engine (random graphs, seeded).

Run from the backend folder:  python ../scripts/benchmark.py
Numbers depend on graph density and the machine; they are indicative, not a guarantee.
"""
import os
import random
import sys
import time

os.environ.setdefault("ATHAR_DB", ":memory:")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.analysis import MAX_HOPS, MAX_PATHS, analyze  # noqa: E402
from app.models import Asset, Environment, Relationship  # noqa: E402
from app.recommendations import recommend  # noqa: E402

random.seed(7)
TYPES = ["user", "service_account", "group", "server", "database", "cloud"]


def make(n: int, e: int) -> Environment:
    assets = [Asset(id=f"a{i}", name=f"A{i}", name_ar=f"أ{i}", type=random.choice(TYPES),
                    criticality=random.randint(1, 5), compromised=(i == 0)) for i in range(n)]
    pairs: set[tuple[int, int]] = set()
    rels: list[Relationship] = []
    while len(rels) < e:
        s, t = random.sample(range(n), 2)
        if (s, t) in pairs:
            continue
        pairs.add((s, t))
        rels.append(Relationship(id=f"r{len(rels)}", source=f"a{s}", target=f"a{t}", type="read_access",
                                 privilege="read", evidence=random.choice(["validated", "inferred", "theoretical"]),
                                 legitimate_use="x" if random.random() < 0.5 else None))
    return Environment(name="bench", assets=assets, relationships=rels)


print(f"limits: max {MAX_HOPS} hops, max {MAX_PATHS} paths")
SIZES = [(15, 20), (50, 90), (100, 200), (200, 400)]
if "--worst" in sys.argv:  # the largest environment the validators accept (500 assets, 5000 relationships)
    SIZES += [(100, 1500), (300, 3000), (500, 5000)]
for n, e in SIZES:
    env = make(n, e)
    t0 = time.time()
    a = analyze(env)
    t1 = time.time()
    r = recommend(env, a)
    t2 = time.time()
    print(f"assets={n:4d} relationships={e:4d} paths={a['summary']['attack_paths']:4d} "
          f"analyze={1000 * (t1 - t0):7.0f} ms  recommend={t2 - t1:6.2f} s  recommendations={len(r)}")
