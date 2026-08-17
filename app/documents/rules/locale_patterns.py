"""Identifier patterns and validators for CN, AE, US, GB document extraction."""

from __future__ import annotations

import re

USCC_WEIGHTS = [1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28]
USCC_CHARS = "0123456789ABCDEFGHJKLMNPQRTUWXY"

USCC_RE = re.compile(r"^[0-9A-Z]{18}$")
AE_TRN_RE = re.compile(r"^100\d{12}$")
US_EIN_RE = re.compile(r"^\d{9}$")
GB_VAT_RE = re.compile(r"^GB(\d{9}|\d{12}|GD\d{3}|HA\d{3})$")
GB_CRN_RE = re.compile(r"^(\d{8}|[A-Z]{2}\d{6})$")


def normalize_uscc(value: str) -> str:
    return re.sub(r"\s+", "", (value or "")).upper()


def is_valid_uscc(value: str) -> bool:
    normalized = normalize_uscc(value)
    if not USCC_RE.match(normalized):
        return False
    if normalized[0] < "1" or normalized[0] > "9":
        return False
    total = 0
    for index, char in enumerate(normalized[:17]):
        code = USCC_CHARS.index(char)
        total += code * USCC_WEIGHTS[index]
    check = USCC_CHARS[(31 - (total % 31)) % 31]
    return normalized[17] == check


def normalize_ae_trn(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def is_valid_ae_trn(value: str) -> bool:
    return bool(AE_TRN_RE.match(normalize_ae_trn(value)))


def normalize_us_ein(value: str) -> str:
    return re.sub(r"[\s-]+", "", value or "")


def format_us_ein(value: str) -> str:
    normalized = normalize_us_ein(value)
    if not US_EIN_RE.match(normalized):
        return value.strip()
    prefix = int(normalized[:2])
    if prefix < 10 or prefix > 99:
        return value.strip()
    return f"{normalized[:2]}-{normalized[2:]}"


def is_valid_us_ein(value: str) -> bool:
    normalized = normalize_us_ein(value)
    if not US_EIN_RE.match(normalized):
        return False
    prefix = int(normalized[:2])
    return 10 <= prefix <= 99


def normalize_gb_vat(value: str) -> str:
    return re.sub(r"\s+", "", (value or "")).upper()


def is_valid_gb_vat(value: str) -> bool:
    return bool(GB_VAT_RE.match(normalize_gb_vat(value)))


def normalize_gb_crn(value: str) -> str:
    return re.sub(r"\s+", "", (value or "")).upper()


def is_valid_gb_crn(value: str) -> bool:
    return bool(GB_CRN_RE.match(normalize_gb_crn(value)))
