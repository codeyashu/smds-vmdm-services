"""
LangGraph-style onboard orchestration graph (deterministic MVP).

Nodes: extract -> registry -> address -> duplicate_precheck -> build_plan.
Full LangGraph checkpointing can replace this module when langgraph is added.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from app.onboard.ag_ui import ag_ui_event


async def run_onboard_graph(session_id: str, context: dict[str, Any]) -> AsyncIterator[str]:
    """Yield AG-UI SSE frames for an onboard run."""
    branch = context.get("branch") or "full_enrichment"
    yield ag_ui_event("RUN_STARTED", session_id)
    yield ag_ui_event("TEXT_MESSAGE_CONTENT", session_id, {"message": f"Starting {branch} chain…"})

    if branch == "chat_only":
        yield ag_ui_event("STEP_STARTED", session_id, {"step": "intake_router"})
        yield ag_ui_event("TEXT_MESSAGE_CONTENT", session_id, {"message": "Routing conversational intake…"})
        yield ag_ui_event("STEP_FINISHED", session_id, {"step": "intake_router"})
        yield ag_ui_event("RUN_FINISHED", session_id)
        return

    steps = ["extract", "registry", "address_enrich", "duplicate_precheck", "build_plan"]
    if branch == "no_docs":
        steps = ["registry", "gap_analysis", "duplicate_precheck", "build_plan"]
    elif branch == "partial_docs":
        steps = ["doc_extract", "registry", "gap_analysis", "duplicate_precheck", "build_plan"]

    for step in steps:
        yield ag_ui_event("STEP_STARTED", session_id, {"step": step})
        yield ag_ui_event("TEXT_MESSAGE_CONTENT", session_id, {"message": f"Running {step}…"})
        yield ag_ui_event("STEP_FINISHED", session_id, {"step": step})

    plan = context.get("plan") or {"sessionId": session_id, "options": [], "stepsCompleted": steps}
    yield ag_ui_event("ENRICHMENT_PLAN", session_id, {"plan": plan})
    yield ag_ui_event("RUN_FINISHED", session_id)
