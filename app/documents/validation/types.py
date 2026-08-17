"""Bundle adjudication types."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Severity = Literal["block", "warn", "info"]
VerdictAction = Literal["accept", "suggest", "steward_required", "reject", "skip"]
CheckStatus = Literal["pass", "warn", "fail", "skip"]
FreshnessStatus = Literal["current", "superseded", "stale_form", "unknown_date"]


class CotStep(BaseModel):
    step: int
    kind: Literal["observe", "normalize", "rule", "compare", "recommend"]
    message: str
    refs: list[str] = Field(default_factory=list)


class BundleCheck(BaseModel):
    id: str
    status: CheckStatus
    severity: Severity
    message: str | None = None
    paths: list[str] = Field(default_factory=list)
    logical_field_ids: list[str] = Field(default_factory=list, alias="logicalFieldIds")
    document_ids: list[str] = Field(default_factory=list, alias="documentIds")

    model_config = {"populate_by_name": True}


class FieldConflict(BaseModel):
    path: str
    label: str
    logical_field_id: str | None = Field(default=None, alias="logicalFieldId")
    option_keys: list[str] = Field(alias="optionKeys")

    model_config = {"populate_by_name": True}


class FieldOption(BaseModel):
    option_key: str = Field(alias="optionKey")
    path: str
    label: str
    logical_field_id: str | None = Field(default=None, alias="logicalFieldId")
    source: Literal["document"] = "document"
    source_label: str = Field(alias="sourceLabel")
    document_id: str | None = Field(default=None, alias="documentId")
    incoming_value: Any = Field(alias="incomingValue")
    incoming_display: str = Field(alias="incomingDisplay")
    confidence: float
    pre_selected: bool = Field(default=False, alias="preSelected")
    needs_resolution: str | None = Field(default=None, alias="needsResolution")
    evidence_snippet: str | None = Field(default=None, alias="evidenceSnippet")
    regex_ok: bool = Field(default=True, alias="regexOk")

    model_config = {"populate_by_name": True}


class FieldEvidenceDetail(BaseModel):
    snippet: str | None = None
    page: int | None = None
    bbox: list[float] | None = None
    address_role: str | None = Field(default=None, alias="addressRole")
    effective_date: str | None = Field(default=None, alias="effectiveDate")

    model_config = {"populate_by_name": True}


class AddressCandidate(BaseModel):
    candidate_key: str = Field(alias="candidateKey")
    address_role: str = Field(alias="addressRole")
    label: str
    full_address_text: str = Field(alias="fullAddressText")
    fields: dict[str, Any] = Field(default_factory=dict)
    source_doc_type: str = Field(alias="sourceDocType")
    document_id: str | None = Field(default=None, alias="documentId")
    confidence: float = 0.0
    effective_date: str | None = Field(default=None, alias="effectiveDate")
    evidence: FieldEvidenceDetail | None = None
    alignment_score: float | None = Field(default=None, alias="alignmentScore")
    matched_fields: list[str] = Field(default_factory=list, alias="matchedFields")
    gaps: list[str] = Field(default_factory=list)
    recommended_for_bill_to: bool = Field(default=False, alias="recommendedForBillTo")

    model_config = {"populate_by_name": True}


class AddressReconciliation(BaseModel):
    selected_candidate_key: str | None = Field(default=None, alias="selectedCandidateKey")
    alignment_score: float = Field(default=0.0, alias="alignmentScore")
    rationale: str = ""

    model_config = {"populate_by_name": True}


class FreshnessFinding(BaseModel):
    path: str
    status: FreshnessStatus
    preferred_option_key: str | None = Field(default=None, alias="preferredOptionKey")
    rationale: str = ""
    compared_dates: list[dict[str, Any]] = Field(default_factory=list, alias="comparedDates")
    superseded_option_keys: list[str] = Field(default_factory=list, alias="supersededOptionKeys")

    model_config = {"populate_by_name": True}


class FieldVerdict(BaseModel):
    path: str
    label: str
    logical_field_id: str | None = Field(default=None, alias="logicalFieldId")
    action: VerdictAction
    reason: str | None = None
    evidence_summary: str | None = Field(default=None, alias="evidenceSummary")
    recommended_option_key: str | None = Field(default=None, alias="recommendedOptionKey")
    conflict_option_keys: list[str] = Field(default_factory=list, alias="conflictOptionKeys")

    model_config = {"populate_by_name": True}


class ExtractionCacheRef(BaseModel):
    extracted_at: str = Field(alias="extractedAt")
    doc_type: str = Field(alias="docType")
    effective_date: str | None = Field(default=None, alias="effectiveDate")
    patches_summary: dict[str, str] = Field(default_factory=dict, alias="patchesSummary")
    address_candidates: list[dict[str, Any]] = Field(default_factory=list, alias="addressCandidates")

    model_config = {"populate_by_name": True}


class ExistingDocumentRef(BaseModel):
    doc_type: str | None = Field(default=None, alias="docType")
    filename: str
    classified_doc_type: str | None = Field(default=None, alias="classifiedDocType")
    uploaded_at: str | None = Field(default=None, alias="uploadedAt")
    extraction_cache: ExtractionCacheRef | None = Field(default=None, alias="extractionCache")

    model_config = {"populate_by_name": True}


class AdjudicateRequest(BaseModel):
    country_code: str = Field(alias="countryCode")
    extractions: list[dict[str, Any]]
    form_snapshot: dict[str, Any] = Field(default_factory=dict, alias="formSnapshot")
    existing_documents: list[ExistingDocumentRef] = Field(default_factory=list, alias="existingDocuments")

    model_config = {"populate_by_name": True}


class DocumentCorroborationSuggestion(BaseModel):
    path: str
    option_key: str = Field(alias="optionKey")
    reason: str | None = None

    model_config = {"populate_by_name": True}


class DocumentCorroboration(BaseModel):
    skipped: bool = True
    skip_reason: str | None = Field(default=None, alias="skipReason")
    verdict: Literal["same", "likely", "different", "insufficient"] | None = None
    narrative: str | None = None
    correlation_score: int | None = Field(default=None, alias="correlationScore")
    suggested_options: list[DocumentCorroborationSuggestion] = Field(
        default_factory=list, alias="suggestedOptions"
    )
    suggested_address_candidate_key: str | None = Field(
        default=None, alias="suggestedAddressCandidateKey"
    )

    model_config = {"populate_by_name": True}


class AdjudicateResponse(BaseModel):
    country_code: str = Field(alias="countryCode")
    playbook_version: int = Field(default=1, alias="playbookVersion")
    options: list[FieldOption]
    conflicts: list[FieldConflict]
    bundle_checks: list[BundleCheck] = Field(alias="bundleChecks")
    field_verdicts: list[FieldVerdict] = Field(alias="fieldVerdicts")
    cot_trace: list[CotStep] = Field(alias="cotTrace")
    warnings: list[str] = Field(default_factory=list)
    bundle_summary: str = Field(default="", alias="bundleSummary")
    address_candidates: list[AddressCandidate] = Field(default_factory=list, alias="addressCandidates")
    address_reconciliation: AddressReconciliation | None = Field(default=None, alias="addressReconciliation")
    freshness_findings: list[FreshnessFinding] = Field(default_factory=list, alias="freshnessFindings")
    document_corroboration: DocumentCorroboration | None = Field(default=None, alias="documentCorroboration")

    model_config = {"populate_by_name": True}

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)
