"""Doc field -> portal form path, plus the portal IN ruleset regexes used as an advisory gate.

The portal form model (smds-vmdmportal) is the contract. Paths here MUST exist in that model:
- scalar top-level: `tradingName`, `legalName`
- primary postal address: `postalAddresses.0.<field>`
- tax slots: `taxInformation.taxIdentificationNumbers.<index>.taxIdentificationNumber`
  where index N corresponds to TAXNO{N+1} (positional, mirrored from the portal's
  `applyTaxSlotAssignments` in map-company-tax-slots.ts).

The regexes are copied from the live IN ruleset fixtures. They are advisory only.
"""

from __future__ import annotations

import re

# TAXNO{n} -> array index. TAXNO1 -> 0, TAXNO3 -> 2, TAXNO4 -> 3.
def tax_slot_index(tax_type_code: str) -> int:
    m = re.match(r"^TAXNO(\d+)$", tax_type_code, re.IGNORECASE)
    if not m:
        raise ValueError(f"Not a TAXNO slot: {tax_type_code!r}")
    return int(m.group(1)) - 1


def tax_number_path(tax_type_code: str) -> str:
    return f"taxInformation.taxIdentificationNumbers.{tax_slot_index(tax_type_code)}.taxIdentificationNumber"


# Address field name (as it appears on the portal primary postal address) -> full path.
ADDRESS_FIELDS = (
    "buildingName",
    "streetNumber",
    "streetName",
    "district",
    "cityName",  # resolved to cityCode client-side; sent as a hint
    "regionCode",
    "postalCode",
)


def address_path(field: str) -> str:
    return f"postalAddresses.0.{field}"


# Advisory regex gate, keyed by the portal ruleset fieldName. Copied from
# in-prospect-vendor.json. A proposed value that fails here is marked needs-review.
IN_FIELD_REGEX: dict[str, re.Pattern[str]] = {
    "tradingName": re.compile(r"^[a-zA-Z0-9.,:;$%&+\]\[*\"( )'\/^\-]{3,128}$"),
    "streetName": re.compile(r"^[a-zA-Z0-9.,:;$%&+\]\[*\"( )'\/^\-]{0,256}$"),
    "streetNumber": re.compile(r"^[a-zA-Z0-9.,:;$%&+\]\[*\"( )'\/^\-]{0,20}$"),
    "buildingName": re.compile(r"^[a-zA-Z0-9.,:;$%&+\]\[*\"( )'\/^\-]{0,36}$"),
    "district": re.compile(r"^[a-zA-Z0-9.,:;$%&+\]\[*\"( )'\/^\-]{0,36}$"),
    "cityCode": re.compile(r"^[a-zA-Z0-9&./]{1,13}$"),
    "regionCode": re.compile(r"^[a-zA-Z0-9 ]{1,15}$"),
    "postalCode": re.compile(r"^[0-9]{6}$"),
    # TAXNO3 = TIN/PAN (also accepts ZZ sentinel), TAXNO4 = GSTIN (four accepted shapes).
    "TAXNO3": re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$|^ZZ$"),
    "TAXNO4": re.compile(
        r"^\d{2}[a-zA-Z]{5}\d{4}[a-zA-Z]{1}.{3}$"
        r"|^\d{2}[A-Za-z]{4}\d{5}[A-Za-z]\d[A-Za-z]{2}$"
        r"|^\d{4}[a-zA-Z]{3}\d{5}[a-zA-Z]{2}\d$"
        r"|^\d{4}[A-Za-z]{3}\d{5}[A-Za-z]{3}$"
    ),
    "TEL": re.compile(r"^[1-9]{1}[0-9]{9}$"),
    "MOB": re.compile(r"^[1-9]{1}[0-9]{9}$"),
    "emailAddress": re.compile(r"^[a-zA-Z0-9+_.-]+@[a-zA-Z0-9.-]+$"),
    "industryClassificationCode": re.compile(r"^[A-Z0-9]{1,4}$"),
}

# Fields that are NOT applicable for IN and must never be proposed (plan §1.1).
IN_NOT_APPLICABLE = frozenset(
    {
        "TAXNO1",  # VAT — not in use for India
        "taxDeclarationTypeCode",
        "taxDeclarationRegimeCode",
        "taxJurisdictionCode",
        "internationalCharacterSetCode",
        "ibanNumber",  # not applicable on the IN bank ruleset
        "bankAccountControlKeyNumber",
    }
)


def passes_field_regex(field_name: str, value: str) -> bool:
    """True when no regex is known for the field, or the value matches it."""
    pattern = IN_FIELD_REGEX.get(field_name)
    return True if pattern is None else bool(pattern.match(value))
