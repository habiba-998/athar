# Deployment

## Status (read this first)

**ATHAR is not deployed to a public URL.** Publishing needs a source-code host account, a hosting account and a person to authorise the connection. None of that can be done from the build environment (no credentials; no `gh`, hosting CLI or Docker on the development machine), and creating accounts or signing in is deliberately left to the owner. Nothing in this repository claims a live address. **No URL may be written into slides, the README or this file until `scripts/verify_deployment.py` has passed against it from outside.**

What *is* done and verified:

| Item | State |
|---|---|
| Single production image/service (FastAPI serves the built app: one origin, no CORS needed) | built and exercised as a simulated image: clean venv from `backend/requirements.prod.txt`, `pip check` clean, image layout reproduced, verifier 36/36 |
| `Dockerfile` (multi-stage, non-root, health check) | **built and tested in CI** (job `image`: build, run, non-root check, verifier against the container). Not built on the development machine (no Docker there). Used for Option B, not for Vercel |
| Dependency advisories | `pip-audit` on the production pins: **no known vulnerabilities**; `npm audit` (production, and all): **0 vulnerabilities** (2026-11-09) |
| CI/CD (`.github/workflows/ci.yml`) | **ran on GitHub: all 7 jobs green** on the first push (backend, frontend, e2e, mutation, image, gate, deploy) |
| Hosting configuration (`vercel.json`, `api/index.py`, `requirements.txt`, `.python-version`) | written and tested locally (entrypoint serves the read-only demo through the ASGI test client); **not yet deployed** |
| External verification (`scripts/verify_deployment.py`) | rehearsed against local production-mode servers only |

## Hosting platform evaluation (2026-11-09)

ATHAR's actual architecture decides what can host it:

* a **stateful Python ASGI API** (FastAPI, `contextvars`, threads, in-memory caches, NetworkX) with **CPU-heavy requests** (plans 1-6 s, sensitivity 7-19 s, first request on a cold process);
* a **SQLite file** for the audit trail and stored environment (local mode);
* a **static React build**;
* a public **read-only demo mode** that is stateless by design (no writes, simulations not stored).

Requirements from the owner: free or lowest cost, **no card and no charges without approval**, HTTPS, deploy from the GitHub repository, no localhost in production.

| Platform | Fit with this architecture | Cost / account facts found (sources checked 2026-11-09; re-check before relying on them) | Verdict |
|---|---|---|---|
| **Vercel (Hobby)** | Static app + Python (FastAPI/ASGI) function in one project; one origin, so no CORS or API base URL. The read-only demo needs no persistence, which suits a function with a read-only filesystem (only `/tmp` is writable). Docs state a 300 s maximum duration on Hobby with Fluid Compute, enough for the slowest request. | Free Hobby plan, deploys from GitHub; no card needed to start. | **Selected** |
| Cloudflare Pages + Workers | Python Workers are generally available on Pyodide (WebAssembly); FastAPI and Pydantic are listed as supported, NetworkX is pure Python. No SQLite persistence (would need a rewrite to D1 or Durable Objects) and per-request CPU limits on the free plan are far below ATHAR's 0.2-19 s requests. | Free tier exists, but CPU limits make it unsuitable without a paid plan. | Rejected: needs a rewrite and a paid CPU limit |
| Railway | Runs the Dockerfile as-is, supports volumes (persistent SQLite). | One-time $5 trial credit (30 days or until spent), then a Free plan with small allowances or the $5/month Hobby plan; whether a card is required is reported inconsistently. | Rejected for now: not free for long and may need a card |
| Fly.io | Runs the Dockerfile, volumes for SQLite. | Sources agree there is **no free allowance for new accounts**: a short trial, then a payment card is required. | Rejected: requires a card and incurs charges |
| Render | Docker service from a Blueprint. | Free web service sleeps and has an ephemeral disk. | Dropped at the owner's request (the sign-in/setup did not work out) |

**What is lost on Vercel, honestly.** A serverless function has no persistent disk and each instance has its own memory, so the deployment is the **read-only demo only**: no administrator writes (the admin token is deliberately not configured), the audit log and simulation history are not stored, and each cold start rebuilds state from the synthetic sample. Rate limits are per instance. The first request after idle can take a few seconds. If you need persistence, run the Docker image on a host with a volume (Option B) or add an external database (not implemented).

Sources: [Vercel function limits](https://vercel.com/docs/functions/limitations) and [Python runtime](https://vercel.com/docs/functions/runtimes), [Railway plans](https://docs.railway.com/pricing/plans), [Fly.io billing](https://fly.io/docs/about/billing/), [Cloudflare Python Workers](https://developers.cloudflare.com/workers/languages/python/).

## Modes

| Mode | Who can do what |
|---|---|
| `ATHAR_MODE=local` (default) | Private instance. Without `ATHAR_API_TOKEN` only loopback clients are accepted; with it, every `/api` call needs the token. Full read/write. |
| `ATHAR_MODE=demo` | **Public and read-only.** Anyone can read and run *stateless* simulations (not persisted, no AI calls, no audit rows). Every other write is refused with `403 read_only_demo` unless the request carries `ATHAR_ADMIN_TOKEN`. API docs are off, no cross-origin callers by default. A demo **refuses to start** if a configured secret is shorter than 16 characters or the two tokens are equal. |

## Deploying to Vercel (selected): step by step

### Already done
1. Code on GitHub (`habiba-998/athar`), CI green, `vercel.json` / `api/index.py` / `requirements.txt` in place, entrypoint tested locally.

### Needs your authorisation (I cannot sign in for you and never ask for passwords or tokens)
1. **Sign in to Vercel** (https://vercel.com/login, "Continue with GitHub" is simplest) in the browser pane. The free **Hobby** plan is enough; do not add a card or upgrade.
2. **Import the repository**: *Add New > Project > Import* `habiba-998/athar`. If Vercel asks to install its GitHub app, approve it for that repository only.
3. **Project settings** (I will drive these once you are signed in): Framework Preset *Other*, Root Directory `./`, leave Build/Install/Output at the values read from `vercel.json`. **No environment variable or secret is required**; the defaults in `api/index.py` are non-secret.
4. **Deploy.** Vercel builds the frontend, installs the Python dependencies and publishes `https://<project>.vercel.app`: a permanent HTTPS address for as long as the project exists.
5. **Gate production on CI** (recommended): create a branch named `release` (the CI deploy job creates it on the first green run), then *Project Settings > Git > Production Branch = `release`*. From then on pushes to `main` only create preview deployments; only the CI `deploy` job, after the `gate` job passed, moves `release`.
6. In GitHub *Settings > Secrets and variables > Actions > Variables* add `PUBLIC_URL` (the verified address) so the pipeline re-verifies every release.

### Verification (I run these once the address exists)
```powershell
python scripts/verify_deployment.py https://<project>.vercel.app --json deployment-report.json
```
then the device profiles (Android, iPhone, tablet, desktop; English and Arabic) with the Playwright suite pointed at the public address. These run from this laptop, which is not a truly independent network: open the address on your phone over **mobile data** for the real external check.

### Why a red check cannot reach production
Vercel's production branch is `release`. Only the CI `deploy` job can update it, `deploy` needs `gate`, and `gate` needs all five jobs. A failing job therefore stops the promotion; the previous release stays live.

## Option B: any container host

```bash
docker build -t athar .
docker run --rm -p 8000:8000 -e ATHAR_ADMIN_TOKEN="$(python -c 'import secrets;print(secrets.token_urlsafe(32))')" athar
```

Put it behind a TLS-terminating proxy or platform load balancer. Set `ATHAR_TRUST_PROXY=1` only if exactly one such proxy sits in front. Mount a volume at `/data` for persistence (the image already points `ATHAR_DB` there).

## Option C: split frontend and API

Frontend on a static host (Vercel config in `frontend/vercel.json`), API as in A or B.
1. Deploy the API and note its https origin.
2. Build the frontend with `VITE_API_BASE=https://<api-origin>` (no trailing slash; **never put a secret here, it is public**).
3. In `frontend/vercel.json` replace `REPLACE_WITH_YOUR_API_ORIGIN` in the CSP `connect-src` (a placeholder is shipped on purpose; no URL is guessed).
4. On the API set `ATHAR_CORS_ORIGINS=https://<frontend-origin>` (no wildcards accepted).
5. Run the verifier against the **frontend** URL and again against the API.

## Environment variables

See [ARCHITECTURE.md](ARCHITECTURE.md#environment-variable-reference); `.env.example` lists every variable the code reads (a test fails if one is missing). Secrets only come from the environment, never from files in the repository.

## Security review summary (2026-11-09)

| Area | Finding |
|---|---|
| Exposed ports | the image exposes only `8000` (`PORT` is honoured); no other listener |
| Secrets | none in the repository or the image (scanned by a test); no token is needed for the read-only demo (none is configured on Vercel); the frontend bundle holds only `VITE_API_BASE` (public) |
| Environment | every variable documented and listed in `.env.example`; weak or equal secrets stop a demo from starting |
| Database | SQLite at `ATHAR_DB`; ephemeral by design on the free tier; unencrypted (documented gap) |
| CORS | explicit allow-list, no wildcard; the demo defaults to none |
| HTTPS / proxy | TLS terminated by the platform; `X-Forwarded-*` trusted only with `ATHAR_TRUST_PROXY=1` and only the right-most entry; optional redirect and HSTS |
| Headers | CSP (`default-src 'self'`, no `unsafe-eval`, no inline scripts), `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, COOP/CORP, `no-store` on the API, immutable caching only for hashed assets |
| Dependencies | no known vulnerabilities in production pins (`pip-audit`) or in npm (production and development) |
| Not done | Docker build locally; external penetration test; real authentication; WebKit/Safari engine testing |

## Pre-share checklist (after step 5)

- [ ] `verify_deployment.py` passes against the real https URL.
- [ ] Desktop Chrome and Edge: dashboard, graph (select a path, search, full screen), simulation, recommendations, plans, evidence.
- [ ] **Android phone on mobile data**: same flow; rotate; Arabic.
- [ ] **iPhone (Safari) on mobile data**: same flow; Arabic. *Automated iPhone tests here emulate Safari's viewport and touch on Chromium, not the WebKit engine, so this manual pass is the only real Safari check.*
- [ ] Redeploy or wait for a cold start; the demo comes back with the synthetic sample (stateless by design).
- [ ] `ATHAR_MODE=demo`, no AI key configured, admin token not shared.
