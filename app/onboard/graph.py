"""
LangGraph-style onboard orchestration graph (deterministic v2).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Awaitable, Callable

from app.onboard.ag_ui import ag_ui_event
from app.onboard.stages import (
    run_address_stage,
    run_build_plan_stage,
    run_duplicate_stage,
    run_extract_stage,
    run_registry_stage,
)

StageRunner = Callable[[dict[str, Any]], Awaitable[tuple[str, dict[str, Any]]]]


def _tool_call_id(session_id: str, step: str) -> str:
    return f"{session_id}-{step}-{int(datetime.now(timezone.utc).timestamp() * 1000)}"


async def _run_stage(
    session_id: str,
    stage_id: str,
    context: dict[str, Any],
    runner: StageRunner,
) -> tuple[str, dict[str, Any], list[str]]:
    frames = [ag_ui_event("STEP_STARTED", session_id, {"step": stage_id})]
    raw_step, next_context = await runner(context)
    steps = list(next_context.get("stepsCompleted") or [])
    if raw_step not in steps:
        steps.append(raw_step)
    next_context["stepsCompleted"] = steps
    tool_call_id = _tool_call_id(session_id, raw_step)
    frames.extend(
        [
            ag_ui_event("TOOL_CALL_START", session_id, {"toolCallId": tool_call_id, "toolCallName": raw_step}),
            ag_ui_event(
                "TOOL_CALL_ARGS",
                session_id,
                {"toolCallId": tool_call_id, "delta": json.dumps({"step": raw_step})},
            ),
            ag_ui_event("TOOL_CALL_END", session_id, {"toolCallId": tool_call_id}),
            ag_ui_event("STEP_FINISHED", session_id, {"step": raw_step}),
        ]
    )
    return raw_step, next_context, frames


async def run_onboard_graph(session_id: str, context: dict[str, Any]) -> AsyncIterator[str]:
    branch = context.get("branch") or "full_enrichment"
    yield ag_ui_event("RUN_STARTED", session_id)
    yield ag_ui_event("TEXT_MESSAGE_CONTENT", session_id, {"message": f"Starting {branch} chain…"})

    if branch == "chat_only":
        yield ag_ui_event("STEP_STARTED", session_id, {"step": "intake_router"})
        yield ag_ui_event("TEXT_MESSAGE_CONTENT", session_id, {"message": "Routing conversational intake…"})
        yield ag_ui_event("STEP_FINISHED", session_id, {"step": "intake_router"})
        yield ag_ui_event("RUN_FINISHED", session_id)
        return

    working: dict[str, Any] = {
        "sessionId": session_id,
        "countryCode": context.get("countryCode"),
        "formState": context.get("formState") or {},
        "workingState": context.get("formState") or {},
        "files": context.get("files") or [],
        "docAvailability": context.get("docAvailability"),
        "patchGroups": context.get("patchGroups") or [],
        "stepsCompleted": [],
        "extractionFailures": [],
    }

    for stage_id, runner in (
        ("extract", run_extract_stage),
        ("address_enrich", run_address_stage),
        ("registry", run_registry_stage),
        ("duplicate_precheck", run_duplicate_stage),
    ):
        _, working, frames = await _run_stage(session_id, stage_id, working, runner)
        for frame in frames:
            yield frame

    yield ag_ui_event("STEP_STARTED", session_id, {"step": "build_plan"})
    plan, working = await run_build_plan_stage(working)
    tool_call_id = _tool_call_id(session_id, "build_plan")
    yield ag_ui_event("TOOL_CALL_START", session_id, {"toolCallId": tool_call_id, "toolCallName": "build_plan"})
    yield ag_ui_event(
        "TOOL_CALL_ARGS",
        session_id,
        {"toolCallId": tool_call_id, "delta": json.dumps({"step": "build_plan"})},
    )
    yield ag_ui_event("TOOL_CALL_END", session_id, {"toolCallId": tool_call_id})
    yield ag_ui_event("STEP_FINISHED", session_id, {"step": "build_plan"})
    steps = list(working.get("stepsCompleted") or [])
    if "build_plan" not in steps:
        steps.append("build_plan")
    working["stepsCompleted"] = steps

    yield ag_ui_event(
        "STATE_DELTA",
        session_id,
        {
            "delta": [
                {"op": "replace", "path": "/stepsCompleted", "value": working.get("stepsCompleted", [])},
                {"op": "replace", "path": "/optionCount", "value": len(plan.get("options") or [])},
            ]
        },
    )
    yield ag_ui_event("CUSTOM", session_id, {"name": "enrichment_plan", "plan": plan})
    yield ag_ui_event("ENRICHMENT_PLAN", session_id, {"plan": plan})
    option_count = len(plan.get("options") or [])
    review_message = (
        f"Ready for review — {option_count} field suggestion{'s' if option_count != 1 else ''}."
        if option_count
        else "Extraction finished but no applyable fields were found — continue with manual gap-fill or upload a GST / incorporation certificate."
    )
    yield ag_ui_event("TEXT_MESSAGE_CONTENT", session_id, {"message": review_message})
    yield ag_ui_event(
        "HITL_REQUIRED",
        session_id,
        {
            "action": "apply_enrichment",
            "reason": "Review and confirm field suggestions before applying.",
        },
    )
    yield ag_ui_event("RUN_FINISHED", session_id)
