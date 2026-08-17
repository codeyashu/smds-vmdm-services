"""Doc-type listing — now a thin, ordered read of the same requirements store the admin
CRUD API writes to (see app/api/v1/requirements.py), rather than a hardcoded list.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select

from app.documents.mapping.field_paths import WRITABLE_DOC_TYPES
from app.documents.playbook.config_store import load_country_playbook
from app.requirements.models import DocumentRequirement
from app.requirements.store import get_engine

router = APIRouter(prefix="/v1", tags=["doctypes"])


def _doctypes_from_playbook(country: str) -> list[dict]:
    book = load_country_playbook(country)
    if book is None:
        return []
    return [
        {
            "id": doc.doc_type,
            "label": doc.doc_type.replace(f"{country}_", "").replace("_", " ").title(),
            "tier": 1 if doc.writable else 2,
        }
        for doc in book.documents
    ]


@router.get("/doctypes")
async def doctypes(country: str = "IN"):
    normalized = country.strip().upper()
    if normalized != "IN":
        doc_types = _doctypes_from_playbook(normalized)
        if not doc_types:
            raise HTTPException(
                status_code=422,
                detail=f"country={normalized} is not supported. Supported: IN, CN, AE, US, GB.",
            )
        return {"country": normalized, "docTypes": doc_types}
    with Session(get_engine()) as session:
        rows = session.exec(
            select(DocumentRequirement)
            .where(DocumentRequirement.country_code == normalized)
            .order_by(DocumentRequirement.sort_order)
        ).all()
        # tier 1 = the extractor has an ingest write target for this doc type; tier 2 = it is
        # recognised but only ever surfaced as `unmapped`. NOT derived from is_mandatory: that
        # flag is admin-editable and says nothing about whether a write path exists.
        doc_types = [
            {
                "id": r.doc_type,
                "label": r.label,
                "tier": 1 if r.doc_type in WRITABLE_DOC_TYPES else 2,
            }
            for r in rows
        ]
    return {"country": normalized, "docTypes": doc_types}
