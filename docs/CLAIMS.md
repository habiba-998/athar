# Claims register: verified, experimental, and not claimed

Use this when presenting ATHAR. If a statement is not in the first table, do not make it.

Status key: **Verified** = backed by an automated test or a reproducible script in this repository, run and passing at the time of writing. **Experimental** = implemented and plausible, but not validated against anything outside the model. **Not claimed** = deliberately out of scope or untrue.

## Verified

| Claim | Evidence |
|---|---|
| Attack-path discovery returns exactly the simple paths of ≤ 6 hops from compromised assets to non-compromised sensitive targets, over enabled, traversable relationships | Independent oracle on 60 random environments + both scenarios (`tests/test_validation.py`); equivalence to NetworkX on 40 random graphs (`test_path_engine.py`); exact hop-limit test; 9 mutation tests |
| Path scores, evidence classes, severity and posture follow the documented formulas | Same oracle; hand-checkable test; aggregate checks |
| Results are deterministic: identical across runs, across input ordering, and across processes with different hash seeds | `test_validation.py`, `test_scenarios.py` |
| A simulation never modifies the live environment, for every action type | Isolation tests, API-level tests, mutation of the copy logic caught |
| Simulation accounting is exact and a simulated action never introduces a path | Metamorphic tests on random environments |
| `disable` and `remove` have identical security effect; `disable` is reversible, `remove` is not | Tests |
| Reported operational impact: affected assets, legitimate access lost, reversibility | Golden and unit tests (estimates are coarse, see below) |
| Incomplete results are flagged rather than hidden (`paths_truncated`, `recommendations_partial`, already-compromised sensitive assets) | Tests; e2e |
| Environment import/edit rejects inconsistent graphs and changes nothing on rejection | API tests; e2e |
| Evaluation results are reproducible and the committed results are current | `scripts/evaluate.py` (runs twice), `tests/test_evaluation.py` |
| On the two scenarios, ATHAR's first recommended change eliminates 9 of 20 (sample, leaving 11) and 37 of 42 (Harbor, leaving 5) paths, with no legitimate access lost | `RESULTS.md`, golden tests |
| Within the model, ATHAR's choices beat random and a naive frequency heuristic and matched the exhaustive optimum in 5 of 6 comparisons | `RESULTS.md` |
| AI narration is off by default, never alters evidence or numbers, and fails safe | Unit tests with mocked responses; live check with an invalid key |
| Local-only access by default; optional token; rate limits; size limits; CORS allow-list | Unit tests and live-server checks (`scripts/verify_live.py`) |
| UI: English/Arabic parity, mirrored layout, no automated axe (WCAG 2.x A/AA) violations on every tab, phone layouts without overflow, keyboard operation | 66 Playwright tests |
| Environment, activity and simulation history persist across a real restart | Live check |

## Experimental

| Claim | Why it is only experimental |
|---|---|
| The scoring weights rank paths in a useful order | Assumed, not calibrated. ±30% changes leave only 51% (sample) or 92% (Harbor) of top-path choices unchanged |
| The recommended change is the best real-world change | "Best" is within the model; greedy search missed the optimum once (sample, k=2) |
| Operational-impact levels reflect real disruption | Derived from two booleans supplied with the data |
| "Validated / inferred / theoretical" reflects real confidence | Declared labels, synthetic in this MVP |
| The model scales to large environments | Benchmarked on random graphs only; results are capped and flagged beyond limits |
| Optional LLM narration is useful and safe | Tested only with mocks and an invalid key; never run with a valid key |
| Arabic text and RTL read naturally | Checked by automated geometry/typography tests and screenshots, not by native-speaking reviewers |
| The interface is accessible | Automated checks and keyboard tests pass; no manual screen-reader testing |
| ATT&CK / NIST CSF mappings | Conceptual and unreviewed by a framework expert; IDs must be re-checked |

## Not claimed

- That ATHAR **predicts** attacks, breaches or their likelihood, or that its scores are probabilities.
- That any result describes a **real** organisation, system or vulnerability.
- **Compliance or certification** with MITRE ATT&CK, NIST CSF, Zero Trust, ISO, or any standard.
- **Detection** of compromise, malware, vulnerabilities or misconfiguration in a live environment.
- That it is **better than**, or a replacement for, vulnerability scanners, attack-path-management, identity-security or breach-simulation products. No comparison was run.
- **Real-world validation**: no pilot, no red-team exercise, no incident data, no user study.
- **Production security**: single shared token, no roles, no TLS, no tamper-evident logging.
- Accessibility **certification**.


---

## Added by the advanced-intelligence sprint

### Verified (automated tests or reproducible scripts)

| Claim | Evidence |
|---|---|
| Scoring weights are configurable, validated, applied consistently to analysis, recommendations, simulation and plans, and cannot leak between concurrent requests | `tests/test_intelligence.py::TestScoringConfig` (incl. a threaded test); the independent oracle agrees with the engine under 25 random configurations (`test_validation.py`) |
| A path's evidence class is its weakest hop (`theoretical < inferred < observed < validated`); `observed` is never reported as `validated` | `TestEvidenceModel`; oracle with four classes |
| Real-world validation cannot be recorded on synthetic data | model validator; API 422 test; no shipped scenario contains it |
| The Pareto relation and front used to compare plans equal an independent implementation (random vectors and all three scenarios); the relation is irreflexive, asymmetric and transitive | `TestParetoRelation`, `TestPlans` |
| The minimum-cut plan eliminates every path, and its weight equals a brute-force optimum on 30 small random graphs | `TestMinimumCut` |
| Every plan's reported metrics equal a direct simulation of its actions; no plan adds a path or raises the posture; plan generation never mutates the environment and does not depend on input order | `TestPlans` |
| The plan suggestion never picks a high-impact plan or one that interrupts a critical service; the plan reaching 0 paths is displayed but not suggested (Meridian) | `test_the_suggestion_never_picks…`, `test_eliminating_every_path_is_not_automatically_favoured` |
| Business impact: interruption, rollback vs re-provisioning, RTO comparison (`unknown` is never treated as fine), approvals | `TestBusinessImpact` |
| Sensitivity analysis is seeded and repeatable, never changes the path set, and its ranges contain the baseline | `TestSensitivity` |
| The nine-question explanation exists in English and Arabic for every recommendation, uses the engine's numbers, and never calls a score a probability | `TestExplanations` |
| The public demo is read-only: every write endpoint is refused for visitors and changes nothing; visitor simulations and explanations are not persisted; weak secrets stop the server from starting | `tests/test_production.py` |
| Security headers, strict CSP, HSTS rules, proxy-header handling, static-file traversal protection, structured logs without secrets, deployment files without secrets | `tests/test_production.py` |
| Every user-visible string used by the UI exists in English and Arabic | `frontend/src/i18n.coverage.test.ts` |

### Experimental / not claimed (additions)

- **Sensitivity and stability labels** use fixed thresholds (top-3 in 90% / 60% of trials); they are a convenience, not a statistical test.
- **Business-impact index, disruption cost and effort** are documented relative scales, not hours or money.
- **Pareto optimality** is relative to the generated plans; **no claim of global optimality** is made. The only exact component is the weighted minimum cut, and only for its own objective.
- **Digital-twin realism**: Meridian is invented to resemble typical enterprise structure; it is not derived from any real organisation and was not validated by practitioners.
- **Deployment**: the deployment package is prepared and rehearsed locally. **No public URL exists unless `scripts/verify_deployment.py` has passed against it.**

### Static (in-browser) build

| Claim | Status | Evidence / limit |
|---|---|---|
| The unchanged backend answers the frontend's API calls inside the browser through an ASGI bridge, identically to the HTTP application | Verified under CPython (status and body equal for 10 endpoints, simulate, writes denied) | `test_inbrowser_bridge.py` |
| The same bridge runs in WebAssembly (Pyodide) and every feature works behind the strict production headers with zero third-party and zero API requests | Verified in Chromium against the local production build | `frontend/tests/static.spec.ts` (5 tests) |
| The library versions in WebAssembly equal the server lock | **Not claimed**: Pyodide ships its own (pydantic 2.12.5, FastAPI 0.136.1, Python 3.14) | the 1,000-test backend suite runs under CPython only |
| Works on iPhone/Safari and Firefox | **Not verified** (Chromium device emulation only) | |
| A public Netlify deployment exists | **No**: not deployed until the owner connects the repository and the verifier passes against the real URL | |

