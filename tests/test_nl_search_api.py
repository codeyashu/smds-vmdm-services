"""API-level tests for /v1/nl-search/parse. No LLM config -> 503, never 500."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from tests.fakes import FakeLlmProvider

client = TestClient(app)


def test_parse_returns_503_when_unconfigured():
    r = client.post("/v1/nl-search/parse", json={"query": "find Acme Ltd"})
    assert r.status_code == 503


def test_parse_success_with_fake_provider(monkeypatch):
    fake = FakeLlmProvider(
        responses=[{"intent": "attribute_search", "tradingName": "Acme Ltd", "summary": "search for Acme"}]
    )
    monkeypatch.setattr("app.api.v1.nl_search.get_llm_provider", lambda: fake)
    r = client.post("/v1/nl-search/parse", json={"query": "find Acme Ltd"})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "attribute_search"
    assert body["tradingName"] == "Acme Ltd"
    assert body["source"] == "llm"
    assert body["confidence"] == "high"


def test_parse_502_when_both_attempts_fail_validation(monkeypatch):
    fake = FakeLlmProvider(
        responses=[
            {"intent": "attribute_search", "country": "XYZ", "summary": "bad"},
            {"intent": "attribute_search", "country": "STILLBAD", "summary": "still bad"},
        ]
    )
    monkeypatch.setattr("app.api.v1.nl_search.get_llm_provider", lambda: fake)
    r = client.post("/v1/nl-search/parse", json={"query": "vendors somewhere"})
    assert r.status_code == 502


def test_parse_502_on_provider_transport_error(monkeypatch):
    fake = FakeLlmProvider(error=RuntimeError("network down"))
    monkeypatch.setattr("app.api.v1.nl_search.get_llm_provider", lambda: fake)
    r = client.post("/v1/nl-search/parse", json={"query": "find Acme"})
    assert r.status_code == 502
