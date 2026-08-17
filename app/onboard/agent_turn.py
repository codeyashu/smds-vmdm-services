"""Build AgentTurn payloads for AG-UI CUSTOM events and chat responses."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.onboard.chat_planner import ChatPlannerResponse

AGENT_TURN_CUSTOM_NAME = "agent_turn"

PORTAL_CARDS = frozenset(
    {
        "upload",
        "progress",
        "enrichment_review",
        "micro_form",
        "duplicate_alert",
        "confirm_action",
        "handoff",
    }
)

_CONVERSATION_TO_PHASE: dict[str, str] = {
    "intake": "setup",
    "collect_docs": "setup",
    "enriching": "enriching",
    "review": "review",
    "duplicate_check": "review",
    "gap_fill": "create",
    "confirm_create": "create",
    "handoff": "bank",
}

_CONVERSATION_TO_LAYOUT: dict[str, str] = {
    "enriching": "watch",
    "review": "decide",
    "duplicate_check": "decide",
    "confirm_create": "decide",
    "gap_fill": "full",
    "handoff": "full",
}


def _card_to_surface_id(card: str | None) -> str | None:
    if not card:
        return None
    if card in PORTAL_CARDS:
        return card
    return card


def chat_planner_to_agent_turn(planned: ChatPlannerResponse) -> dict[str, Any]:
    conversation_state = planned.conversationState
    phase = _CONVERSATION_TO_PHASE.get(conversation_state, "setup")
    layout_mode = _CONVERSATION_TO_LAYOUT.get(conversation_state, "converse")

    turn: dict[str, Any] = {
        "message": planned.reply,
        "phase": phase,
        "layout": {"mode": layout_mode},
        "meta": {
            "conversationState": conversation_state,
            "card": planned.card,
            "gapField": planned.gapField.model_dump() if planned.gapField else None,
            "source": "chat_planner",
        },
    }

    if planned.quickReplies:
        turn["quickReplies"] = planned.quickReplies

    surface_id = _card_to_surface_id(planned.card)
    if surface_id:
        props: dict[str, Any] = {}
        if planned.gapField:
            props["gapField"] = planned.gapField.model_dump()
        turn["surface"] = {"id": surface_id, "props": props or None}

    if planned.uiAction or planned.branch:
        turn["run"] = {
            "uiAction": planned.uiAction,
            "branch": planned.branch,
        }

    if planned.card == "upload":
        turn["await"] = "doc_upload"
    elif planned.card == "progress":
        turn["await"] = "enrichment_run"
    elif planned.uiAction == "run_enrichment":
        turn["await"] = "enrichment_run"

    return turn


def enrichment_review_agent_turn(message: str, plan: dict[str, Any]) -> dict[str, Any]:
    """AgentTurn emitted after enrichment pipeline — layout hint for external hosts."""
    option_count = len(plan.get("options") or [])
    return {
        "message": message,
        "phase": "review",
        "layout": {"mode": "decide"},
        "surface": {"id": "enrichment_review"},
        "meta": {
            "conversationState": "review",
            "card": "enrichment_review",
            "source": "enrichment_run",
            "optionCount": option_count,
        },
        "await": "hitl_apply_enrichment",
    }


def build_agent_turn_custom_frame(planned: ChatPlannerResponse) -> str:
    """SSE data frame with CUSTOM agent_turn event."""
    event = {
        "type": "CUSTOM",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": {
            "name": AGENT_TURN_CUSTOM_NAME,
            "turn": chat_planner_to_agent_turn(planned),
        },
    }
    return f"data: {json.dumps(event)}\n\n"
