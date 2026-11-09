# Evaluation methodology and results

Everything here is **measured on synthetic scenarios by this repository's engine** and can be reproduced with one command. Nothing is copied from elsewhere, estimated by hand, or taken from a real environment. The evaluation measures how ATHAR behaves *inside its model*; it is **not** evidence of real-world risk reduction.

## 1. Questions

1. **Baseline**: what does ATHAR report for a given environment (paths, evidence classes, severity, posture)?
2. **Remediation**: if the recommendations are applied one at a time, how do paths, posture and residual risk change, and what does it cost operationally?
3. **Residual risk**: what remains if the plan may *not* cut business-critical access?
4. **Quality**: are the recommended changes better than naive choices *within the model*, and how close to optimal?
5. **Robustness**: how much do conclusions depend on the (assumed) scoring weights?
6. **Reproducibility**: is every result identical across runs, input orderings and processes?

## 2. Scenarios

| Scenario | Size | Starting points | Purpose |
|---|---|---|---|
| `acme-sample` | 16 assets / 20 relationships | one phished employee | the small demo environment |
| `harbor-logistics` | 34 assets / 55 relationships | a phished helpdesk analyst and an internet-facing portal | a richer environment: 7 identities at different privilege levels, 3 service accounts, 4 groups, 8 servers, 4 databases, 4 cloud resources, 4 controls; all three evidence levels and all four privilege levels |

Both are fictional (`scenarios/*.json`, importable through the UI). Harbor encodes typical misconfiguration patterns (stale bastion access, credentials left on a CI runner, an over-privileged deploy role, a direct database connection from a web portal); it does not describe any real organisation.

## 3. Method

`scripts/evaluate.py` runs, for each scenario:

- the **baseline** analysis;
- three **greedy remediation plans** (apply the top recommendation, re-analyse, repeat, up to 8 steps): all action types; remove-only (for like-for-like comparison); and **business-safe**, which refuses any step whose operational impact is *high*;
- a **comparison at k removals** against: a static *frequency* heuristic (remove the relationships on the most paths), *random* relationships that lie on attack paths (500 seeded trials, a deliberately favourable baseline), and the **exhaustive optimum** (minimum remaining paths over all k-subsets, where the search is small);
- the graph **minimum cut**: the fewest relationship removals that would cut every path (ignoring the 6-hop limit, so an upper bound for the model).

Metrics: attack paths, validated paths, posture index, summed score, severity distribution, residual paths (named), step and cumulative operational impact (level, reversibility, legitimate-identity access lost, business-critical relationships touched). Removal sets are evaluated exactly from the baseline path set (valid because removal never adds paths or changes surviving scores; this is a tested property).

`scripts/sensitivity.py` perturbs every weight by up to ±30% (200 seeded trials) and measures stability of the path ranking and recommendations.

## 4. Results (see `docs/evaluation/RESULTS.md` and `SENSITIVITY.md` for full tables)

### Harbor Synthetic Logistics (42 attack paths, posture 67.3)

| Plan | Paths after each step | Notes |
|---|---|---|
| Baseline | 42 (validated 12, inferred 23, theoretical 7); severity 5 / 25 / 12 / 0 | highest path 88.0 |
| **First recommendation only** (`remove r02`: helpdesk group's admin login to the jump host; no recorded business use) | **42 → 5**; posture 67.3 → 22.8; validated paths 12 → 2 | impact **low**, no legitimate access lost; the same effect is available as a reversible *disable* |
| All actions | 5 → 1 → 0 | reaches 0 only by *disabling the portal's link to the orders API*: **high** impact, business-critical |
| **Business-safe plan** (refuses high-impact steps) | 5 → 4 → 3 → 2 | **residual risk: `portal → orders API` (88.0, critical, validated) and `portal → orders API → orders database` (73.8)**. These are business-critical links that need a different control (for example the web application firewall, rate limiting or request validation, none of which ATHAR models). |

### Acme sample (20 paths, posture 54.8)

| Plan | Paths after each step | Notes |
|---|---|---|
| First recommendation (`remove r03`: employee's stale admin login to the jump host) | 20 → 11; posture 54.8 → 51.3 | impact low |
| All actions | 11 → 6 → 0 | reaches 0 by cutting the employee's *portal login*: **high** impact |
| Business-safe plan | 11 → 6 → 3 → 3 | residual: 3 paths from the portal through the application server (top 54.3, high, validated) |

### Quality of choices (remaining paths after k removals; lower is better)

| Scenario | k | ATHAR | static frequency | random mean [min–max] | exhaustive optimum |
|---|---|---|---|---|---|
| Harbor | 1 / 2 / 3 | 5 / 1 / 0 | 5 / 5 / 5 | 36.0 [5–41] / 30.4 [1–40] / 27.3 [1–40] | 5 / 1 / 0 |
| Acme | 1 / 2 / 3 | 11 / 6 / 0 | 11 / 6 / 3 | 15.0 / 11.3 / 8.2 | 11 / **5** / 0 |

- ATHAR matched the exhaustive optimum in 5 of 6 cells; in Acme at k=2 the greedy choice left 6 paths where the optimum leaves 5 (a limitation of greedy search, L9).
- The static frequency heuristic stalls in Harbor because the two most frequent relationships are redundant (they cut the same 37 paths); re-simulation after each step avoids that.
- Graph minimum cut is **3** in both scenarios; the remove-only greedy plan reached zero paths in 3 steps.

### Robustness to the weights (±30%, 200 trials)

| | Harbor | Acme |
|---|---|---|
| Path ordering vs baseline (Kendall τ-b), mean / 5th percentile | 0.868 / 0.806 | 0.757 / 0.603 |
| Highest-scoring path unchanged | 92% | **51%** |
| #1 recommendation unchanged | **100%** | **100%** |
| Posture index range (baseline) | 59.8–78.3 (67.3) | 47.1–73.5 (54.8) |

**Interpretation:** which relationship to cut first is robust to the assumed weights in these environments, because it follows from the graph. The *absolute* posture value and the identity of the single highest-scoring path are not robust, so ATHAR's numbers should be used for relative prioritisation and not read as measurements.

### Reproducibility
Evaluation run twice in one process (identical JSON); full output hash identical under three different `PYTHONHASHSEED` values and under shuffled input order (`tests/test_validation.py`, `tests/test_scenarios.py`); committed results are checked against a fresh run by `tests/test_evaluation.py`.

## 5. What this evaluation does not show

- No real environment, real attacker, incident data or vulnerability data was used.
- "Optimal" and "random" are relative to ATHAR's own path set; fewer modelled paths is not the same as less real risk.
- Operational impact is a three-level estimate from two flags the data author supplies.
- Results on two small scenarios do not establish how ATHAR behaves on large or messy real environments (scaling is only benchmarked on random graphs, `ARCHITECTURE.md`).
- No user study; no comparison against other products.

## 6. Reproduce

```powershell
cd backend
python ../scripts/evaluate.py      # RESULTS.md + results.json (fails if two runs differ)
python ../scripts/sensitivity.py   # SENSITIVITY.md
python -m pytest tests/test_evaluation.py tests/test_scenarios.py tests/test_validation.py -q
```
