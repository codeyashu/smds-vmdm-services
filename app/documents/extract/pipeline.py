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
from app.documents.classify.country_guard import doc_type_matches_country
from app.documents.classify.doctype import (
    classify_by_anchors,
    classify_by_filename,
    extract_aadhaar_number,
    is_aadhaar_only_document,
    resolve_filename_hint,
    Classification,
)
from app.documents.extract.errors import ExtractionUnavailable, ExtractionUpstreamError
from app.documents.extract.focused import (
    apply_focused_extractions,
    merge_envelopes,
    missing_critical_fields,
)
from app.documents.extract.prompts.india.envelope import (
    build_envelope_messages,
    build_vision_retry_messages,
    envelope_json_schema,
)
from app.documents.extract.schemas.india import (
    ENVELOPE_DOC_TYPES,
    CoiExtraction,
    ExtractionEnvelope,
    MtoExtraction,
    PanExtraction,
    PartnershipExtraction,
)
from app.documents.rules.in_patterns import PAN_RE, normalize_identifier
from app.documents.mapping.address_candidates import collect_address_candidates_from_envelope
from app.documents.mapping.to_patches import (
    Patch,
    patches_from_address_proof,
    patches_from_cheque,
    patches_from_coi,
    patches_from_gst,
    patches_from_iec,
    patches_from_mto,
    patches_from_pan,
    patches_from_partnership,
)
from app.documents.rules.crosscheck import CrossCheck, ExtractedIdentity, run_all
from app.providers.llm.base import LlmMessage
from app.providers.llm.factory import get_llm_provider
from app.providers.ocr.factory import get_ocr_provider

log = get_logger()

_DOC_TYPES_ALLOWING_PAN = frozenset({"IN_PAN_CARD", "IN_GST_CERTIFICATE"})
_DOC_TYPES_ALLOWING_GST = frozenset({"IN_GST_CERTIFICATE"})
_DOC_TYPES_ALLOWING_CHEQUE = frozenset({"IN_CANCELLED_CHEQUE"})
_DOC_TYPES_ALLOWING_COI = frozenset({"IN_CERTIFICATE_OF_INCORPORATION"})
_DOC_TYPES_ALLOWING_ADDRESS_PROOF = frozenset({"IN_ADDRESS_PROOF"})
_DOC_TYPES_ALLOWING_IEC = frozenset({"IN_IEC_CERTIFICATE"})
_DOC_TYPES_ALLOWING_PARTNERSHIP = frozenset({"IN_DEED_OF_PARTNERSHIP"})
_DOC_TYPES_ALLOWING_MTO = frozenset({"IN_MTO_IATA_CHA_CERTIFICATE"})


@dataclass
class ExtractResult:
    document_id: str
    doc_type: str
    doc_type_confidence: float
    patches: list[Patch] = field(default_factory=list)
    cross_checks: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unmapped: list[dict] = field(default_factory=list)
    address_candidates: list[dict] = field(default_factory=list)
    effective_date: str | None = None
    # Base64 PNGs per page, already rendered for the vision LLM pass (render_page_images_b64).
    # Reused here instead of re-rendered — as_dict() only ships the pages evidence points at.
    page_images_b64: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        out = {
            "documentId": self.document_id,
            "docType": self.doc_type,
            "docTypeConfidence": self.doc_type_confidence,
            "patches": [p.as_dict() for p in self.patches],
            "crossChecks": self.cross_checks,
            "warnings": self.warnings,
            "unmapped": self.unmapped,
            "addressCandidates": self.address_candidates,
        }
        if self.effective_date:
            out["effectiveDate"] = self.effective_date
        page_images = self._referenced_page_images()
        if page_images:
            out["pageImages"] = page_images
        return out

    def _referenced_page_images(self) -> dict[str, str]:
        pages: set[int] = set()
        for patch in self.patches:
            if patch.evidence and patch.evidence.page:
                pages.add(patch.evidence.page)
        for candidate in self.address_candidates:
            evidence = candidate.get("evidence") if isinstance(candidate, dict) else None
            page = evidence.get("page") if isinstance(evidence, dict) else None
            if page:
                pages.add(page)
        images: dict[str, str] = {}
        for page in sorted(pages)[:5]:
            index = page - 1
            if 0 <= index < len(self.page_images_b64):
                images[str(page)] = self.page_images_b64[index]
        return images


async def _complete_envelope(llm, messages: list[LlmMessage], schema: dict, timeout_s: float) -> ExtractionEnvelope:
    raw = await llm.complete_json(messages, schema=schema, timeout_s=timeout_s, trace_name="extract.envelope")
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


def _salvage_blocks_for_doc_type(envelope: ExtractionEnvelope) -> ExtractionEnvelope:
    """When filename override changes doc_type, remap fields the LLM put in the wrong block."""
    updates: dict = {}
    doc_type = envelope.doc_type

    if doc_type == "IN_MTO_IATA_CHA_CERTIFICATE" and envelope.mto is None and envelope.iec and envelope.iec.iec_code:
        updates["mto"] = MtoExtraction(
            licence_number=envelope.iec.iec_code,
            holder_name=envelope.iec.holder_name,
            confidence=envelope.iec.confidence,
        )

    if doc_type == "IN_PAN_CARD" and envelope.pan is None:
        pan_val = None
        holder = None
        confidence = 0.0
        if envelope.address_proof and envelope.address_proof.holder_name:
            holder = envelope.address_proof.holder_name
            confidence = envelope.address_proof.confidence
        if envelope.iec and envelope.iec.iec_code:
            candidate = normalize_identifier(envelope.iec.iec_code)
            if PAN_RE.match(candidate):
                pan_val = candidate
                confidence = max(confidence, envelope.iec.confidence)
                holder = holder or envelope.iec.holder_name
        if pan_val or holder:
            updates["pan"] = PanExtraction(pan=pan_val, holder_name=holder, confidence=confidence)

    if doc_type == "IN_DEED_OF_PARTNERSHIP" and envelope.partnership is None and envelope.coi:
        updates["partnership"] = PartnershipExtraction(
            firm_name=envelope.coi.company_name,
            registration_number=envelope.coi.cin,
            confidence=envelope.coi.confidence,
        )

    if doc_type == "IN_CERTIFICATE_OF_INCORPORATION" and envelope.coi is None and envelope.partnership:
        updates["coi"] = CoiExtraction(
            cin=envelope.partnership.registration_number,
            company_name=envelope.partnership.firm_name,
            confidence=envelope.partnership.confidence,
        )

    return envelope.model_copy(update=updates) if updates else envelope


def _missing_vision_fields(envelope: ExtractionEnvelope) -> list[str]:
    return missing_critical_fields(envelope)


async def _maybe_vision_retry(
    llm,
    envelope: ExtractionEnvelope,
    page_images_b64: list[str],
    schema: dict,
    timeout_s: float,
) -> ExtractionEnvelope:
    if not page_images_b64 or not getattr(llm, "supports_vision", True):
        return envelope
    missing = _missing_vision_fields(envelope)
    if not missing:
        return envelope
    log.info(
        "extract.vision_retry",
        doc_type=envelope.doc_type,
        missing_fields=missing,
        llm_provider=llm.id,
    )
    retry_messages = build_vision_retry_messages(envelope.doc_type, missing, page_images_b64)
    retried = await _complete_envelope_with_retry(llm, retry_messages, schema, timeout_s)
    retried = retried.model_copy(update={"doc_type": envelope.doc_type})
    merged = merge_envelopes(envelope, retried)
    if len(missing_critical_fields(merged)) < len(missing_critical_fields(envelope)):
        return merged
    return envelope


def _identity_for(envelope: ExtractionEnvelope) -> ExtractedIdentity:
    doc_type = envelope.doc_type
    pan = envelope.pan.pan if envelope.pan and doc_type in _DOC_TYPES_ALLOWING_PAN else None
    gstin = envelope.gst.gstin if envelope.gst and doc_type in _DOC_TYPES_ALLOWING_GST else None
    ifsc = envelope.cheque.ifsc if envelope.cheque and doc_type in _DOC_TYPES_ALLOWING_CHEQUE else None
    return ExtractedIdentity(
        pan=pan,
        gstin=gstin,
        ifsc=ifsc,
        region_code=None,
        is_natural_person=None,
    )


def _patches_and_unmapped(envelope: ExtractionEnvelope) -> tuple[list[Patch], list[dict]]:
    patches: list[Patch] = []
    unmapped: list[dict] = []
    doc_type = envelope.doc_type

    if envelope.pan is not None and doc_type in _DOC_TYPES_ALLOWING_PAN:
        patches.extend(patches_from_pan(envelope.pan))
    if envelope.gst is not None and doc_type in _DOC_TYPES_ALLOWING_GST:
        patches.extend(patches_from_gst(envelope.gst))
    if envelope.cheque is not None and doc_type in _DOC_TYPES_ALLOWING_CHEQUE:
        patches.extend(patches_from_cheque(envelope.cheque))
    if envelope.udyam is not None and envelope.udyam.udyam_number and doc_type == "IN_UDYAM_CERTIFICATE":
        unmapped.append({"label": "Udyam number", "value": envelope.udyam.udyam_number})
    if envelope.coi is not None and doc_type in _DOC_TYPES_ALLOWING_COI:
        coi_patches = patches_from_coi(envelope.coi)
        patches.extend(coi_patches)
        if envelope.coi.cin:
            unmapped.append({"label": "CIN", "value": envelope.coi.cin})
    if envelope.address_proof is not None and doc_type in _DOC_TYPES_ALLOWING_ADDRESS_PROOF:
        patches.extend(patches_from_address_proof(envelope.address_proof))
    if envelope.iec is not None and doc_type in _DOC_TYPES_ALLOWING_IEC:
        iec_patches = patches_from_iec(envelope.iec)
        patches.extend(iec_patches)
        if envelope.iec.iec_code:
            unmapped.append({"label": "IEC", "value": envelope.iec.iec_code})
    if envelope.partnership is not None and doc_type in _DOC_TYPES_ALLOWING_PARTNERSHIP:
        partnership_patches = patches_from_partnership(envelope.partnership)
        patches.extend(partnership_patches)
        if envelope.partnership.registration_number:
            unmapped.append(
                {"label": "Partnership registration number", "value": envelope.partnership.registration_number}
            )
    if envelope.mto is not None and doc_type in _DOC_TYPES_ALLOWING_MTO:
        mto_patches = patches_from_mto(envelope.mto)
        patches.extend(mto_patches)
        if envelope.mto.licence_number:
            unmapped.append({"label": "MTO/IATA/CHA licence number", "value": envelope.mto.licence_number})

    return patches, unmapped


def _address_candidates_and_date(envelope: ExtractionEnvelope, document_id: str) -> tuple[list[dict], str | None]:
    candidates = collect_address_candidates_from_envelope(
        envelope.doc_type,
        document_id,
        gst=envelope.gst,
        coi=envelope.coi,
        address_proof=envelope.address_proof,
        partnership=envelope.partnership,
        udyam=envelope.udyam,
    )
    effective: str | None = None
    if envelope.gst and envelope.gst.date_of_registration:
        effective = envelope.gst.date_of_registration
    elif envelope.coi and envelope.coi.date_of_incorporation:
        effective = envelope.coi.date_of_incorporation
    return candidates, effective


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


async def run_extraction(
    content: bytes,
    mime: str,
    country: str,
    doc_type_hint: str | None = None,
    filename: str | None = None,
) -> ExtractResult:
    country_upper = country.strip().upper()
    if country_upper != "IN":
        from app.documents.extract.pipeline_locale import run_locale_extraction
        from app.documents.extract.supported_countries import is_supported_extraction_country

        if not is_supported_extraction_country(country_upper):
            raise ExtractionUnavailable(f"Country {country_upper} is not supported for document extraction.")
        return await run_locale_extraction(content, mime, country_upper, doc_type_hint, filename)

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
    filename_type = resolve_filename_hint(filename, ocr_result.text)
    if filename_type:
        hint = Classification(
            filename_type,
            max(hint.confidence, 0.8),
            ambiguous=False,
        )
    if doc_type_hint and doc_type_hint.strip().upper().startswith(f"{country.strip().upper()}_"):
        hint = Classification(
            doc_type_hint.strip().upper(),
            max(hint.confidence, 0.85),
            ambiguous=False,
        )
    messages = build_envelope_messages(ocr_result.text, ocr_result.page_images_b64, hint)
    schema = envelope_json_schema()

    envelope = await _complete_envelope_with_retry(llm, messages, schema, settings.llm_timeout_s)

    filename_type = resolve_filename_hint(filename, ocr_result.text)
    if filename_type and filename_type != envelope.doc_type:
        log.info(
            "extract.filename_doc_type_override",
            document_id=document_id,
            llm_doc_type=envelope.doc_type,
            filename_doc_type=filename_type,
        )
        envelope = envelope.model_copy(update={"doc_type": filename_type})

    envelope = _salvage_blocks_for_doc_type(envelope)
    envelope = await _maybe_vision_retry(
        llm, envelope, ocr_result.page_images_b64, schema, settings.llm_timeout_s
    )
    envelope = _salvage_blocks_for_doc_type(envelope)
    envelope = await apply_focused_extractions(
        llm,
        envelope,
        ocr_result.page_images_b64,
        settings.llm_timeout_s,
        content=content,
        mime=mime,
        filename=filename,
    )
    envelope = _salvage_blocks_for_doc_type(envelope)

    if envelope.doc_type not in ENVELOPE_DOC_TYPES or envelope.doc_type == "UNKNOWN":
        log.info("extract.unknown_doc_type", document_id=document_id, ocr_provider=ocr_result.provider_id)
        return ExtractResult(
            document_id=document_id,
            doc_type="UNKNOWN",
            doc_type_confidence=envelope.doc_type_confidence,
            warnings=["Document type not recognised — enter fields manually."],
        )

    if not doc_type_matches_country(country, envelope.doc_type):
        log.info(
            "extract.country_mismatch",
            document_id=document_id,
            country=country,
            doc_type=envelope.doc_type,
        )
        return ExtractResult(
            document_id=document_id,
            doc_type="UNKNOWN",
            doc_type_confidence=envelope.doc_type_confidence,
            warnings=[
                f"Document type {envelope.doc_type} does not apply to country {country.strip().upper()}."
            ],
        )

    patches, unmapped = _patches_and_unmapped(envelope)
    address_candidates, effective_date = _address_candidates_and_date(envelope, document_id)
    warnings: list[str] = []
    if envelope.doc_type == "IN_PAN_CARD" and (not envelope.pan or not envelope.pan.pan):
        if is_aadhaar_only_document(ocr_result.text):
            warnings.append(
                "Scan appears to be Aadhaar only — no PAN visible. Re-upload the PAN card or enter PAN manually."
            )
            aadhaar_no = extract_aadhaar_number(ocr_result.text)
            if aadhaar_no:
                unmapped.append({"label": "Aadhaar number", "value": aadhaar_no})
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
        warnings=warnings,
        unmapped=unmapped,
        address_candidates=address_candidates,
        effective_date=effective_date,
        page_images_b64=ocr_result.page_images_b64,
    )
