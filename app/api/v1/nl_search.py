"""Natural-language vendor search parsing, migrated from the portal's
``src/lib/nl-search/llm-parse.ts``.

No ``get_llm_provider()`` -> 503. Any failure (transport error, both validation attempts
failing) -> 502, never 500.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import require_service_bearer
from app.core.logging import get_logger
from app.nl_search.context import NlSearchParseContext
from app.nl_search.parse import parse_natural_language_with_llm
from app.providers.llm.factory import get_llm_provider

router = APIRouter(
    prefix="/v1/nl-search",
    tags=["nl-search"],
    dependencies=[Depends(require_service_bearer)],
)
log = get_logger()


class NlSearchParseRequest(BaseModel):
    query: str
    context: NlSearchParseContext | None = None


@router.post("/parse")
async def parse_route(body: NlSearchParseRequest) -> dict[str, Any]:
    provider = get_llm_provider()
    if provider is None:
        raise HTTPException(
            status_code=503,
            detail="No LLM provider available — configure DOCAI_LLM_PROVIDER.",
        )

    try:
        result = await parse_natural_language_with_llm(provider, body.query, body.context)
    except Exception as exc:
        log.warning("nl_search.parse.failed", error=str(exc))
        raise HTTPException(status_code=502, detail="Failed to parse natural language query.") from exc

    return result.model_dump(exclude_none=True)
