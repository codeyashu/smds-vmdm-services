"""Single prompt: classify AND extract in one LLM call.

The deterministic keyword classifier's guess is passed as a hint, not ground truth — the
model is instructed to verify it against the actual document content and correct it if wrong.
"""

from __future__ import annotations

from typing import Any

from app.documents.classify.doctype import Classification
from app.documents.extract.schemas.india import ExtractionEnvelope
from app.providers.llm.base import LlmMessage

_MAX_OCR_CHARS = 12000
_MAX_IMAGES = 5

_DOC_TYPE_DESCRIPTIONS = """
- IN_PAN_CARD: Indian Income Tax PAN card (10-char PAN, holder name). Includes sole-proprietor scans where Aadhaar appears on the same page — still IN_PAN_CARD, not IN_ADDRESS_PROOF.
- IN_GST_CERTIFICATE: GST registration certificate / Form REG-06 (GSTIN, trade name, legal name, address)
- IN_CANCELLED_CHEQUE: cancelled cheque, bank passbook page, or bank letter (account number, IFSC, bank name)
- IN_UDYAM_CERTIFICATE: Udyam / MSME registration certificate
- IN_CERTIFICATE_OF_INCORPORATION: MCA Certificate of Incorporation (CIN, company name)
- IN_ADDRESS_PROOF: address proof document (utility bill, rent agreement, bank statement). Not a PAN card even if an address is visible.
- IN_IEC_CERTIFICATE: Importer Exporter Code (IEC) certificate from DGFT — 10-character IEC code, not a PAN
- IN_DEED_OF_PARTNERSHIP: partnership deed or LLP agreement (firm name, registration number, address)
- IN_MTO_IATA_CHA_CERTIFICATE: MTO / IATA / Customs House Agent licence or certificate (not an IEC certificate)
- UNKNOWN: none of the above, or the document is unreadable
""".strip()

_SYSTEM_PROMPT = f"""You classify and extract data from Indian vendor-onboarding documents in one pass.

Step 1 — decide the document type from this list:
{_DOC_TYPE_DESCRIPTIONS}

Step 2 — extract every field you can read for that type into the matching block of the response.
Leave a field null if it is not visible or not legible — never guess or invent a value.
Only populate the "pan" block when doc_type is IN_PAN_CARD or IN_GST_CERTIFICATE (embedded PAN on a GST cert).
Never put an IEC code, licence number, or Aadhaar number into the "pan" block.
Populate the "iec" block only when doc_type is IN_IEC_CERTIFICATE.
Populate the "mto" block only when doc_type is IN_MTO_IATA_CHA_CERTIFICATE.

For ExtractedAddress on Indian documents, split multi-line addresses carefully:
- building_name: door/plot/building line (e.g. "D.NO.61B, 15")
- street_name: road name only (e.g. "VELAMPALAYAM MAIN ROAD")
- district: locality or taluk/district when printed as its own line (e.g. "ANUPPARPALAYAM", "Tiruppur")
- city_name: post town / city (e.g. "Avinashi") — not the district when both appear
- postal_code: 6-digit PIN only, no spaces

When page images are attached, read identifiers directly from the image — especially on scans where OCR text is empty or unreliable.
PAN, GSTIN, IEC, CIN, and licence numbers are often printed in small type; inspect the full image carefully.

Respond with JSON only, matching the provided schema exactly."""

_SCAN_OCR_CHAR_THRESHOLD = 80


def _is_scan_document(ocr_text: str, page_images_b64: list[str]) -> bool:
    return bool(page_images_b64) and len(ocr_text.strip()) < _SCAN_OCR_CHAR_THRESHOLD


def build_envelope_messages(
    ocr_text: str,
    page_images_b64: list[str],
    anchor_hint: Classification,
) -> list[LlmMessage]:
    hint_line = (
        f"A keyword pass guessed doc_type={anchor_hint.doc_type or 'UNKNOWN'} "
        f"(confidence {anchor_hint.confidence:.2f}, ambiguous={anchor_hint.ambiguous}). "
        "Verify this against the document — correct it if wrong."
    )
    scan_note = ""
    if _is_scan_document(ocr_text, page_images_b64):
        scan_note = (
            "\n\nThis document is a scan with little or no embedded text. "
            f"{len(page_images_b64[:_MAX_IMAGES])} page image(s) are attached — "
            "treat the images as the primary source and extract every visible identifier "
            "(PAN, GSTIN, IEC, CIN, names, addresses)."
        )
    ocr_section = ocr_text.strip() or "(no embedded text — read from attached images)"
    user_text = f"{hint_line}{scan_note}\n\nDocument text (OCR, may be incomplete):\n{ocr_section[:_MAX_OCR_CHARS]}"
    return [
        LlmMessage(role="system", text=_SYSTEM_PROMPT),
        LlmMessage(role="user", text=user_text, images_b64=page_images_b64[:_MAX_IMAGES]),
    ]


def build_vision_retry_messages(
    doc_type: str,
    missing_fields: list[str],
    page_images_b64: list[str],
) -> list[LlmMessage]:
    """Second pass when Azure OpenAI vision missed key identifiers on a scan."""
    fields = ", ".join(missing_fields)
    user_text = (
        f"You classified this document as {doc_type} but left these fields empty: {fields}.\n"
        "Read the attached page image(s) again and extract every visible value for those fields.\n"
        "On PAN cards the number is printed prominently (often labelled 'Permanent Account Number').\n"
        "Do not confuse IEC, Aadhaar, or licence numbers with PAN.\n"
        "PAN is exactly 10 characters (LLLLLNNNNL). GSTIN is 15 characters. IEC is 10 characters.\n"
        "Respond with the full JSON envelope matching the schema — keep doc_type unchanged."
    )
    return [
        LlmMessage(role="system", text=_SYSTEM_PROMPT),
        LlmMessage(role="user", text=user_text, images_b64=page_images_b64[:_MAX_IMAGES]),
    ]


def _make_strict(node: Any) -> Any:
    """Recursively rewrite a JSON schema into OpenAI structured-outputs `strict: true` form.

    Two requirements the spec imposes that pydantic's generated schema does not satisfy:
      1. every object schema carries `additionalProperties: false`;
      2. every object's `required` lists ALL of its declared properties.

    (2) is free here because every optional field on these models is generated as
    `anyOf: [{...}, {"type": "null"}]` — pydantic v2 expresses "optional" as *nullable*, not as
    "absent from required". So requiring the key while still permitting `null` keeps exactly the
    same set of accepted payloads. Returns new dicts; never mutates the input.
    """
    if isinstance(node, list):
        return [_make_strict(item) for item in node]
    if not isinstance(node, dict):
        return node

    out = {key: _make_strict(value) for key, value in node.items()}
    if out.get("type") == "object" or "properties" in out:
        out["additionalProperties"] = False
        out["required"] = list(out.get("properties", {}).keys())
    return out


def envelope_json_schema() -> dict:
    """The envelope schema, post-processed so it is valid for `strict: true` structured outputs.

    `app/providers/llm/openai_compatible.py` sends this with `"strict": True`; a schema that is
    not strict-compatible is rejected by OpenAI/Azure OpenAI with a 400 before the model runs.
    """
    return strict_json_schema(ExtractionEnvelope)


def strict_json_schema(model: type) -> dict:
    """Post-process a pydantic model schema for OpenAI/Azure `strict: true` structured outputs."""
    return _make_strict(model.model_json_schema())
