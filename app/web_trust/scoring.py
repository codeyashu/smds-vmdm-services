"""Deterministic field comparison for web-trust scoring."""

from __future__ import annotations

import re
from typing import Any

from rapidfuzz import fuzz

from app.web_trust.types import FieldConfidence, FieldMatchStatus

FIELD_WEIGHTS: dict[str, int] = {
    "tradingName": 30,
    "tax": 25,
    "city": 15,
    "street": 15,
    "postalCode": 10,
    "country": 5,
    "phone": 5,
}


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", value.lower())).strip()


def levenshtein_ratio(left: str | None, right: str | None) -> int:
    a = normalize_text(left)
    b = normalize_text(right)
    if not a or not b:
        return 0
    return int(round(fuzz.ratio(a, b)))


def token_overlap_score(left: str | None, right: str | None) -> int:
    a = normalize_text(left)
    b = normalize_text(right)
    if not a or not b:
        return 0
    if a == b:
        return 100
    a_tokens = set(a.split())
    b_tokens = set(b.split())
    if not a_tokens or not b_tokens:
        return 0
    overlap = len(a_tokens & b_tokens)
    union = len(a_tokens | b_tokens)
    return int(round((overlap / union) * 100))


def _tax_match_score(vendor_tax: str, extracted_tax: str) -> int:
    if not vendor_tax or not extracted_tax:
        return 0
    vendor_norm = normalize_text(vendor_tax)
    extracted_norm = normalize_text(extracted_tax)
    if vendor_norm == extracted_norm:
        return 100
    vendor_parts = [
        normalize_text(part)
        for part in re.split(r"[·,;/\s]+", vendor_tax)
        if part and part.strip()
    ]
    if extracted_norm in vendor_parts:
        return 100
    for part in vendor_parts:
        if part and (part in extracted_norm or extracted_norm in part):
            return max(levenshtein_ratio(part, extracted_norm), 85)
    return levenshtein_ratio(vendor_tax, extracted_tax)


def status_from_score(score: int) -> FieldMatchStatus:
    if score >= 85:
        return "match"
    if score >= 50:
        return "partial"
    return "mismatch"


def compute_overall_match(field_confidence: list[FieldConfidence]) -> tuple[int, int, int]:
  compared = [entry for entry in field_confidence if entry.status != "unknown"]
  if not compared:
      return 0, 0, len(field_confidence)
  weighted_sum = 0
  weight_total = 0
  for entry in compared:
      weight = FIELD_WEIGHTS.get(entry.field, 1)
      weighted_sum += entry.score * weight
      weight_total += weight
  score = int(round(weighted_sum / weight_total)) if weight_total else 0
  skipped = len(field_confidence) - len(compared)
  return score, len(compared), skipped


def compare_field(
    *,
    field: str,
    label: str,
    left: str | None,
    right: str | None,
    score: int,
    missing_left_reason: str = "not on vendor record",
    missing_right_reason: str = "not returned by source",
) -> FieldConfidence:
    left_display = left.strip() if left and left.strip() else None
    right_display = right.strip() if right and right.strip() else None
    if not left_display or not right_display:
        return FieldConfidence(
            field=field,
            label=label,
            score=0,
            status="unknown",
            leftDisplay=left_display,
            rightDisplay=right_display,
            skipReason=missing_left_reason if not left_display else missing_right_reason,
        )
    return FieldConfidence(
        field=field,
        label=label,
        score=score,
        status=status_from_score(score),
        leftDisplay=left_display,
        rightDisplay=right_display,
    )


def build_vendor_field_evidence(
    request: dict[str, Any],
    extracted: dict[str, Any],
) -> list[FieldConfidence]:
    address = request.get("address") or {}
    vendor_street = " ".join(
        part
        for part in [
            address.get("streetNumber"),
            address.get("streetName"),
            address.get("buildingName"),
        ]
        if part
    ).strip()

    trading_name_score = max(
        levenshtein_ratio(request.get("tradingName"), extracted.get("tradingName")),
        levenshtein_ratio(request.get("tradingName"), extracted.get("legalName")),
        levenshtein_ratio(request.get("legalName"), extracted.get("legalName")),
    )

    vendor_tax = " · ".join(request.get("taxIdentificationNumbers") or [])
    extracted_tax = extracted.get("taxIdentificationNumber") or extracted.get("taxId") or ""
    tax_score = _tax_match_score(vendor_tax, str(extracted_tax) if extracted_tax else "")

    city_score = max(
        levenshtein_ratio(address.get("cityName"), extracted.get("cityName")),
        token_overlap_score(address.get("cityName"), extracted.get("cityName")),
    )

    postal_score = (
        100
        if address.get("postalCode")
        and extracted.get("postalCode")
        and normalize_text(address.get("postalCode")) == normalize_text(extracted.get("postalCode"))
        else 0
    )

    country_score = (
        100
        if request.get("iso2CountryCode")
        and extracted.get("iso2CountryCode")
        and str(request.get("iso2CountryCode")).upper() == str(extracted.get("iso2CountryCode")).upper()
        else 0
    )

    return [
        compare_field(
            field="tradingName",
            label="Trading name",
            left=request.get("tradingName"),
            right=extracted.get("tradingName") or extracted.get("legalName"),
            score=trading_name_score,
        ),
        compare_field(
            field="tax",
            label="Tax ID",
            left=vendor_tax or None,
            right=str(extracted_tax) if extracted_tax else None,
            score=tax_score,
        ),
        compare_field(
            field="city",
            label="City",
            left=address.get("cityName"),
            right=extracted.get("cityName"),
            score=city_score,
        ),
        compare_field(
            field="street",
            label="Street",
            left=vendor_street or None,
            right=extracted.get("street"),
            score=token_overlap_score(vendor_street, extracted.get("street")),
        ),
        compare_field(
            field="postalCode",
            label="Postal code",
            left=address.get("postalCode"),
            right=extracted.get("postalCode"),
            score=postal_score,
        ),
        compare_field(
            field="country",
            label="Country",
            left=request.get("iso2CountryCode"),
            right=extracted.get("iso2CountryCode"),
            score=country_score,
        ),
    ]
