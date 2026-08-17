"""MCP-style tool gateway — routes orchestrator stages through portal BFF (MDM proxy)."""

from __future__ import annotations

from typing import Any

from app.mcp.handlers import (
    adjudicate_documents_handler,
    get_vendor_document_extractions_handler,
    reconcile_address_candidates_handler,
    resolve_field_conflicts_handler,
)
from app.onboard import bff_client


async def enrich_address(args: dict[str, Any]) -> dict[str, Any]:
    return await bff_client.post_json("/api/addresses/enrich", args.get("body") or {})


async def search_company_registry(args: dict[str, Any]) -> dict[str, Any]:
    query = {k: str(v) for k, v in (args.get("query") or {}).items() if v is not None}
    return await bff_client.get_json("/api/companies/search", params=query)


async def search_duplicates(args: dict[str, Any]) -> dict[str, Any]:
    return await bff_client.post_json("/api/vendors/duplicates", args.get("body") or {})


READ_TOOL_HANDLERS = {
    "enrich_address": enrich_address,
    "search_company_registry": search_company_registry,
    "search_duplicates": search_duplicates,
    "adjudicate_documents": adjudicate_documents_handler,
    "get_vendor_document_extractions": get_vendor_document_extractions_handler,
    "reconcile_address_candidates": reconcile_address_candidates_handler,
    "resolve_field_conflicts": resolve_field_conflicts_handler,
}


async def invoke_read_tool(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    handler = READ_TOOL_HANDLERS.get(tool_name)
    if handler is None:
        raise ValueError(f"Unknown read tool: {tool_name}")
    return await handler(args)
