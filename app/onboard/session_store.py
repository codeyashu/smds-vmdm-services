"""Ephemeral onboard session store with TTL."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4


@dataclass
class OnboardSession:
    session_id: str
    country_code: str
    steward_id: str | None
    created_at: datetime
    expires_at: datetime
    state: dict[str, Any] = field(default_factory=dict)


SESSION_TTL = timedelta(hours=1)
_sessions: dict[str, OnboardSession] = {}


def _purge_expired() -> None:
    now = datetime.now(timezone.utc)
    expired = [sid for sid, s in _sessions.items() if s.expires_at <= now]
    for sid in expired:
        _sessions.pop(sid, None)


def create_session(country_code: str, steward_id: str | None = None) -> OnboardSession:
    _purge_expired()
    now = datetime.now(timezone.utc)
    session = OnboardSession(
        session_id=str(uuid4()),
        country_code=country_code,
        steward_id=steward_id,
        created_at=now,
        expires_at=now + SESSION_TTL,
    )
    _sessions[session.session_id] = session
    return session


def get_session(session_id: str) -> OnboardSession | None:
    _purge_expired()
    return _sessions.get(session_id)


def update_session_state(session_id: str, patch: dict[str, Any]) -> None:
    session = get_session(session_id)
    if session:
        session.state.update(patch)
