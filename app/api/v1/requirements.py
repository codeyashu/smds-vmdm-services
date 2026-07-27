"""Document-requirements CRUD — the admin-editable per-country checklist.

Reads are public (the checklist widget on create/edit needs them with no auth). Writes are
gated by `service_bearer_token` when one is configured — the same dev-mode-disables-auth
pattern already used for the service's other admin surface.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.auth import require_service_bearer
from app.core.config import get_settings
from app.requirements.models import DocumentRequirement
from app.requirements.store import get_engine

router = APIRouter(prefix="/v1", tags=["requirements"])


class RequirementIn(BaseModel):
    country_code: str
    doc_type: str
    label: str
    is_mandatory: bool = True
    sort_order: int = 0

    @field_validator("country_code")
    @classmethod
    def _normalize_country_code(cls, v: str) -> str:
        """Reads upper-case the country query param, so a row stored lower-case would be
        invisible from both GET endpoints forever. Normalise on the way in instead — on the
        model, so create and update stay consistent."""
        return v.strip().upper()


class RequirementOut(RequirementIn):
    id: int


def _require_bearer(authorization: str | None) -> None:
    require_service_bearer(authorization)


def _reject_duplicate(session: Session, body: RequirementIn, *, exclude_id: int | None = None) -> None:
    """409s when (country_code, doc_type) is already taken.

    `exclude_id` is the row being updated — without it a plain label edit would conflict with
    itself. `country_code` is already normalised by RequirementIn's validator, so this compares
    against stored values on the same footing.
    """
    stmt = select(DocumentRequirement).where(
        DocumentRequirement.country_code == body.country_code,
        DocumentRequirement.doc_type == body.doc_type,
    )
    if exclude_id is not None:
        stmt = stmt.where(DocumentRequirement.id != exclude_id)
    if session.exec(stmt).first() is not None:
        raise HTTPException(
            status_code=409,
            detail=f"{body.doc_type} is already configured for {body.country_code}.",
        )


def _commit_or_conflict(session: Session, body: RequirementIn) -> None:
    """Commits, translating the unique-constraint violation a concurrent writer can still
    cause between _reject_duplicate and here into the same 409 rather than a 500."""
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"{body.doc_type} is already configured for {body.country_code}.",
        ) from exc


def _to_out(row: DocumentRequirement) -> RequirementOut:
    return RequirementOut(
        id=row.id,
        country_code=row.country_code,
        doc_type=row.doc_type,
        label=row.label,
        is_mandatory=row.is_mandatory,
        sort_order=row.sort_order,
    )


@router.get("/doc-requirements", response_model=list[RequirementOut])
async def list_requirements(country: str = "IN"):
    with Session(get_engine()) as session:
        rows = session.exec(
            select(DocumentRequirement)
            .where(DocumentRequirement.country_code == country.strip().upper())
            .order_by(DocumentRequirement.sort_order)
        ).all()
        return [_to_out(row) for row in rows]


@router.post("/doc-requirements", response_model=RequirementOut, status_code=201)
async def create_requirement(body: RequirementIn, authorization: str | None = Header(default=None)):
    _require_bearer(authorization)
    with Session(get_engine()) as session:
        _reject_duplicate(session, body)
        row = DocumentRequirement(**body.model_dump())
        session.add(row)
        _commit_or_conflict(session, body)
        session.refresh(row)
        return _to_out(row)


@router.put("/doc-requirements/{requirement_id}", response_model=RequirementOut)
async def update_requirement(
    requirement_id: int, body: RequirementIn, authorization: str | None = Header(default=None)
):
    _require_bearer(authorization)
    with Session(get_engine()) as session:
        row = session.get(DocumentRequirement, requirement_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Requirement not found.")
        _reject_duplicate(session, body, exclude_id=requirement_id)
        row.country_code = body.country_code
        row.doc_type = body.doc_type
        row.label = body.label
        row.is_mandatory = body.is_mandatory
        row.sort_order = body.sort_order
        row.updated_at = datetime.now(timezone.utc)
        session.add(row)
        _commit_or_conflict(session, body)
        session.refresh(row)
        return _to_out(row)


@router.delete("/doc-requirements/{requirement_id}", status_code=204)
async def delete_requirement(requirement_id: int, authorization: str | None = Header(default=None)):
    _require_bearer(authorization)
    with Session(get_engine()) as session:
        row = session.get(DocumentRequirement, requirement_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Requirement not found.")
        session.delete(row)
        session.commit()
    return None
