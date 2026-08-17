"""Orchestrate web-trust verification for a vendor snapshot."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from app.web_trust.connectors import run_connector
from app.web_trust.correlation import compute_field_correlation, merge_llm_corroboration
from app.web_trust.learning import get_learning_hints
from app.web_trust.llm_corroboration import corroborate_with_llm_async
from app.web_trust.playbook import load_web_trust_playbook
from app.web_trust.scoring import build_vendor_field_evidence, compute_overall_match
from app.web_trust.types import (
    BillToAddressReview,
    FieldConfidence,
    FieldCorrelationSummary,
    WebMatchedRecord,
    WebTrustBand,
    WebTrustSource,
    WebTrustVerifyRequest,
    WebTrustVerifyResponse,
)


def _trust_band(score: int | None) -> WebTrustBand:
    if score is None:
        return "insufficient"
    if score >= 85:
        return "high"
    if score >= 60:
        return "medium"
    return "low"


def _skipped_response(country_code: str, reason: str) -> WebTrustVerifyResponse:
    return WebTrustVerifyResponse(
        skipped=True,
        skipReason=reason,
        countryCode=country_code,
        playbookStatus="off",
        trustScore=None,
        trustBand=None,
    )


def _build_entered_data(request_dict: dict[str, Any]) -> dict[str, Any]:
    address = request_dict.get("address") or {}
    street = " ".join(
        part
        for part in [
            address.get("streetNumber"),
            address.get("streetName"),
            address.get("buildingName"),
        ]
        if part
    ).strip()
    tax_ids = request_dict.get("taxIdentificationNumbers") or []
    return {
        "tradingName": request_dict.get("tradingName"),
        "legalName": request_dict.get("legalName"),
        "taxIdentificationNumbers": tax_ids,
        "addressPurpose": "BILL_TO",
        "addressLine": street or None,
        "cityName": address.get("cityName"),
        "postalCode": address.get("postalCode"),
        "countryCode": request_dict.get("iso2CountryCode"),
        "website": request_dict.get("website"),
    }


def _build_bill_to_review(matched_records: list[WebMatchedRecord]) -> BillToAddressReview | None:
    record = next((entry for entry in matched_records if entry.connectorId == "bill_to_address"), None)
    if not record:
        return None
    limitations = [
        line
        for line in [
            "Bill-to address is incomplete or failed format checks."
            if record.matchScore < 70
            else None
        ]
        if line
    ]
    return BillToAddressReview(
        purposeCode="BILL_TO",
        completenessScore=record.matchScore,
        fieldEvidence=record.fieldEvidence,
        limitations=limitations,
    )


def _composite_trust_score(matched_records: list[WebMatchedRecord]) -> int:
    address = next((entry for entry in matched_records if entry.connectorId == "bill_to_address"), None)
    tax_records = [entry for entry in matched_records if entry.connectorId != "bill_to_address"]
    if tax_records and address:
        best_tax = max(tax_records, key=lambda entry: entry.matchScore * entry.authorityWeight)
        return int(round(best_tax.matchScore * 0.65 + address.matchScore * 0.35))
    if tax_records:
        best_tax = max(tax_records, key=lambda entry: entry.matchScore * entry.authorityWeight)
        return best_tax.matchScore
    if address:
        return address.matchScore
    return 0


def _dedupe_format_when_live_registry(raw_hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    live_tax_ids = {
        str((hit.get("extracted") or {}).get("taxIdentificationNumber", "")).upper()
        for hit in raw_hits
        if hit.get("verificationMode") == "live_registry"
        and (hit.get("extracted") or {}).get("taxIdentificationNumber")
    }
    if not live_tax_ids:
        return raw_hits
    filtered: list[dict[str, Any]] = []
    for hit in raw_hits:
        if hit.get("connectorId") in ("gb_company_number", "in_gstin"):
            tax_id = str((hit.get("extracted") or {}).get("taxIdentificationNumber", "")).upper()
            if tax_id in live_tax_ids:
                continue
        filtered.append(hit)
    return filtered


def _discover_website_url(
    body_website: str | None,
    raw_hits: list[dict[str, Any]],
) -> str | None:
    if body_website and body_website.strip():
        return body_website.strip()
    for hit in raw_hits:
        if hit.get("connectorId") != "commercial_directory":
            continue
        extracted = hit.get("extracted") or {}
        for candidate in (extracted.get("website"), hit.get("sourceUrl")):
            if isinstance(candidate, str) and candidate.strip().startswith("http"):
                return candidate.strip()
    return None


def _maybe_chain_website_probe(
    *,
    raw_hits: list[dict[str, Any]],
    tax_ids: list[str],
    trading_name: str | None,
    legal_name: str | None,
    address: dict[str, Any],
    country: str,
    website: str | None,
) -> None:
    if any(hit.get("connectorId") == "company_website" for hit in raw_hits):
        return
    discovered = _discover_website_url(website, raw_hits)
    if not discovered:
        return
    raw_hits.extend(
        run_connector(
            "company_website_probe",
            tax_ids=tax_ids,
            trading_name=trading_name,
            legal_name=legal_name,
            address=address,
            country=country,
            website=discovered,
        )
    )


def _build_verification_disclaimer(matched_records: list[WebMatchedRecord]) -> str | None:
    if not matched_records:
        return "No verification sources ran for this country."
    modes = {record.verificationMode for record in matched_records}
    source_types = {record.sourceType for record in matched_records}
    has_enrichment = bool(source_types & {"commercial_directory", "company_website"})
    if modes == {"format_check"} and not has_enrichment:
        return (
            "Format and structure checks only — not confirmed with a live government "
            "registry lookup."
        )
    if modes == {"format_check"} and has_enrichment:
        return (
            "Format checks plus commercial directory and/or company website signals — "
            "not confirmed with a live government registry lookup."
        )
    if "live_registry" in modes and "format_check" in modes:
        return (
            "Some rows are format-only; rows labeled Live registry were fetched from a "
            "government API at review time."
        )
    return None


def _trace_verification(review_id: str, *, country: str, request_dict: dict[str, Any], response: WebTrustVerifyResponse) -> None:
    try:
        from app.observability.langfuse_trace import get_langfuse_client

        client = get_langfuse_client()
        if client is None:
            return
        client.trace(
            id=review_id,
            name="web_trust_verify",
            input={
                "countryCode": country,
                "tradingName": request_dict.get("tradingName"),
                "taxIdCount": len(request_dict.get("taxIdentificationNumbers") or []),
            },
            output={
                "trustScore": response.trustScore,
                "trustBand": response.trustBand,
                "matchedRecordCount": len(response.matchedRecords),
            },
            metadata={"playbookStatus": response.playbookStatus},
        )
        client.flush()
    except Exception:  # noqa: BLE001
        return


async def verify_web_trust_async(body: WebTrustVerifyRequest) -> WebTrustVerifyResponse:
    country = body.iso2CountryCode.strip().upper()
    playbook = load_web_trust_playbook(country)
    if playbook is None:
        return _skipped_response(country, f"No web-trust playbook for {country}.")
    if playbook.status in ("off", "registry_only"):
        return _skipped_response(country, f"Web trust is {playbook.status} for {country}.")

    request_dict: dict[str, Any] = {
        "tradingName": body.tradingName,
        "legalName": body.legalName,
        "iso2CountryCode": country,
        "taxIdentificationNumbers": [value.strip() for value in body.taxIdentificationNumbers if value.strip()],
        "address": body.address.model_dump() if body.address else {},
        "website": body.website,
    }

    raw_hits: list[dict[str, Any]] = []
    connector_types = [connector.type for connector in playbook.connectors]
    if playbook.fallbackWebSearch:
        for fallback_type in ("company_registry_lookup", "company_website_probe"):
            if fallback_type not in connector_types:
                connector_types.append(fallback_type)

    for connector_type in connector_types:
        raw_hits.extend(
            run_connector(
                connector_type,
                tax_ids=request_dict["taxIdentificationNumbers"],
                trading_name=body.tradingName,
                legal_name=body.legalName,
                address=request_dict["address"],
                country=country,
                website=body.website,
            )
        )

    raw_hits = _dedupe_format_when_live_registry(raw_hits)
    _maybe_chain_website_probe(
        raw_hits=raw_hits,
        tax_ids=request_dict["taxIdentificationNumbers"],
        trading_name=body.tradingName,
        legal_name=body.legalName,
        address=request_dict["address"],
        country=country,
        website=body.website,
    )

    matched_records: list[WebMatchedRecord] = []
    sources: list[WebTrustSource] = []
    limitations: list[str] = []

    for index, hit in enumerate(raw_hits):
        for note in hit.get("limitations") or []:
            if note not in limitations:
                limitations.append(note)

    if not raw_hits and not request_dict["taxIdentificationNumbers"]:
        limitations.append("No tax identifiers supplied — format connectors could not run.")

    for index, hit in enumerate(raw_hits):
        if hit.get("skipMatchedRecord"):
            continue

        extracted = hit.get("extracted") or {}
        precomputed = hit.get("fieldEvidence")
        if precomputed:
            field_evidence = precomputed
            match_score = int(hit.get("completenessScore") or 0)
        else:
            field_evidence = build_vendor_field_evidence(request_dict, extracted)
            match_score, _, _ = compute_overall_match(field_evidence)
        record_id = f"{hit.get('connectorId', 'source')}-{index}"
        source_url = hit.get("sourceUrl")
        if source_url:
            domain = urlparse(source_url).netloc
            sources.append(
                WebTrustSource(
                    url=source_url,
                    domain=domain,
                    retrievedAt=hit.get("retrievedAt") or datetime.now(timezone.utc).isoformat(),
                )
            )
        matched_records.append(
            WebMatchedRecord(
                id=record_id,
                sourceType=hit.get("sourceType", "format_validator"),
                verificationMode=hit.get("verificationMode", "format_check"),
                sourceUrl=source_url,
                connectorId=hit.get("connectorId", "unknown"),
                displayName=hit.get("displayName", "Verification source"),
                extractedFields=extracted,
                matchScore=match_score,
                fieldEvidence=field_evidence,
                authorityWeight=float(hit.get("authorityWeight", 0.5)),
            )
        )

    if not matched_records:
        limitations.append("No authoritative web sources matched the entered identifiers.")
        review_id = str(uuid4())
        connector_ids = [connector.id for connector in playbook.connectors]
        response = WebTrustVerifyResponse(
            skipped=False,
            reviewId=review_id,
            countryCode=country,
            playbookStatus=playbook.status,
            trustScore=0,
            trustBand="insufficient",
            enteredData=_build_entered_data(request_dict),
            billToAddressReview=_build_bill_to_review(matched_records),
            learningHints=get_learning_hints(country, connector_ids),
            matchedRecords=[],
            fieldEvidence=[],
            fieldCorrelation=FieldCorrelationSummary(),
            sources=[],
            limitations=limitations,
            verificationDisclaimer=_build_verification_disclaimer(matched_records),
            minTrustToAutoProceed=playbook.minTrustToAutoProceed,
            submitPolicy=playbook.submitPolicy,
        )
        _trace_verification(review_id, country=country, request_dict=request_dict, response=response)
        return response

    trust_score = _composite_trust_score(matched_records)
    bill_to_review = _build_bill_to_review(matched_records)
    if bill_to_review and bill_to_review.completenessScore < 70:
        trust_score = min(trust_score, 55)
        if "Bill-to address is incomplete or failed format checks." not in limitations:
            limitations.append("Bill-to address is incomplete or failed format checks.")

    tax_records = [entry for entry in matched_records if entry.connectorId != "bill_to_address"]
    best = (
        max(tax_records, key=lambda entry: entry.matchScore * entry.authorityWeight)
        if tax_records
        else matched_records[0]
    )
    aggregate_evidence, field_correlation = compute_field_correlation(matched_records)

    run_llm = playbook.fallbackWebSearch or any(
        connector.type == "llm_entity_corroboration" for connector in playbook.connectors
    )
    if run_llm:
        llm_record = await corroborate_with_llm_async(request_dict, matched_records)
        if llm_record:
            matched_records.append(llm_record)
            corroborated = [
                entry.field
                for entry in llm_record.fieldEvidence
                if entry.status != "unknown" and entry.score >= 50
            ]
            field_correlation = merge_llm_corroboration(
                field_correlation,
                llm_verdict=llm_record.llmVerdict or "likely",
                llm_score=llm_record.matchScore,
                corroborated_fields=corroborated,
            )
            aggregate_evidence, _ = compute_field_correlation(matched_records)

    if field_correlation.isolatedMatch:
        trust_score = min(trust_score, 60)
        if "Only tax/country matched — trading name and address were not corroborated." not in limitations:
            limitations.append(
                "Only tax/country matched — trading name and address were not corroborated."
            )

    if len(matched_records) >= 2:
        tax_scores = [
            entry.score
            for entry in best.fieldEvidence
            if entry.field == "tax" and entry.status != "unknown"
        ]
        if tax_scores and tax_scores[0] >= 85:
            trust_score = min(100, trust_score + 5)

    live_gstin = next(
        (record for record in matched_records if record.connectorId == "in_gstin_live"),
        None,
    )
    if (
        live_gstin
        and bill_to_review
        and bill_to_review.completenessScore >= 70
    ):
        name_scores = [
            entry.score
            for entry in live_gstin.fieldEvidence
            if entry.field == "tradingName" and entry.status != "unknown"
        ]
        if name_scores and name_scores[0] >= 85:
            trust_score = min(100, trust_score + 5)

    if any(record.llmVerdict == "different" for record in matched_records):
        trust_score = min(trust_score, 30)

    if not any(record.verificationMode == "live_registry" for record in matched_records):
        trust_score = min(trust_score, 70)
        if "No live government-registry lookup confirmed this record." not in limitations:
            limitations.append("No live government-registry lookup confirmed this record.")

    review_id = str(uuid4())
    connector_ids = sorted({record.connectorId for record in matched_records})
    response = WebTrustVerifyResponse(
        skipped=False,
        reviewId=review_id,
        countryCode=country,
        playbookStatus=playbook.status,
        trustScore=trust_score,
        trustBand=_trust_band(trust_score),
        enteredData=_build_entered_data(request_dict),
        billToAddressReview=bill_to_review,
        learningHints=get_learning_hints(country, connector_ids),
        matchedRecords=sorted(
            matched_records,
            key=lambda entry: entry.matchScore * entry.authorityWeight,
            reverse=True,
        ),
        fieldEvidence=aggregate_evidence,
        fieldCorrelation=field_correlation,
        sources=sources,
        limitations=limitations,
        verificationDisclaimer=_build_verification_disclaimer(matched_records),
        minTrustToAutoProceed=playbook.minTrustToAutoProceed,
        submitPolicy=playbook.submitPolicy,
    )
    _trace_verification(review_id, country=country, request_dict=request_dict, response=response)
    return response


def verify_web_trust(body: WebTrustVerifyRequest) -> WebTrustVerifyResponse:
    """Sync entry for scripts/tests — FastAPI routes should call verify_web_trust_async."""
    return asyncio.run(verify_web_trust_async(body))
