# Threat model

Two different things are modelled here, and they must not be confused:

- **Part A** is the *attacker model that ATHAR's analysis assumes* about the environment it analyses.
- **Part B** is the *threat model of ATHAR itself* as a piece of software.

## Part A: the attacker model inside the analysis

| # | Assumption | Consequence |
|---|---|---|
| A1 | The analyst declares where the attacker starts (assets marked compromised). ATHAR does not detect compromise. | Paths are conditional: "if this account is breached, then…". |
| A2 | The attacker can traverse any modelled, enabled relationship from an asset they hold. Reachability is the only question. | No exploit difficulty, vulnerability, tooling, skill, time or luck is modelled. |
| A3 | Holding a group, role or credential relationship means holding what it grants. | Group membership, credential storage and role assumption are fully traversable. |
| A4 | The attacker cannot create relationships that are not in the data, and does not use unmodelled channels (physical access, social engineering of a second person, zero-day pivots). | The model can only be as complete as the data. Missing edges mean missing paths. |
| A5 | The defender is passive: no detection, response, or time-based containment. | Residual risk is an *upper bound on reachability*, not a prediction of loss. |
| A6 | Paths are simple (no revisits) and at most 6 hops. | Longer chains and loops are not reported. |
| A7 | Evidence levels (validated, inferred, theoretical) are declared by the data author and weight the score. | ATHAR cannot detect mislabelled evidence. |
| A8 | A target's value is its declared criticality (1–5). | No business-impact or data-volume model. |

**Out of scope for the analysis:** malware behaviour, network traffic, vulnerabilities and CVEs, patch levels, secrets scanning, detection coverage, insider intent, supply-chain compromise, availability attacks.

## Part B: threats to ATHAR (STRIDE)

### System and trust boundaries

```
 Analyst browser ──HTTP(loopback or token)──▶ FastAPI ──▶ SQLite file (activity, runs, explanations, environment)
        ▲                                        │
   JSON file import (untrusted)                  └──(optional, off by default)──▶ api.anthropic.com  (facts only)
```
Trust boundaries: browser ↔ API; imported file ↔ validator; API ↔ disk; API ↔ third-party model.
The MVP is designed to run on one machine with synthetic data. It is **not** designed for multi-user or internet exposure.

### STRIDE

| Threat | Scenario | Mitigation in the MVP | Residual risk |
|---|---|---|---|
| **S**poofing | Another local process or remote host calls the API | Loopback-only by default (`403 local_only`); optional shared token compared in constant time | One shared secret; no per-user identity; any local process on the machine is trusted |
| **T**ampering | A crafted environment file corrupts state or crashes analysis | Strict schema (`extra=forbid`), id charset, size limits (1 MB body, 500 assets, 5000 relationships), whole-graph consistency validation, rejected imports change nothing | A *well-formed but false* environment is accepted: ATHAR trusts declared evidence and flags |
| | Direct edit of the SQLite file | none (local file permissions only) | Anyone with file access can alter history or the stored environment |
| **R**epudiation | "I never ran that simulation" | Every run, edit and explanation is logged with a UTC timestamp and stored evidence | Log is not tamper-evident, not signed, and has no user identity |
| **I**nformation disclosure | Data leaves the machine | Synthetic data only; optional AI narration is off unless configured and sends only the finding's structured facts to a fixed host; API key read from environment, never returned or logged | If a user enables AI with real data, facts (asset names, paths) go to a third party. The key lives in the process environment |
| | Cross-origin reads from a web page | CORS allow-list (no wildcard); guard rejections also carry CORS headers | No CSRF token or CSP is served by the dev setup |
| **D**enial of service | Giant or pathological environment, request floods | Pruned search with caps (500 paths, 400k expansions) that are reported, candidate cap, body-size limit, per-client rate limits | In-memory per-process limiter keyed by IP; a worst-case 500-asset import costs ~11 s of CPU on the development machine |
| **E**levation of privilege | A reader performs writes | Not applicable: there is one trust level | No roles. Token holders can do everything |

### Additional threats specific to this tool

| Threat | Detail | Mitigation | Residual |
|---|---|---|---|
| **Prompt injection via data** | Asset or relationship names in an imported file could contain text that tries to steer the optional AI narration | The model receives only structured facts; its output is rendered as plain text in a separate labelled block, capped at 1,500 characters, and cannot create findings, change a number or call tools | The narration itself could be misleading; users are told it is not evidence. Untested with a live model |
| **False assurance** | A dashboard can look authoritative | Evidence tags say "declared, synthetic"; scores documented as heuristic; incomplete results are flagged (`paths_truncated`, `partial`); sensitivity analysis published | Presentation can still be over-read; see `CLAIMS.md` |
| **Misuse of results** | Using paths to plan an attack | ATHAR only reasons over a user-supplied model and offers no scanning, exploitation or credential handling | It could help an insider reason about a modelled environment, as any attack-graph tool can |
| **Supply chain** | Malicious or vulnerable dependency | Python versions pinned in a lockfile (no hashes); `pip-audit` and `npm audit` clean at the time of writing; self-hosted fonts | Lockfile lacks hashes; audits are point-in-time |
| **Unsafe deployment** | Binding to a network interface, using real data | Documented as unsupported; loopback default | Nothing prevents a user from doing it |

## What would be needed before real data
Authentication and roles, TLS and CSP behind a reverse proxy, tamper-evident audit logging with identity, an authorised data-collection design (and its own threat model), encryption at rest, calibration of weights, and an independent security review. None of this exists today.


## Additions for the public read-only demo

| Threat | Mitigation | Residual |
|---|---|---|
| Visitor modifies or wipes the shared model | Demo mode refuses every write without the admin token (`403 read_only_demo`), tested for each write endpoint | Anyone holding the admin token can still write: protect it like a password |
| Visitor fills the audit database | Visitor requests create no audit rows; simulations are computed but not stored | Rate limits still apply to reads |
| Visitor burns CPU with heavy requests | Shared small rate bucket for plans, sensitivity, reports, explain; sensitivity ignores visitor parameters and serves a cached run; plans are cached per state | A distributed flood is a platform-level problem (use the host's DDoS controls) |
| Visitor spends the AI budget | The public demo never calls the AI provider for visitors | none |
| Spoofed `X-Forwarded-For` to dodge limits or look like loopback | Header ignored unless `ATHAR_TRUST_PROXY=1`; only the right-most entry is trusted | Setting the flag without a proxy re-opens the spoof |
| Weak or reused secrets | Start-up refuses weak or colliding secrets in demo mode | Operator can still choose a guessable 16-character value |
| XSS via stored names | React escapes output; strict CSP without `unsafe-eval` and without inline scripts; a test stores HTML in names | `style-src 'unsafe-inline'` remains (graph library) |
| Clickjacking | `frame-ancestors 'none'` and `X-Frame-Options: DENY` | none |
| Secrets in the shipped bundle | Bundle scan in the build test and in `verify_deployment.py`; only `VITE_API_BASE` is compiled in | An operator could put a secret in a `VITE_` variable: documented as forbidden |
| Misleading evidence claims | `real_world` validation is rejected by the model; evidence labels are shown as declared, never upgraded | Declared labels can still be wrong; the UI says so |
| Presenting a heuristic as a probability | Every score view and explanation says "index, not a probability"; sensitivity ranges are labelled not confidence intervals | A reader can still ignore the text |
