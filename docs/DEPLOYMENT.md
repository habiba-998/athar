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
| Hosting configuration (`vercel.json` with a `services` block, `backend/pyproject.toml` `[tool.vercel]`, `backend/requirements.txt`, `backend/.python-version`) | written; the backend runs as the read-only demo when `VERCEL=1` (tested locally through the ASGI test client); **not yet deployed, so the Vercel build itself is unverified** |
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
1. Code on GitHub (`habiba-998/athar`), CI green, Services layout in place, backend defaults tested locally.

### How the project is laid out for Vercel (one project, two services)
`vercel.json` uses **Vercel Services** (Beta, all plans per Vercel's docs). Exactly two services, no duplicates:

| Service | Root | What it is | Settings |
|---|---|---|---|
| `frontend` | `frontend/` | the Vite + React single-page app (entry `frontend/index.html` -> `src/main.tsx`) | `npm ci`, `npm run build`, output `dist`, security headers and asset caching (service-scoped `headers`) |
| `backend` | `backend/` | the **only** FastAPI application, `backend/app/main.py`, loaded as module `app.main` (variable `app`) | framework `fastapi`, entrypoint `app.main:app`, dependencies from `backend/requirements.txt` (pinned runtime set), Python 3.12 from `backend/.python-version` |

**Which service handles which route** (top-level `rewrites`, evaluated in order, first match wins; the service receives the original path):

| Public request | Handled by | Notes |
|---|---|---|
| `/api/*` (health, ready, auth, environment, analysis, plans, sensitivity, evidence, services, simulate, explain, ...) | `backend` | all 30 API paths the frontend calls start with `/api` and exist on the backend (checked) |
| `/` and every other path (`/assets/*`, `index.html`, fonts) | `frontend` | static files; the app has no client-side routes, so unknown paths are a plain 404 |

The browser only talks to its own origin: **no API base URL, no localhost, no CORS**; `VITE_API_BASE` is empty. **Service bindings are not needed**: bindings are only for one service calling another from server code, and here the browser reaches the backend through the public rewrite. On Vercel (`VERCEL=1`) the backend defaults to the read-only demo with a `/tmp` database (`backend/app/__init__.py`), so **no environment variable and no secret is required**. CORS: same origin needs none; the demo allows no cross-origin callers unless `ATHAR_CORS_ORIGINS` is set.

**What is documented by Vercel and what is not.** Documented: the `services` key, `root`, `framework`, `entrypoint` (module:variable for Python), per-service `installCommand` / `buildCommand` / `outputDirectory` / `headers`, top-level `rewrites` with `destination.service`, original-path pass-through, Hobby plan availability (Beta), 300 s maximum duration on Hobby. **Not stated in the docs I read, so only provable by a real build:** that `app.main:app` resolves relative to `backend/` (the docs' own example `root: backend/` with `main:app` implies it), where Vercel looks for `requirements.txt` and `.python-version` inside a service root, and the dashboard Framework Preset. Local emulation (static service + backend behind one origin, 36/36 verifier checks, browser workflow) proves ATHAR's side, not Vercel's.

### About "Vercel detects multiple FastAPI applications"
I could not see the exact message from your dashboard, so the cause is **not confirmed**. What I verified is the repository: there is exactly one FastAPI application (`backend/app/main.py`), one Python project root, and no stray entrypoint shims (`api/`, root `requirements.txt` and `frontend/vercel.json` were removed because each looked like another app or project; a test enforces this). The first attempt used a root-level shim (`api/index.py` importing the backend), which is the most likely source of a second "application". The **production entry point is `backend/app/main.py`, imported as the module `app.main`** (the package uses relative imports, so a bare-file import would fail; that is why `[tool.vercel] entrypoint = "app.main:app"` and the explicit `services` block are set). If Vercel still reports the ambiguity, send me the exact text.

### Needs your authorisation (I cannot sign in for you and never ask for passwords or tokens)
The built-in browser pane could not hold a Vercel login, so use **your own browser**:
1. Sign in at https://vercel.com (the free **Hobby** plan; do not add a card or upgrade).
2. *Add New > Project > Import* `habiba-998/athar` (approve Vercel's GitHub app for that repository only).
3. Settings on the import screen: **Root Directory `./`** (the repository root, where `vercel.json` is). If a *Framework Preset* is required choose **Services** if it is offered, otherwise **Other**. Leave build/install/output empty: they come from the services. **Add no environment variables.**
4. Click **Deploy** and wait. Vercel publishes `https://<project>.vercel.app`, a permanent HTTPS address while the project exists.
5. Send me that address. If the build fails, copy the build log (not any token) to me.
6. **Gate production on CI** (afterwards): *Project Settings > Git > Production Branch = `release`*; the CI `deploy` job moves that branch only after the gate is green. Then add the GitHub Actions variable `PUBLIC_URL`.

### Verification (I run these once the address exists)
```powershell
python scripts/verify_deployment.py https://<project>.vercel.app --json deployment-report.json
```
then the device profiles (Android, iPhone, tablet, desktop; English and Arabic) with the Playwright suite pointed at the public address. These run from this laptop, which is not a truly independent network: open the address on your phone over **mobile data** for the real external check.

### Why a red check cannot reach production
Vercel's production branch is `release`. Only the CI `deploy` job can update it, `deploy` needs `gate`, and `gate` needs all five jobs. A failing job therefore stops the promotion; the previous release stays live.

## Fallback if Vercel Services cannot host the backend
Services is a Beta feature. If the build fails in a way I cannot fix from the log, the compatible free alternative that keeps the frontend on Vercel is: backend as the Docker image on a no-card host (for example a Hugging Face Docker Space, which serves on one port and is free but has an ephemeral disk; **unverified here**), frontend on Vercel built with `VITE_API_BASE=https://<backend-address>` and the backend started with `ATHAR_CORS_ORIGINS=https://<project>.vercel.app`. I would only do this after the Services attempt fails.

## Option B: any container host

```bash
docker build -f deploy/Dockerfile -t athar .
docker run --rm -p 8000:8000 -e ATHAR_ADMIN_TOKEN="$(python -c 'import secrets;print(secrets.token_urlsafe(32))')" athar
```

Put it behind a TLS-terminating proxy or platform load balancer. Set `ATHAR_TRUST_PROXY=1` only if exactly one such proxy sits in front. Mount a volume at `/data` for persistence (the image already points `ATHAR_DB` there).

## Option C: split frontend and API

Frontend on a static host (config in `deploy/vercel.frontend-only.json`: copy it to `vercel.json` of a project whose Root Directory is `frontend`), API as in Option B.
1. Deploy the API and note its https origin.
2. Build the frontend with `VITE_API_BASE=https://<api-origin>` (no trailing slash; **never put a secret here, it is public**).
3. In that file replace `REPLACE_WITH_YOUR_API_ORIGIN` in the CSP `connect-src` (a placeholder is shipped on purpose; no URL is guessed).
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
