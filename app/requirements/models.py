"""The document-requirements rule engine's one table: which document types a country expects."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DocumentRequirement(SQLModel, table=True):
    # A country must not list the same doc type twice — /v1/doctypes would emit it twice and
    # the checklist UI would render a duplicate row. Enforced here as the backstop (and to
    # collapse write races into an IntegrityError rather than a silent duplicate); the API
    # layer pre-checks so the normal path returns a 409 instead of a 500.
    # NB: `create_all` does not ALTER pre-existing tables, so databases created before this
    # constraint was added keep relying on the API-level check alone.
    __table_args__ = (UniqueConstraint("country_code", "doc_type", name="uq_doc_requirement_country_doc_type"),)

    id: int | None = Field(default=None, primary_key=True)
    country_code: str = Field(index=True)
    doc_type: str
    label: str
    is_mandatory: bool = True
    sort_order: int = 0
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
