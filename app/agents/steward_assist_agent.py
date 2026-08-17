"""Optional Pydantic AI enhancement for steward assist endpoints."""

from __future__ import annotations

import os
from typing import Any, TypeVar, cast

from pydantic import BaseModel

from app.agents.steward_assist import (
    RuleExplainerRequest,
    RuleExplainerResponse,
    WorkflowSummaryRequest,
    WorkflowSummaryResponse,
    explain_validation_failure,
    summarize_workflow_changes,
)
from app.observability.langfuse_trace import trace_generation, update_generation_usage

T = TypeVar("T", bound=BaseModel)


def is_steward_assist_llm_enabled() -> bool:
    return os.getenv("DOCAI_STEWARD_ASSIST_LLM", "").lower() in ("1", "true", "yes")


def _azure_configured() -> bool:
    return bool(os.getenv("DOCAI_AOAI_ENDPOINT") and os.getenv("DOCAI_AOAI_KEY"))


def _azure_deployment() -> str:
    return os.getenv("DOCAI_AOAI_DEPLOYMENT", "gpt-4o")


def _build_agent(system_prompt: str, result_type: type[T]):
    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIModel
    from pydantic_ai.providers.openai import OpenAIProvider

    endpoint = os.getenv("DOCAI_AOAI_ENDPOINT", "").rstrip("/")
    deployment = _azure_deployment()
    api_key = os.getenv("DOCAI_AOAI_KEY", "")

    provider = OpenAIProvider(
        base_url=f"{endpoint}/openai/deployments/{deployment}",
        api_key=api_key,
        http_client=None,
    )
    model = OpenAIModel(deployment, provider=provider)
    return Agent(model, system_prompt=system_prompt, result_type=result_type)


async def _run_traced_agent(
    agent: Any,
    prompt: str,
    *,
    trace_name: str,
    metadata: dict[str, Any] | None = None,
) -> BaseModel:
    with trace_generation(
        trace_name,
        model=_azure_deployment(),
        input=prompt[:2000],
        metadata=metadata,
    ) as generation:
        result = await agent.run(prompt)
        usage = getattr(result, "usage", None)
        update_generation_usage(
            generation,
            input_tokens=getattr(usage, "input_tokens", None) if usage else None,
            output_tokens=getattr(usage, "output_tokens", None) if usage else None,
            output=result.data.model_dump(),
            model=_azure_deployment(),
        )
        return result.data


async def explain_validation_failure_async(body: RuleExplainerRequest) -> RuleExplainerResponse:
    if is_steward_assist_llm_enabled() and _azure_configured():
        try:
            agent = _build_agent(
                (
                    "You explain vendor MDM validation failures to data stewards. "
                    "Be concise, cite the field path, and suggest a concrete fix. "
                    f"Country: {body.countryCode}."
                ),
                RuleExplainerResponse,
            )
            prompt = (
                f"Field: {body.fieldPath}\n"
                f"Message: {body.validationMessage}\n"
                f"Form snapshot keys: {list(body.formState.keys())}"
            )
            return cast(
                RuleExplainerResponse,
                await _run_traced_agent(
                    agent,
                    prompt,
                    trace_name="steward_assist.explain_validation",
                    metadata={"countryCode": body.countryCode, "fieldPath": body.fieldPath},
                ),
            )
        except Exception:  # noqa: BLE001
            pass
    return explain_validation_failure(body)


async def summarize_workflow_changes_async(body: WorkflowSummaryRequest) -> WorkflowSummaryResponse:
    if is_steward_assist_llm_enabled() and _azure_configured():
        try:
            agent = _build_agent(
                (
                    "You summarize vendor workflow change sets for approvers. "
                    "Highlight tax, bank, and status risk fields."
                ),
                WorkflowSummaryResponse,
            )
            snapshot = body.changeSnapshot[:20]
            prompt = (
                f"Vendor: {body.vendorCode}\n"
                f"Workflow status: {body.workflowStatus or 'unknown'}\n"
                f"Changes: {snapshot}"
            )
            return cast(
                WorkflowSummaryResponse,
                await _run_traced_agent(
                    agent,
                    prompt,
                    trace_name="steward_assist.summarize_workflow",
                    metadata={"vendorCode": body.vendorCode},
                ),
            )
        except Exception:  # noqa: BLE001
            pass
    return summarize_workflow_changes(body)
