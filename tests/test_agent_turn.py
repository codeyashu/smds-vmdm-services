"""Tests for AgentTurn mapping from chat planner."""

from app.onboard.agent_turn import chat_planner_to_agent_turn, enrichment_review_agent_turn
from app.onboard.chat_planner import plan_chat_turn


def test_chat_planner_to_agent_turn_intake() -> None:
    planned = plan_chat_turn("", "intake", "none", "IN", {})
    turn = chat_planner_to_agent_turn(planned)
    assert turn["message"] == planned.reply
    assert turn["phase"] == "setup"
    assert turn["layout"]["mode"] == "converse"
    assert turn["meta"]["conversationState"] == "collect_docs"
    assert turn["surface"]["id"] == "upload"


def test_enrichment_review_agent_turn() -> None:
    turn = enrichment_review_agent_turn("Ready for review — 3 field suggestions.", {"options": [{}, {}, {}]})
    assert turn["phase"] == "review"
    assert turn["layout"]["mode"] == "decide"
    assert turn["surface"]["id"] == "enrichment_review"
    assert turn["await"] == "hitl_apply_enrichment"
