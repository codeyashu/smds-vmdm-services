"""Deterministic tax-ID format validators (no live registry calls)."""

from __future__ import annotations

import re
from typing import Any

GSTIN_PATTERN = re.compile(
    r"^(?P<state>\d{2})(?P<pan>[A-Z]{5}\d{4}[A-Z])(?P<entity>[1-9A-Z])Z(?P<checksum>[0-9A-Z])$"
)
PAN_PATTERN = re.compile(r"^[A-Z]{5}\d{4}[A-Z]$")
GB_COMPANY_NUMBER_PATTERN = re.compile(r"^(?:\d{8}|[A-Z]{2}\d{6})$")

GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _gstin_checksum_valid(gstin: str) -> bool:
    factor = [1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2]
    total = 0
    for index in range(14):
        code = GSTIN_CHARS.index(gstin[index])
        weighted = code * factor[index]
        total += weighted // 36 + weighted % 36
    check = (36 - (total % 36)) % 36
    return gstin[14] == GSTIN_CHARS[check]


def validate_in_gstin(value: str) -> dict[str, Any] | None:
    normalized = value.strip().upper()
    if len(normalized) != 15:
        return None
    match = GSTIN_PATTERN.match(normalized)
    if not match:
        return None
    if normalized[13] != "Z":
        return None
    if not _gstin_checksum_valid(normalized):
        return None
    return {
        "taxIdentificationNumber": normalized,
        "panEmbedded": match.group("pan"),
        "stateCode": match.group("state"),
        "iso2CountryCode": "IN",
        "status": "format_valid",
    }


def validate_in_pan(value: str) -> dict[str, Any] | None:
    normalized = value.strip().upper()
    if not PAN_PATTERN.match(normalized):
        return None
    return {
        "taxIdentificationNumber": normalized,
        "iso2CountryCode": "IN",
        "status": "format_valid",
    }


def validate_gb_company_number(value: str) -> dict[str, Any] | None:
    normalized = value.strip().upper().replace(" ", "")
    if not GB_COMPANY_NUMBER_PATTERN.match(normalized):
        return None
    return {
        "taxIdentificationNumber": normalized,
        "iso2CountryCode": "GB",
        "status": "format_valid",
    }
