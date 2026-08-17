"""Bill-to (BILL_TO) address review — only billing address is verified."""

from __future__ import annotations

import re
from typing import Any

from app.web_trust.scoring import status_from_score
from app.web_trust.types import FieldConfidence

IN_POSTAL_PATTERN = re.compile(r"^\d{6}$")
GB_POSTAL_PATTERN = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$", re.IGNORECASE)

BILL_TO_PURPOSE = "BILL_TO"


def _join_street(address: dict[str, Any]) -> str:
    return " ".join(
        part
        for part in [
            address.get("streetNumber"),
            address.get("streetName"),
            address.get("buildingName"),
        ]
        if isinstance(part, str) and part.strip()
    ).strip()


def _presence_row(
    *,
    field: str,
    label: str,
    value: str | None,
    required: bool,
    right_ok: str,
    right_missing: str,
) -> FieldConfidence:
    display = value.strip() if value and value.strip() else None
    if not display:
        if not required:
            return FieldConfidence(
                field=field,
                label=label,
                score=0,
                status="unknown",
                leftDisplay=None,
                rightDisplay=None,
                skipReason="optional for bill-to review",
            )
        return FieldConfidence(
            field=field,
            label=label,
            score=0,
            status="mismatch",
            leftDisplay="—",
            rightDisplay=right_missing,
        )
    return FieldConfidence(
        field=field,
        label=label,
        score=100,
        status="match",
        leftDisplay=display,
        rightDisplay=right_ok,
    )


def _postal_row(address: dict[str, Any], country: str) -> FieldConfidence:
    postal = address.get("postalCode")
    display = postal.strip() if isinstance(postal, str) and postal.strip() else None
    if not display:
        return FieldConfidence(
            field="postalCode",
            label="Postal code",
            score=0,
            status="mismatch",
            leftDisplay="—",
            rightDisplay="Required for bill-to address",
        )

    if country == "IN":
        valid = bool(IN_POSTAL_PATTERN.match(display))
        return FieldConfidence(
            field="postalCode",
            label="Postal code",
            score=100 if valid else 40,
            status=status_from_score(100 if valid else 40),
            leftDisplay=display,
            rightDisplay="Valid 6-digit PIN" if valid else "Expected 6-digit India PIN",
        )

    if country == "GB":
        normalized = display.upper().replace("  ", " ")
        valid = bool(GB_POSTAL_PATTERN.match(normalized))
        return FieldConfidence(
            field="postalCode",
            label="Postal code",
            score=100 if valid else 50,
            status=status_from_score(100 if valid else 50),
            leftDisplay=display,
            rightDisplay="Valid UK postcode format" if valid else "Check UK postcode format",
        )

    return FieldConfidence(
        field="postalCode",
        label="Postal code",
        score=100,
        status="match",
        leftDisplay=display,
        rightDisplay="Present",
    )


def _country_row(address: dict[str, Any], country: str) -> FieldConfidence:
    entered = address.get("iso2CountryCode") or country
    entered_display = str(entered).upper() if entered else None
    expected = country.upper()
    if not entered_display:
        return FieldConfidence(
            field="country",
            label="Country",
            score=0,
            status="mismatch",
            leftDisplay="—",
            rightDisplay=f"Expected {expected}",
        )
    match = entered_display == expected
    return FieldConfidence(
        field="country",
        label="Country",
        score=100 if match else 0,
        status=status_from_score(100 if match else 0),
        leftDisplay=entered_display,
        rightDisplay=expected,
    )


def _gstin_state_row(tax_ids: list[str], country: str) -> FieldConfidence | None:
    if country != "IN":
        return None
    from app.web_trust.tax_validators import validate_in_gstin

    gstin = next((value for value in tax_ids if validate_in_gstin(value)), None)
    if not gstin:
        return FieldConfidence(
            field="gstinState",
            label="GSTIN state code",
            score=0,
            status="unknown",
            skipReason="no valid GSTIN on record — state cross-check skipped",
        )
    state_code = gstin[:2]
    return FieldConfidence(
        field="gstinState",
        label="GSTIN state code",
        score=100,
        status="match",
        leftDisplay=state_code,
        rightDisplay="Verify bill-to city/region aligns with this GSTIN state",
    )


def review_bill_to_address(
    address: dict[str, Any] | None,
    *,
    country: str,
    tax_ids: list[str],
) -> dict[str, Any]:
    """Review only the BILL_TO billing address — never ship-to or other purposes."""
    normalized_country = country.upper()
    address = address or {}
    purpose = str(address.get("contactAddressPurposeCode") or BILL_TO_PURPOSE).upper()
    limitations: list[str] = []

    if purpose != BILL_TO_PURPOSE:
        limitations.append(f"Address purpose is {purpose}; only BILL_TO is reviewed.")

    street = _join_street(address)
    field_evidence: list[FieldConfidence] = [
        _presence_row(
            field="street",
            label="Street",
            value=street or None,
            required=True,
            right_ok="Present",
            right_missing="Required for bill-to address",
        ),
        _presence_row(
            field="city",
            label="City",
            value=address.get("cityName") if isinstance(address.get("cityName"), str) else None,
            required=True,
            right_ok="Present",
            right_missing="Required for bill-to address",
        ),
        _postal_row(address, normalized_country),
        _country_row(address, normalized_country),
    ]

    gstin_row = _gstin_state_row(tax_ids, normalized_country)
    if gstin_row:
        field_evidence.append(gstin_row)

    compared = [row for row in field_evidence if row.status != "unknown"]
    completeness = (
        int(round(sum(row.score for row in compared) / len(compared))) if compared else 0
    )

    if not street:
        completeness = min(completeness, 65)
        if "Bill-to street is missing." not in limitations:
            limitations.append("Bill-to street is missing.")

    if completeness < 70 and not any(
        "incomplete" in note.lower() for note in limitations
    ):
        limitations.append("Bill-to address is incomplete or failed format checks.")

    if not street and not address.get("cityName"):
        limitations.append("No bill-to address content was supplied.")

    return {
        "purposeCode": BILL_TO_PURPOSE,
        "completenessScore": completeness,
        "fieldEvidence": field_evidence,
        "limitations": limitations,
        "extracted": {
            "street": street or None,
            "cityName": address.get("cityName"),
            "postalCode": address.get("postalCode"),
            "iso2CountryCode": address.get("iso2CountryCode") or normalized_country,
            "contactAddressPurposeCode": BILL_TO_PURPOSE,
            "status": "bill_to_review",
        },
    }
