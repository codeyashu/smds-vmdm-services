"""Durable run record — must survive a services restart, unlike session_store's TTL cache."""

from __future__ import annotations

from app.onboard import run_store


def test_create_and_get_run():
    run_store.create_run("run-1", "IN")
    run = run_store.get_run("run-1")
    assert run is not None
    assert run.country_code == "IN"
    assert run.status == "pending"
    assert run.autonomy == "supervised"


def test_get_missing_run_returns_none():
    assert run_store.get_run("does-not-exist") is None


def test_update_status():
    run_store.create_run("run-2", "IN")
    run_store.update_status("run-2", "running")
    assert run_store.get_run("run-2").status == "running"


def test_append_stage_result_and_tool_call_accumulate():
    run_store.create_run("run-3", "IN")
    run_store.append_stage_result("run-3", "extract", {"fieldCount": 19})
    run_store.append_stage_result("run-3", "address_enrich", {"candidates": 4})
    run_store.append_tool_call("run-3", "call-1", "extract_documents")

    run = run_store.get_run("run-3")
    body = run_store.to_dict(run)
    assert [s["stage"] for s in body["stageResults"]] == ["extract", "address_enrich"]
    assert body["stageResults"][0]["detail"] == {"fieldCount": 19}
    assert body["toolCallLog"] == [{"toolCallId": "call-1", "toolName": "extract_documents", "at": body["toolCallLog"][0]["at"]}]


def test_set_working_state_round_trips():
    run_store.create_run("run-4", "IN")
    run_store.set_working_state("run-4", {"tradingName": "Acme"})
    assert run_store.to_dict(run_store.get_run("run-4"))["workingState"] == {"tradingName": "Acme"}


def test_run_survives_a_fresh_engine_connection():
    """Simulates a process restart: a brand new engine object pointed at the same sqlite file
    must still read back everything written through the old one."""
    run_store.create_run("run-5", "IN")
    run_store.append_stage_result("run-5", "extract", {})
    run_store.update_status("run-5", "running")

    run_store.reset_engine_for_tests()

    run = run_store.get_run("run-5")
    assert run is not None
    assert run.status == "running"
    assert len(run_store.to_dict(run)["stageResults"]) == 1


def test_mutating_unknown_run_is_a_no_op_not_an_error():
    run_store.update_status("ghost", "running")
    run_store.append_stage_result("ghost", "extract", {})
    run_store.append_tool_call("ghost", "call-1", "extract_documents")
    run_store.set_working_state("ghost", {})
    assert run_store.get_run("ghost") is None


def test_list_runs_orders_most_recently_updated_first():
    run_store.create_run("run-a", "IN")
    run_store.create_run("run-b", "IN")
    run_store.update_status("run-a", "running")  # bumps run-a's updated_at past run-b's

    runs = run_store.list_runs()
    ids = [r.run_id for r in runs]
    assert ids.index("run-a") < ids.index("run-b")


def test_list_runs_respects_limit():
    for i in range(5):
        run_store.create_run(f"run-limit-{i}", "IN")
    assert len(run_store.list_runs(limit=3)) == 3


def test_to_summary_dict_reports_counts_not_full_payloads():
    run_store.create_run("run-6", "IN")
    run_store.append_stage_result("run-6", "extract", {"fieldCount": 19})
    run_store.append_tool_call("run-6", "call-1", "extract_documents")

    summary = run_store.to_summary_dict(run_store.get_run("run-6"))
    assert summary["stageCount"] == 1
    assert summary["toolCallCount"] == 1
    assert "stageResults" not in summary
    assert "toolCallLog" not in summary
    assert "workingState" not in summary
