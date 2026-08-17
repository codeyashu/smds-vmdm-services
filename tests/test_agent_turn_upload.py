def test_chat_planner_to_agent_turn_upload_await() -> None:
    planned = plan_chat_turn("", "intake", "none", "IN", {}, quick_reply_id="docs_full")
    turn = chat_planner_to_agent_turn(planned)
    assert turn.get("surface", {}).get("id") == "upload"
    assert turn.get("await") == "doc_upload"
