"""NL search orchestration — heuristic + LLM parse in services."""

from __future__ import annotations

from typing import Any

from app.nl_search.context import NlSearchParseContext
from app.nl_search.heuristic import heuristic_parse_natural_language, should_use_heuristic_immediately
from app.nl_search.parse import parse_natural_language_with_llm
from app.providers.llm.base import LlmProvider


async def orchestrate_nl_search(
    provider: LlmProvider | None,
    query: str,
    context: NlSearchParseContext | None = None,
) -> dict[str, Any]:
    trimmed = query.strip()
    if not trimmed:
        raise ValueError("Enter a search query.")

    heuristic = heuristic_parse_natural_language(trimmed)
    parser: dict[str, Any] = {
        "llmAttempted": False,
        "llmProvider": provider.id if provider else None,
        "heuristicAvailable": heuristic is not None,
    }

    parsed: dict[str, Any] | None = None
    if heuristic and should_use_heuristic_immediately(heuristic):
        parsed = heuristic

    if parsed is None and provider is not None:
        parser["llmAttempted"] = True
        try:
            result = await parse_natural_language_with_llm(provider, trimmed, context)
            parsed = result.model_dump(exclude_none=True)
        except Exception as exc:
            parser["llmError"] = str(exc)
            if heuristic:
                parsed = heuristic

    if parsed is None and heuristic:
        parsed = heuristic

    if parsed is None:
        raise ValueError(
            "Could not understand that query. Try a vendor code (IN000070343), SAP MDG BP code, name + country, or tax ID."
        )

    return {"parsed": parsed, "parser": parser}
