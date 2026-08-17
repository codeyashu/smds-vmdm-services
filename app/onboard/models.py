"""The durable onboard run record — survives a services restart, unlike session_store's TTL cache."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


class OnboardRun(SQLModel, table=True):
    # run_id == the onboard session_id — one durable run per onboarding session in v1.
    # A separate run_id would only earn its keep once a session can host more than one run,
    # which isn't a case this pipeline has yet.
    run_id: str = Field(primary_key=True)
    country_code: str
    status: str = "pending"  # pending | running | done | failed
    autonomy: str = "supervised"
    # JSON-encoded lists/dicts — SQLite has no native array/object column; kept as text and
    # (de)serialized in run_store rather than reaching for a JSON column type this project
    # doesn't otherwise use.
    working_state_json: str = "{}"
    stage_results_json: str = "[]"
    tool_call_log_json: str = "[]"
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    expires_at: datetime | None = None
