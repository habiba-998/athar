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
| **Static build for Netlify** (`netlify.toml`, `npm run build:static`): the unchanged backend runs in the browser (Pyodide/WebAssembly) | built locally; 5 browser tests pass behind the production headers (zero third-party and zero `/api` requests); `verify_deployment.py --static` 13 passed, 0 failed, 1 skipped (HSTS, needs https); the same browser tests also pass through `playwright.external.config.ts` against the local build. CI job `static` added (not yet run on GitHub) |
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
| **Vercel (Hobby)** | Static app + Python (FastAPI/ASGI) function in one project; one origin, so no CORS or API base URL. The read-only demo needs no persistence, which suits a function with a read-only filesystem (only `/tmp` is writable). Docs state a 300 s maximum duration on Hobby with Fluid Compute, enough for the slowest request. | Free Hobby plan, deploys from GitHub; no card needed to start. | Tried first; **unresolved** (see below): three projects were created, the backend project returned 500 and the main one stayed behind Vercel Authentication |
| Cloudflare Pages + Workers | Python Workers are generally available on Pyodide (WebAssembly); FastAPI and Pydantic are listed as supported, NetworkX is pure Python. No SQLite persistence (would need a rewrite to D1 or Durable Objects) and per-request CPU limits on the free plan are far below ATHAR's 0.2-19 s requests. | Free tier exists, but CPU limits make it unsuitable without a paid plan. | Rejected: needs a rewrite and a paid CPU limit |
| Railway | Runs the Dockerfile as-is, supports volumes (persistent SQLite). | One-time $5 trial credit (30 days or until spent), then a Free plan with small allowances or the $5/month Hobby plan; whether a card is required is reported inconsistently. | Rejected for now: not free for long and may need a card |
| Fly.io | Runs the Dockerfile, volumes for SQLite. | Sources agree there is **no free allowance for new accounts**: a short trial, then a payment card is required. | Rejected: requires a card and incurs charges |
| Render | Docker service from a Blueprint. | Free web service sleeps and has an ephemeral disk. | Dropped at the owner's request (the sign-in/setup did not work out) |
| **Netlify (static, engine in the browser)** | Netlify Functions run JavaScript/TypeScript and Go only (confirmed in its current docs: no Python page, no FastAPI), so the backend cannot run there as a server. It does not need to: the same Python code runs in the visitor's browser (Pyodide/WebAssembly) and the site is purely static. Free plan: 300 credits/month with a hard limit (docs); whether a card is needed to sign up is **not stated** in the pages I read. | **Selected** (no server, no second host) |
| Hugging Face Docker Space | Runs the repository's own Docker image (frontend + API on one origin), no rewrite of ATHAR, no second service. Free CPU hardware; the Space reads its settings (`sdk: docker`, `app_port`) from the README header. | Free tier exists; whether a card is required was **not found** in the sources I read, check on the site. The Docker Spaces docs say there is no built-in persistence, which suits the stateless demo. | Prepared as the alternative that runs a real server (sign-up hit a human-check wall) |

**What is lost on Vercel, honestly.** A serverless function has no persistent disk and each instance has its own memory, so the deployment is the **read-only demo only**: no administrator writes (the admin token is deliberately not configured), the audit log and simulation history are not stored, and each cold start rebuilds state from the synthetic sample. Rate limits are per instance. The first request after idle can take a few seconds. If you need persistence, run the Docker image on a host with a volume (Option B) or add an external database (not implemented).

Sources: [Vercel function limits](https://vercel.com/docs/functions/limitations) and [Python runtime](https://vercel.com/docs/functions/runtimes), [Railway plans](https://docs.railway.com/pricing/plans), [Fly.io billing](https://fly.io/docs/about/billing/), [Cloudflare Python Workers](https://developers.cloudflare.com/workers/languages/python/).

## Modes

| Mode | Who can do what |
|---|---|
| `ATHAR_MODE=local` (default) | Private instance. Without `ATHAR_API_TOKEN` only loopback clients are accepted; with it, every `/api` call needs the token. Full read/write. |
| `ATHAR_MODE=demo` | **Public and read-only.** Anyone can read and run *stateless* simulations (not persisted, no AI calls, no audit rows). Every other write is refused with `403 read_only_demo` unless the request carries `ATHAR_ADMIN_TOKEN`. API docs are off, no cross-origin callers by default. A demo **refuses to start** if a configured secret is shorter than 16 characters or the two tokens are equal. |

## Deploying the static site to Netlify (selected): step by step

**What it is.** Netlify cannot run Python (its documented function runtimes are JavaScript/TypeScript and Go), so there is no server to deploy. Instead the **unchanged Python backend runs inside the visitor's browser**: Pyodide (CPython compiled to WebAssembly) in a Web Worker loads `backend/app` and answers every `/api/...` call of the frontend through an in-process ASGI bridge (`frontend/src/inbrowser/bridge.py`). Routing, validation, the read-only demo guard, scoring, plans, sensitivity and explanations are the same code as the server deployment, and the browser test suite exercises them end to end. The whole site is static files: `npm run build:static` produces `frontend/dist-static` (the app, the self-hosted Python runtime and libraries, the backend source, and a `_headers` file with the security headers). **Nothing is requested from any third-party host and no API request ever leaves the page** (a browser test asserts both).

**Measured here (Chromium, development laptop).** Python runtime + libraries about 16 MB on the first visit (cached afterwards, as the files are content-immutable); the dashboard appears 13-30 s after the first visit in the tests; analysis and recommendations are computed in under a second inside WebAssembly, plans about 0.7 s, a sensitivity run about 2.3 s (in Node's WebAssembly; phones were **not** measured and will be slower). Each visitor has a **private engine and state**: nothing is stored or shared, a reload resets everything, and it is the read-only demo only (no administrator, no editing, no stored history).

**What only you can do (accounts and approval).** I never see your password.
1. Sign in at https://app.netlify.com (the free plan; do not upgrade). If a human-check page blocks you ("Max challenge attempts exceeded"), see the troubleshooting list in the conversation or try *Continue with GitHub*.
2. *Add new site > Import an existing project > GitHub*, authorise Netlify for the repository `habiba-998/athar` only.
3. Netlify reads `netlify.toml`: base directory `frontend`, build command `npm ci && npm run build:static`, publish directory `dist-static`, Node 22. **Leave everything as detected and add no environment variables.** Click *Deploy*.
4. When the deploy is published Netlify shows `https://<name>.netlify.app` (you may rename it under *Site configuration > Change site name*). That is the permanent HTTPS address.
5. Verify from outside (I will run the same):
   ```powershell
   python scripts/verify_deployment.py https://<name>.netlify.app --static
   $env:ATHAR_STATIC_URL = "https://<name>.netlify.app"; cd frontend; npx playwright test -c playwright.external.config.ts
   ```
   The first checks the headers, the self-hosted runtime and the bundle; the second really starts the engine in a browser and runs the dashboard, recommendations, plans, simulation and sensitivity against the live site. Then open it on your phone over mobile data.
6. Send me the address. I will write it into the README only after both pass.

**No new account at all: GitHub Pages.** The same static build can be published from this repository with no extra service: *Settings > Pages > Source: GitHub Actions*, (GitHub does not let the workflow token create the Pages site, so enable it once by hand; until then the `pages` job skips its steps); the `pages` job publishes `https://habiba-998.github.io/athar/` after the gate. Pages cannot set response headers, so the CSP/HSTS of the Netlify deployment are **not** available there (the page still works: a relative-URL build).

**Known limits (honest).** Needs a browser with WebAssembly and module workers (verified: Chromium only; Safari 15+/Firefox 114+ are expected to work, not tested). Pyodide ships its own library versions (Python 3.14, pydantic 2.12.5, FastAPI 0.136.1, Starlette 1.0.0) which differ from the server lock (Python 3.12, pydantic 2.14.3, FastAPI 0.162.2); the bridge parity tests run under CPython and the browser tests run the real WebAssembly build, but the full 1,000-test backend suite does not run inside WebAssembly. The wheels are downloaded at build time from the official Pyodide distribution of the pinned version and **checked against its sha256 lock** before use.

## Deploying to a Hugging Face Docker Space (alternative with a real server): step by step

**What it is.** One container from `deploy/huggingface/Dockerfile` serves the built app and the API on one origin (no CORS, no API base URL, no localhost). It is the **public read-only demo** (`ATHAR_MODE=demo`, no admin token exists, simulations are not stored, runs as user 1000). The Space repository is a **derived build context** that `scripts/make_hf_space.py` assembles from this repository (Dockerfile, README with the Space settings, `backend/app`, the pinned runtime requirements, the frontend sources, nothing else). Your permanent address is `https://<hf-user>-<space-name>.hf.space` for as long as the Space exists (Hugging Face lowercases the name and turns dots/underscores into hyphens; copy the exact "Direct URL" the Space shows). **Free Spaces may be paused after inactivity and restart on the next visit; I did not verify the exact policy.**

**Done and verified locally (no Docker on the development machine).** The assembled Space was built from scratch: `npm ci && npm run build` inside the assembled folder, a clean virtual environment from the pinned requirements, the app run with the Space's environment on port 7860: the deployment verifier passed 36 of 36, the browser loaded the dashboard through `/api`, a simulation returned `ephemeral: true`. CI additionally builds **the Space's own Dockerfile** and checks it runs as uid 1000 (job `image`).

**What only you can do (accounts, tokens, approval).** I never see your password or token.
1. Create a free account at https://huggingface.co/join and confirm your e-mail.
2. *New Space*: owner = you, name `athar`, **SDK: Docker (Blank)**, hardware **CPU basic (free)**, visibility **Public**. Create it.
3. *Settings > Access Tokens > Create new token*: a **fine-grained** token with *write* access to that Space only (or the classic *Write* token). Copy it once. **Never paste it into chat, a file in the repository or the frontend.**
4. Publish, either way:
   - **From GitHub CI (recommended; only green commits are pushed).** In the GitHub repository *Settings > Secrets and variables > Actions*: add secret `HF_TOKEN` (the token), variables `HF_SPACE` = `<hf-user>/athar` and `SPACE_URL` = the Space's direct URL. Then re-run the latest workflow (or push any commit): the job `deploy-space` assembles the Space, force-pushes it, and re-verifies `SPACE_URL` from outside.
   - **By hand.** `python scripts/make_hf_space.py --out build/hf-space`, then `cd build/hf-space; git init -b main; git add -A; git commit -m "ATHAR"; git remote add space https://huggingface.co/spaces/<hf-user>/athar; git push --force space main`. Git asks for a username and password in your terminal: user name = your Hugging Face name, password = the token.
5. Watch the Space page: *Building* then *Running* (first build takes a few minutes). Then verify from your machine:
   ```powershell
   python scripts/verify_deployment.py https://<hf-user>-athar.hf.space --json space-report.json
   ```
   Every line must say PASS. Open it on a phone over mobile data. Send me the address and I will run the device checks and write it into the README only after they pass.

**Settings you may meet.** `app_port: 7860` in the Space README must equal the port in the Dockerfile (a test checks it). The Space page embeds the app in an iframe, so the container allows framing by `https://huggingface.co` and `https://*.hf.space` only (`ATHAR_FRAME_ANCESTORS`); everyone else is still refused. Forwarded headers are not trusted (the platform's proxy chain is not documented here), so the per-client rate limits are shared and are raised to 3000/600/300 per minute.

## Deploying to Vercel (tried first; unresolved): step by step

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

**What is documented by Vercel and what is not.** Documented (including Vercel's own FastAPI starter, which uses `root: backend/` with `entrypoint: app.main:app`, "relative to `backend/`"): the `services` key, `root`, `framework`, `entrypoint` (module:variable for Python), per-service `installCommand` / `buildCommand` / `outputDirectory` / `headers`, top-level `rewrites` with `destination.service`, original-path pass-through, Hobby plan availability (Beta), 300 s maximum duration on Hobby. **Not stated in the docs I read, so only provable by a real build:** where Vercel looks for `requirements.txt` and `.python-version` inside a service root, and the dashboard Framework Preset. Local emulation (static service + backend behind one origin, 36/36 verifier checks, browser workflow) proves ATHAR's side, not Vercel's.

### About "Vercel detects multiple FastAPI applications"
I could not see the exact message from your dashboard, so the cause is **not confirmed**. What I verified is the repository: there is exactly one FastAPI application (`backend/app/main.py`), one Python project root, and no stray entrypoint shims (`api/`, root `requirements.txt` and `frontend/vercel.json` were removed because each looked like another app or project; a test enforces this). The first attempt used a root-level shim (`api/index.py` importing the backend), which is the most likely source of a second "application". The **production entry point is `backend/app/main.py`, imported as the module `app.main`** (the package uses relative imports, so a bare-file import would fail; that is why `[tool.vercel] entrypoint = "app.main:app"` and the explicit `services` block are set). If Vercel still reports the ambiguity, send me the exact text.

### What the first Vercel import produced (observed 2026-11-09, from GitHub commit statuses and public probes)
Vercel built the repository as **three separate projects** under the same account (`athar`, `athar-31bj`, `athar-d85h`), all reporting success on commit `57de688`. That is almost certainly the "multiple applications" behaviour: the import created one project per detected app instead of one project with two services. Public probes: `athar-31bj.vercel.app` answers 404 on `/api/health` (a frontend-only project); `athar-d85h.vercel.app` answers **500 FUNCTION_INVOCATION_FAILED** (a backend-only project whose function crashed); the main project's URLs answer **302 "Protected by Vercel Authentication"**, so it is not public yet. The crash cause is not confirmed (no log access); one candidate is a platform loading `app/main.py` as a bare file, which failed with "attempted relative import with no known parent package". `main.py` now handles that case and `backend/pyproject.toml` declares `[tool.vercel] entrypoint = "app.main:app"`, both tested locally.

**Fix:** keep exactly **one** Vercel project: Root Directory empty (repository root), Framework Preset **Services**; **delete the other two projects**; under *Project Settings > Deployment Protection* turn **Vercel Authentication off** for production so the demo is public; redeploy.

### Needs your authorisation (I cannot sign in for you and never ask for passwords or tokens)
The built-in browser pane could not hold a Vercel login, so use **your own browser**:
1. Sign in at https://vercel.com (the free **Hobby** plan; do not add a card or upgrade).
2. *Add New > Project > Import* `habiba-998/athar` (approve Vercel's GitHub app for that repository only).
3. Settings on the import screen: **Root Directory = the repository root** (leave it empty or `./`, where `vercel.json` is) and **Framework Preset = Services**. Vercel's own guide for a FastAPI + frontend project says: "Set the project's Root Directory to the repository root and select the Services framework preset" (CLI equivalent: `vercel project update --framework services`); with any other preset only one app may build. If the project already exists: *Project Settings > Build and Deployment > Framework Preset = Services*, Root Directory empty, then *Deployments > Redeploy* (settings apply from the next deployment). Leave build/install/output commands empty: they come from the services. **Add no environment variables.**
4. Click **Deploy** and wait. Vercel publishes `https://<project>.vercel.app`, a permanent HTTPS address while the project exists.
5. Send me that address. If the build fails, copy the build log (not any token) to me.
6. **Gate production on CI** (afterwards): *Project Settings > Git > Production Branch = `release`*; the CI `deploy` job moves that branch only after the gate is green. Then add the GitHub Actions variable `PUBLIC_URL`.

### Verification (I run these once the address exists)
```powershell
python scripts/verify_deployment.py https://<project>.vercel.app --json deployment-report.json
```
then the device profiles (Android, iPhone, tablet, desktop; English and Arabic) with the Playwright suite pointed at the public address. These run from this laptop, which is not a truly independent network: open the address on your phone over **mobile data** for the real external check.

### Why a red check cannot reach production
Vercel's production branch is `release`. Only the CI `deploy` job can update it, `deploy` needs `gate`, and `gate` needs all six jobs (backend, frontend, e2e, mutation, image, static). A failing job therefore stops the promotion; the previous release stays live.

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
