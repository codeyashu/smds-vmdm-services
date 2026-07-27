"""End-to-end extraction pipeline: OCR -> classify hint -> single LLM envelope call ->
cross-checks -> portal-shaped patches.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.core.config import get_settings
from app.core.logging import get_logger
from app.documents.classify.doctype import classify_by_anchors
from app.documents.extract.errors import ExtractionUnavailable, ExtractionUpstreamError
from app.documents.extract.prompts.india.envelope import build_envelope_messages, envelope_json_schema
from app.documents.extract.schemas.india import ENVELOPE_DOC_TYPES, ExtractionEnvelope
from app.documents.mapping.to_patches import Patch, patches_from_cheque, patches_from_gst, patches_from_pan
from app.documents.rules.crosscheck import CrossCheck, ExtractedIdentity, run_all
from app.providers.llm.base import LlmMessage
from app.providers.llm.factory import get_llm_provider
from app.providers.ocr.factory import get_ocr_provider

log = get_logger()


@dataclass
class ExtractResult:
    document_id: str
    doc_type: str
    doc_type_confidence: float
    patches: list[Patch] = field(default_factory=list)
    cross_checks: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unmapped: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "documentId": self.document_id,
            "docType": self.doc_type,
            "docTypeConfidence": self.doc_type_confidence,
            "patches": [p.as_dict() for p in self.patches],
            "crossChecks": self.cross_checks,
            "warnings": self.warnings,
            "unmapped": self.unmapped,
        }


async def _complete_envelope(llm, messages: list[LlmMessage], schema: dict, timeout_s: float) -> ExtractionEnvelope:
    raw = await llm.complete_json(messages, schema=schema, timeout_s=timeout_s)
    return ExtractionEnvelope(**raw)


async def _complete_envelope_with_retry(
    llm, messages: list[LlmMessage], schema: dict, timeout_s: float
) -> ExtractionEnvelope:
    try:
        return await _complete_envelope(llm, messages, schema, timeout_s)
    except (ValidationError, json.JSONDecodeError, TypeError) as exc:
        log.warning("extract.envelope_parse_retry", error=str(exc))
        retry_messages = [
            *messages,
            LlmMessage(
                role="user",
                text="Your previous response did not match the required JSON schema. "
                "Respond again with JSON only, matching the schema exactly.",
            ),
        ]
        try:
            return await _complete_envelope(llm, retry_messages, schema, timeout_s)
        except Exception as retry_exc:
            # Any failure on the retry — parse error or transport error alike — is terminal.
            raise ExtractionUpstreamError(
                "LLM response did not match the extraction schema after one retry."
            ) from retry_exc
    except Exception as exc:  # transport failure on the first attempt: timeout, connection, provider error
        raise ExtractionUpstreamError("LLM provider call failed.") from exc


def _identity_for(envelope: ExtractionEnvelope) -> ExtractedIdentity:
    return ExtractedIdentity(
        pan=envelope.pan.pan if envelope.pan else None,
        gstin=envelope.gst.gstin if envelope.gst else None,
        ifsc=envelope.cheque.ifsc if envelope.cheque else None,
        # No independently-sourced region code exists from a single-document extraction —
        # to_patches.py's own regionCode is itself derived FROM the GSTIN, so comparing it
        # here would be a self-referential no-op. Left None until a field genuinely comes
        # from elsewhere (e.g. a value already typed into the form).
        region_code=None,
        is_natural_person=None,
    )


def _patches_and_unmapped(envelope: ExtractionEnvelope) -> tuple[list[Patch], list[dict]]:
    patches: list[Patch] = []
    unmapped: list[dict] = []

    if envelope.pan is not None:
        patches.extend(patches_from_pan(envelope.pan))
    if envelope.gst is not None:
        patches.extend(patches_from_gst(envelope.gst))
    if envelope.cheque is not None:
        patches.extend(patches_from_cheque(envelope.cheque))
    if envelope.udyam is not None and envelope.udyam.udyam_number:
        # Tier 2 doctype — no ingest write target exists yet. Surfaced for reviewer
        # visibility only, never as an applyable patch.
        unmapped.append({"label": "Udyam number", "value": envelope.udyam.udyam_number})
    if envelope.coi is not None and envelope.coi.cin:
        unmapped.append({"label": "CIN", "value": envelope.coi.cin})

    return patches, unmapped


# Tax slots the PAN/GSTIN identity cross-checks can invalidate. to_patches.py promises
# `pre_selected` is never true for a value in a failing cross-check, but patches and checks are
# computed independently below — so the join happens here.
_IDENTITY_TAX_TYPE_CODES = frozenset({"TAXNO3", "TAXNO4"})  # PAN, GSTIN

# Checks whose failure implicates the PAN/GSTIN values themselves. `ifsc_shape` is excluded on
# purpose: a malformed IFSC says nothing about the PAN, and the IFSC patch is never pre-selected
# anyway (to_patches.patches_from_cheque hardcodes pre_selected=False pending bank-master lookup).
_IDENTITY_CHECK_IDS = frozenset({"gstin_contains_pan", "pan_shape", "gstin_shape"})


def _clear_pre_select_for_failed_identity_checks(patches: list[Patch], checks: list[CrossCheck]) -> None:
    """Mutate `patches` in place: drop pre-selection from the PAN/GSTIN patches when an identity
    cross-check failed. Deliberately narrow — patches those checks do not implicate (trading
    name, address, bank fields) keep whatever pre_selected verdict the mapping layer gave them.
    """
    failed = {c.id for c in checks if c.status == "fail"}
    if not failed & _IDENTITY_CHECK_IDS:
        return
    for patch in patches:
        if patch.tax_type_code in _IDENTITY_TAX_TYPE_CODES:
            patch.pre_selected = False


async def run_extraction(content: bytes, mime: str, country: str) -> ExtractResult:
    settings = get_settings()
    ocr = get_ocr_provider()
    llm = get_llm_provider()
    if ocr is None or llm is None:
        raise ExtractionUnavailable("No extraction backend available — configure an OCR and LLM provider.")

    document_id = f"eph_{uuid.uuid4().hex[:12]}"

    try:
        ocr_result = await ocr.run(content, mime)
    except Exception as exc:
        raise ExtractionUpstreamError("OCR provider failed.") from exc

    hint = classify_by_anchors(ocr_result.text)
    messages = build_envelope_messages(ocr_result.text, ocr_result.page_images_b64, hint)
    schema = envelope_json_schema()

    envelope = await _complete_envelope_with_retry(llm, messages, schema, settings.llm_timeout_s)

    if envelope.doc_type not in ENVELOPE_DOC_TYPES or envelope.doc_type == "UNKNOWN":
        log.info("extract.unknown_doc_type", document_id=document_id, ocr_provider=ocr_result.provider_id)
        return ExtractResult(
            document_id=document_id,
            doc_type="UNKNOWN",
            doc_type_confidence=envelope.doc_type_confidence,
            warnings=["Document type not recognised — enter fields manually."],
        )

    patches, unmapped = _patches_and_unmapped(envelope)
    checks = run_all(_identity_for(envelope))
    _clear_pre_select_for_failed_identity_checks(patches, checks)

    log.info(
        "extract.completed",
        document_id=document_id,
        doc_type=envelope.doc_type,
        ocr_provider=ocr_result.provider_id,
        llm_provider=llm.id,
        patch_count=len(patches),
    )

    return ExtractResult(
        document_id=document_id,
        doc_type=envelope.doc_type,
        doc_type_confidence=envelope.doc_type_confidence,
        patches=patches,
        cross_checks=[c.as_dict() for c in checks],
        unmapped=unmapped,
    )
