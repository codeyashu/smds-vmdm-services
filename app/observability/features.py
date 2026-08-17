"""Catalog of direct LLM features traced in portal + vmdm-services."""

from __future__ import annotations

from typing import Any

FEATURE_CATALOG: list[dict[str, Any]] = [
    {
        "id": "doc_extract",
        "label": "Document extraction",
        "description": "Envelope, focused, and vision retry LLM calls during document extraction.",
        "tracePrefixes": ["extract.", "llm.complete_json"],
    },
    {
        "id": "doc_corroboration",
        "label": "Document corroboration",
        "description": "Bundle-level entity consistency checks after adjudication.",
        "tracePrefixes": ["documents.entity_corroboration"],
    },
    {
        "id": "nl_search",
        "label": "Natural language search",
        "description": "LLM parse and repair for vendor search queries.",
        "tracePrefixes": ["nl_search."],
    },
    {
        "id": "company_search",
        "label": "Company search assist",
        "description": "Name/address normalization, tax classify, adjudicate, similarity.",
        "tracePrefixes": ["company_search."],
    },
    {
        "id": "onboard_chat",
        "label": "Agent onboard chat",
        "description": "Pydantic AI chat planner for steward onboarding.",
        "tracePrefixes": ["onboard.chat_plan"],
    },
    {
        "id": "steward_assist",
        "label": "Steward assist",
        "description": "Validation explain + workflow summary agents.",
        "tracePrefixes": ["steward_assist."],
    },
    {
        "id": "web_trust",
        "label": "Web trust LLM",
        "description": "LLM corroboration during web-trust verification.",
        "tracePrefixes": ["trustlens."],
    },
]


def infer_feature(trace_name: str) -> str:
    name = (trace_name or "").strip()
    for entry in FEATURE_CATALOG:
        for prefix in entry["tracePrefixes"]:
            if name == prefix or name.startswith(prefix):
                return entry["id"]
    if name.startswith("extract.") or name == "llm.complete_json":
        return "doc_extract"
    return "other"


def feature_label(feature_id: str) -> str:
    for entry in FEATURE_CATALOG:
        if entry["id"] == feature_id:
            return entry["label"]
    return feature_id
