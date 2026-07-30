"""VMDM reference context injected into the NL-search LLM system prompt."""

from __future__ import annotations

from pydantic import BaseModel, Field

DEFAULT_ALTERNATIVE_CODE_TYPES: list[tuple[str, str]] = [
    ("SMDS_VNDR_CD", "SMDS Vendor Code"),
    ("S4_BP_VNDR_CD", "S4 MDG BP Code"),
    ("FACT_BP_VNDR_CD", "FACT Vendor Code"),
]

DEFAULT_VENDOR_STATUSES: list[str] = [
    "ACTIVE",
    "INACTIVE",
    "SUSPENDED",
    "PENDING",
    "REJECTED",
]


class AlternativeCodeTypeItem(BaseModel):
    code: str
    name: str


class NlSearchParseContext(BaseModel):
    alternativeCodeTypes: list[AlternativeCodeTypeItem] = Field(default_factory=list)
    vendorStatuses: list[str] = Field(default_factory=list)


def _format_alternative_code_types(context: NlSearchParseContext | None) -> str:
    items = (
        [(item.code, item.name) for item in context.alternativeCodeTypes]
        if context and context.alternativeCodeTypes
        else DEFAULT_ALTERNATIVE_CODE_TYPES
    )
    return "\n".join(f"- {code}: {name}" for code, name in items)


def _format_vendor_statuses(context: NlSearchParseContext | None) -> str:
    statuses = (
        context.vendorStatuses
        if context and context.vendorStatuses
        else DEFAULT_VENDOR_STATUSES
    )
    return ", ".join(statuses)


def build_system_prompt(context: NlSearchParseContext | None = None) -> str:
    alternative_code_types = _format_alternative_code_types(context)
    vendor_statuses = _format_vendor_statuses(context)

    return f"""You convert vendor master data search requests into JSON for the Maersk Vendor Search API.

Return ONLY valid JSON with this shape:
{{
  "intent": "code_lookup" | "attribute_search",
  "code": "optional vendor or alternative code",
  "codeType": "optional alternative code type code — must be an exact value from the list below",
  "tradingName": "optional min 3 chars",
  "country": "optional ISO2 like IN",
  "taxId": "optional tax identification number",
  "cityName": "optional",
  "streetName": "optional",
  "postalCode": "optional",
  "vendorStatus": "optional one of: {vendor_statuses}",
  "hasDraft": "optional boolean — true when user wants vendors with unpublished draft",
  "inWorkflow": "optional boolean — true when user wants vendors in approval workflow",
  "accountType": "optional EXTERNAL or INTERNAL",
  "tradingPartnerCode": "optional",
  "summary": "short human-readable interpretation"
}}

Vendor master data rules:
- SMDS vendor codes look like IN000070343 (ISO2 country prefix + digits).
- Numeric alternative codes are zero-padded to 10 digits in the system (e.g. 10562 -> 0000010562, 4256911 -> 0004256911).
- Use code_lookup when the user gives a specific vendor code or alternative ERP code.
- Use attribute_search for trading name, tax ID, address, country, or status filters.
- taxId is NEVER a vendor code — do not use code_lookup for tax IDs like AAPCS9575E.
- codeType must be one of these exact alternative code type codes (never invent aliases like SMDS or SAP):
{alternative_code_types}
- When user says "SMDS vendor code" or "SMDS code", use codeType SMDS_VNDR_CD.
- When user says "SAP MDG BP" or "MDG BP code", use codeType S4_BP_VNDR_CD.
- country must be ISO 3166-1 alpha-2 when present.
- Prefer attribute_search for name/location/tax queries unless a specific code is clearly requested.
- summary is required."""
