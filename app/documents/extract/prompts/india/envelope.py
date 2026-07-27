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
- IN_PAN_CARD: Indian Income Tax PAN card (10-char PAN, holder name)
- IN_GST_CERTIFICATE: GST registration certificate / Form REG-06 (GSTIN, trade name, legal name, address)
- IN_CANCELLED_CHEQUE: cancelled cheque, bank passbook page, or bank letter (account number, IFSC, bank name)
- IN_UDYAM_CERTIFICATE: Udyam / MSME registration certificate
- IN_CERTIFICATE_OF_INCORPORATION: MCA Certificate of Incorporation (CIN, company name)
- UNKNOWN: none of the above, or the document is unreadable
""".strip()

_SYSTEM_PROMPT = f"""You classify and extract data from Indian vendor-onboarding documents in one pass.

Step 1 — decide the document type from this list:
{_DOC_TYPE_DESCRIPTIONS}

Step 2 — extract every field you can read for that type into the matching block of the response.
Leave a field null if it is not visible or not legible — never guess or invent a value.
Populate the "pan" block too if a PAN is visible on a GST certificate, even when doc_type is IN_GST_CERTIFICATE.

Respond with JSON only, matching the provided schema exactly."""


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
    user_text = f"{hint_line}\n\nDocument text (OCR):\n{ocr_text[:_MAX_OCR_CHARS]}"
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
    return _make_strict(ExtractionEnvelope.model_json_schema())
