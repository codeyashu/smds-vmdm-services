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
