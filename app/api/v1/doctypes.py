from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/v1", tags=["doctypes"])

# Tier 1 doctypes exposed to the portal in phase 1.
_IN_DOCTYPES = [
    {"id": "IN_PAN_CARD", "label": "PAN card", "tier": 1},
    {"id": "IN_GST_CERTIFICATE", "label": "GST registration certificate (REG-06)", "tier": 1},
    {"id": "IN_CANCELLED_CHEQUE", "label": "Cancelled cheque / bank letter", "tier": 1},
]


@router.get("/doctypes")
async def doctypes(country: str = "IN"):
    if country.strip().upper() != "IN":
        raise HTTPException(status_code=422, detail="Only country=IN is supported in phase 1.")
    return {"country": "IN", "docTypes": _IN_DOCTYPES}
