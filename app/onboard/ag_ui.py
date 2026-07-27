"""AG-UI compatible event helpers for onboard orchestration."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def ag_ui_event(event_type: str, session_id: str, payload: dict[str, Any] | None = None) -> str:
    body = {
        "type": event_type,
        "sessionId": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": payload or {},
    }
    return f"data: {json.dumps(body)}\n\n"
