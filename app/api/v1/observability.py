"""Observability API — Langfuse-backed LLM cost and trace summaries."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth import require_service_bearer
from app.observability.langfuse_query import build_status_payload, fetch_recent_generations, fetch_summary
from app.providers.llm.factory import get_llm_provider

router = APIRouter(
    prefix="/v1/observability",
    tags=["observability"],
    dependencies=[Depends(require_service_bearer)],
)


@router.get("/status")
async def observability_status() -> dict:
    llm = get_llm_provider()
    return build_status_payload(
        llm_provider=llm.id if llm else None,
        llm_model=llm.model if llm else None,
    )


@router.get("/summary")
async def observability_summary(days: int = 7, includeTests: bool = False) -> dict:
    return await fetch_summary(days=days, include_tests=includeTests)


@router.get("/recent")
async def observability_recent(limit: int = 25, includeTests: bool = False) -> dict:
    return await fetch_recent_generations(limit=limit, include_tests=includeTests)
