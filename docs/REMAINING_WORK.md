# Remaining work, prioritised

Ordered by how much each item limits the credibility of ATHAR for a competition or a first real user. Effort is a rough estimate for a two-person team.

## P0: before claiming more than "a validated prototype on synthetic data"

| # | Work | Why it matters | Effort |
|---|---|---|---|
| 1 | **Calibrate or replace the scoring weights using real data** (public breach/path datasets, or a pilot environment with red-team results) | Sensitivity analysis shows absolute scores move a lot (posture 47.1–73.5 under ±30%); only the *structural* recommendation is robust. This is the largest scientific gap. | weeks |
| 2 | **One pilot on a real (consented, anonymised) environment**, with a security practitioner judging the paths and recommendations | Everything so far is synthetic; "does it find paths a practitioner finds useful?" is unanswered | 2–4 weeks |
| 3 | **Evidence ingestion**: let a scanner or IaC/IAM export set evidence levels instead of the author declaring them | "Validated" is currently a label. Without a source of truth it cannot be defended | weeks |

## P1: strengthens the competition case

| # | Work | Why | Effort |
|---|---|---|---|
| 4 | Compare against an established open-source attack-path tool on the same graph (paths found, ranking) | Only internal oracles exist; no external comparison was run | days |
| 5 | Review of the ATT&CK/CSF mappings and all Arabic text by domain experts; re-verify technique IDs against the current ATT&CK release | Both are author-written and unreviewed | days |
| 6 | Small usability study (5–8 analysts) with task success and time-to-decision | No user evidence yet | 1 week |
| 7 | Manual accessibility testing with NVDA/VoiceOver and a keyboard-only run-through | Only automated axe and keyboard tests exist | days |
| 8 | Run the optional LLM narration with a valid key under a red-team prompt-injection test (names in imported files) | Untested live; injection via names is a known residual | days |
| 9 | Model *control effects* (WAF, EDR) so residual risks like portal → orders API can show mitigation | Currently controls are displayed but have no effect on scores | 1–2 weeks |

## P2: engineering hardening for any non-demo use

| # | Work | Why | Effort |
|---|---|---|---|
| 10 | Real authentication, roles, per-user audit identity; TLS and CSP behind a reverse proxy | Single shared token, loopback only | 1–2 weeks |
| 11 | Tamper-evident audit log; encryption at rest; DB migrations; persistent undo history | SQLite file is unprotected and unmigrated; undo history is in memory | 1 week |
| 12 | Better search than greedy (e.g. small beam/ILP for the best *set* of changes) and a non-additive path aggregate | Greedy missed the optimum once; summed path score grows with path multiplicity (L2) | 1 week |
| 13 | Multiple relationships per asset pair; hop limit and caps configurable per environment; streaming analysis for large graphs | Model restrictions (one per pair, 6 hops, 500 paths) | 1–2 weeks |
| 14 | Hash-pinned Python lockfile; CI running the full suite (Chromium, Firefox, WebKit) on Linux and Windows | Tested on Windows/Chromium only; lockfile lacks hashes | days |
| 15 | Frontend line-coverage measurement | UI is covered by e2e tests only | 1 day |

## Known limitations carried forward
See `TECHNICAL_VALIDATION.md` (L1 to L10), `SECURITY.md`, and `CLAIMS.md` ("Experimental" and "Not claimed").


## Added after the advanced-intelligence sprint

| # | Work | Why | Effort |
|---|---|---|---|
| 16 | **Publish a real deployment**: connect the repository to Netlify (static build, `netlify.toml` is ready; steps in `docs/DEPLOYMENT.md`) and run `verify_deployment.py --static` plus `playwright.external.config.ts` against the URL | Needs the owner's Netlify account and approval; no URL exists today | minutes |
| 17 | Calibrate the weights, now that a sensitivity view shows which ones matter (`exposure_bonus`, `evidence_observed`, `length_penalty` on Meridian) | Same gap as #1, but the sensitivity analysis says where to start | weeks |
| 18 | Evidence ingestion that fills `evidence_source`, `collected_at` and `confidence` from an IAM export or scanner instead of the author | Provenance fields are still declared | weeks |
| 19 | Real authentication, roles and per-user audit for the admin role (the demo uses one shared token) | Single admin token | 1-2 weeks |
| 20 | Persist the demo visitor's simulation history in the browser (the public demo deliberately stores nothing server-side) | History tab is empty in demo mode | 1 day |
| 21 | Code-split the frontend (the bundle is about 600 kB, 178 kB gzip) | Build warning; acceptable for a demo | 1 day |
| 22 | Mutation testing in CI for the new modules (it was done by hand, see TECHNICAL_VALIDATION.md) | Hand-run mutation checks are not repeatable by others | days |
| 23 | Review the Arabic strings of the new views (plans, evidence, sensitivity, reports) with a native-speaking security professional | Written by the developer assistant | days |
