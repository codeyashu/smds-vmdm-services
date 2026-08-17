"""Agent surfaces — rule explainer and workflow summarizer (stubs)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RuleExplainerRequest(BaseModel):
    countryCode: str = Field(min_length=2, max_length=2)
    fieldPath: str
    validationMessage: str
    formState: dict[str, Any] = Field(default_factory=dict)


class RuleExplainerResponse(BaseModel):
    explanation: str
    suggestedAction: str | None = None
    wikiHint: str | None = None


class WorkflowSummaryRequest(BaseModel):
    vendorCode: str
    changeSnapshot: list[dict[str, Any]] = Field(default_factory=list)
    workflowStatus: str | None = None


class WorkflowSummaryResponse(BaseModel):
    summary: str
    riskFields: list[str] = Field(default_factory=list)
    recommendation: str | None = None


def explain_validation_failure(body: RuleExplainerRequest) -> RuleExplainerResponse:
    """Deterministic stub — Pydantic AI enhancement in follow-up."""
    return RuleExplainerResponse(
        explanation=(
            f"Field `{body.fieldPath}` failed validation for {body.countryCode}: "
            f"{body.validationMessage}"
        ),
        suggestedAction="Correct the field value or check country-specific rules in the field wiki.",
        wikiHint=body.fieldPath,
    )


def summarize_workflow_changes(body: WorkflowSummaryRequest) -> WorkflowSummaryResponse:
    """Deterministic stub — Pydantic AI enhancement in follow-up."""
    count = len(body.changeSnapshot)
    risk = [str(row.get("fieldPath") or row.get("path") or "") for row in body.changeSnapshot[:5]]
    risk = [p for p in risk if p]
    return WorkflowSummaryResponse(
        summary=f"{count} field change(s) on vendor {body.vendorCode}.",
        riskFields=risk,
        recommendation="Review tax, bank, and status fields before approve.",
    )
