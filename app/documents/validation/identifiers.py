"""Identifier validators — schwifty IBAN + India regex patterns."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.documents.rules.in_patterns import (
    GSTIN_ANY_RE,
    IFSC_RE,
    PAN_RE,
    normalize_identifier as normalize_in_id,
    pan_from_gstin,
)
from app.documents.rules.locale_patterns import (
    format_us_ein,
    is_valid_ae_trn,
    is_valid_gb_crn,
    is_valid_gb_vat,
    is_valid_us_ein,
    is_valid_uscc,
    normalize_ae_trn,
    normalize_gb_crn,
    normalize_gb_vat,
    normalize_us_ein,
    normalize_uscc,
)
from app.documents.validation.normalize import normalize_identifier


@dataclass(frozen=True)
class IdentifierValidation:
    ok: bool
    normalized: str
    message: str | None = None


def validate_pan(value: str) -> IdentifierValidation:
    v = normalize_in_id(value)
    if PAN_RE.match(v):
        return IdentifierValidation(True, v)
    return IdentifierValidation(False, v, "PAN must match LLLLLNNNNL.")


def validate_gstin(value: str) -> IdentifierValidation:
    v = normalize_in_id(value)
    if GSTIN_ANY_RE.match(v):
        return IdentifierValidation(True, v)
    return IdentifierValidation(False, v, "GSTIN shape not recognised.")


def validate_ifsc(value: str) -> IdentifierValidation:
    v = normalize_in_id(value)
    if IFSC_RE.match(v):
        return IdentifierValidation(True, v)
    return IdentifierValidation(False, v, "IFSC must be 4 letters, 0, then 6 alphanumerics.")


def validate_iban(value: str) -> IdentifierValidation:
    raw = re.sub(r"\s+", "", (value or "")).upper()
    if not raw:
        return IdentifierValidation(False, raw, "IBAN is empty.")
    try:
        from schwifty import IBAN

        iban = IBAN(raw)
        return IdentifierValidation(True, str(iban.compact))
    except ImportError:
        if re.match(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$", raw):
            return IdentifierValidation(True, raw)
        return IdentifierValidation(False, raw, "IBAN format invalid.")
    except Exception as exc:
        return IdentifierValidation(False, raw, str(exc))


def validate_uscc(value: str) -> IdentifierValidation:
    v = normalize_uscc(value)
    if is_valid_uscc(v):
        return IdentifierValidation(True, v)
    return IdentifierValidation(False, v, "USCC checksum or shape invalid.")


def validate_trn(value: str) -> IdentifierValidation:
    v = normalize_ae_trn(value)
    if is_valid_ae_trn(v):
        return IdentifierValidation(True, v)
    return IdentifierValidation(False, v, "UAE TRN must be 15 digits starting with 100.")


def validate_ein(value: str) -> IdentifierValidation:
    v = normalize_us_ein(value)
    if is_valid_us_ein(v):
        return IdentifierValidation(True, format_us_ein(v))
    return IdentifierValidation(False, v, "US EIN must be XX-XXXXXXX.")


def validate_gb_vat(value: str) -> IdentifierValidation:
    v = normalize_gb_vat(value)
    if is_valid_gb_vat(v):
        return IdentifierValidation(True, v)
    return IdentifierValidation(False, v, "GB VAT number shape not recognised.")


def validate_gb_crn(value: str) -> IdentifierValidation:
    v = normalize_gb_crn(value)
    if is_valid_gb_crn(v):
        return IdentifierValidation(True, v)
    return IdentifierValidation(False, v, "Companies House number shape not recognised.")


_VALIDATORS = {
    "pan": validate_pan,
    "gstin": validate_gstin,
    "ifsc": validate_ifsc,
    "iban": validate_iban,
    "uscc": validate_uscc,
    "trn": validate_trn,
    "ein": validate_ein,
    "gb_vat": validate_gb_vat,
    "gb_crn": validate_gb_crn,
}


def validate_identifier_kind(kind: str, value: str) -> IdentifierValidation:
    fn = _VALIDATORS.get(kind.strip().lower())
    if fn is None:
        v = normalize_identifier(value)
        return IdentifierValidation(True, v)
    return fn(value)


def embedded_pan_in_gstin(gstin: str) -> str | None:
    return pan_from_gstin(gstin)
