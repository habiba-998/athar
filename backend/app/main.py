"""ATHAR FastAPI application: analysis, environment management and simulation over synthetic data."""
from __future__ import annotations

import sys
from pathlib import Path

if not __package__:
    # Some platforms load the entrypoint FILE directly (as a top-level module named "main") instead of importing `app.main`; the
    # relative imports below would then fail with "no known parent package". Make the package importable and name it.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "app"

import logging
import os
import time
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import ValidationError

from . import logging_setup, security
from .analysis import DEFAULT_CONFIG
from .business import service_dependencies
from .evidence import evidence_overview
from .explain import ai_narrative, ai_status, path_facts, template_path, template_recommendation
from .models import Asset, Environment, ExplainRequest, Relationship, ScoringConfig, SimulationRequest
from .narrative import plan_report, plan_summary, recommendation_explanation
from .sensitivity import DEFAULT_SEED, DEFAULT_SPREAD, DEFAULT_TRIALS, MAX_SPREAD, MAX_TRIALS
from .simulation import SimulationError, simulate
from .state import AppState
from .store import Store

VERSION = "0.3.0"
logging_setup.setup()
_problems = security.secret_problems()
if _problems and security.is_demo():
    raise RuntimeError("refusing to start a public demo with weak secrets: " + "; ".join(_problems))   # fail closed
for _p in _problems:
    logging_setup.log("configuration_warning", logging.WARNING, problem=_p)

# Interactive API docs are convenient locally but are disabled in the public demo (smaller attack surface, strict CSP).
_docs = not security.is_demo() or os.environ.get("ATHAR_DOCS") == "1"
app = FastAPI(title="ATHAR API", version=VERSION,
              description="Synthetic-data attack path analysis and defensive simulation. No real systems are touched.",
              docs_url="/docs" if _docs else None, redoc_url=None, openapi_url="/openapi.json" if _docs else None)

DB_PATH = os.environ.get("ATHAR_DB", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "athar.db"))
if DB_PATH != ":memory:":
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)

state = AppState(Store(DB_PATH))
limiter = security.RateLimiter()


def _origins() -> list[str]:
    # A public demo is same-origin by default (the API serves the app), so it allows NO cross-origin callers unless configured.
    default = "" if security.is_demo() else "http://localhost:5173,http://127.0.0.1:5173"
    raw = os.environ.get("ATHAR_CORS_ORIGINS", default)
    return [o.strip() for o in raw.split(",") if o.strip().startswith(("http://", "https://")) and "*" not in o]


def _csp() -> str:
    extra = " ".join(o for o in os.environ.get("ATHAR_CSP_CONNECT", "").split() if o.startswith("https://") and "*" not in o)
    return ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; "
            f"connect-src 'self' {extra}".rstrip() + "; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")


CSP = _csp()
DOC_PATHS = {"/docs", "/openapi.json"}


@app.middleware("http")
async def guard_and_headers(request: Request, call_next):
    rid = uuid.uuid4().hex[:12]
    t0 = time.perf_counter()
    if os.environ.get("ATHAR_FORCE_HTTPS") == "1" and security.trust_proxy() and request.url.path not in ("/api/health", "/api/ready"):
        # Behind a trusted TLS-terminating proxy: anything that arrived as plain http is sent to https (308 keeps the method).
        if request.headers.get("x-forwarded-proto", "").split(",")[-1].strip() == "http":
            host = request.headers.get("host", "")
            return RedirectResponse(f"https://{host}{request.url.path}" + (f"?{request.url.query}" if request.url.query else ""), status_code=308)
    try:
        resp = await security.guard(request, call_next, limiter)
    except Exception:
        logging_setup.log("request", logging.ERROR, request_id=rid, method=request.method, path=request.url.path, status=500,
                          ms=round(1000 * (time.perf_counter() - t0), 1))
        raise
    h = resp.headers
    h["X-Content-Type-Options"] = "nosniff"
    h["Referrer-Policy"] = "no-referrer"
    h["X-Frame-Options"] = "DENY"
    h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    h["Cross-Origin-Opener-Policy"] = "same-origin"
    h["Cross-Origin-Resource-Policy"] = "same-site"
    h["X-Request-ID"] = rid
    if request.url.path not in DOC_PATHS:
        h["Content-Security-Policy"] = CSP
    if "cache-control" not in h:
        h["Cache-Control"] = "no-store"
    if security.is_https(request) or os.environ.get("ATHAR_HSTS") == "1":
        h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.url.path.startswith("/api"):
        h["Cache-Control"] = "no-store"
    logging_setup.log("request", request_id=rid, method=request.method, path=request.url.path, status=resp.status_code,
                      ms=round(1000 * (time.perf_counter() - t0), 1), client=logging_setup.short_hash(security.client_ip(request)),
                      mode=security.mode())
    return resp


# Added after the guard so CORS is the OUTER layer: guard rejections (401/403/429) still carry CORS headers.
app.add_middleware(CORSMiddleware, allow_origins=_origins(), allow_methods=["GET", "POST", "PUT", "DELETE"],
                   allow_headers=["content-type", "x-athar-token"])


def _errors(exc: ValidationError | RequestValidationError) -> list[dict[str, str]]:
    return [{"loc": ".".join(str(p) for p in e.get("loc", ())), "msg": str(e.get("msg", ""))} for e in exc.errors()]


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": _errors(exc)})


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"error": "internal_error"})  # no internals leaked


def _apply(mutator, reason: str, detail: dict[str, Any]) -> dict[str, Any]:
    """Apply an edit to a copy of the environment; commit only if the whole graph validates."""
    with state.lock:
        raw = state.env.model_dump()
        mutator(raw)
        try:
            new_env = Environment.model_validate(raw)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=_errors(e)) from e
        state.replace(new_env, reason, detail)
        return state.meta()


# ------------------------------------------------------------------ read endpoints
@app.get("/api/health")
def health() -> dict[str, Any]:
    """Liveness: the process is up. Reveals no configuration beyond mode and version."""
    return {"status": "ok", "synthetic_data": True, "version": VERSION, "mode": security.mode()}


@app.get("/api/ready")
def ready() -> JSONResponse:
    """Readiness: the database answers and the analysis has produced a result."""
    try:
        state.store.activity(1)
        ok = bool(state.base["summary"]["total_assets"])
    except Exception:
        ok = False
    return JSONResponse(status_code=200 if ok else 503, content={"ready": ok})


@app.get("/api/auth/status")
def auth_status() -> dict[str, object]:
    return security.auth_status()


@app.get("/api/auth/whoami")
def whoami(request: Request) -> dict[str, bool]:
    """Whether THIS request may write (administrator token in demo mode; any authorised caller in local mode)."""
    return {"can_write": bool(request.state.admin)}


@app.get("/api/ai/status")
def ai_state() -> dict[str, Any]:
    return ai_status()


@app.get("/api/environment")
def environment() -> dict[str, Any]:
    return state.env.model_dump(mode="json")


@app.get("/api/environment/meta")
def environment_meta() -> dict[str, Any]:
    return state.meta()


@app.get("/api/analysis")
def analysis() -> dict[str, Any]:
    return state.base


@app.get("/api/recommendations")
def recommendations() -> list[dict[str, Any]]:
    return state.recs


@app.get("/api/scoring-config")
def scoring_config() -> dict[str, Any]:
    return {"config": state.config.model_dump(), "defaults": DEFAULT_CONFIG.model_dump(), "hash": state.config_key,
            "is_default": state.config == DEFAULT_CONFIG,
            "notice": "Scoring weights are modelling assumptions, not calibrated values. Scores are heuristic indices, not probabilities."}


@app.put("/api/scoring-config")
def set_scoring_config(cfg: ScoringConfig) -> dict[str, Any]:
    state.set_config(cfg)
    return scoring_config()


@app.post("/api/scoring-config/reset")
def reset_scoring_config() -> dict[str, Any]:
    state.set_config(DEFAULT_CONFIG, "scoring_config_reset")
    return scoring_config()


@app.get("/api/sensitivity")
def sensitivity(request: Request, trials: int = DEFAULT_TRIALS, spread: float = DEFAULT_SPREAD, seed: int = DEFAULT_SEED) -> dict[str, Any]:
    if not (1 <= trials <= MAX_TRIALS) or not (0.01 <= spread <= MAX_SPREAD):
        raise HTTPException(status_code=422, detail=f"trials must be 1..{MAX_TRIALS} and spread 0.01..{MAX_SPREAD}")
    if request.state.ephemeral:      # public demo: one cached default run only, so anonymous callers cannot force new heavy computations
        return state.sensitivity(DEFAULT_TRIALS, DEFAULT_SPREAD, DEFAULT_SEED, audit=False)
    return state.sensitivity(trials, spread, seed)


@app.get("/api/services")
def services() -> list[dict[str, Any]]:
    with state.lock:
        return service_dependencies(state.env, state.base)


@app.get("/api/evidence")
def evidence() -> dict[str, Any]:
    with state.lock:
        return evidence_overview(state.env, state.base)


@app.get("/api/attack-scenarios")
def attack_scenarios() -> list[dict[str, Any]]:
    with state.lock:
        now = {a.id for a in state.env.assets if a.compromised}
        return [{**s.model_dump(), "active": set(s.compromised) == now} for s in state.env.attack_scenarios]


@app.post("/api/attack-scenarios/{scenario_id}/activate")
def activate_attack_scenario(scenario_id: str) -> dict[str, Any]:
    def mut(raw: dict[str, Any]) -> None:
        sc = next((s for s in raw["attack_scenarios"] if s["id"] == scenario_id), None)
        if sc is None:
            raise HTTPException(status_code=404, detail="attack scenario not found")
        for a in raw["assets"]:
            a["compromised"] = a["id"] in sc["compromised"]

    return _apply(mut, "attack_scenario_activated", {"id": scenario_id})


@app.get("/api/plans")
def plans() -> dict[str, Any]:
    result = state.plans()
    with state.lock:
        env = state.env
    return {**result, "env_hash": state.hash, "config_hash": state.config_key,
            "plans": [{**p, "summary": {"en": plan_summary(env, p, "en"), "ar": plan_summary(env, p, "ar")}} for p in result["plans"]]}


@app.get("/api/plans/{plan_id}/report")
def plan_report_md(plan_id: str, request: Request, lang: str = "en") -> dict[str, Any]:
    if lang not in ("en", "ar"):
        raise HTTPException(status_code=422, detail="lang must be en or ar")
    plan = next((p for p in state.plans()["plans"] if p["id"] == plan_id), None)
    if plan is None:
        raise HTTPException(status_code=404, detail="plan not found")
    with state.lock:
        env = state.env
    if not request.state.ephemeral:
        state.store.log("plan_report_generated", {"plan": plan_id, "lang": lang})
    return {"plan_id": plan_id, "lang": lang, "format": "markdown", "markdown": plan_report(env, plan, lang)}


@app.get("/api/recommendations/{rec_id}/explanation")
def recommendation_explanation_endpoint(rec_id: str) -> dict[str, Any]:
    with state.lock:
        env, base, recs = state.env, state.base, state.recs
    rec = next((r for r in recs if r["id"] == rec_id), None)
    if rec is None:
        raise HTTPException(status_code=404, detail="recommendation not found")
    with state.scoring():
        return recommendation_explanation(env, base, rec, state.stability_of(rec_id))


@app.get("/api/activity")
def activity(limit: int = 50) -> list[dict[str, Any]]:
    return state.store.activity(max(1, min(limit, 200)))


@app.get("/api/simulations")
def simulations(limit: int = 30) -> list[dict[str, Any]]:
    rows = state.store.list_simulations(max(1, min(limit, 100)))
    for r in rows:
        r["current_environment"] = r["env_hash"] == state.hash
    return rows


@app.get("/api/simulations/{sim_id}")
def simulation_record(sim_id: int) -> dict[str, Any]:
    rec = state.store.get_simulation(sim_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="simulation record not found")
    rec["current_environment"] = rec["env_hash"] == state.hash
    return rec


@app.get("/api/explanations")
def explanations(limit: int = 30) -> list[dict[str, Any]]:
    return state.store.list_explanations(max(1, min(limit, 100)))


# ------------------------------------------------------------------ environment management
@app.put("/api/environment")
def import_environment(env: Environment) -> dict[str, Any]:
    state.replace(env, "environment_imported", {})
    return state.meta()


@app.post("/api/environment/reset")
def reset_environment() -> dict[str, Any]:
    state.reset()
    return state.meta()


@app.post("/api/environment/undo")
def undo_environment() -> dict[str, Any]:
    if not state.undo():
        raise HTTPException(status_code=409, detail="nothing to undo")
    return state.meta()


@app.post("/api/assets")
def create_asset(asset: Asset) -> dict[str, Any]:
    return _apply(lambda raw: raw["assets"].append(asset.model_dump()), "asset_created", {"id": asset.id})


@app.put("/api/assets/{asset_id}")
def update_asset(asset_id: str, asset: Asset) -> dict[str, Any]:
    if asset.id != asset_id:
        raise HTTPException(status_code=422, detail=[{"loc": "id", "msg": "asset id cannot be changed"}])

    def mut(raw: dict[str, Any]) -> None:
        idx = next((i for i, a in enumerate(raw["assets"]) if a["id"] == asset_id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail="asset not found")
        raw["assets"][idx] = asset.model_dump()

    return _apply(mut, "asset_updated", {"id": asset_id})


@app.delete("/api/assets/{asset_id}")
def delete_asset(asset_id: str, cascade: bool = False) -> Any:
    with state.lock:
        if not any(a.id == asset_id for a in state.env.assets):
            raise HTTPException(status_code=404, detail="asset not found")
        refs = [r.id for r in state.env.relationships if asset_id in (r.source, r.target)]
        if refs and not cascade:
            return JSONResponse(status_code=409, content={"detail": "asset is referenced by relationships",
                                                          "relationship_ids": refs})

        def mut(raw: dict[str, Any]) -> None:
            raw["assets"] = [a for a in raw["assets"] if a["id"] != asset_id]
            raw["relationships"] = [r for r in raw["relationships"] if r["id"] not in refs]
            for a in raw["assets"]:
                a["controls"] = [c for c in a["controls"] if c != asset_id]

        return _apply(mut, "asset_deleted", {"id": asset_id, "relationships_removed": len(refs)})


@app.post("/api/relationships")
def create_relationship(rel: Relationship) -> dict[str, Any]:
    return _apply(lambda raw: raw["relationships"].append(rel.model_dump()), "relationship_created", {"id": rel.id})


@app.put("/api/relationships/{rel_id}")
def update_relationship(rel_id: str, rel: Relationship) -> dict[str, Any]:
    if rel.id != rel_id:
        raise HTTPException(status_code=422, detail=[{"loc": "id", "msg": "relationship id cannot be changed"}])

    def mut(raw: dict[str, Any]) -> None:
        idx = next((i for i, r in enumerate(raw["relationships"]) if r["id"] == rel_id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail="relationship not found")
        raw["relationships"][idx] = rel.model_dump()

    return _apply(mut, "relationship_updated", {"id": rel_id})


@app.delete("/api/relationships/{rel_id}")
def delete_relationship(rel_id: str) -> dict[str, Any]:
    def mut(raw: dict[str, Any]) -> None:
        if not any(r["id"] == rel_id for r in raw["relationships"]):
            raise HTTPException(status_code=404, detail="relationship not found")
        raw["relationships"] = [r for r in raw["relationships"] if r["id"] != rel_id]

    return _apply(mut, "relationship_deleted", {"id": rel_id})


# ------------------------------------------------------------------ simulation & explanation
@app.post("/api/simulate")
def run_simulation(req: SimulationRequest, request: Request) -> dict[str, Any]:
    with state.lock:
        env, base, h = state.env, state.base, state.hash
    try:
        with state.scoring():
            res = simulate(env, req.actions, baseline=base)  # works on an isolated copy
    except SimulationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if request.state.ephemeral:
        # Public read-only demo: the result is computed and returned but never written to the shared audit database.
        return {**res, "record_id": None, "recorded_at": None, "env_hash": h, "current_environment": True, "ephemeral": True}
    record_id, ts = state.store.save_simulation(h, res["actions"], res)
    state.store.log("simulation_run", {"record_id": record_id, "actions": len(req.actions),
                                       "risk_reduction_pct": res["risk_reduction_pct"],
                                       "paths_eliminated": len(res["paths_eliminated"])})
    return {**res, "record_id": record_id, "recorded_at": ts, "env_hash": h, "current_environment": True, "ephemeral": False}


@app.post("/api/explain")
def explain(req: ExplainRequest, request: Request) -> dict[str, Any]:
    with state.lock:
        env, base, recs, h = state.env, state.base, state.recs, state.hash
    if req.kind == "path":
        path = next((p for p in base["paths"] if p["id"] == req.id), None)
        if path is None:
            raise HTTPException(status_code=404, detail="path not found")
        text, facts = template_path(env, path, req.lang), path_facts(env, path)
    else:
        rec = next((r for r in recs if r["id"] == req.id), None)
        if rec is None:
            raise HTTPException(status_code=404, detail="recommendation not found")
        text, facts = template_recommendation(env, rec, req.lang), {k: rec[k] for k in (
            "action", "risk_reduction_pct", "paths_eliminated", "paths_mitigated", "tradeoff")}
    # The public demo never sends data to an AI provider on behalf of anonymous visitors (cost and abuse control).
    ai_text, ai_error = (None, "ai_disabled") if request.state.ephemeral else ai_narrative(facts, req.lang)
    status = ai_error or "ok"
    if not request.state.ephemeral:
        state.store.save_explanation(req.kind, req.id, req.lang, facts, text, ai_text, status, h)
        state.store.log("explanation_requested", {"target": req.kind, "id": req.id, "ai_status": status})
    return {"evidence": facts, "template_explanation": text, "ai_explanation": ai_text, "ai_status": status,
            "notice": "AI text is narration only; it cannot create findings or execute actions."}


# ------------------------------------------------------------------ single-page app (optional, same origin as the API)
def _static_root() -> Path | None:
    """Directory holding the built frontend, if any: ATHAR_STATIC_DIR, else <repo>/frontend/dist when it exists."""
    configured = os.environ.get("ATHAR_STATIC_DIR")
    candidate = Path(configured) if configured else Path(__file__).resolve().parents[2] / "frontend" / "dist"
    return candidate.resolve() if (candidate / "index.html").is_file() else None


STATIC_ROOT = _static_root()

if STATIC_ROOT is not None:
    _ROOT: Path = STATIC_ROOT

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not found")
        target = (_ROOT / full_path).resolve()
        if full_path and target.is_file() and _ROOT in target.parents:        # never serve anything outside the build folder
            immutable = full_path.startswith("assets/")                         # content-hashed by the bundler
            return FileResponse(target, headers={"Cache-Control": "public, max-age=31536000, immutable" if immutable else "no-cache"})
        return FileResponse(_ROOT / "index.html", headers={"Cache-Control": "no-cache"})
