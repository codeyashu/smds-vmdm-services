"""Company-search LLM-assist endpoints, migrated from the portal's
``src/lib/company-search/*-llm.ts`` helpers.

Every endpoint here follows the same rule: no ``get_llm_provider()`` -> 503 (reused from
``extract.py``'s pattern); the LLM call itself failing (transport error, bad JSON, provider
raises) -> 502 with a short detail, never 500. There is deliberately no enabled/disabled flag
check — the portal owns that decision and simply won't call these routes when its AI toggle is
off.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.company_search import adjudicate, classify_tax, expand_terms, normalize_address, normalize_name, similarity
from app.company_search.guardrails import LLM_CANDIDATE_CAP
from app.company_search.normalize_name import EmptyNormalizedNameError
from app.core.logging import get_logger
from app.providers.llm.base import LlmProvider
from app.providers.llm.factory import get_llm_provider

router = APIRouter(prefix="/v1/company-search", tags=["company-search"])
log = get_logger()

_ADDRESS_RESPONSE_KEYS = {
    "streetName",
    "streetNumber",
    "apartmentOrFloor",
    "city",
    "postalCode",
    "regionName",
    "explanation",
}


def _require_provider() -> LlmProvider:
    provider = get_llm_provider()
    if provider is None:
        raise HTTPException(
            status_code=503,
            detail="No LLM provider available — configure DOCAI_LLM_PROVIDER.",
        )
    return provider


# --- normalize-address -----------------------------------------------------------------


class NormalizeAddressRequest(BaseModel):
    freeTextAddress: str | None = None
    tradingName: str | None = None
    iso2CountryCode: str | None = None


@router.post("/normalize-address")
async def normalize_address_route(body: NormalizeAddressRequest) -> dict[str, Any]:
    provider = _require_provider()
    try:
        result = await normalize_address.normalize_address_with_llm(
            provider,
            free_text_address=body.freeTextAddress,
            trading_name=body.tradingName,
            iso2_country_code=body.iso2CountryCode,
        )
    except Exception as exc:
        log.warning("company_search.normalize_address.failed", error=str(exc))
        raise HTTPException(status_code=502, detail="Address normalization failed.") from exc

    if not isinstance(result, dict):
        raise HTTPException(status_code=502, detail="Address normalization returned an unexpected shape.")
    return {k: v for k, v in result.items() if k in _ADDRESS_RESPONSE_KEYS and v is not None}


# --- normalize-name ---------------------------------------------------------------------


class NormalizeNameRequest(BaseModel):
    tradingName: str
    iso2CountryCode: str | None = None
    ruleBasedSuggestion: str | None = None


@router.post("/normalize-name")
async def normalize_name_route(body: NormalizeNameRequest) -> dict[str, Any]:
    provider = _require_provider()
    try:
        return await normalize_name.normalize_name_with_llm(
            provider,
            trading_name=body.tradingName,
            iso2_country_code=body.iso2CountryCode,
            rule_based_suggestion=body.ruleBasedSuggestion,
        )
    except EmptyNormalizedNameError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        log.warning("company_search.normalize_name.failed", error=str(exc))
        raise HTTPException(status_code=502, detail="Name normalization failed.") from exc


# --- classify-tax ------------------------------------------------------------------------


class ClassifyTaxRequest(BaseModel):
    rawIdentifiers: Any = None
    iso2CountryCode: str


@router.post("/classify-tax")
async def classify_tax_route(body: ClassifyTaxRequest) -> dict[str, Any]:
    provider = _require_provider()
    try:
        assignments = await classify_tax.classify_tax_with_llm(
            provider,
            raw_identifiers=body.rawIdentifiers,
            iso2_country_code=body.iso2CountryCode,
        )
    except Exception as exc:
        log.warning("company_search.classify_tax.failed", error=str(exc))
        raise HTTPException(status_code=502, detail="Tax classification failed.") from exc
    return {"assignments": assignments}


# --- expand-terms ------------------------------------------------------------------------


class ExpandTermsRequest(BaseModel):
    tradingName: str
    iso2CountryCode: str | None = None
    alreadyTried: list[str] = Field(default_factory=list)


@router.post("/expand-terms")
async def expand_terms_route(body: ExpandTermsRequest) -> dict[str, Any]:
    provider = _require_provider()
    try:
        return await expand_terms.expand_terms_with_llm(
            provider,
            trading_name=body.tradingName,
            iso2_country_code=body.iso2CountryCode,
            already_tried=body.alreadyTried,
        )
    except Exception as exc:
        log.warning("company_search.expand_terms.failed", error=str(exc))
        raise HTTPException(status_code=502, detail="Search-term expansion failed.") from exc


# --- adjudicate --------------------------------------------------------------------------


class AdjudicateCandidate(BaseModel):
    id: str | None = None
    companyName: str | None = None
    address: str | None = None
    deterministicScore: float | None = None
    registryNote: str | None = None


class AdjudicateRequest(BaseModel):
    tradingName: str | None = None
    address: str | None = None
    iso2CountryCode: str | None = None
    candidates: list[AdjudicateCandidate] = Field(default_factory=list)


@router.post("/adjudicate")
async def adjudicate_route(body: AdjudicateRequest) -> dict[str, Any]:
    capped = [c for c in body.candidates[:LLM_CANDIDATE_CAP] if c.id]
    if not capped:
        raise HTTPException(status_code=400, detail="candidates must include at least one entry with an id.")

    provider = _require_provider()
    try:
        return await adjudicate.adjudicate_with_llm(
            provider,
            trading_name=body.tradingName,
            address=body.address,
            iso2_country_code=body.iso2CountryCode,
            candidates=[c.model_dump() for c in capped],
        )
    except Exception as exc:
        log.warning("company_search.adjudicate.failed", error=str(exc))
        raise HTTPException(status_code=502, detail="Adjudication failed.") from exc


# --- similarity --------------------------------------------------------------------------


class SimilarityCandidate(BaseModel):
    id: str | None = None
    companyName: str | None = None
    address: str | None = None


class SimilarityRequest(BaseModel):
    tradingName: str | None = None
    address: str | None = None
    iso2CountryCode: str | None = None
    candidates: list[SimilarityCandidate] = Field(default_factory=list)


@router.post("/similarity")
async def similarity_route(body: SimilarityRequest) -> dict[str, Any]:
    if not (body.tradingName or "").strip() and not (body.address or "").strip():
        raise HTTPException(status_code=400, detail="tradingName or address is required.")

    capped = [c for c in body.candidates[:LLM_CANDIDATE_CAP] if c.id]

    provider = _require_provider()
    try:
        return await similarity.similarity_with_llm(
            provider,
            trading_name=body.tradingName,
            address=body.address,
            iso2_country_code=body.iso2CountryCode,
            candidates=[c.model_dump() for c in capped],
        )
    except Exception as exc:
        log.warning("company_search.similarity.failed", error=str(exc))
        raise HTTPException(status_code=502, detail="Similarity scoring failed.") from exc
