"""Pydantic AI chat entry — optional LLM enhancement over deterministic planner."""

from __future__ import annotations

import os
from typing import Any

from app.onboard.chat_planner import ChatPlannerResponse, plan_chat_turn


def is_chat_llm_enabled() -> bool:
    return os.getenv("DOCAI_ONBOARD_CHAT_LLM", "").lower() in ("1", "true", "yes")


async def plan_chat_turn_async(
    message: str,
    conversation_state: str,
    doc_availability: str,
    country_code: str,
    form_state: dict[str, Any],
    quick_reply_id: str | None = None,
) -> ChatPlannerResponse:
    """Deterministic planner today; Pydantic AI path when DOCAI_ONBOARD_CHAT_LLM=true."""
    if is_chat_llm_enabled() and os.getenv("DOCAI_AOAI_ENDPOINT") and os.getenv("DOCAI_AOAI_KEY"):
        try:
            return await _plan_with_pydantic_ai(
                message,
                conversation_state,
                doc_availability,
                country_code,
                form_state,
                quick_reply_id,
            )
        except Exception:  # noqa: BLE001
            pass

    return plan_chat_turn(
        message,
        conversation_state,
        doc_availability,
        country_code,
        form_state,
        quick_reply_id,
    )


async def _plan_with_pydantic_ai(
    message: str,
    conversation_state: str,
    doc_availability: str,
    country_code: str,
    form_state: dict[str, Any],
    quick_reply_id: str | None = None,
) -> ChatPlannerResponse:
    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIModel
    from pydantic_ai.providers.openai import OpenAIProvider

    endpoint = os.getenv("DOCAI_AOAI_ENDPOINT", "").rstrip("/")
    deployment = os.getenv("DOCAI_AOAI_DEPLOYMENT", "gpt-4o")
    api_key = os.getenv("DOCAI_AOAI_KEY", "")
    api_version = os.getenv("DOCAI_AOAI_API_VERSION", "2024-08-01-preview")

    provider = OpenAIProvider(
        base_url=f"{endpoint}/openai/deployments/{deployment}",
        api_key=api_key,
        http_client=None,
    )
    model = OpenAIModel(deployment, provider=provider)

    agent = Agent(
        model,
        system_prompt=(
            "You are a vendor onboarding assistant for Maersk MDM. "
            "Respond with structured next-step guidance for steward chat onboarding. "
            f"Country: {country_code}. State: {conversation_state}. Doc availability: {doc_availability}."
        ),
        result_type=ChatPlannerResponse,
    )

    prompt = (
        f"Message: {message}\nQuick reply id: {quick_reply_id or ''}\nForm keys: {list(form_state.keys())}"
    )
    from app.observability.langfuse_trace import trace_generation, update_generation_usage

    with trace_generation(
        "onboard.chat_plan",
        model=deployment,
        input=prompt[:2000],
        metadata={"countryCode": country_code, "state": conversation_state},
    ) as generation:
        result = await agent.run(prompt)
        usage = getattr(result, "usage", None)
        update_generation_usage(
            generation,
            input_tokens=getattr(usage, "input_tokens", None) if usage else None,
            output_tokens=getattr(usage, "output_tokens", None) if usage else None,
            output=result.data.model_dump(),
            model=deployment,
        )
        return result.data
