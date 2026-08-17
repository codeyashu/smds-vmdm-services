"""Aggregate steward feedback into playbook tuning hints."""

from __future__ import annotations

from collections import defaultdict

from app.web_trust.feedback_store import read_recent_feedback

MIN_SAMPLES = 8
NEGATIVE_RATE_THRESHOLD = 0.4


def get_learning_hints(country_code: str, connector_ids: list[str]) -> list[str]:
    rows = read_recent_feedback(country_code=country_code)
    if not rows:
        return []

    hints: list[str] = []
    by_connector: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        rating = row.get("rating")
        if not rating:
            continue
        for connector_id in row.get("connectorIds") or []:
            by_connector[str(connector_id)].append(str(rating))

    for connector_id in connector_ids:
        ratings = by_connector.get(connector_id, [])
        if len(ratings) < MIN_SAMPLES:
            continue
        negative = sum(1 for rating in ratings if rating == "not_helpful")
        rate = negative / len(ratings)
        if rate >= NEGATIVE_RATE_THRESHOLD:
            hints.append(
                f"Stewards often mark {connector_id} checks as not helpful ({int(rate * 100)}% "
                f"of recent {country_code} reviews) — consider uploading supporting documents."
            )

    country_rows = rows[-MIN_SAMPLES:]
    if len(country_rows) >= MIN_SAMPLES:
        country_negative = sum(1 for row in country_rows if row.get("rating") == "not_helpful")
        country_rate = country_negative / len(country_rows)
        if country_rate >= NEGATIVE_RATE_THRESHOLD:
            hints.append(
                f"Recent {country_code} web reviews are frequently rated not helpful — "
                "results may be too shallow for this country; manual review is recommended."
            )

    return hints[:3]
