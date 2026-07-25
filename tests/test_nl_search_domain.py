"""Domain-logic tests for app/nl_search/* — direct calls against a FakeLlmProvider."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.nl_search.models import NlSearchParams
from app.nl_search.parse import parse_natural_language_with_llm
from tests.fakes import FakeLlmProvider


@pytest.mark.asyncio
async def test_parse_valid_response_first_try():
    provider = FakeLlmProvider(
        responses=[{"intent": "attribute_search", "tradingName": "Acme Ltd", "summary": "search for Acme"}]
    )
    result = await parse_natural_language_with_llm(provider, "find Acme Ltd")
    assert result.intent == "attribute_search"
    assert result.tradingName == "Acme Ltd"
    assert result.source == "llm"
    assert result.confidence == "high"
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_parse_normalizes_country_name_to_iso2():
    provider = FakeLlmProvider(
        responses=[{"intent": "attribute_search", "country": "India", "summary": "vendors in India"}]
    )
    result = await parse_natural_language_with_llm(provider, "vendors in India")
    assert result.country == "IN"


@pytest.mark.asyncio
async def test_parse_uppercases_vendor_status():
    provider = FakeLlmProvider(
        responses=[{"intent": "attribute_search", "vendorStatus": "active", "summary": "active vendors"}]
    )
    result = await parse_natural_language_with_llm(provider, "active vendors")
    assert result.vendorStatus == "ACTIVE"


@pytest.mark.asyncio
async def test_parse_does_one_repair_round_trip_on_bad_first_response():
    provider = FakeLlmProvider(
        responses=[
            {"intent": "attribute_search", "country": "XYZ", "summary": "bad country"},  # invalid: not len 2
            {"intent": "attribute_search", "country": "IN", "summary": "fixed"},
        ]
    )
    result = await parse_natural_language_with_llm(provider, "vendors in some place")
    assert result.country == "IN"
    assert len(provider.calls) == 2
    # The repair call includes the original messages + assistant echo + repair instruction.
    repair_messages = provider.calls[1]
    assert repair_messages[-1].role == "user"
    assert "did not match the required schema" in repair_messages[-1].text


@pytest.mark.asyncio
async def test_parse_raises_when_repair_also_fails():
    provider = FakeLlmProvider(
        responses=[
            {"intent": "attribute_search", "country": "XYZ", "summary": "bad"},
            {"intent": "attribute_search", "country": "ALSO_BAD", "summary": "still bad"},
        ]
    )
    with pytest.raises(ValidationError):
        await parse_natural_language_with_llm(provider, "vendors somewhere")
    assert len(provider.calls) == 2


def test_country_must_be_exactly_length_two():
    with pytest.raises(ValidationError):
        NlSearchParams(intent="attribute_search", country="USA")
    NlSearchParams(intent="attribute_search", country="US")  # does not raise
