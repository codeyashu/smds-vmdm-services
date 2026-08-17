"""Steward assist agents — rule explainer, workflow summarizer."""

from __future__ import annotations

from fastapi import APIRouter

from app.agents.steward_assist_agent import (
    explain_validation_failure_async,
    summarize_workflow_changes_async,
)
from app.agents.steward_assist import (
    RuleExplainerRequest,
    RuleExplainerResponse,
    WorkflowSummaryRequest,
    WorkflowSummaryResponse,
)

router = APIRouter(prefix="/v1/agents", tags=["agents"])


@router.post("/explain-validation", response_model=RuleExplainerResponse)
async def explain_validation(body: RuleExplainerRequest) -> RuleExplainerResponse:
    return await explain_validation_failure_async(body)


@router.post("/summarize-workflow", response_model=WorkflowSummaryResponse)
async def summarize_workflow(body: WorkflowSummaryRequest) -> WorkflowSummaryResponse:
    return await summarize_workflow_changes_async(body)
