"""Third-pass focused extraction — narrow schema + vision prompt per doc type.

After the full envelope call and a full-envelope vision retry, run one micro-extract per
document type when critical identifiers are still missing. Smaller JSON schema helps Azure
OpenAI vision read small printed numbers on scans (PAN, GSTIN, IEC, IFSC, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.documents.extract.prompts.india.envelope import strict_json_schema
from app.documents.extract.schemas.india import (
    AddressProofExtraction,
    ChequeExtraction,
    CoiExtraction,
    ExtractionEnvelope,
    ExtractedAddress,
    GstExtraction,
    IecExtraction,
    MtoExtraction,
    PanExtraction,
    PartnershipExtraction,
    UdyamExtraction,
)
from app.providers.llm.base import LlmMessage
from app.providers.ocr.render import vision_focus_images_b64
from app.documents.rules.in_patterns import PAN_RE, normalize_identifier

log = get_logger()

_MAX_IMAGES = 5

_SYSTEM = (
    "You extract structured data from a scanned Indian vendor document image. "
    "Read only what is visibly printed — never guess. Respond with JSON matching the schema."
)

_PAN_ONLY_SYSTEM = (
    "You read Indian PAN cards from document images. "
    "Return only the 10-character Permanent Account Number (format LLLLLNNNNL). "
    "Ignore Aadhaar numbers (12 digits), VID, enrolment numbers, and IEC codes."
)


class PanNumberOnly(BaseModel):
    pan: str | None = Field(default=None, description="10-char PAN, LLLLLNNNNL")
    confidence: float = 0.0


@dataclass(frozen=True)
class FocusedSpec:
    block_attr: str
    model: type[BaseModel]
    label: str
    field_hints: str
    is_incomplete: Callable[[ExtractionEnvelope], bool]


def _address_sparse(addr: ExtractedAddress | None) -> bool:
    if addr is None:
        return True
    return not any(
        [
            addr.postal_code,
            addr.city_name,
            addr.street_name,
            addr.building_name,
        ]
    )


FOCUSED_SPECS: dict[str, FocusedSpec] = {
    "IN_PAN_CARD": FocusedSpec(
        block_attr="pan",
        model=PanExtraction,
        label="PAN card",
        field_hints=(
            "Extract the 10-character Permanent Account Number (format LLLLLNNNNL). "
            "On sole-proprietor scans Aadhaar may appear on the same page — never use Aadhaar, "
            "IEC, or licence numbers as PAN."
        ),
        is_incomplete=lambda e: not e.pan or not e.pan.pan,
    ),
    "IN_GST_CERTIFICATE": FocusedSpec(
        block_attr="gst",
        model=GstExtraction,
        label="GST registration certificate",
        field_hints="Extract the 15-character GSTIN, legal name, trade name, principal place of business, and all additional places of business listed on the certificate.",
        is_incomplete=lambda e: not e.gst or not e.gst.gstin,
    ),
    "IN_IEC_CERTIFICATE": FocusedSpec(
        block_attr="iec",
        model=IecExtraction,
        label="IEC certificate",
        field_hints="Extract the 10-character Importer Exporter Code from DGFT. This is not a PAN.",
        is_incomplete=lambda e: not e.iec or not e.iec.iec_code,
    ),
    "IN_CERTIFICATE_OF_INCORPORATION": FocusedSpec(
        block_attr="coi",
        model=CoiExtraction,
        label="Certificate of Incorporation",
        field_hints="Extract the 21-character CIN and the registered company name.",
        is_incomplete=lambda e: not e.coi or not e.coi.cin,
    ),
    "IN_MTO_IATA_CHA_CERTIFICATE": FocusedSpec(
        block_attr="mto",
        model=MtoExtraction,
        label="MTO / IATA / CHA licence",
        field_hints="Extract the MTO, IATA, or Customs House Agent licence number.",
        is_incomplete=lambda e: not e.mto or not e.mto.licence_number,
    ),
    "IN_CANCELLED_CHEQUE": FocusedSpec(
        block_attr="cheque",
        model=ChequeExtraction,
        label="cancelled cheque or bank document",
        field_hints="Extract account number, IFSC, bank name, and account holder name.",
        is_incomplete=lambda e: not e.cheque or (not e.cheque.ifsc and not e.cheque.account_number),
    ),
    "IN_DEED_OF_PARTNERSHIP": FocusedSpec(
        block_attr="partnership",
        model=PartnershipExtraction,
        label="partnership deed",
        field_hints="Extract firm name, registration number, and registered address.",
        is_incomplete=lambda e: not e.partnership
        or (not e.partnership.firm_name and not e.partnership.registration_number),
    ),
    "IN_UDYAM_CERTIFICATE": FocusedSpec(
        block_attr="udyam",
        model=UdyamExtraction,
        label="Udyam / MSME certificate",
        field_hints="Extract Udyam registration number (UDYAM-XX-NN-NNNNNNN) and enterprise name.",
        is_incomplete=lambda e: not e.udyam or not e.udyam.udyam_number,
    ),
    "IN_ADDRESS_PROOF": FocusedSpec(
        block_attr="address_proof",
        model=AddressProofExtraction,
        label="address proof",
        field_hints=(
            "Extract holder name and full Indian postal address. "
            "building_name = door/plot/building line; street_name = road name only; "
            "district = locality/taluk line when present; city_name = post town/city line "
            "(e.g. Avinashi, not Tiruppur when both appear); postal_code = 6-digit PIN without spaces."
        ),
        is_incomplete=lambda e: not e.address_proof
        or not e.address_proof.holder_name
        or _address_sparse(e.address_proof.address),
    ),
}


def missing_critical_fields(envelope: ExtractionEnvelope) -> list[str]:
    spec = FOCUSED_SPECS.get(envelope.doc_type)
    if spec is None or not spec.is_incomplete(envelope):
        return []
    return [spec.label]


def _merge_models(existing: BaseModel | None, focused: BaseModel) -> BaseModel:
    if existing is None:
        return focused
    updates: dict[str, Any] = {}
    for field_name in type(existing).model_fields:
        new_val = getattr(focused, field_name)
        old_val = getattr(existing, field_name)
        if isinstance(new_val, BaseModel) and isinstance(old_val, BaseModel):
            updates[field_name] = _merge_models(old_val, new_val)
        elif isinstance(new_val, BaseModel):
            updates[field_name] = new_val if old_val is None else _merge_models(old_val, new_val)
        elif new_val is None or new_val == "" or new_val == []:
            updates[field_name] = old_val
        elif old_val is None or old_val == "" or old_val == []:
            updates[field_name] = new_val
        elif field_name == "confidence":
            updates[field_name] = max(float(old_val or 0), float(new_val or 0))
        else:
            updates[field_name] = old_val
    return existing.model_copy(update=updates)


def merge_envelopes(primary: ExtractionEnvelope, secondary: ExtractionEnvelope) -> ExtractionEnvelope:
    """Keep doc_type from primary; fill null block fields from secondary."""
    updates: dict[str, Any] = {}
    for spec in FOCUSED_SPECS.values():
        attr = spec.block_attr
        primary_block = getattr(primary, attr)
        secondary_block = getattr(secondary, attr)
        if secondary_block is None:
            continue
        merged = _merge_models(primary_block, secondary_block)
        if merged != primary_block:
            updates[attr] = merged
    if not updates:
        return primary
    return primary.model_copy(update=updates)


def build_focused_messages(
    doc_type: str,
    spec: FocusedSpec,
    page_images_b64: list[str],
) -> list[LlmMessage]:
    user_text = (
        f"This is a scanned {spec.label} ({doc_type}).\n"
        f"{spec.field_hints}\n"
        "Read the attached page image(s) carefully and return every field you can see."
    )
    return [
        LlmMessage(role="system", text=_SYSTEM),
        LlmMessage(role="user", text=user_text, images_b64=page_images_b64[:_MAX_IMAGES]),
    ]


async def _run_focused_call(
    llm,
    envelope: ExtractionEnvelope,
    spec: FocusedSpec,
    page_images_b64: list[str],
    timeout_s: float,
) -> ExtractionEnvelope:
    messages = build_focused_messages(envelope.doc_type, spec, page_images_b64)
    schema = strict_json_schema(spec.model)
    try:
        raw = await llm.complete_json(messages, schema=schema, timeout_s=timeout_s, trace_name="extract.focused")
        focused_block = spec.model(**raw)
    except Exception as exc:
        log.warning("extract.focused_failed", doc_type=envelope.doc_type, error=str(exc))
        return envelope

    existing = getattr(envelope, spec.block_attr)
    merged_block = _merge_models(existing, focused_block)
    if merged_block == existing:
        return envelope
    return envelope.model_copy(update={spec.block_attr: merged_block})


async def apply_pan_number_boost(
    llm,
    envelope: ExtractionEnvelope,
    page_images_b64: list[str],
    timeout_s: float,
    *,
    content: bytes | None = None,
    mime: str | None = None,
    filename: str | None = None,
) -> ExtractionEnvelope:
    """Fourth pass: PAN-only schema on high-DPI crops for composite PAN+Aadhaar scans."""
    if envelope.doc_type != "IN_PAN_CARD" or (envelope.pan and envelope.pan.pan):
        return envelope
    if not page_images_b64 and not content:
        return envelope
    if not getattr(llm, "supports_vision", True):
        return envelope

    images = vision_focus_images_b64(
        content or b"",
        mime or "application/pdf",
        doc_type=envelope.doc_type,
        filename=filename,
        base_images=page_images_b64,
    )
    if not images:
        return envelope

    log.info("extract.pan_only_boost", llm_provider=llm.id, image_count=len(images))
    user_text = (
        "These images are from a composite PAN + Aadhaar scan. "
        "One crop may be the PAN card. Extract ONLY the 10-character Permanent Account Number."
    )
    messages = [
        LlmMessage(role="system", text=_PAN_ONLY_SYSTEM),
        LlmMessage(role="user", text=user_text, images_b64=images[:_MAX_IMAGES]),
    ]
    try:
        raw = await llm.complete_json(
            messages,
            schema=strict_json_schema(PanNumberOnly),
            timeout_s=timeout_s,
            trace_name="extract.pan_only",
        )
        candidate = normalize_identifier(raw.get("pan") or "")
    except Exception as exc:
        log.warning("extract.pan_only_boost_failed", error=str(exc))
        return envelope

    if not PAN_RE.match(candidate):
        return envelope

    existing = envelope.pan or PanExtraction()
    merged = _merge_models(
        existing,
        PanExtraction(pan=candidate, confidence=float(raw.get("confidence") or 0.9)),
    )
    return envelope.model_copy(update={"pan": merged})


async def apply_focused_extractions(
    llm,
    envelope: ExtractionEnvelope,
    page_images_b64: list[str],
    timeout_s: float,
    *,
    content: bytes | None = None,
    mime: str | None = None,
    filename: str | None = None,
) -> ExtractionEnvelope:
    """Run a narrow-schema vision call when critical fields are still missing."""
    if not page_images_b64 and not content:
        return envelope
    if not getattr(llm, "supports_vision", True):
        return envelope

    spec = FOCUSED_SPECS.get(envelope.doc_type)
    if spec is None or not spec.is_incomplete(envelope):
        return envelope

    images = vision_focus_images_b64(
        content or b"",
        mime or "application/pdf",
        doc_type=envelope.doc_type,
        filename=filename,
        base_images=page_images_b64,
    )
    if not images:
        return envelope

    log.info(
        "extract.focused",
        doc_type=envelope.doc_type,
        block=spec.block_attr,
        llm_provider=llm.id,
        image_count=len(images),
    )
    envelope = await _run_focused_call(llm, envelope, spec, images, timeout_s)
    if envelope.doc_type == "IN_PAN_CARD" and (not envelope.pan or not envelope.pan.pan):
        envelope = await apply_pan_number_boost(
            llm,
            envelope,
            page_images_b64,
            timeout_s,
            content=content,
            mime=mime,
            filename=filename,
        )
    return envelope
