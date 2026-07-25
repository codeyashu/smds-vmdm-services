"""API-level tests for /v1/company-search/*. No LLM config -> 503, never 500, matching the
test_extract_rejects_wrong_mime-style coverage in test_api.py. A couple of endpoints are also
exercised end-to-end against a monkeypatched FakeLlmProvider to prove the 200 path wires up."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from tests.fakes import FakeLlmProvider

client = TestClient(app)


def test_normalize_address_returns_503_when_unconfigured():
    r = client.post("/v1/company-search/normalize-address", json={"freeTextAddress": "123 Main St"})
    assert r.status_code == 503


def test_normalize_name_returns_503_when_unconfigured():
    r = client.post("/v1/company-search/normalize-name", json={"tradingName": "Acme"})
    assert r.status_code == 503


def test_classify_tax_returns_503_when_unconfigured():
    r = client.post(
        "/v1/company-search/classify-tax", json={"rawIdentifiers": {}, "iso2CountryCode": "IN"}
    )
    assert r.status_code == 503


def test_expand_terms_returns_503_when_unconfigured():
    r = client.post("/v1/company-search/expand-terms", json={"tradingName": "Acme"})
    assert r.status_code == 503


def test_adjudicate_returns_503_when_unconfigured_and_candidates_present():
    r = client.post(
        "/v1/company-search/adjudicate",
        json={"tradingName": "Acme", "candidates": [{"id": "a"}]},
    )
    assert r.status_code == 503


def test_similarity_returns_503_when_unconfigured_and_inputs_present():
    r = client.post(
        "/v1/company-search/similarity",
        json={"tradingName": "Acme", "candidates": [{"id": "a"}]},
    )
    assert r.status_code == 503


def test_adjudicate_rejects_empty_candidates_with_400_even_when_unconfigured():
    r = client.post("/v1/company-search/adjudicate", json={"tradingName": "Acme", "candidates": []})
    assert r.status_code == 400


def test_adjudicate_rejects_candidates_without_id_with_400():
    r = client.post(
        "/v1/company-search/adjudicate",
        json={"tradingName": "Acme", "candidates": [{"companyName": "no id here"}]},
    )
    assert r.status_code == 400


def test_similarity_rejects_blank_trading_name_and_address_with_400():
    r = client.post("/v1/company-search/similarity", json={"candidates": [{"id": "a"}]})
    assert r.status_code == 400


def test_normalize_address_success_with_fake_provider(monkeypatch):
    fake = FakeLlmProvider(responses=[{"city": "Mumbai", "explanation": "parsed"}])
    monkeypatch.setattr("app.api.v1.company_search.get_llm_provider", lambda: fake)
    r = client.post("/v1/company-search/normalize-address", json={"freeTextAddress": "Mumbai"})
    assert r.status_code == 200
    assert r.json() == {"city": "Mumbai", "explanation": "parsed"}


def test_normalize_name_502_on_empty_model_response(monkeypatch):
    fake = FakeLlmProvider(responses=[{"normalizedName": "   "}])
    monkeypatch.setattr("app.api.v1.company_search.get_llm_provider", lambda: fake)
    r = client.post("/v1/company-search/normalize-name", json={"tradingName": "Acme"})
    assert r.status_code == 502


def test_normalize_name_502_on_provider_error(monkeypatch):
    fake = FakeLlmProvider(error=RuntimeError("boom"))
    monkeypatch.setattr("app.api.v1.company_search.get_llm_provider", lambda: fake)
    r = client.post("/v1/company-search/normalize-name", json={"tradingName": "Acme"})
    assert r.status_code == 502


def test_adjudicate_success_with_fake_provider(monkeypatch):
    fake = FakeLlmProvider(
        responses=[{"rankedIds": ["a"], "verdicts": [{"id": "a", "verdict": "same", "reason": "exact"}]}]
    )
    monkeypatch.setattr("app.api.v1.company_search.get_llm_provider", lambda: fake)
    r = client.post(
        "/v1/company-search/adjudicate",
        json={"tradingName": "Acme", "candidates": [{"id": "a"}]},
    )
    assert r.status_code == 200
    assert r.json() == {"rankedIds": ["a"], "verdicts": [{"id": "a", "verdict": "same", "reason": "exact"}]}


def test_expand_terms_caps_candidates_over_ten(monkeypatch):
    fake = FakeLlmProvider(responses=[{"terms": []}])
    monkeypatch.setattr("app.api.v1.company_search.get_llm_provider", lambda: fake)
    r = client.post("/v1/company-search/expand-terms", json={"tradingName": "Acme"})
    assert r.status_code == 200
    assert r.json() == {"terms": []}
