"""Persist steward feedback for web-trust reviews."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

WebTrustFeedbackRating = str  # helpful | not_helpful


class WebTrustFeedbackRequest(BaseModel):
    reviewId: str
    rating: str = Field(pattern=r"^(helpful|not_helpful)$")
    comment: str | None = Field(default=None, max_length=2000)
    countryCode: str
    trustScore: int | None = None
    trustBand: str | None = None
    mode: str = Field(pattern=r"^(create|edit)$")
    trigger: str = Field(pattern=r"^(submit|explicit)$")
    connectorIds: list[str] = Field(default_factory=list)


class WebTrustFeedbackResponse(BaseModel):
    feedbackId: str
    recorded: bool = True


def _feedback_dir() -> Path:
    env = os.getenv("WEB_TRUST_FEEDBACK_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "data" / "web-trust-feedback"


def _feedback_file() -> Path:
    path = _feedback_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path / "feedback.jsonl"


def append_feedback(entry: dict[str, Any]) -> str:
    feedback_id = str(uuid4())
    row = {
        "feedbackId": feedback_id,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        **entry,
    }
    with _feedback_file().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return feedback_id


def read_recent_feedback(*, country_code: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
    path = _feedback_file()
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if country_code and row.get("countryCode", "").upper() != country_code.upper():
            continue
        rows.append(row)
    return rows[-limit:]


def record_web_trust_feedback(body: WebTrustFeedbackRequest) -> WebTrustFeedbackResponse:
    feedback_id = append_feedback(body.model_dump())
    _emit_langfuse_feedback(body.reviewId, body.rating, body.comment)
    return WebTrustFeedbackResponse(feedbackId=feedback_id)


def _emit_langfuse_feedback(review_id: str, rating: str, comment: str | None) -> None:
    try:
        from app.observability.langfuse_trace import get_langfuse_client

        client = get_langfuse_client()
        if client is None:
            return
        score_value = 1 if rating == "helpful" else 0
        client.create_score(
            trace_id=review_id,
            name="web_trust_review_helpful",
            value=score_value,
            comment=comment,
        )
        client.flush()
    except Exception:  # noqa: BLE001
        return
