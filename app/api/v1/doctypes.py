"""Doc-type listing — now a thin, ordered read of the same requirements store the admin
CRUD API writes to (see app/api/v1/requirements.py), rather than a hardcoded list.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select

from app.requirements.models import DocumentRequirement
from app.requirements.store import get_engine

router = APIRouter(prefix="/v1", tags=["doctypes"])


@router.get("/doctypes")
async def doctypes(country: str = "IN"):
    normalized = country.strip().upper()
    if normalized != "IN":
        raise HTTPException(status_code=422, detail="Only country=IN is supported in phase 1.")
    with Session(get_engine()) as session:
        rows = session.exec(
            select(DocumentRequirement)
            .where(DocumentRequirement.country_code == normalized)
            .order_by(DocumentRequirement.sort_order)
        ).all()
        doc_types = [{"id": r.doc_type, "label": r.label, "tier": 1 if r.is_mandatory else 2} for r in rows]
    return {"country": normalized, "docTypes": doc_types}
