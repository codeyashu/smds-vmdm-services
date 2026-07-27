"""
MCP tool catalog for vendor MDM agent onboarding.

Tools call the portal BFF (Backend-for-Agents pattern). Write tools require HITL tokens
issued by the portal — see ADR-0007 in smds-vmdmportal.
"""

from __future__ import annotations

from typing import Any

READ_TOOLS = [
    "get_validation_rules",
    "validate_vendor_draft",
    "search_duplicates",
    "extract_documents",
    "search_company_registry",
    "match_company_registry",
    "enrich_address",
    "search_bank",
    "propose_vendor_patch",
]

WRITE_TOOLS = [
    "apply_vendor_patch",
    "create_prospect",
    "save_draft",
    "submit_vendor",
]

ALL_TOOLS = READ_TOOLS + WRITE_TOOLS


def tool_schema(name: str) -> dict[str, Any]:
    write = name in WRITE_TOOLS
    return {
        "name": name,
        "description": f"VMDM onboard tool: {name}",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sessionId": {"type": "string"},
                "hitlToken": {"type": "string"} if write else {},
                "payload": {"type": "object"},
            },
            "required": ["sessionId"] + (["hitlToken"] if write else []),
        },
    }


def list_tools() -> list[dict[str, Any]]:
    return [tool_schema(name) for name in ALL_TOOLS]
