# Deployment

## Status (read this first)

**ATHAR is not deployed to a public URL.** Publishing needs a source-code host account, a hosting account and a person to authorise the connection. None of that can be done from the build environment (no credentials; no `gh`, hosting CLI or Docker on the development machine), and creating accounts or signing in is deliberately left to the owner. Nothing in this repository claims a live address. **No URL may be written into slides, the README or this file until `scripts/verify_deployment.py` has passed against it from outside.**

What *is* done and verified:

| Item | State |
|---|---|
| Single production image/service (FastAPI serves the built app: one origin, no CORS needed) | built and exercised as a simulated image: clean venv from `backend/requirements.prod.txt`, `pip check` clean, image layout reproduced, verifier 36/36 |
| `Dockerfile` (multi-stage, non-root, health check) | written; **not built on this machine (no Docker)**. The CI job `image` builds it, starts it, checks it runs as non-root and runs the verifier against it |
| Dependency advisories | `pip-audit` on the production pins: **no known vulnerabilities**; `npm audit` (production, and all): **0 vulnerabilities** (2026-11-09) |
| CI/CD (`.github/workflows/ci.yml`) | written; **has not run yet** (no repository exists remotely) |
| Hosting configuration (`render.yaml`, `frontend/vercel.json`, `.env.example`) | written and parsed; not applied |
| External verification (`scripts/verify_deployment.py`) | rehearsed against local production-mode servers only |

## Hosting platform evaluation

Requirements: run a stateful Python API with a small SQLite file, serve a static React build, permanent HTTPS URL, low cost, deployable from a repository, no cloud expertise needed. Facts below are from general knowledge of these products and **must be re-checked on the vendor's pricing page before you commit** (plans change).

| Platform | Fit | Notes |
|---|---|---|
| **Render (recommended)** | Docker web service from a Blueprint; free `*.onrender.com` HTTPS URL that stays the same for the life of the service; deploy hook for CI; custom domains with managed TLS | Free instances sleep when idle (first request can take tens of seconds) and have an ephemeral disk. A paid instance can attach a persistent disk. |
| Fly.io | Docker, volumes for SQLite, regional placement | Needs a payment card and the `flyctl` CLI; more operational surface than needed here. |
| Google Cloud Run / Azure Container Apps | Excellent HTTPS and scaling | Needs a cloud project, billing and IAM; SQLite on local disk is ephemeral (would need a database or a mounted bucket). Over-built for a demo. |
| Railway / Koyeb | Similar to Render | Free allowances change often. |
| Vercel / Netlify | Excellent for the **React build only** | The API is a long-running stateful process with SQLite and background caches; serverless functions are a poor fit. Use only for a split layout (Option C). |
| Hugging Face Spaces (Docker) | Free, public | Port and storage conventions differ; not a general application host. |

**Choice: Render, single Docker service.** It serves API and app from one origin (so nothing to "connect" between two services), gives a permanent HTTPS URL, and has a deploy hook the CI pipeline can call.

**Persistence.** The public demo is read-only and **deliberately stateless**: it restarts from the synthetic sample, so no persistent disk is needed for it. If you want administrator edits, imported environments and the audit log to survive restarts, use a paid instance with a disk and uncomment the `disk:` block in `render.yaml` (it mounts `/data` and sets `ATHAR_DB=/data/athar.db`). Restart persistence of the local build is verified by `scripts/verify_live.py` (edit, history, evidence and activity survive a real process restart: 26/26 checks).

## Modes

| Mode | Who can do what |
|---|---|
| `ATHAR_MODE=local` (default) | Private instance. Without `ATHAR_API_TOKEN` only loopback clients are accepted; with it, every `/api` call needs the token. Full read/write. |
| `ATHAR_MODE=demo` | **Public and read-only.** Anyone can read and run *stateless* simulations (not persisted, no AI calls, no audit rows). Every other write is refused with `403 read_only_demo` unless the request carries `ATHAR_ADMIN_TOKEN`. API docs are off, no cross-origin callers by default. A demo **refuses to start** if a configured secret is shorter than 16 characters or the two tokens are equal. |

## Step-by-step: what I did and what only you can do

### Already done (no action needed)
1. Production build, simulated image, audits, header/CORS/HTTPS-proxy review, tests and CI definition (see Status).
2. A local git repository with one commit containing the whole project (see "Repository" below).

### YOU must do these (each needs your accounts or approval)
1. **Create an empty GitHub repository** (private or public) named, for example, `athar`. Do not add a README.
2. **Push the project** (in `athar/`): `git remote add origin https://github.com/<you>/athar.git` then `git push -u origin main`. (Git will ask you to sign in; I never see your credentials.)
3. **Watch the first CI run** (Actions tab). All of `backend`, `frontend`, `e2e`, `mutation`, `image` must be green; the `gate` job summarises them. If one fails, send me its log and I will fix it.
4. **Create the Render service**: sign in to Render, **New > Blueprint**, pick the repository, review, **Apply**. Render builds the `Dockerfile`; wait for the deploy to finish. It shows the permanent HTTPS address (`https://<service-name>.onrender.com`).
5. **Verify from outside** (from your own machine or phone network):
   ```powershell
   python scripts/verify_deployment.py https://<the-address-render-shows> --json deployment-report.json
   ```
   Every line must say PASS. Then open the address on your phone and desktop (checklist below).
6. **Turn on continuous deployment through CI** (optional): in Render, *Settings > Deploy Hook* copy the URL; in GitHub *Settings > Secrets and variables > Actions*, add secret `RENDER_DEPLOY_HOOK_URL` and variable `PUBLIC_URL` (the address from step 4). From then on every push to `main` deploys **only if the gate is green**, and the pipeline re-verifies the public URL. In GitHub *Settings > Environments > production* you may add required reviewers for a manual approval.
7. Give me the verified address and I will put it in the README and the demo script.

### Why the gate cannot be bypassed by accident
`render.yaml` sets `autoDeploy: false`, so Render never deploys on its own. The only automated path is the `deploy` job, which `needs: gate`, which `needs` all five jobs; it runs only on `main`, inside the `production` environment.

## Option A: one service on Render (recommended, described above)

Notes: `ATHAR_TRUST_PROXY=1` is set because Render is exactly one trusted proxy hop that appends the client address to `X-Forwarded-For`; only the right-most entry is trusted. `ATHAR_FORCE_HTTPS=1` redirects anything the proxy reports as plain http to https (health and readiness probes are exempt), `ATHAR_HSTS=1` sends `Strict-Transport-Security`. `ATHAR_ADMIN_TOKEN` is generated by Render; read it in the dashboard only if you want administrator writes.

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
| Secrets | none in the repository or the image (scanned by a test); tokens from the environment; Render generates the admin token; the frontend bundle holds only `VITE_API_BASE` (public) |
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
- [ ] Restart the service in the Render dashboard; the demo comes back with the sample (stateless by design).
- [ ] `ATHAR_MODE=demo`, no AI key configured, admin token not shared.
