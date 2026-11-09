"""Local SQLite persistence (standard library only).

Stores the activity log, every simulation run (with full evidence: actions, before/after
paths and their score factors), explanation records, and the current environment.
Everything is parameterised SQL; nothing user-controlled is interpolated into a statement.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

MAX_ACTIVITY = 2000
MAX_SIMULATIONS = 200
MAX_EXPLANATIONS = 500

SCHEMA = """
CREATE TABLE IF NOT EXISTS activity (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS simulations (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, env_hash TEXT NOT NULL,
  actions TEXT NOT NULL, result TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS explanations (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, kind TEXT NOT NULL, ref TEXT NOT NULL,
  lang TEXT NOT NULL, evidence TEXT NOT NULL, template_text TEXT NOT NULL,
  ai_text TEXT, ai_status TEXT NOT NULL, env_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Store:
    def __init__(self, path: str) -> None:
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.executescript(SCHEMA)
            self._db.commit()

    # ---- activity
    def log(self, kind: str, detail: dict[str, Any] | None = None) -> None:
        with self._lock:
            self._db.execute("INSERT INTO activity (ts, kind, detail) VALUES (?,?,?)",
                             (now(), kind, json.dumps(detail or {}, ensure_ascii=False)))
            self._db.execute("DELETE FROM activity WHERE id <= (SELECT MAX(id) FROM activity) - ?", (MAX_ACTIVITY,))
            self._db.commit()

    def activity(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT id, ts, kind, detail FROM activity ORDER BY id DESC LIMIT ?",
                                    (limit,)).fetchall()
        return [{"id": r["id"], "time": r["ts"], "kind": r["kind"], **json.loads(r["detail"])} for r in rows]

    # ---- simulations
    def save_simulation(self, env_hash: str, actions: list[dict[str, Any]], result: dict[str, Any]) -> tuple[int, str]:
        ts = now()
        with self._lock:
            cur = self._db.execute("INSERT INTO simulations (ts, env_hash, actions, result) VALUES (?,?,?,?)",
                                   (ts, env_hash, json.dumps(actions), json.dumps(result)))
            self._db.execute("DELETE FROM simulations WHERE id <= (SELECT MAX(id) FROM simulations) - ?",
                             (MAX_SIMULATIONS,))
            self._db.commit()
            return int(cur.lastrowid or 0), ts

    def list_simulations(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT id, ts, env_hash, actions, result FROM simulations "
                                    "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            res = json.loads(r["result"])
            out.append({"id": r["id"], "time": r["ts"], "env_hash": r["env_hash"],
                        "actions": json.loads(r["actions"]),
                        "risk_reduction_pct": res["risk_reduction_pct"],
                        "paths_before": res["before"]["attack_paths"], "paths_after": res["after"]["attack_paths"]})
        return out

    def get_simulation(self, sim_id: int) -> dict[str, Any] | None:
        with self._lock:
            r = self._db.execute("SELECT id, ts, env_hash, result FROM simulations WHERE id=?", (sim_id,)).fetchone()
        if r is None:
            return None
        return {**json.loads(r["result"]), "record_id": r["id"], "recorded_at": r["ts"], "env_hash": r["env_hash"]}

    # ---- explanations
    def save_explanation(self, kind: str, ref: str, lang: str, evidence: dict[str, Any], template_text: str,
                         ai_text: str | None, ai_status: str, env_hash: str) -> int:
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO explanations (ts, kind, ref, lang, evidence, template_text, ai_text, ai_status, env_hash) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (now(), kind, ref, lang, json.dumps(evidence, ensure_ascii=False), template_text, ai_text,
                 ai_status, env_hash))
            self._db.execute("DELETE FROM explanations WHERE id <= (SELECT MAX(id) FROM explanations) - ?",
                             (MAX_EXPLANATIONS,))
            self._db.commit()
            return int(cur.lastrowid or 0)

    def list_explanations(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM explanations ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"id": r["id"], "time": r["ts"], "kind": r["kind"], "ref": r["ref"], "lang": r["lang"],
                 "evidence": json.loads(r["evidence"]), "template_explanation": r["template_text"],
                 "ai_explanation": r["ai_text"], "ai_status": r["ai_status"], "env_hash": r["env_hash"]}
                for r in rows]

    # ---- key/value (current environment)
    def kv_get(self, key: str) -> str | None:
        with self._lock:
            r = self._db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return None if r is None else str(r["value"])

    def kv_set(self, key: str, value: str) -> None:
        with self._lock:
            self._db.execute("INSERT INTO kv (key, value) VALUES (?,?) "
                             "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
            self._db.commit()

    def kv_delete(self, key: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM kv WHERE key=?", (key,))
            self._db.commit()
