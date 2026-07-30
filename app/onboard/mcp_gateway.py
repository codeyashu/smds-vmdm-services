"""MCP-style tool gateway — routes orchestrator stages through named tools to the portal BFF."""

from __future__ import annotations

from typing import Any

from app.onboard import bff_client


async def extract_documents(args: dict[str, Any]) -> dict[str, Any]:
    country_code = str(args.get("countryCode") or "IN")
    files = args.get("files") or []
    decoded = bff_client.decode_upload_files(files)
    if not decoded:
        return {"results": []}
    return await bff_client.post_multipart(
        "/api/documents/extract/batch",
        decoded,
        {"countryCode": country_code},
    )


async def enrich_address(args: dict[str, Any]) -> dict[str, Any]:
    return await bff_client.post_json("/api/addresses/enrich", args.get("body") or {})


async def search_company_registry(args: dict[str, Any]) -> dict[str, Any]:
    query = {k: str(v) for k, v in (args.get("query") or {}).items() if v is not None}
    return await bff_client.get_json("/api/companies/search", params=query)


async def search_duplicates(args: dict[str, Any]) -> dict[str, Any]:
    return await bff_client.post_json("/api/vendors/duplicates", args.get("body") or {})


async def propose_vendor_patch(args: dict[str, Any]) -> dict[str, Any]:
    return await bff_client.post_json("/api/onboard/internal/build-plan", args.get("body") or {})


async def map_extraction_results(args: dict[str, Any]) -> dict[str, Any]:
    return await bff_client.post_json("/api/onboard/internal/map-extraction", args.get("body") or {})


READ_TOOL_HANDLERS = {
    "extract_documents": extract_documents,
    "enrich_address": enrich_address,
    "search_company_registry": search_company_registry,
    "search_duplicates": search_duplicates,
    "propose_vendor_patch": propose_vendor_patch,
    "map_extraction_results": map_extraction_results,
}


async def invoke_read_tool(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    handler = READ_TOOL_HANDLERS.get(tool_name)
    if handler is None:
        raise ValueError(f"Unknown read tool: {tool_name}")
    return await handler(args)
