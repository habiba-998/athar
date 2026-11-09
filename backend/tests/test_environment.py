"""Environment import, editing, consistency validation, undo/reset and persistence."""
import copy

import pytest
from fastapi.testclient import TestClient

from app import main
from app.data.demo import build_demo_environment
from app.models import Environment
from app.state import AppState

client = TestClient(main.app)


def sample() -> dict:
    return build_demo_environment().model_dump(mode="json")


def test_import_round_trip_of_exported_environment():
    exported = client.get("/api/environment").json()
    r = client.put("/api/environment", json=exported)
    assert r.status_code == 200 and r.json()["is_sample"] is True
    assert client.get("/api/analysis").json()["summary"]["attack_paths"] == 20


def test_environment_arabic_name_is_optional_for_imports():
    env = sample()
    assert env["name_ar"]                                   # the sample ships one
    del env["name_ar"]                                      # older exports without it must still import
    assert client.put("/api/environment", json=env).status_code == 200
    assert client.get("/api/environment").json()["name_ar"] == ""


def test_import_custom_environment_recomputes_everything():
    env = {"name": "Tiny", "synthetic": True,
           "assets": [
               {"id": "u1", "name": "U", "name_ar": "م", "type": "user", "compromised": True},
               {"id": "db", "name": "DB", "name_ar": "ق", "type": "database", "criticality": 5}],
           "relationships": [{"id": "x1", "source": "u1", "target": "db", "type": "read_access",
                              "privilege": "read", "evidence": "validated"}]}
    assert client.put("/api/environment", json=env).status_code == 200
    a = client.get("/api/analysis").json()
    assert a["summary"]["attack_paths"] == 1 and a["paths"][0]["nodes"] == ["u1", "db"]
    assert client.get("/api/environment/meta").json()["is_sample"] is False
    assert client.get("/api/recommendations").json()  # recomputed for the new graph


@pytest.mark.parametrize("mutate,expect", [
    (lambda e: e["relationships"][0].update(target="ghost"), "unknown asset"),
    (lambda e: e["relationships"][0].update(source="ghost"), "unknown asset"),
    (lambda e: e["assets"].append(copy.deepcopy(e["assets"][0])), "duplicate asset id"),
    (lambda e: e["relationships"].append(copy.deepcopy(e["relationships"][0])), "duplicate relationship id"),
    (lambda e: e["relationships"][0].update(target=e["relationships"][0]["source"]), "self-loop"),
    (lambda e: e["relationships"].append({**e["relationships"][0], "id": "dup2"}), "one relationship per ordered"),
    (lambda e: e["assets"][0].update(id="Bad Id!"), "pattern"),
    (lambda e: e["assets"][0].update(criticality=9), "less than or equal"),
    (lambda e: e["assets"][0].update(controls=["nope"]), "unknown control"),
    (lambda e: e.update(synthetic=False), "True"),
    (lambda e: e["assets"][0].update(surprise=1), "Extra inputs"),
    (lambda e: e["relationships"][-1].update(type="read_access"), "protects"),   # control using a non-protects rel
    (lambda e: e["relationships"][0].update(target="fw-dmz"), "control"),         # control as target
])
def test_import_rejects_inconsistent_graphs(mutate, expect):
    env = sample()
    mutate(env)
    before = client.get("/api/environment").json()
    r = client.put("/api/environment", json=env)
    assert r.status_code == 422, r.text
    assert expect.lower() in str(r.json()).lower()
    assert client.get("/api/environment").json() == before  # rejected import never changes state


def test_import_rejects_oversized_payload(monkeypatch):
    monkeypatch.setenv("ATHAR_MAX_BODY", "500")
    r = client.put("/api/environment", json=sample())
    assert r.status_code == 413


def test_import_rejects_non_json_and_wrong_shape():
    assert client.put("/api/environment", content=b"not json", headers={"content-type": "application/json"}).status_code == 422
    assert client.put("/api/environment", json=[1, 2, 3]).status_code == 422
    assert client.put("/api/environment", json={}).status_code == 422


def test_asset_crud_and_reference_checks():
    new = {"id": "ws-2", "name": "WS", "name_ar": "ج", "type": "server", "criticality": 2}
    assert client.post("/api/assets", json=new).status_code == 200
    assert client.post("/api/assets", json=new).status_code == 422                       # duplicate
    assert client.put("/api/assets/ws-2", json={**new, "criticality": 4}).status_code == 200
    assert next(a for a in client.get("/api/environment").json()["assets"] if a["id"] == "ws-2")["criticality"] == 4
    assert client.put("/api/assets/ws-2", json={**new, "id": "other"}).status_code == 422  # id immutable
    assert client.put("/api/assets/nope", json={**new, "id": "nope"}).status_code == 404
    assert client.delete("/api/assets/ws-2").status_code == 200
    assert client.delete("/api/assets/ws-2").status_code == 404


def test_relationship_crud_updates_paths():
    base_paths = client.get("/api/analysis").json()["summary"]["attack_paths"]
    rel = {"id": "r90", "source": "emp-sara", "target": "db-hr", "type": "read_access", "privilege": "read",
           "evidence": "inferred"}
    assert client.post("/api/relationships", json=rel).status_code == 200
    assert client.get("/api/analysis").json()["summary"]["attack_paths"] > base_paths
    bad = {**rel, "id": "r91", "target": "ghost"}
    assert client.post("/api/relationships", json=bad).status_code == 422
    assert client.put("/api/relationships/r90", json={**rel, "disabled": True}).status_code == 200
    assert client.get("/api/analysis").json()["summary"]["attack_paths"] == base_paths   # disabled edge ignored
    assert client.delete("/api/relationships/r90").status_code == 200
    assert client.delete("/api/relationships/r90").status_code == 404


def test_delete_asset_requires_cascade_when_referenced():
    r = client.delete("/api/assets/jump-host")
    assert r.status_code == 409 and set(r.json()["relationship_ids"]) >= {"r03", "r07"}
    assert any(a["id"] == "jump-host" for a in client.get("/api/environment").json()["assets"])
    r = client.delete("/api/assets/jump-host?cascade=true")
    assert r.status_code == 200
    env = client.get("/api/environment").json()
    assert all("jump-host" not in (x["source"], x["target"]) for x in env["relationships"])
    assert client.get("/api/analysis").json()["summary"]["attack_paths"] < 20


def test_deleting_a_control_removes_it_from_asset_controls():
    assert client.delete("/api/assets/fw-dmz?cascade=true").status_code == 200
    env = client.get("/api/environment").json()
    assert all("fw-dmz" not in a["controls"] for a in env["assets"])
    Environment.model_validate(env)  # still consistent


def test_undo_and_reset():
    assert client.post("/api/environment/undo").status_code == 409                       # nothing yet
    client.delete("/api/relationships/r03")
    client.delete("/api/relationships/r07")
    assert client.get("/api/environment/meta").json()["history_depth"] == 2
    assert client.post("/api/environment/undo").status_code == 200
    ids = {r["id"] for r in client.get("/api/environment").json()["relationships"]}
    assert "r07" in ids and "r03" not in ids                                             # only last edit undone
    assert client.post("/api/environment/undo").status_code == 200
    assert client.get("/api/environment/meta").json()["is_sample"] is True
    client.delete("/api/relationships/r03")
    assert client.post("/api/environment/reset").json()["is_sample"] is True
    assert client.get("/api/analysis").json()["summary"]["attack_paths"] == 20


def test_environment_persists_across_restart():
    client.delete("/api/relationships/r03")
    edited = main.state.env.model_dump()
    reloaded = AppState(main.state.store)           # simulates a process restart on the same database
    assert reloaded.env.model_dump() == edited
    assert reloaded.is_sample is False
    assert all(r.id != "r03" for r in reloaded.env.relationships)
