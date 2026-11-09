"""Application state: the current environment, its cached analysis, undo history and persistence."""
from __future__ import annotations

import hashlib
import json
import threading
from contextlib import AbstractContextManager
from typing import Any

from pydantic import ValidationError

from .analysis import DEFAULT_CONFIG, analyze, use_config
from .data.demo import build_demo_environment
from .models import Environment, ScoringConfig
from .plans import generate_plans
from .recommendations import recommend_ex
from .sensitivity import DEFAULT_SEED, DEFAULT_SPREAD, DEFAULT_TRIALS, run_sensitivity
from .store import Store

HISTORY_LIMIT = 20


def env_hash(env: Environment) -> str:
    return hashlib.sha256(json.dumps(env.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()[:16]


def config_hash(cfg: ScoringConfig) -> str:
    return hashlib.sha256(json.dumps(cfg.model_dump(), sort_keys=True).encode()).hexdigest()[:12]


class AppState:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.lock = threading.RLock()
        self.sample_hash = env_hash(build_demo_environment())
        self.history: list[str] = []  # JSON snapshots of previous environments (in memory only)
        self.config = self._load_config()
        self._plans: tuple[tuple[str, str], dict[str, Any]] | None = None       # ((env hash, config hash), result)
        self._sens: tuple[tuple[Any, ...], dict[str, Any]] | None = None
        self._set(self._load_initial())
        self.store.log("environment_loaded", {"assets": len(self.env.assets), "synthetic": True,
                                              "sample": self.is_sample})
        self.store.log("analysis_run", {"paths": self.base["summary"]["attack_paths"]})

    def _load_initial(self) -> Environment:
        raw = self.store.kv_get("environment")
        if raw:
            try:
                return Environment.model_validate_json(raw)
            except ValidationError:
                self.store.log("environment_invalid_on_load", {})  # fall back to the sample
        return build_demo_environment()

    def _load_config(self) -> ScoringConfig:
        raw = self.store.kv_get("scoring_config")
        if raw:
            try:
                return ScoringConfig.model_validate_json(raw)
            except ValidationError:
                self.store.log("scoring_config_invalid_on_load", {})    # fall back to the documented defaults
        return DEFAULT_CONFIG

    def scoring(self) -> AbstractContextManager[ScoringConfig]:
        """Context manager that makes the stored scoring configuration the active one (context-local)."""
        return use_config(self.config)

    def _set(self, env: Environment) -> None:
        self.env = env
        self.hash = env_hash(env)
        with self.scoring():
            self.base: dict[str, Any] = analyze(env)
            self.recs: list[dict[str, Any]]
            self.recs, self.recs_partial = recommend_ex(env, self.base)
        self._plans = None
        self._sens = None

    @property
    def is_sample(self) -> bool:
        return self.hash == self.sample_hash

    @property
    def config_key(self) -> str:
        return config_hash(self.config)

    def meta(self) -> dict[str, Any]:
        return {"hash": self.hash, "is_sample": self.is_sample, "can_undo": bool(self.history),
                "history_depth": len(self.history), "synthetic": True,
                "recommendations_partial": self.recs_partial,
                "paths_truncated": bool(self.base["summary"]["paths_truncated"]),
                "config_hash": self.config_key, "config_is_default": self.config == DEFAULT_CONFIG}

    def set_config(self, cfg: ScoringConfig, reason: str = "scoring_config_changed") -> None:
        with self.lock:
            self.config = cfg
            self.store.kv_set("scoring_config", cfg.model_dump_json())
            self._set(self.env)                                  # recompute analysis + recommendations under the new weights
            self.store.log(reason, {"config_hash": self.config_key, "paths": self.base["summary"]["attack_paths"],
                                    "posture": self.base["summary"]["posture_score"]})

    def plans(self) -> dict[str, Any]:
        # Computed outside the lock on an immutable snapshot (environments are never mutated in place), so a slow
        # computation does not block other requests; the result is only cached if the state did not change meanwhile.
        with self.lock:
            key = (self.hash, self.config_key)
            if self._plans is not None and self._plans[0] == key:
                return self._plans[1]
            env, base, cfg = self.env, self.base, self.config
        with use_config(cfg):
            result = generate_plans(env, base)
        with self.lock:
            if (self.hash, self.config_key) == key:
                self._plans = (key, result)
        return result

    def sensitivity(self, trials: int = DEFAULT_TRIALS, spread: float = DEFAULT_SPREAD, seed: int = DEFAULT_SEED,
                    audit: bool = True) -> dict[str, Any]:
        with self.lock:
            key = (self.hash, self.config_key, trials, spread, seed)
            if self._sens is not None and self._sens[0] == key:
                return self._sens[1]
            env, cfg = self.env, self.config
        result = run_sensitivity(env, cfg, trials, spread, seed)
        with self.lock:
            if (self.hash, self.config_key) == key[:2]:
                self._sens = (key, result)
                if audit:
                    self.store.log("sensitivity_run", {"trials": trials, "spread": spread, "config_hash": key[1]})
        return result

    def stability_of(self, rec_id: str) -> str | None:
        """Stability label of a recommendation from the latest sensitivity run, if it matches the current state."""
        with self.lock:
            if self._sens is None or self._sens[0][:2] != (self.hash, self.config_key):
                return None
            row = next((r for r in self._sens[1]["recommendations"] if r["id"] == rec_id), None)
            return None if row is None else str(row["stability"])

    def replace(self, env: Environment, reason: str, detail: dict[str, Any] | None = None) -> None:
        with self.lock:
            self.history.append(self.env.model_dump_json())
            del self.history[:-HISTORY_LIMIT]
            self._set(env)
            self.store.kv_set("environment", env.model_dump_json())
            self.store.log(reason, {**(detail or {}), "assets": len(env.assets),
                                    "relationships": len(env.relationships), "paths": self.base["summary"]["attack_paths"]})

    def reset(self) -> None:
        self.replace(build_demo_environment(), "environment_reset")

    def undo(self) -> bool:
        with self.lock:
            if not self.history:
                return False
            env = Environment.model_validate_json(self.history.pop())
            self._set(env)
            self.store.kv_set("environment", env.model_dump_json())
            self.store.log("environment_undo", {"assets": len(env.assets), "paths": self.base["summary"]["attack_paths"]})
            return True
