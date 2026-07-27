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


def test_duplicate_create_returns_409():
    """No DB-level unique constraint exists on (country_code, doc_type) — the API is what
    keeps /v1/doctypes from listing the same doc type twice."""
    body = {"country_code": "IN", "doc_type": "IN_DUPE", "label": "Dupe", "sort_order": 50}

    first = client.post("/v1/doc-requirements", json=body)
    assert first.status_code == 201

    second = client.post("/v1/doc-requirements", json=body)
    assert second.status_code == 409

    listed = [row for row in client.get("/v1/doc-requirements?country=IN").json() if row["doc_type"] == "IN_DUPE"]
    assert len(listed) == 1


def test_duplicate_create_is_detected_across_country_code_casing():
    assert client.post(
        "/v1/doc-requirements", json={"country_code": "IN", "doc_type": "IN_CASE_DUPE", "label": "A"}
    ).status_code == 201
    assert client.post(
        "/v1/doc-requirements", json={"country_code": "in", "doc_type": "IN_CASE_DUPE", "label": "A"}
    ).status_code == 409


def test_update_into_an_existing_doc_type_returns_409():
    """Uniqueness has to hold on the update path too — repointing a row's doc_type at one
    that already exists for the country duplicates it just as effectively as a POST would."""
    created = client.post(
        "/v1/doc-requirements",
        json={"country_code": "IN", "doc_type": "IN_UPD_DUPE", "label": "U", "sort_order": 51},
    ).json()

    clash = client.put(
        f"/v1/doc-requirements/{created['id']}",
        json={"country_code": "IN", "doc_type": "IN_PAN_CARD", "label": "U", "sort_order": 51},
    )
    assert clash.status_code == 409

    rows = client.get("/v1/doc-requirements?country=IN").json()
    assert len([r for r in rows if r["doc_type"] == "IN_PAN_CARD"]) == 1


def test_update_keeping_own_doc_type_is_not_a_self_conflict():
    """The 409 check must exclude the row being updated, or every plain label edit would 409."""
    created = client.post(
        "/v1/doc-requirements",
        json={"country_code": "IN", "doc_type": "IN_SELF", "label": "Before", "sort_order": 52},
    ).json()

    updated = client.put(
        f"/v1/doc-requirements/{created['id']}",
        json={"country_code": "IN", "doc_type": "IN_SELF", "label": "After", "sort_order": 52},
    )
    assert updated.status_code == 200
    assert updated.json()["label"] == "After"


def test_same_doc_type_in_another_country_is_allowed():
    assert client.post(
        "/v1/doc-requirements", json={"country_code": "IN", "doc_type": "SHARED_DOC", "label": "S"}
    ).status_code == 201
    assert client.post(
        "/v1/doc-requirements", json={"country_code": "SG", "doc_type": "SHARED_DOC", "label": "S"}
    ).status_code == 201


def test_lowercase_country_code_is_normalized_and_retrievable():
    """Reads upper-case the query param, so a row stored lower-case would be unreachable."""
    created = client.post(
        "/v1/doc-requirements",
        json={"country_code": "in", "doc_type": "IN_LOWER", "label": "Lower", "sort_order": 60},
    )
    assert created.status_code == 201
    assert created.json()["country_code"] == "IN"

    doc_types = {row["doc_type"] for row in client.get("/v1/doc-requirements?country=IN").json()}
    assert "IN_LOWER" in doc_types

    assert "IN_LOWER" in {d["id"] for d in client.get("/v1/doctypes?country=IN").json()["docTypes"]}


def test_update_normalizes_country_code_too():
    created = client.post(
        "/v1/doc-requirements",
        json={"country_code": "IN", "doc_type": "IN_UPD_CASE", "label": "X", "sort_order": 61},
    ).json()
    updated = client.put(
        f"/v1/doc-requirements/{created['id']}",
        json={"country_code": "in", "doc_type": "IN_UPD_CASE", "label": "Y", "sort_order": 61},
    )
    assert updated.status_code == 200
    assert updated.json()["country_code"] == "IN"
    assert "IN_UPD_CASE" in {row["doc_type"] for row in client.get("/v1/doc-requirements?country=IN").json()}


def test_update_nonexistent_returns_404():
    r = client.put(
        "/v1/doc-requirements/999999",
        json={"country_code": "IN", "doc_type": "IN_X", "label": "X"},
    )
    assert r.status_code == 404
