"""Domain-logic tests for app/company_search/* — exercised directly against a FakeLlmProvider,
no HTTP involved. Mirrors the filtering/dedup/cap rules in the portal's *-llm.ts sources."""

from __future__ import annotations

import pytest

from app.company_search.adjudicate import adjudicate_with_llm
from app.company_search.classify_tax import classify_tax_with_llm
from app.company_search.expand_terms import expand_terms_with_llm
from app.company_search.normalize_address import normalize_address_with_llm
from app.company_search.normalize_name import EmptyNormalizedNameError, normalize_name_with_llm
from app.company_search.similarity import similarity_with_llm
from tests.fakes import FakeLlmProvider


# --- normalize_address --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_normalize_address_passes_through_model_output():
    provider = FakeLlmProvider(responses=[{"city": "Mumbai", "postalCode": "400001"}])
    result = await normalize_address_with_llm(provider, free_text_address="123 Main St, Mumbai")
    assert result == {"city": "Mumbai", "postalCode": "400001"}


# --- normalize_name ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_normalize_name_returns_trimmed_name_and_explanation():
    provider = FakeLlmProvider(responses=[{"normalizedName": "  Acme Pvt Ltd  ", "explanation": " fixed spacing "}])
    result = await normalize_name_with_llm(provider, trading_name="AcmePvtLtd")
    assert result == {"normalizedName": "Acme Pvt Ltd", "explanation": "fixed spacing"}


@pytest.mark.asyncio
async def test_normalize_name_raises_on_empty_normalized_name():
    provider = FakeLlmProvider(responses=[{"normalizedName": "   "}])
    with pytest.raises(EmptyNormalizedNameError):
        await normalize_name_with_llm(provider, trading_name="AcmePvtLtd")


@pytest.mark.asyncio
async def test_normalize_name_raises_when_key_missing():
    provider = FakeLlmProvider(responses=[{}])
    with pytest.raises(EmptyNormalizedNameError):
        await normalize_name_with_llm(provider, trading_name="AcmePvtLtd")


# --- classify_tax --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classify_tax_filters_invalid_tax_type_codes():
    provider = FakeLlmProvider(
        responses=[
            {
                "assignments": [
                    {"taxTypeCode": "TAXNO4", "taxIdentificationNumber": "27ABCDE1234F1Z5", "label": "GSTIN"},
                    {"taxTypeCode": "NOTATAXCODE", "taxIdentificationNumber": "123", "label": "bad code"},
                    {"taxTypeCode": "TAXNO3", "taxIdentificationNumber": "  ", "label": "blank id"},
                    {"taxTypeCode": "taxno1", "taxIdentificationNumber": "12345678901", "label": "lowercase ok"},
                ]
            }
        ]
    )
    result = await classify_tax_with_llm(provider, raw_identifiers={}, iso2_country_code="IN")
    assert result == [
        {"taxTypeCode": "TAXNO4", "taxIdentificationNumber": "27ABCDE1234F1Z5", "label": "GSTIN"},
        {"taxTypeCode": "taxno1", "taxIdentificationNumber": "12345678901", "label": "lowercase ok"},
    ]


@pytest.mark.asyncio
async def test_classify_tax_empty_assignments_is_empty_list():
    provider = FakeLlmProvider(responses=[{"assignments": []}])
    result = await classify_tax_with_llm(provider, raw_identifiers={}, iso2_country_code="IN")
    assert result == []


# --- expand_terms --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expand_terms_dedupes_against_trading_name_and_already_tried():
    provider = FakeLlmProvider(
        responses=[{"terms": ["Acme Ltd", "acme pvt ltd", "Already Tried Co", "New Term"], "reason": "variants"}]
    )
    result = await expand_terms_with_llm(
        provider, trading_name="Acme Ltd", already_tried=["Already Tried Co"]
    )
    assert result == {"terms": ["acme pvt ltd", "New Term"], "reason": "variants"}


@pytest.mark.asyncio
async def test_expand_terms_caps_at_six():
    provider = FakeLlmProvider(responses=[{"terms": [f"Term {i}" for i in range(10)]}])
    result = await expand_terms_with_llm(provider, trading_name="Acme")
    assert len(result["terms"]) == 6


@pytest.mark.asyncio
async def test_expand_terms_empty_is_valid():
    provider = FakeLlmProvider(responses=[{"terms": []}])
    result = await expand_terms_with_llm(provider, trading_name="Acme")
    assert result == {"terms": []}


# --- adjudicate -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adjudicate_drops_unknown_ids_and_dedupes_and_appends_unranked():
    candidates = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    provider = FakeLlmProvider(
        responses=[
            {
                "rankedIds": ["b", "b", "unknown-id"],
                "verdicts": [
                    {"id": "b", "verdict": "same", "reason": "exact match"},
                    {"id": "b", "verdict": "likely", "reason": "duplicate, should be dropped"},
                    {"id": "unknown-id", "verdict": "same", "reason": "invented id, should be dropped"},
                ],
            }
        ]
    )
    result = await adjudicate_with_llm(
        provider, trading_name="Acme", address=None, iso2_country_code="IN", candidates=candidates
    )
    assert result["verdicts"] == [{"id": "b", "verdict": "same", "reason": "exact match"}]
    # b ranked first (from model), then a and c appended in original order.
    assert result["rankedIds"] == ["b", "a", "c"]


@pytest.mark.asyncio
async def test_adjudicate_empty_verdicts_after_filtering_is_valid():
    candidates = [{"id": "a"}]
    provider = FakeLlmProvider(responses=[{"rankedIds": [], "verdicts": []}])
    result = await adjudicate_with_llm(
        provider, trading_name="Acme", address=None, iso2_country_code="IN", candidates=candidates
    )
    assert result == {"rankedIds": ["a"], "verdicts": []}


# --- similarity -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_similarity_clamps_scores_and_drops_unknown_ids():
    candidates = [{"id": "a"}, {"id": "b"}]
    provider = FakeLlmProvider(
        responses=[
            {
                "candidates": [
                    {"id": "a", "nameScore": 150, "addressScore": -20, "note": "clamped"},
                    {"id": "unknown", "nameScore": 90},
                    {"id": "b"},  # no scores at all -> dropped
                ]
            }
        ]
    )
    result = await similarity_with_llm(
        provider, trading_name="Acme", address=None, iso2_country_code="IN", candidates=candidates
    )
    assert result == {"candidates": [{"id": "a", "nameScore": 100, "addressScore": 0, "note": "clamped"}]}
