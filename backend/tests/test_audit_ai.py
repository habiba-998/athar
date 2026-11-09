"""Persistent audit trail, preserved evidence, and AI transparency/fallback behaviour."""
import io
import json
import urllib.error

import pytest
from fastapi.testclient import TestClient

from app import explain, main

client = TestClient(main.app)
SIM = {"actions": [{"kind": "remove_relationship", "relationship_id": "r03"}]}


def first_path_id() -> str:
    return client.get("/api/analysis").json()["paths"][0]["id"]


# ------------------------------------------------------------------ audit / persistence
def test_simulation_is_recorded_with_timestamp_actions_and_full_evidence():
    r = client.post("/api/simulate", json=SIM).json()
    rec = client.get(f"/api/simulations/{r['record_id']}").json()
    assert rec["recorded_at"].endswith("+00:00") and rec["actions"] == SIM["actions"]
    assert rec["before"]["attack_paths"] == 20 and rec["after"]["attack_paths"] == 11
    # score explanations preserved: every stored path carries its factors and per-step evidence labels
    assert rec["before_paths"] and all(p["factors"] and p["steps"] for p in rec["after_paths"])
    assert {s["evidence"] for p in rec["before_paths"] for s in p["steps"]} <= {"validated", "inferred", "theoretical"}
    assert rec["current_environment"] is True


def test_simulation_history_lists_newest_first_and_flags_stale_environment():
    a = client.post("/api/simulate", json=SIM).json()["record_id"]
    b = client.post("/api/simulate", json={"actions": [{"kind": "disable_relationship", "relationship_id": "r03"}]}).json()["record_id"]
    rows = client.get("/api/simulations").json()
    assert [r["id"] for r in rows[:2]] == [b, a]
    assert all(r["current_environment"] for r in rows[:2])
    client.delete("/api/relationships/r05")                       # environment changes afterwards
    rows = client.get("/api/simulations").json()
    assert not rows[0]["current_environment"]
    assert client.get(f"/api/simulations/{a}").json()["current_environment"] is False
    assert client.get("/api/simulations/999999").status_code == 404


def test_activity_is_persisted_in_sqlite_and_survives_restart():
    client.post("/api/simulate", json=SIM)
    client.delete("/api/relationships/r05")
    kinds = [e["kind"] for e in client.get("/api/activity").json()]
    assert kinds[:2] == ["relationship_deleted", "simulation_run"]
    from app.state import AppState
    reloaded = AppState(main.state.store)                          # new "process", same database file
    persisted = [e["kind"] for e in reloaded.store.activity(20)]
    assert "simulation_run" in persisted and "relationship_deleted" in persisted
    assert persisted[:2] == ["analysis_run", "environment_loaded"]  # the restart itself is logged too
    rows = main.state.store._db.execute("SELECT kind, ts FROM activity").fetchall()   # real table, real rows
    assert rows and all(r["ts"] for r in rows)


def test_failed_simulations_and_rejected_edits_are_not_recorded_as_runs():
    n = len(client.get("/api/simulations").json())
    client.post("/api/simulate", json={"actions": [{"kind": "remove_relationship", "relationship_id": "zzz"}]})
    client.post("/api/assets", json={"id": "Bad Id", "name": "x", "name_ar": "x", "type": "server"})
    assert len(client.get("/api/simulations").json()) == n


def test_explanations_are_persisted_with_their_evidence():
    pid = first_path_id()
    client.post("/api/explain", json={"kind": "path", "id": pid, "lang": "ar"})
    rows = client.get("/api/explanations").json()
    assert rows[0]["ref"] == pid and rows[0]["lang"] == "ar"
    assert rows[0]["evidence"]["route"] and rows[0]["evidence"]["factors"]
    assert rows[0]["template_explanation"] and rows[0]["ai_explanation"] is None
    assert rows[0]["ai_status"] == "ai_disabled"


def test_activity_limit_is_clamped():
    assert client.get("/api/activity?limit=100000").status_code == 200
    assert len(client.get("/api/activity?limit=2").json()) == 2


# ------------------------------------------------------------------ AI transparency
def test_ai_is_disabled_by_default_and_response_says_so():
    assert client.get("/api/ai/status").json() == {"enabled": False, "provider": None, "reason": "ai_disabled"}
    r = client.post("/api/explain", json={"kind": "path", "id": first_path_id()}).json()
    assert r["ai_explanation"] is None and r["ai_status"] == "ai_disabled" and r["template_explanation"]


@pytest.mark.parametrize("provider", ["openai", "ANTHROPIC", "", "anthropic "])
def test_unknown_provider_values_keep_ai_disabled(monkeypatch, provider):
    monkeypatch.setenv("ATHAR_AI_PROVIDER", provider)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert client.get("/api/ai/status").json()["enabled"] is False


def test_provider_without_key_reports_not_configured(monkeypatch):
    monkeypatch.setenv("ATHAR_AI_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert client.get("/api/ai/status").json() == {"enabled": False, "provider": "anthropic", "reason": "ai_not_configured"}
    r = client.post("/api/explain", json={"kind": "path", "id": first_path_id()}).json()
    assert r["ai_explanation"] is None and r["ai_status"] == "ai_not_configured" and r["template_explanation"]


def _enable(monkeypatch):
    monkeypatch.setenv("ATHAR_AI_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-never-logged")


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_status_never_exposes_the_key(monkeypatch):
    _enable(monkeypatch)
    s = client.get("/api/ai/status")
    assert s.json() == {"enabled": True, "provider": "anthropic", "reason": "ok"}
    assert "test-key" not in s.text


@pytest.mark.parametrize("failure", [
    urllib.error.URLError("down"), TimeoutError(), OSError("reset"), ValueError("bad"),
])
def test_ai_network_failures_fall_back_to_deterministic_text(monkeypatch, failure):
    _enable(monkeypatch)

    def boom(*a, **k):
        raise failure
    monkeypatch.setattr(explain.urllib.request, "urlopen", boom)
    r = client.post("/api/explain", json={"kind": "path", "id": first_path_id()})
    assert r.status_code == 200
    j = r.json()
    assert j["ai_explanation"] is None and j["ai_status"] == "ai_unavailable"
    assert j["template_explanation"] and j["evidence"]["route"]          # deterministic parts unaffected


@pytest.mark.parametrize("payload", [b"", b"not json", b"[]", b'{"content": []}', b'{"content": [{"type":"text","text":"   "}]}',
                                     b'{"content": "oops"}', b'{"content": [1,2]}'])
def test_malformed_or_empty_ai_responses_never_produce_text(monkeypatch, payload):
    _enable(monkeypatch)
    monkeypatch.setattr(explain.urllib.request, "urlopen", lambda *a, **k: _Resp(payload))
    j = client.post("/api/explain", json={"kind": "path", "id": first_path_id()}).json()
    assert j["ai_explanation"] is None and j["ai_status"] == "ai_unavailable"


def test_successful_ai_text_is_separate_capped_and_does_not_change_evidence(monkeypatch):
    pid = first_path_id()
    plain = client.post("/api/explain", json={"kind": "path", "id": pid}).json()
    _enable(monkeypatch)
    captured = {}

    def fake(req, timeout=None):
        captured["url"], captured["body"] = req.full_url, json.loads(req.data)
        return _Resp(json.dumps({"content": [{"type": "text", "text": "A" * 5000}]}).encode())
    monkeypatch.setattr(explain.urllib.request, "urlopen", fake)
    j = client.post("/api/explain", json={"kind": "path", "id": pid}).json()
    assert j["ai_status"] == "ok" and len(j["ai_explanation"]) == explain.MAX_AI_CHARS
    assert j["evidence"] == plain["evidence"] and j["template_explanation"] == plain["template_explanation"]
    assert captured["url"] == "https://api.anthropic.com/v1/messages"     # fixed host, never user-controlled
    sent = captured["body"]["messages"][0]["content"]
    assert json.loads(sent) == plain["evidence"]                           # the model receives only the facts
    assert "Use ONLY the JSON facts" in captured["body"]["system"]
    assert "api_key" not in sent and "test-key" not in sent


def test_ai_output_cannot_create_findings_or_change_analysis(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(explain.urllib.request, "urlopen", lambda *a, **k: _Resp(json.dumps(
        {"content": [{"type": "text", "text": "CRITICAL: new path attacker -> db-hr, score 100"}]}).encode()))
    before = client.get("/api/analysis").json()
    client.post("/api/explain", json={"kind": "path", "id": first_path_id()})
    assert client.get("/api/analysis").json() == before
