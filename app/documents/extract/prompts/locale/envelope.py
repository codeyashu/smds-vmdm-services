"""Single-pass classify + extract prompts for CN, AE, US, GB."""

from __future__ import annotations

from typing import Any

from app.documents.classify.doctype import Classification
from app.documents.extract.schemas.locale import (
    AeExtractionEnvelope,
    CnExtractionEnvelope,
    GbExtractionEnvelope,
    UsExtractionEnvelope,
)
from app.providers.llm.base import LlmMessage

_MAX_OCR_CHARS = 12000
_MAX_IMAGES = 5

_COUNTRY_DOC_TYPES: dict[str, str] = {
    "CN": """
- CN_BUSINESS_LICENSE: Chinese business license / 营业执照 (USCC, legal name, address)
- CN_BANK_ACCOUNT_PERMIT: bank account opening permit / 开户许可证
- UNKNOWN: unreadable or not one of the above
""".strip(),
    "AE": """
- AE_TRADE_LICENSE: UAE trade licence (Arabic + English zones when present)
- AE_VAT_CERTIFICATE: UAE VAT / TRN certificate
- UNKNOWN: unreadable or not one of the above
""".strip(),
    "US": """
- US_W9: IRS Form W-9 (EIN, legal name)
- US_VOIDED_CHECK: voided check or bank letter (routing + account number)
- US_CERTIFICATE_OF_GOOD_STANDING: state certificate of good standing
- UNKNOWN: unreadable or not one of the above
""".strip(),
    "GB": """
- GB_COMPANIES_HOUSE_CERTIFICATE: Companies House certificate (company number, legal name, address)
- GB_VAT_CERTIFICATE: HMRC VAT certificate
- UNKNOWN: unreadable or not one of the above
""".strip(),
}

_LOCALE_RULES: dict[str, str] = {
    "CN": """
For Chinese documents:
- Extract USCC as 18 Latin alphanumeric characters with checksum validity in mind.
- For legal_name and trading_name return LocaleNameField with:
  - native: verbatim Chinese from the document
  - romanized: transliteration only (do not translate proper nouns)
  - english: English text printed on the document when present
- Never auto-translate Chinese company names into invented English.
- Address fields in Chinese go in registered_address; keep native script in the address values.
""".strip(),
    "AE": """
For UAE documents:
- Trade licences are often bilingual. Extract Arabic into native and English zone text into english/romanized.
- TRN is always Latin digits.
- legal_name and trading_name use LocaleNameField with native Arabic when present.
- Read RTL layout carefully from images when OCR text order is unreliable.
""".strip(),
    "US": """
For US documents:
- EIN format XX-XXXXXXX.
- Names are English only.
""".strip(),
    "GB": """
For UK documents:
- Company number is 8 digits or 2 letters + 6 digits.
- VAT number starts with GB.
- Names and addresses are English only.
""".strip(),
}


def _envelope_model_for_country(country: str):
    return {
        "CN": CnExtractionEnvelope,
        "AE": AeExtractionEnvelope,
        "US": UsExtractionEnvelope,
        "GB": GbExtractionEnvelope,
    }[country.strip().upper()]


def build_locale_envelope_messages(
    country: str,
    ocr_text: str,
    page_images_b64: list[str],
    anchor_hint: Classification,
) -> list[LlmMessage]:
    country_code = country.strip().upper()
    doc_types = _COUNTRY_DOC_TYPES[country_code]
    locale_rules = _LOCALE_RULES[country_code]
    hint_line = (
        f"A keyword pass guessed doc_type={anchor_hint.doc_type or 'UNKNOWN'} "
        f"(confidence {anchor_hint.confidence:.2f}, ambiguous={anchor_hint.ambiguous}). "
        "Verify this against the document — correct it if wrong."
    )
    scan_note = ""
    if page_images_b64 and len(ocr_text.strip()) < 80:
        scan_note = (
            f"\n\nThis document is a scan with little embedded text. "
            f"{len(page_images_b64[:_MAX_IMAGES])} page image(s) are attached — treat images as primary."
        )
    system_prompt = f"""You classify and extract vendor onboarding documents for country {country_code} in one pass.

Step 1 — decide doc_type from:
{doc_types}

Step 2 — extract fields for that doc type into the matching response block only.
Leave fields null when not visible. Never invent identifiers.

{locale_rules}

Respond with JSON only, matching the provided schema exactly."""
    user_text = (
        f"{hint_line}\n\n"
        f"OCR text (may be incomplete for non-Latin scripts):\n"
        f"{ocr_text.strip() or '(no embedded text — read from attached images)'}"
        f"{scan_note}"
    )
    return [
        LlmMessage(role="system", text=system_prompt),
        LlmMessage(role="user", text=user_text, images_b64=page_images_b64[:_MAX_IMAGES]),
    ]


def locale_envelope_json_schema(country: str) -> dict[str, Any]:
    model = _envelope_model_for_country(country)
    return _make_strict(model.model_json_schema())


def _make_strict(node: Any) -> Any:
    if isinstance(node, list):
        return [_make_strict(item) for item in node]
    if not isinstance(node, dict):
        return node
    out = {key: _make_strict(value) for key, value in node.items()}
    if out.get("type") == "object" or "properties" in out:
        out["additionalProperties"] = False
        out["required"] = list(out.get("properties", {}).keys())
    return out
