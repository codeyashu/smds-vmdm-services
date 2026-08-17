"""Persist steward feedback on document bundle adjudication conclusions."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

Rating = Literal["helpful", "not_helpful"]


class AdjudicationFeedbackRequest(BaseModel):
    review_id: str = Field(alias="reviewId")
    country_code: str = Field(alias="countryCode")
    rating: Rating
    bundle_summary: str | None = Field(default=None, alias="bundleSummary")
    document_ids: list[str] = Field(default_factory=list, alias="documentIds")
    comment: str | None = None

    model_config = {"populate_by_name": True}


class AdjudicationFeedbackResponse(BaseModel):
    feedback_id: str = Field(alias="feedbackId")

    model_config = {"populate_by_name": True}


def _feedback_dir() -> Path:
    env = os.environ.get("DOC_ADJUDICATION_FEEDBACK_DIR", "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "data" / "doc-adjudication-feedback"


def _feedback_file() -> Path:
    path = _feedback_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path / "feedback.jsonl"


def append_feedback(entry: dict[str, Any]) -> str:
    feedback_id = str(uuid4())
    row = {
        "feedbackId": feedback_id,
        "recordedAt": datetime.now(timezone.utc).isoformat(),
        **entry,
    }
    with _feedback_file().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return feedback_id


def record_adjudication_feedback(body: AdjudicationFeedbackRequest) -> AdjudicationFeedbackResponse:
    feedback_id = append_feedback(body.model_dump(by_alias=True))
    return AdjudicationFeedbackResponse(feedbackId=feedback_id)
