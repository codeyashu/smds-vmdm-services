import json
import tempfile
from pathlib import Path

import pytest

from app.web_trust.feedback_store import append_feedback, read_recent_feedback, record_web_trust_feedback
from app.web_trust.feedback_store import WebTrustFeedbackRequest
from app.web_trust.learning import get_learning_hints


@pytest.fixture
def feedback_dir(monkeypatch: pytest.MonkeyPatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("WEB_TRUST_FEEDBACK_DIR", tmp)
        yield Path(tmp)


def test_feedback_round_trip(feedback_dir: Path):
    append_feedback(
        {
            "reviewId": "review-1",
            "rating": "not_helpful",
            "countryCode": "IN",
            "connectorIds": ["in_gstin"],
        }
    )
    rows = read_recent_feedback(country_code="IN")
    assert len(rows) == 1
    assert rows[0]["rating"] == "not_helpful"


def test_learning_hints_after_negative_feedback(feedback_dir: Path):
    for _ in range(10):
        append_feedback(
            {
                "reviewId": "review-x",
                "rating": "not_helpful",
                "countryCode": "IN",
                "connectorIds": ["in_gstin"],
            }
        )
    hints = get_learning_hints("IN", ["in_gstin"])
    assert len(hints) >= 1


def test_record_feedback_endpoint_shape(feedback_dir: Path):
    response = record_web_trust_feedback(
        WebTrustFeedbackRequest(
            reviewId="abc",
            rating="helpful",
            countryCode="IN",
            mode="create",
            trigger="submit",
            connectorIds=["in_gstin"],
        )
    )
    assert response.recorded is True
    assert response.feedbackId
