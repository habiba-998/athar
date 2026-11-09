# Security assumptions, controls and limitations

## Scope and what ATHAR does not do
Synthetic data only. No scanning, no network calls to targets, no exploitation, no credential handling, no execution of any change. The only outbound request is the optional AI narration to the fixed host `api.anthropic.com`, which receives only the structured facts of one finding (synthetic data).

## Access model (local demo)
- **Default: local-only.** Without `ATHAR_API_TOKEN` the API accepts only loopback clients (`127.0.0.1`, `::1`); others get `403 local_only`. Run uvicorn on loopback (the default); binding it to `0.0.0.0` is not a supported configuration.
- **Token mode.** With `ATHAR_API_TOKEN` set, every `/api` call except `/api/health` and `/api/auth/status` must carry `X-ATHAR-Token` (constant-time comparison); otherwise `401`. The UI prompts for the token and keeps it in `sessionStorage` only (never `localStorage`), discarding it on a 401.
- This is a demo-grade shared secret. It gives no per-user identity, roles, or accountability.

## Controls and how they were verified
| Control | Behaviour | Evidence |
|---|---|---|
| Rate limiting | Sliding window per client IP: reads 300/min, writes 90/min, explain 40/min (configurable); `429` + `Retry-After`; unauthenticated requests count too | unit tests; live server test (limit enforced, buckets independent) |
| Request size | `413` above 1 MB; `411` when `Content-Length` is missing (blocks chunked bypass) | unit + live tests |
| CORS | Explicit origin list (no `*`, scheme-checked); only GET/POST/PUT/DELETE and two headers; guard rejections still carry CORS headers so the UI can read them | unit + live tests |
| Input validation | Strict Pydantic models (`extra=forbid`), safe-charset ids, bounded sizes, enum-only action kinds, whole-graph consistency on every edit/import; rejected input never changes state | unit + e2e tests incl. XSS/SQLi-shaped payloads |
| Injection | Parameterised SQL only; ids are never used to build paths, commands or SQL | tests with injection-shaped ids; DB verified intact |
| XSS | React escapes all output; no `dangerouslySetInnerHTML`; AI text rendered as plain text; API is JSON-only | review + test that HTML in names round-trips as inert data |
| SSRF | No user-controlled URL anywhere; AI endpoint is a constant | review |
| Secrets | None in the repo; the API key comes from the environment and is never returned or logged (`/api/ai/status` shows only enabled/provider/reason) | unit test |
| Errors | Unhandled exceptions return `{"error":"internal_error"}` only | unit test |
| Headers | `X-Content-Type-Options: nosniff`, `Cache-Control: no-store`, `Referrer-Policy: no-referrer` on all responses incl. errors | unit test |
| Denial of service by input | pruned path search, global caps and a deterministic step budget; candidate cap for recommendations; copy-on-write simulation | worst-case test (500 assets / 5000 relationships analysed in 72 ms; recommendations 8 s) |
| AI containment | model gets only the evidence JSON; output capped at 1500 chars, rendered in a separate labelled block, cannot create findings or trigger actions; every failure falls back to deterministic text | unit tests with mocked responses; live check with a fake key |

## Dependencies
- **Python**: `requirements.lock.txt` pins 30 packages (versions, no hashes). `pip-audit` reported no known vulnerabilities. A fresh virtualenv built only from the lock passes all backend tests.
- **npm**: `npm audit` was reporting 1 moderate advisory (minimatch via ESLint, dev-only). npm's suggested fix was a *downgrade* to ESLint 9, which I did not accept. Instead `package.json` has `"overrides": {"minimatch": "^11.0.5"}`; ESLint, TypeScript, Vitest and the build all still work and `npm audit` now reports 0 vulnerabilities. Revisit the override when ESLint publishes a release that depends on a fixed minimatch itself.
- Added dev dependencies: `@axe-core/playwright` (accessibility tests), `@types/node`.

See also `THREAT_MODEL.md` (STRIDE analysis of ATHAR and the attacker model assumed by the analysis) and `TECHNICAL_VALIDATION.md`.

**Prompt injection through data.** Asset and relationship names in an imported file are part of the facts sent to the optional AI narration, so a crafted name could try to steer the narration. Mitigations: structured facts only, plain-text rendering in a separate "not evidence" block, a 1,500-character cap, and no tool use or influence on any number. Not tested against a live model.

## Known limitations (do not deploy as-is)
1. Shared token / loopback only; no users, roles, session management or per-user audit.
2. No TLS and no `Content-Security-Policy`/other browser hardening headers are served for the frontend (Vite dev server); a real deployment needs a reverse proxy with HTTPS and CSP.
3. The rate limiter is in-memory, per process and keyed by client IP (behind a proxy every client would look like the proxy).
4. SQLite file is unencrypted; no schema migrations; undo history is memory-only.
5. Environment import is JSON only and trusts the declared `evidence` labels.
6. Scores and evidence labels are synthetic modelling choices, not measurements of real risk.
7. The AI path has never been exercised with a valid key. Sending even synthetic findings to a third-party model is a data-handling decision for any real deployment.
8. A real deployment would ingest real environment data, which brings new threat surface (authorised collection, tenant isolation, secret handling) that this MVP deliberately avoids.


## Production hardening (advanced-intelligence sprint)

**Two access modes** (`ATHAR_MODE`, see `DEPLOYMENT.md` and `ARCHITECTURE.md`):

- `local` (default): loopback only, or a shared `ATHAR_API_TOKEN` (constant-time comparison).
- `demo`: public and read-only. Visitors may read and run stateless simulations; **every other write needs `ATHAR_ADMIN_TOKEN`**. Visitor requests never create audit rows, never call the AI provider and never trigger new heavy computations (the sensitivity endpoint ignores their parameters and serves one cached default run). The interactive API docs are disabled. The server **fails closed at start-up** if a configured secret is shorter than 16 characters or the two tokens are equal.

**Transport and browser hardening.** Every response carries `Content-Security-Policy` (`default-src 'self'`, `script-src 'self'`, `object-src 'none'`, `base-uri 'none'`, `frame-ancestors 'none'`; style `'unsafe-inline'` is needed by the graph library), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, a restrictive `Permissions-Policy`, `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy`, and `Cache-Control: no-store` on the API. `Strict-Transport-Security` is sent over https (or when forced with `ATHAR_HSTS=1`). TLS itself is terminated by the hosting platform; ATHAR does not terminate TLS.

**Proxy handling.** `X-Forwarded-For` / `X-Forwarded-Proto` are ignored unless `ATHAR_TRUST_PROXY=1`, and then only the right-most `X-Forwarded-For` entry is used (the part a client can forge is on the left). Without this, a caller could claim to be loopback or reset its rate-limit window.

**CORS and HTTPS.** Cross-origin access is an explicit allow-list (no wildcards); the public demo defaults to *no* cross-origin callers because it serves the app itself. `ATHAR_FORCE_HTTPS=1` (with a trusted proxy) redirects plain-http requests to https; HSTS is sent over https.

**Rate limiting and size limits** as before; expensive endpoints (explain, plans, sensitivity, reports) share the small bucket.

**Secrets.** Tokens come only from the environment; they are never logged, never echoed, never in the frontend bundle (`VITE_API_BASE` is public by design and documented as such), and a test scans the repository for secret-shaped strings. `.env` is git-ignored; `.env.example` has empty secret fields.

**Logging.** One JSON line per request (`request_id`, method, path, status, duration, a short one-way hash of the client address, mode). No bodies, query strings, tokens, raw addresses or tracebacks.

**Static serving.** The single-page app is served only from the configured build directory; path traversal (including encoded forms) is tested.

**Container.** Multi-stage build, non-root user, runtime-only pinned dependencies (`backend/requirements.prod.txt`, a test checks they are a subset of the lock with identical versions), health check on `/api/ready`.

### Known gaps (unchanged by this sprint)
A shared token is not user authentication: no accounts, roles, SSO or per-user audit. The rate limiter is per process. SQLite is unencrypted. There has been no external penetration test; `scripts/verify_deployment.py` is a configuration check, not an attack.
