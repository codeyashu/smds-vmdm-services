"""Country-routed extraction pipeline for CN, AE, US, GB."""

from __future__ import annotations

import json
import uuid
from typing import Any

from pydantic import ValidationError

from app.core.config import get_settings
from app.core.logging import get_logger
from app.documents.classify.country_guard import doc_type_matches_country
from app.documents.classify.locale import classify_by_anchors_for_country, resolve_filename_hint_for_country
from app.documents.extract.errors import ExtractionUnavailable, ExtractionUpstreamError
from app.documents.extract.pipeline import ExtractResult
from app.documents.extract.prompts.locale.envelope import (
    build_locale_envelope_messages,
    locale_envelope_json_schema,
)
from app.documents.extract.schemas.locale import (
    AE_ENVELOPE_DOC_TYPES,
    CN_ENVELOPE_DOC_TYPES,
    GB_ENVELOPE_DOC_TYPES,
    US_ENVELOPE_DOC_TYPES,
    AeExtractionEnvelope,
    CnExtractionEnvelope,
    GbExtractionEnvelope,
    UsExtractionEnvelope,
)
from app.documents.mapping.locale_patches import (
    patches_from_ae_envelope,
    patches_from_cn_envelope,
    patches_from_gb_envelope,
    patches_from_us_envelope,
)
from app.documents.mapping.to_patches import Patch
from app.documents.rules.locale_crosscheck import run_locale_crosschecks
from app.providers.llm.base import LlmMessage
from app.providers.llm.factory import get_llm_provider
from app.providers.ocr.factory import get_ocr_provider

log = get_logger()

_ENVELOPE_TYPES = {
    "CN": (CnExtractionEnvelope, CN_ENVELOPE_DOC_TYPES, patches_from_cn_envelope),
    "AE": (AeExtractionEnvelope, AE_ENVELOPE_DOC_TYPES, patches_from_ae_envelope),
    "US": (UsExtractionEnvelope, US_ENVELOPE_DOC_TYPES, patches_from_us_envelope),
    "GB": (GbExtractionEnvelope, GB_ENVELOPE_DOC_TYPES, patches_from_gb_envelope),
}

_IDENTITY_CHECK_IDS = frozenset(
    {"uscc_checksum", "ae_trn_shape", "us_ein_shape", "gb_vat_shape", "gb_crn_shape"}
)
_IDENTITY_TAX_TYPE_CODES = frozenset({"TAXNO1"})


def _clear_pre_select_for_failed_identity_checks(patches: list[Patch], checks: list) -> None:
    failed = {check.id for check in checks if check.status == "fail"}
    if not failed & _IDENTITY_CHECK_IDS:
        return
    for patch in patches:
        if patch.tax_type_code in _IDENTITY_TAX_TYPE_CODES or patch.path.startswith("_unmapped."):
            patch.pre_selected = False


async def _complete_envelope(llm, messages: list[LlmMessage], schema: dict, timeout_s: float, model_cls):
    raw = await llm.complete_json(messages, schema=schema, timeout_s=timeout_s, trace_name="extract.locale_envelope")
    return model_cls(**raw)


async def run_locale_extraction(
    content: bytes,
    mime: str,
    country: str,
    doc_type_hint: str | None = None,
    filename: str | None = None,
) -> ExtractResult:
    country_code = country.strip().upper()
    model_cls, allowed_types, patch_mapper = _ENVELOPE_TYPES[country_code]
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

    hint = classify_by_anchors_for_country(ocr_result.text, country_code)
    filename_type = resolve_filename_hint_for_country(filename, country_code)
    if filename_type:
        from app.documents.classify.doctype import Classification

        hint = Classification(filename_type, max(hint.confidence, 0.8), ambiguous=False)
    if doc_type_hint and doc_type_hint.strip().upper().startswith(f"{country_code}_"):
        from app.documents.classify.doctype import Classification

        hint = Classification(doc_type_hint.strip().upper(), max(hint.confidence, 0.85), ambiguous=False)

    messages = build_locale_envelope_messages(country_code, ocr_result.text, ocr_result.page_images_b64, hint)
    schema = locale_envelope_json_schema(country_code)

    try:
        envelope = await _complete_envelope(llm, messages, schema, settings.llm_timeout_s, model_cls)
    except (ValidationError, json.JSONDecodeError, TypeError) as exc:
        log.warning("extract.locale_envelope_parse_failed", country=country_code, error=str(exc))
        return ExtractResult(
            document_id=document_id,
            doc_type="UNKNOWN",
            doc_type_confidence=0.0,
            warnings=["Could not parse extraction response — enter fields manually."],
        )

    if envelope.doc_type not in allowed_types or envelope.doc_type == "UNKNOWN":
        return ExtractResult(
            document_id=document_id,
            doc_type="UNKNOWN",
            doc_type_confidence=envelope.doc_type_confidence,
            warnings=["Document type not recognised — enter fields manually."],
        )

    if not doc_type_matches_country(country_code, envelope.doc_type):
        return ExtractResult(
            document_id=document_id,
            doc_type="UNKNOWN",
            doc_type_confidence=envelope.doc_type_confidence,
            warnings=[f"Document type {envelope.doc_type} does not apply to country {country_code}."],
        )

    patches, unmapped = patch_mapper(envelope)
    checks = run_locale_crosschecks(country_code, patches)
    _clear_pre_select_for_failed_identity_checks(patches, checks)

    log.info(
        "extract.locale_completed",
        document_id=document_id,
        country=country_code,
        doc_type=envelope.doc_type,
        patch_count=len(patches),
    )

    return ExtractResult(
        document_id=document_id,
        doc_type=envelope.doc_type,
        doc_type_confidence=envelope.doc_type_confidence,
        patches=patches,
        cross_checks=[check.as_dict() for check in checks],
        warnings=[],
        unmapped=unmapped,
        page_images_b64=ocr_result.page_images_b64,
    )
