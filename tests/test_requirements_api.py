"""Requirements CRUD API — isolated SQLite per test via the autouse conftest fixture."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_list_requirements_returns_seeded_in_defaults():
    r = client.get("/v1/doc-requirements?country=IN")
    assert r.status_code == 200
    doc_types = {row["doc_type"] for row in r.json()}
    assert "IN_PAN_CARD" in doc_types


def test_create_requirement_without_token_when_none_configured(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.delenv("DOCAI_SERVICE_BEARER_TOKEN", raising=False)
    get_settings.cache_clear()
    body = {
        "country_code": "IN",
        "doc_type": "IN_TEST_DOC",
        "label": "Test doc",
        "is_mandatory": False,
        "sort_order": 9,
    }
    r = client.post("/v1/doc-requirements", json=body)
    assert r.status_code == 201
    assert r.json()["doc_type"] == "IN_TEST_DOC"
    get_settings.cache_clear()


def test_create_requirement_requires_token_when_configured(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("DOCAI_SERVICE_BEARER_TOKEN", "secret")
    get_settings.cache_clear()
    body = {"country_code": "IN", "doc_type": "IN_TEST_DOC2", "label": "Test doc 2"}

    unauthorized = client.post("/v1/doc-requirements", json=body)
    assert unauthorized.status_code == 401

    authorized = client.post("/v1/doc-requirements", json=body, headers={"Authorization": "Bearer secret"})
    assert authorized.status_code == 201

    get_settings.cache_clear()


def test_update_and_delete_requirement():
    created = client.post(
        "/v1/doc-requirements",
        json={"country_code": "IN", "doc_type": "IN_TEMP", "label": "Temp", "sort_order": 99},
    ).json()
    requirement_id = created["id"]

    updated = client.put(
        f"/v1/doc-requirements/{requirement_id}",
        json={"country_code": "IN", "doc_type": "IN_TEMP", "label": "Temp Updated", "sort_order": 99},
    )
    assert updated.status_code == 200
    assert updated.json()["label"] == "Temp Updated"

    deleted = client.delete(f"/v1/doc-requirements/{requirement_id}")
    assert deleted.status_code == 204

    missing = client.delete(f"/v1/doc-requirements/{requirement_id}")
    assert missing.status_code == 404


def test_update_nonexistent_returns_404():
    r = client.put(
        "/v1/doc-requirements/999999",
        json={"country_code": "IN", "doc_type": "IN_X", "label": "X"},
    )
    assert r.status_code == 404
