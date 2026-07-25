"""The document-requirements rule engine's one table: which document types a country expects."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DocumentRequirement(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    country_code: str = Field(index=True)
    doc_type: str
    label: str
    is_mandatory: bool = True
    sort_order: int = 0
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
