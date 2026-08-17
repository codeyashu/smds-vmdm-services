"""SQLite-backed durable run record — status, working state, stage results, tool-call log.

Distinct from session_store's in-memory TTL cache: session_store is the ephemeral chat/run
working area for a single process's lifetime, this is the record that has to survive a
restart so a run can be resumed or read back (`GET /v1/onboard/runs/{run_id}`) after one.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlmodel import Session, SQLModel, create_engine, desc, select

from app.onboard.models import OnboardRun

RUN_TTL = timedelta(days=90)

_engine = None


def _db_path() -> str:
    path = os.getenv("DOCAI_DB_PATH", "./data/docai.db")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return path


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(f"sqlite:///{_db_path()}", connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(_engine)
    return _engine


def reset_engine_for_tests() -> None:
    global _engine
    _engine = None


def create_run(run_id: str, country_code: str, autonomy: str = "supervised") -> OnboardRun:
    now = datetime.now(timezone.utc)
    run = OnboardRun(
        run_id=run_id,
        country_code=country_code,
        status="pending",
        autonomy=autonomy,
        created_at=now,
        updated_at=now,
        expires_at=now + RUN_TTL,
    )
    with Session(get_engine()) as session:
        session.add(run)
        session.commit()
        session.refresh(run)
    return run


def get_run(run_id: str) -> OnboardRun | None:
    with Session(get_engine()) as session:
        return session.exec(select(OnboardRun).where(OnboardRun.run_id == run_id)).first()


def list_runs(limit: int = 50) -> list[OnboardRun]:
    """Most-recently-updated first. No filtering by consumer/starter — that identity doesn't
    exist yet (no REST agent API or MCP consumers registered), so every run today is portal-
    started; see docs/architecture/decisions/0012-propose-commit-durable-run.md."""
    with Session(get_engine()) as session:
        return list(
            session.exec(select(OnboardRun).order_by(desc(OnboardRun.updated_at)).limit(limit)).all()
        )


def _load(session: Session, run_id: str) -> OnboardRun | None:
    return session.exec(select(OnboardRun).where(OnboardRun.run_id == run_id)).first()


def update_status(run_id: str, status: str) -> None:
    with Session(get_engine()) as session:
        run = _load(session, run_id)
        if run is None:
            return
        run.status = status
        run.updated_at = datetime.now(timezone.utc)
        session.add(run)
        session.commit()


def set_working_state(run_id: str, working_state: dict[str, Any]) -> None:
    with Session(get_engine()) as session:
        run = _load(session, run_id)
        if run is None:
            return
        run.working_state_json = json.dumps(working_state)
        run.updated_at = datetime.now(timezone.utc)
        session.add(run)
        session.commit()


def append_stage_result(run_id: str, stage: str, detail: dict[str, Any] | None = None) -> None:
    with Session(get_engine()) as session:
        run = _load(session, run_id)
        if run is None:
            return
        results = json.loads(run.stage_results_json)
        results.append(
            {
                "stage": stage,
                "detail": detail or {},
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
        run.stage_results_json = json.dumps(results)
        run.updated_at = datetime.now(timezone.utc)
        session.add(run)
        session.commit()


def append_tool_call(run_id: str, tool_call_id: str, tool_name: str) -> None:
    with Session(get_engine()) as session:
        run = _load(session, run_id)
        if run is None:
            return
        calls = json.loads(run.tool_call_log_json)
        calls.append(
            {
                "toolCallId": tool_call_id,
                "toolName": tool_name,
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
        run.tool_call_log_json = json.dumps(calls)
        run.updated_at = datetime.now(timezone.utc)
        session.add(run)
        session.commit()


def to_dict(run: OnboardRun) -> dict[str, Any]:
    return {
        "runId": run.run_id,
        "countryCode": run.country_code,
        "status": run.status,
        "autonomy": run.autonomy,
        "workingState": json.loads(run.working_state_json),
        "stageResults": json.loads(run.stage_results_json),
        "toolCallLog": json.loads(run.tool_call_log_json),
        "createdAt": run.created_at.isoformat(),
        "updatedAt": run.updated_at.isoformat(),
        "expiresAt": run.expires_at.isoformat() if run.expires_at else None,
    }


def to_summary_dict(run: OnboardRun) -> dict[str, Any]:
    """Counts, not the full JSON blobs — a list of 50 runs at full detail would be a lot of
    context for very little signal. Full detail is one GET /v1/onboard/runs/{run_id} away."""
    return {
        "runId": run.run_id,
        "countryCode": run.country_code,
        "status": run.status,
        "autonomy": run.autonomy,
        "stageCount": len(json.loads(run.stage_results_json)),
        "toolCallCount": len(json.loads(run.tool_call_log_json)),
        "createdAt": run.created_at.isoformat(),
        "updatedAt": run.updated_at.isoformat(),
    }
