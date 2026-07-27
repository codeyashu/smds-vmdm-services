"""API surface tests. No Azure config -> extraction returns 503, never 500. Boots clean."""

from __future__ import annotations

import io

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_ready_reports_azure_unconfigured():
    body = client.get("/ready").json()
    assert body["status"] == "ok"
    assert body["azureConfigured"] is False


def test_doctypes_in():
    body = client.get("/v1/doctypes?country=IN").json()
    ids = {d["id"] for d in body["docTypes"]}
    assert {"IN_PAN_CARD", "IN_GST_CERTIFICATE", "IN_CANCELLED_CHEQUE"} <= ids


def test_doctypes_tier_reflects_ingest_write_target_not_mandatory_flag():
    """Tier 1 == the extractor can produce applyable patches for it. Tier 2 doc types
    (Udyam, COI) only ever surface as `unmapped`, whatever their is_mandatory flag says."""
    body = client.get("/v1/doctypes?country=IN").json()
    tiers = {d["id"]: d["tier"] for d in body["docTypes"]}
    assert tiers["IN_PAN_CARD"] == 1
    assert tiers["IN_GST_CERTIFICATE"] == 1
    assert tiers["IN_CANCELLED_CHEQUE"] == 1
    assert tiers["IN_UDYAM_CERTIFICATE"] == 2
    assert tiers["IN_CERTIFICATE_OF_INCORPORATION"] == 2


def test_doctypes_tier_ignores_is_mandatory_changes():
    """An admin marking Udyam mandatory must not silently relabel it tier 1 — it still has
    no ingest write path. Conversely an optional PAN card stays tier 1."""
    udyam = next(
        row
        for row in client.get("/v1/doc-requirements?country=IN").json()
        if row["doc_type"] == "IN_UDYAM_CERTIFICATE"
    )
    promoted = client.put(
        f"/v1/doc-requirements/{udyam['id']}",
        json={**{k: v for k, v in udyam.items() if k != "id"}, "is_mandatory": True},
    )
    assert promoted.status_code == 200
    assert promoted.json()["is_mandatory"] is True

    tiers = {d["id"]: d["tier"] for d in client.get("/v1/doctypes?country=IN").json()["docTypes"]}
    assert tiers["IN_UDYAM_CERTIFICATE"] == 2


def test_doctypes_non_in_rejected():
    assert client.get("/v1/doctypes?country=US").status_code == 422


def test_extract_rejects_wrong_mime():
    files = {"file": ("x.txt", io.BytesIO(b"not a pdf"), "text/plain")}
    r = client.post("/v1/extract", files=files, data={"countryCode": "IN"})
    assert r.status_code == 415


def test_extract_rejects_oversize(monkeypatch):
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DOCAI_MAX_FILE_BYTES", "10")
    big = b"%PDF-" + b"0" * 100
    files = {"file": ("x.pdf", io.BytesIO(big), "application/pdf")}
    r = client.post("/v1/extract", files=files, data={"countryCode": "IN"})
    assert r.status_code == 413
    get_settings.cache_clear()


def test_extract_valid_pdf_but_azure_unconfigured_returns_503():
    files = {"file": ("gst.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")}
    r = client.post("/v1/extract", files=files, data={"countryCode": "IN"})
    assert r.status_code == 503


def test_extract_success_returns_patches(monkeypatch):
    import io

    from app.documents.extract import pipeline
    from tests.fakes import GST_ENVELOPE, FakeLlm, FakeOcr

    monkeypatch.setattr(pipeline, "get_ocr_provider", lambda: FakeOcr())
    monkeypatch.setattr(pipeline, "get_llm_provider", lambda: FakeLlm([GST_ENVELOPE]))

    files = {"file": ("gst.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")}
    r = client.post("/v1/extract", files=files, data={"countryCode": "IN"})
    assert r.status_code == 200
    body = r.json()
    assert body["docType"] == "IN_GST_CERTIFICATE"
    assert any(p["path"].endswith("taxIdentificationNumber") for p in body["patches"])


def test_extract_batch_rejects_too_many_files(monkeypatch):
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DOCAI_MAX_BATCH_FILES", "2")
    files = [
        ("files", ("a.pdf", io.BytesIO(b"%PDF-1.4 a"), "application/pdf")),
        ("files", ("b.pdf", io.BytesIO(b"%PDF-1.4 b"), "application/pdf")),
        ("files", ("c.pdf", io.BytesIO(b"%PDF-1.4 c"), "application/pdf")),
    ]
    r = client.post("/v1/extract/batch", files=files, data={"countryCode": "IN"})
    assert r.status_code == 413
    get_settings.cache_clear()


def test_extract_batch_isolates_per_file_errors(monkeypatch):
    from app.documents.extract import pipeline
    from tests.fakes import GST_ENVELOPE, FakeLlm, FakeOcr

    monkeypatch.setattr(pipeline, "get_ocr_provider", lambda: FakeOcr())
    monkeypatch.setattr(pipeline, "get_llm_provider", lambda: FakeLlm([GST_ENVELOPE, GST_ENVELOPE]))

    files = [
        ("files", ("bad.txt", io.BytesIO(b"nope"), "text/plain")),
        ("files", ("gst.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")),
    ]
    r = client.post("/v1/extract/batch", files=files, data={"countryCode": "IN"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["results"]) == 2
    assert body["results"][0]["docType"] == "UNKNOWN"
    assert body["results"][1]["docType"] == "IN_GST_CERTIFICATE"
