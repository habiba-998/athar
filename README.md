# ATHAR — See the attack before it happens.

**Predict. Simulate. Prevent.** A defensive attack-path analysis and decision-validation platform.
*ATHAR turns cybersecurity from identifying attack paths into understanding, comparing, and validating defensive decisions before implementing them.*

The MVP uses **synthetic data only**. It never scans, exploits or touches real systems, and it executes no change anywhere: every recommendation and plan requires human approval. ATHAR contains **no trained predictive model**; scores are deterministic heuristic indices, **not probabilities**.

## What it does

- **Understands** the environment: assets, relationships, privileges, identity provider, service accounts, network segments, business services and assumed-breach scenarios. Import, edit, export, undo, reset; every change is validated as a whole graph.
- **Discovers and explains** attack paths (bounded, pruned search) with transparent scores, per-hop **evidence** (validated / observed / inferred / theoretical, with source, collection date, confidence and validation status, all *declared by the data author*), the weakest hop, and what holds the score back.
- **Stress-tests its own assumptions**: configurable scoring weights and a seeded **sensitivity analysis** (score ranges, recommendation rank stability, which assumption matters most). It reports that absolute scores move a lot while structural conclusions are far more stable.
- **Compares defensive plans** (smallest change, business-safe, reversible-only, balanced, maximum reduction, minimum-disruption cut) on paths left, residual posture, disruption and effort, with **Pareto** status. Business services, recovery times against RTO and required approvals are shown side by side. It never auto-favours "eliminate every path" and makes no global-optimality claim.
- **Validates before acting**: reversible what-if simulation on an isolated copy, queue/undo/reset/history, and a downloadable **decision record** in English or Arabic.
- **Explains** every recommendation by answering nine questions (what, why, evidence, confidence, what changes, business impact, residual risk, what could be wrong, who approves/how to undo) in English and Arabic.
- **Audits** every action in a local SQLite database. Optional AI narration is off by default, labelled, and can never create findings.
- English / Arabic with full RTL, keyboard operation, automated accessibility checks, phone layouts.

### Interface
Deep-navy surfaces, one teal accent, red/amber/gold/green reserved for severity and impact; IBM Plex Sans with its Arabic companion, self-hosted (no CDN). The signature element is the **route trace**, drawn with evidence-coded lines: solid = validated, dash-dot = observed, dashed = inferred, dotted = theoretical. The graph has search, filters (asset type, evidence class), full screen, an "isolate path" mode with the full evidence chain, and a marker for sensitive assets.

## Run it locally (Windows / PowerShell)

Requirements: Python 3.12+, Node.js 20+ (developed on Node 26). **Use a short virtualenv path**: deep project paths break `pip` on Windows.

```powershell
python -m venv "$env:LOCALAPPDATA\athar-venv"
& "$env:LOCALAPPDATA\athar-venv\Scripts\python.exe" -m pip install -r backend\requirements.lock.txt
cd frontend; npm ci
```

Terminal 1 (API, http://localhost:8000, docs at /docs):
```powershell
cd backend
& "$env:LOCALAPPDATA\athar-venv\Scripts\python.exe" -m uvicorn app.main:app --port 8000
```
Terminal 2 (UI, **http://localhost:5173**): `cd frontend; npm run dev`

Three synthetic scenarios ship in `scenarios/` (import them in the *Environment* tab): `acme-sample` (the default), `harbor-logistics`, and **`meridian-enterprise`**, the digital twin used in the competition demo.

## Run it as a single production-style service

```powershell
cd frontend; npm run build
cd ../backend
$env:ATHAR_MODE="demo"; $env:ATHAR_ADMIN_TOKEN="<16+ random characters>"
python -m uvicorn app.main:app --port 8200      # serves API and the built app on one origin
```

`ATHAR_MODE=demo` is the **public read-only mode**: visitors can read and run stateless simulations; every write needs the admin token. See [Deployment](docs/DEPLOYMENT.md).

> **Deployment status: not deployed.** No public URL exists. Selected: a **static build on Netlify** in which the unchanged Python backend runs inside the visitor's browser (Pyodide / WebAssembly), so no server is needed. It is built and tested locally (browser suite, strict CSP, zero requests to any other origin); publishing needs your Netlify account: exact steps in [Deployment](docs/DEPLOYMENT.md). Also prepared: a Hugging Face Docker Space (real server) and a Vercel attempt that is unresolved. Do not quote any URL that has not passed the verifier from outside.

## Configuration

Every environment variable is documented in [ARCHITECTURE.md](docs/ARCHITECTURE.md#environment-variable-reference) and listed in `.env.example` (a test fails if the code reads one that is missing). Key ones: `ATHAR_MODE`, `ATHAR_API_TOKEN`, `ATHAR_ADMIN_TOKEN`, `ATHAR_CORS_ORIGINS`, `ATHAR_TRUST_PROXY`, `ATHAR_DB`, `VITE_API_BASE` (frontend build, public).

## Tests and checks (results from the final run)

| Check | Command | Result |
|---|---|---|
| Backend tests | `cd backend; python -m pytest -q` | **1007 passed, 0 failed** (about 2 minutes). Includes the independent oracle (also under random scoring configurations), metamorphic, determinism, Pareto, minimum-cut, sensitivity, documentation-drift, mutation-list and production tests. Coverage measured earlier: 97% (CI fails under 95%) |
| Python types | `python -m mypy app` | no issues |
| Mutation checks | `python scripts/mutation_check.py` (also a CI job) | 13 hand-chosen mutants of the security- and decision-critical code, all caught (24 of 24 with the earlier hand-run ones); a surviving or stale mutant fails the run. Not a statistical mutation score |
| Frontend unit | `cd frontend; npm test` | 17 passed (incl. translation coverage: every `t('key')` exists in English and Arabic) |
| Types / lint / build | `npx tsc -b`, `npm run lint`, `npm run build` | clean; build succeeds (about 600 kB JS, 178 kB gzip; chunk-size warning) |
| End-to-end | `set ATHAR_PYTHON=<venv python>`; `npx playwright install chromium` once; `npm run e2e` | **102 passed, 0 failed** (Chromium, about 5.5 minutes). Layouts at 375/390/430/768/1024/1280/1440 px in English and Arabic; axe (WCAG 2.x A/AA) on every tab and the new sub-views; **Android (Pixel 7) and iPhone 14 profiles with touch input, plus desktop, each in English and Arabic** (tab navigation, graph path isolation, recommendation to simulation); the public read-only demo against its own backend. **The iPhone profile emulates Safari's viewport/touch/user agent on Chromium; it is not the WebKit engine** |
| Live restart checks | `python scripts/verify_live.py` | 26 of 26: edits, history, evidence and activity survive a real process restart; token mode; rate limits; CORS |
| Dependency advisories | `pip-audit -r backend/requirements.prod.txt`; `npm audit --omit=dev`; `npm audit` | **no known vulnerabilities** in production pins, in npm production dependencies, or in npm development dependencies (2026-11-09) |
| Production image | simulated: clean venv from `requirements.prod.txt`, `pip check`, image layout, `verify_deployment.py` | 36 passed, 0 failed, plus proxy redirect and header checks. **`docker build` itself was not run: Docker is not installed on the development machine.** The CI job `image` builds and tests the real image |
| Deployment verifier | `python scripts/verify_deployment.py http://127.0.0.1:8200 --allow-insecure-local` | rehearsal against a local production-mode demo server: 36 passed, 0 failed (38 with `--admin-token-env`). **This is not a public deployment check.** |
| Not re-run in this sprint | `scripts/verify_independent.py`, `scripts/benchmark.py` | earlier results are not claimed as current |


Frontend **line coverage was not measured**: unit tests cover pure logic; the UI is covered by the end-to-end suite.

## Documentation

**Competition pack:** [Product overview](docs/PRODUCT_OVERVIEW.md) · [Competition demo (six-minute story + Arabic notes)](docs/COMPETITION_DEMO.md) · [Technical validation](docs/TECHNICAL_VALIDATION.md) · [Evaluation](docs/EVALUATION.md) ([RESULTS](docs/evaluation/RESULTS.md), [SENSITIVITY](docs/evaluation/SENSITIVITY.md), [MERIDIAN](docs/evaluation/MERIDIAN.md)) · [Framework mapping](docs/FRAMEWORK_MAPPING.md) · [Threat model](docs/THREAT_MODEL.md) · [Claims register](docs/CLAIMS.md) · [Remaining work](docs/REMAINING_WORK.md)

**Engineering:** [Architecture, API and environment reference](docs/ARCHITECTURE.md) · [Deployment](docs/DEPLOYMENT.md) · [Security](docs/SECURITY.md) · [Data model](docs/DATA_MODEL.md) · [Short demo script](docs/DEMO.md) · [Synthetic scenarios](scenarios/README.md)

### Reproducible commands
```powershell
cd backend
python -m pytest -q                          # backend suite incl. oracle, metamorphic, Pareto, min-cut, production tests
python -m mypy app
python ../scripts/evaluate.py                # docs/evaluation/RESULTS.md (two runs must be identical)
python ../scripts/sensitivity.py             # docs/evaluation/SENSITIVITY.md
python ../scripts/meridian_report.py         # docs/evaluation/MERIDIAN.md and meridian.json
python ../scripts/export_scenarios.py        # scenarios/*.json from the builders
python ../scripts/verify_deployment.py <url> # outside-in check of a deployed instance
```

## Known limitations (prioritised)

1. **Not production-grade authentication**: one shared token (or one admin token in demo mode); no users, roles or per-user audit; TLS is the host's job. Hardening done: CSP and security headers, proxy-aware rate limiting, fail-closed secrets, non-persisting public demo (see SECURITY.md).
2. **Declared evidence and uncalibrated scoring**: evidence, provenance and business-service data are declared by the data author and not verified by ATHAR; weights are documented assumptions. The sensitivity view shows absolute scores move substantially while the top recommendation is stable in the shipped scenarios.
3. **Heuristic plans**: plans come from greedy search plus one exact weighted cut; Pareto status is relative to the generated plans; no global optimality is claimed.
4. **Large environments are approximated**: path enumeration is capped (6 hops, 500 paths, 400k expansions) and recommendations evaluate at most 150 candidates (60 above 200 relationships). Caps are flagged in the API and UI.
5. **Arabic text was written by the developer assistant and not reviewed by a native-speaking security professional**; RTL was verified by automated geometry checks and screenshots.
6. **Accessibility is only partly verified**: automated axe checks and keyboard tests; no manual screen-reader testing.
7. **No real-world validation**: synthetic data only; no pilot, red-team or user study. AI narration has only been tested with mocks and an invalid key.
8. In the public demo the simulation history is intentionally not stored, so the History list is empty there.
