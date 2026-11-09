# Technical validation

This document records an audit of ATHAR's analysis engine (`backend/app/analysis.py`, `simulation.py`, `recommendations.py`): what was checked, how, what was found, what was fixed, and what remains an assumption. It claims *internal* correctness (the code does what the specification says, deterministically). It does **not** claim that the model predicts real attacks.

## 1. What the engine computes (specification)

| Concept | Definition |
|---|---|
| Graph | Directed graph of assets; edges are relationships. `protects` edges (controls) and `disabled` edges are not traversable. One relationship per ordered asset pair. |
| Start points | Assets marked `compromised` (assumed breach: an input, never a finding). |
| Targets | Assets with criticality ≥ 4 and type server/database/cloud that are **not** themselves compromised. |
| Attack path | A *simple* path (no repeated asset) from a start point to a target with at most 6 relationships. |
| Edge weight | `evidence (validated 1.0 / inferred 0.7 / theoretical 0.4) × privilege (none 1.0 / read 0.7 / write 0.85 / admin 1.0) × (0.35 if MFA is required)` |
| Path score | `min(100, round(100 × criticality/5 × ease × length_factor × exposure_factor, 1))`, with `ease` = geometric mean of edge weights, `length_factor = 1/(1+0.1·(hops−1))`, `exposure_factor = 1.1` if the path crosses an internet-exposed asset. |
| Path evidence class | `validated` only if every hop is validated; `theoretical` if any hop is theoretical; otherwise `inferred` (weakest link). |
| Posture index | Mean, over scored sensitive assets, of the worst path score reaching each (0 if none). |
| Summed path score | Sum of all path scores (an index of attack-surface breadth, see L2). |

The score is a heuristic **index**, not a probability, and the engine contains no learned component.

## 2. How it was audited

1. **Code reading** of the traversal, scoring, aggregation, simulation and recommendation code (findings in §4).
2. **Independent oracle** (`tests/test_validation.py`): a from-the-specification re-implementation (plain recursive DFS, no pruning, no NetworkX, constants re-stated rather than imported) compared with the engine on 60 random environments, the two shipped scenarios, and aggregate values (posture, summed score, class counts, severity distribution). A guard test asserts the random environments really exercise the engine (349 paths in total, up to 44 per environment, all three evidence classes).
3. **Metamorphic properties** (must hold for *any* environment; seeded random environments): removing a relationship never adds a path or raises any score; adding a relationship never removes a path; stronger evidence or privilege never lowers a score; MFA never raises one; `disable` and `remove` have identical security effect; independent removals commute; simulation accounting is exact (eliminated ∪ remaining = baseline, nothing is ever introduced); the live environment is bit-identical after every action kind.
4. **Determinism**: repeated runs identical; **input-order invariance** (shuffling assets and relationships yields identical paths, scores, findings and recommendations on 25 random environments); **cross-process determinism** (identical SHA-256 of the full analysis + recommendations + simulations under three different `PYTHONHASHSEED` values, for both scenarios).
5. **Mutation testing** (deliberately injecting defects and confirming the suite fails; done by hand with the source restored after each, and verified restored): see §3.
6. **Measurement**, not argument: evaluation against baselines and an exhaustive optimum (`docs/evaluation/RESULTS.md`), and a weight-sensitivity analysis (`docs/evaluation/SENSITIVITY.md`).

Result at the time of writing: **652 backend tests pass** (455 of them in `test_validation.py`), 97% line coverage of `backend/app`, mypy clean.

## 3. Mutation testing

| # | Injected defect | Caught? |
|---|---|---|
| M1 | inferred-evidence weight 0.70 → 0.71 | yes |
| M2 | length penalty 0.10 → 0.11 | yes |
| M3 | hop limit 6 → 7 | yes (after fixing the oracle, see F4) |
| M4 | path class ignores theoretical hops | yes |
| M5 | posture counts already-compromised targets again (regression of F1) | yes |
| M6 | disabled relationships traversable | yes |
| M7 | hop limit 6 → 5 | yes |
| M8 | internet-exposure bonus never applied | yes |
| M9 | arithmetic instead of geometric mean for `ease` | yes |
| M10 | simulation without any copy (mutates the live environment) | yes (26 tests fail) |
| M11 | copy-on-write defeated (mutates shared relationship objects) | yes |

All 11 were detected. M3 initially *survived*, which exposed a weakness in the test oracle itself (F4).

## 4. Findings

### Fixed during the audit

| ID | Finding | Why it mattered | Fix and evidence |
|---|---|---|---|
| **F1** | A sensitive asset that is itself marked compromised was still a target. It had no path to itself, scored 0, and that 0 was averaged into the posture index. | The more assets were already breached, the *better* the posture looked. | Compromised assets are excluded from targets and from the posture mean, and are reported in `summary.compromised_sensitive_assets` (shown as a dashboard warning). Tests: `test_f1_*`, mutation M5, e2e. |
| **F2** | Recommendation output (`affected_relationships`, `affected_assets`) for MFA and segmentation listed items in *input order*. | Same environment, different file ordering, different output: not reproducible. | Hit lists are sorted. Found by the order-invariance test; now passes on 25 random environments. |
| **F3** | Reducing privilege on a *business-critical* relationship was rated one level lower ("access remains"). | Write→read on an order-processing link can break it; the impact was understated, and the business-safe plan could take such a step. | Privilege reduction keeps its `high` rating; MFA (which genuinely keeps the access) keeps the discount. Test: `test_f3_*`. |
| **F4** | The test oracle imported `MAX_HOPS` from the engine, so it silently followed a mutation of that constant. | A test that cannot fail is not evidence. | Oracle constants are re-stated from the specification; added an exact hop-limit test. M3 and M7 are now caught. |
| **F5** | UI evidence note said "validated within the synthetic data" but did not say that the levels are *declared by the data author*. | Overstates what ATHAR knows. | Wording now states that evidence levels are declared in the input and not verified by ATHAR (EN/AR). |
| F6 | Recommendations were ranked over at most 60 candidates even for small environments. | Needless `partial` warnings on a 34-asset scenario. | Cap is 150 for environments up to 200 relationships, 60 above; deterministic in the input size and still flagged when hit. |

### Documented limitations (not fixed; they are properties of the model)

| ID | Limitation | Consequence |
|---|---|---|
| **L1** | **Absolute scores are assumption-dependent.** Varying every weight by up to ±30% (200 seeded trials) moves the posture index across 47.1–73.5 (baseline 54.8) in the sample environment and 59.8–78.3 (baseline 67.3) in Harbor, and in the sample environment leaves the single highest-scoring path unchanged in only 51% of trials (92% in Harbor). | Use scores for *relative* prioritisation inside one configuration; do not treat them as measurements. See `SENSITIVITY.md`. |
| L1b | The *#1 recommendation* was identical in 100% of trials in both scenarios. | Structural conclusions (which relationship is the chokepoint) are far more robust than numbers, in these two environments. |
| **L2** | `total_path_score` sums overlapping paths, so it grows with path multiplicity (parallel routes) rather than attacker capability. It also drives recommendation ranking. | Recommendation *priority* favours edges on many paths. The posture index (max per target) is not affected by multiplicity. |
| L3 | `ease` is a geometric mean, so one weak hop in a long chain is diluted. | A path with a single theoretical hop can still score high; its evidence *class* (weakest link) does not hide this. |
| L4 | Score is capped at 100. | Several one-hop, admin, validated, criticality-5 paths would tie at 100. Not triggered by the shipped scenarios. |
| L5 | Reachability is not exploitability: no vulnerability, difficulty, detection, time or attacker-skill model. | An "attack path" means "the model says this chain of access exists", not "this is easy or likely". |
| L6 | Evidence levels are declared inputs. ATHAR cannot verify them. | "Validated" is a label supplied with the data. In this MVP all of it is synthetic. |
| L7 | Search limits: 6 hops, simple paths only, 500 paths, 400,000 expansions. Results are flagged `paths_truncated` when a cap is hit, and truncated output depends on input order. | Large dense graphs are reported as incomplete rather than silently wrong. |
| L8 | "Lost access" is reachability lost by legitimate identities, not privileges lost; operational impact has three coarse levels derived from two booleans (business-critical, has recorded use). | An estimate for triage, not an impact assessment. |
| L9 | The recommendation search is greedy over single actions. | In the sample environment it needed 6 remaining paths at k=2 where the exhaustive optimum reaches 5 (`RESULTS.md`). |
| L10 | The minimum cut used in the evaluation ignores the hop limit. | It is an upper bound on the removals the hop-limited model needs. |

## 5. Assumptions and synthetic data (explicit list)

- All environments are invented (`acme-sample`, `harbor-logistics`); no real system, person, credential or vulnerability is described or tested.
- Starting points are assumptions: ATHAR is told what is compromised; it does not detect compromise.
- Every weight, band and impact rule is a documented assumption (§1, `ARCHITECTURE.md`); none is calibrated on incident data.
- Group membership, trust and credential-holding edges are assumed to be fully traversable by an attacker who holds the source.
- Recorded "legitimate use" and "business-critical" flags are supplied by the data author.
- The AI narration (optional) never influences any number; it has been tested only with mocks and with a deliberately invalid key.

## 6. Evidence classification: is it technically honest?

- A path is only labelled `validated` when **all** hops carry that label, and a single theoretical hop makes the path `theoretical`; the class is therefore a lower bound on support, never an average.
- The label is supplied by the data author. The UI states this everywhere an evidence tag appears, and the text says the data is synthetic in this MVP.
- Evidence is never inferred or upgraded by ATHAR, and the AI layer cannot change it.
- What the labels do **not** mean: that an exploit was run, that the path is likely, or that a scanner confirmed it.

## 7. Reproducing everything

```powershell
cd backend
python -m pytest -q                       # 652 tests incl. oracle, metamorphic, determinism, scenarios, evaluation
python -m mypy app
python ../scripts/evaluate.py             # regenerates docs/evaluation/RESULTS.md and results.json (runs twice, must be identical)
python ../scripts/sensitivity.py          # regenerates docs/evaluation/SENSITIVITY.md
python ../scripts/export_scenarios.py     # regenerates scenarios/*.json (a test fails if they drift from the builders)
python ../scripts/verify_live.py          # real uvicorn processes: restart persistence, token mode, rate limits
```


## 8. Advanced-intelligence sprint: what was verified and how

**Baseline re-established first:** all 652 earlier backend tests passed before any change, and the earlier numbers (Harbor 42 paths, posture 67.3, top recommendation `r02` eliminating 37) are unchanged by the new model (a golden test pins them).

**New independent checks**

- The oracle was extended to four evidence classes, the identity-provider target type and **arbitrary scoring configurations**; the engine matches it on 60 random environments and on 25 random valid configurations.
- The **Pareto relation** is re-implemented from its definition inside the tests and compared with the production function on 40 random vector sets and on every plan set of all three scenarios; algebraic properties (irreflexive, asymmetric, transitive, non-empty front) are checked on random sets.
- The **minimum-cut plan** is compared with a brute-force minimum hitting set on 30 small random graphs (the weights are re-stated in the test).
- Plan metrics are cross-checked against direct simulation; plan generation is checked for determinism, non-mutation and input-order invariance.
- Sensitivity analysis: seeded repeatability, baseline containment, path-set invariance, valid perturbed configurations for 60 seeds.
- The production layer is tested end to end (modes, headers, proxy handling, static serving, logging) in `tests/test_production.py`.

**Mutation checks** on the new code (a script injected each defect, ran the relevant tests, and restored the file; sources verified restored afterwards). A suite that passed on its very first run was the reason for doing this: several early assertions turned out to be vacuous and were rewritten.

| # | Injected defect | Caught? |
|---|---|---|
| M12 | Pareto dominance requires strictly-better on every objective | yes |
| M13 | Pareto dominance drops the strictly-better-somewhere requirement | yes |
| M14 | Recommendation confidence can be "high" without a sensitivity run | yes |
| M15 | Real-world validation accepted on synthetic data | yes |
| M16 | Path evidence class uses the strongest hop instead of the weakest | yes |
| M17 | Proxy handling trusts the forgeable left-most `X-Forwarded-For` entry | yes |
| M18 | Demo mode lets `PUT` through as a read | yes |
| M19 | Unknown recovery time reported as within the RTO | yes |
| M20 | Plan suggestion ignores high operational impact | yes |
| M21 | Minimum cut ignores business criticality in its weights | yes |
| M22 | Perturbation no longer keeps observed >= inferred | yes |
| M23 | Public-demo simulation is persisted | yes |
| M24 | Weight-table cache ignores the active configuration | yes |

All 13 were detected (together with the earlier M1-M11: 24 of 24). The script is not part of CI (see REMAINING_WORK #22).

**Findings fixed during this sprint**

| ID | Finding | Fix |
|---|---|---|
| F7 | Three assertions I first wrote could not fail (`or True`, `and False`) | Replaced with real checks; found by re-reading the first all-green run |
| F8 | A test counted audit rows through a capped endpoint, so it passed or failed depending on test order | Compares the newest row instead |
| F9 | `X-Forwarded-For` handling first used the left-most entry, which a client can forge | Right-most entry only, and only with `ATHAR_TRUST_PROXY=1` (tested) |
| F10 | Public demo visitors could have forced new sensitivity computations with arbitrary parameters | Visitors get one cached default run (tested) |
| F11 | A worst-case import timing test failed once (over 90 s) in a 14-minute coverage run on a throttled laptop CPU | Measured: 8-9 s plain, 23-26 s under coverage, flat over repeated imports (no regression). The 90 s bound is unchanged but now scaled (at most 6x) by a same-process measurement of the machine's current speed |
| F12 | The public demo allowed the local-development CORS origins by default; HTTP was never redirected behind a TLS proxy | Demo default is no cross-origin callers; optional `ATHAR_FORCE_HTTPS` redirect (tested) |

**Honest limits.** CPU throttling on the development laptop made the first plan or sensitivity request 3x slower than a cold benchmark (6 to 19 s on Meridian). The deployment verifier and the production build were exercised locally only.
