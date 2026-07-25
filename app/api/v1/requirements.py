"""Document-requirements CRUD — the admin-editable per-country checklist.

Reads are public (the checklist widget on create/edit needs them with no auth). Writes are
gated by `service_bearer_token` when one is configured — the same dev-mode-disables-auth
pattern already used for the service's other admin surface.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

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


class RequirementOut(RequirementIn):
    id: int


def _require_bearer(authorization: str | None) -> None:
    token = get_settings().service_bearer_token
    if not token:
        return
    if authorization != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="Missing or invalid bearer token.")


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
        row = DocumentRequirement(**body.model_dump())
        session.add(row)
        session.commit()
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
        row.country_code = body.country_code
        row.doc_type = body.doc_type
        row.label = body.label
        row.is_mandatory = body.is_mandatory
        row.sort_order = body.sort_order
        row.updated_at = datetime.now(timezone.utc)
        session.add(row)
        session.commit()
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
