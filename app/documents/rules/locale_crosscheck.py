"""Locale cross-checks for CN, AE, US, GB."""

from __future__ import annotations

from app.documents.rules.crosscheck import CrossCheck
from app.documents.rules.locale_patterns import (
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


def _shape_check(check_id: str, label: str, value: str | None, validator) -> CrossCheck:
    if not value or not str(value).strip():
        return CrossCheck(check_id, "skip")
    if validator(str(value)):
        return CrossCheck(check_id, "pass")
    return CrossCheck(check_id, "fail", f"{label} shape or checksum invalid.")


def run_locale_crosschecks(country: str, patches: list) -> list[CrossCheck]:
    country_code = country.strip().upper()
    by_path = {patch.path: patch for patch in patches}
    checks: list[CrossCheck] = []

    def tax_value() -> str | None:
        for patch in patches:
            if patch.path.endswith("taxIdentificationNumber"):
                return str(patch.value)
        return None

    if country_code == "CN":
        uscc = tax_value()
        checks.append(_shape_check("uscc_checksum", "USCC", uscc, is_valid_uscc))
    elif country_code == "AE":
        trn = tax_value()
        checks.append(_shape_check("ae_trn_shape", "TRN", trn, is_valid_ae_trn))
    elif country_code == "US":
        ein = tax_value()
        checks.append(_shape_check("us_ein_shape", "EIN", ein, is_valid_us_ein))
    elif country_code == "GB":
        vat = tax_value()
        checks.append(_shape_check("gb_vat_shape", "VAT number", vat, is_valid_gb_vat))
        company = None
        for patch in patches:
            if patch.path == "_unmapped.companyNumber":
                company = str(patch.value)
        checks.append(_shape_check("gb_crn_shape", "Company number", company, is_valid_gb_crn))

    return checks
