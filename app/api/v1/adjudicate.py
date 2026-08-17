"""Document bundle adjudication — cross-document validation and conflict resolution."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.auth import require_service_bearer
from app.documents.playbook.config_store import list_playbook_countries, playbook_as_dict
from app.documents.validation.adjudicate import adjudicate_bundle
from app.documents.validation.document_corroboration import corroborate_documents_async
from app.documents.validation.types import AdjudicateRequest

router = APIRouter(prefix="/v1", tags=["documents"])


@router.get("/document-playbook")
async def get_document_playbook(
    country: str = Query(..., min_length=2, max_length=2),
    _auth: None = Depends(require_service_bearer),
):
    data = playbook_as_dict(country)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"No document playbook for country {country.strip().upper()}.",
        )
    return data


@router.get("/document-playbook/apply-config")
async def get_document_apply_config(
    country: str = Query(..., min_length=2, max_length=2),
    _auth: None = Depends(require_service_bearer),
):
    from app.documents.playbook.apply_config import load_apply_config

    data = load_apply_config(country)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"No document playbook for country {country.strip().upper()}.",
        )
    return data


@router.get("/document-playbook/countries")
async def list_document_playbook_countries(_auth: None = Depends(require_service_bearer)):
    return {"countries": list_playbook_countries()}


class ApplyConfigPutBody(BaseModel):
    config: dict[str, Any]


class ApplyConfigMutationBody(BaseModel):
    action: str
    doc: dict[str, Any] | None = None
    docType: str | None = None
    attribute: dict[str, Any] | None = None
    attributeId: str | None = None


@router.put("/document-playbook/apply-config")
async def put_document_apply_config(
    country: str = Query(..., min_length=2, max_length=2),
    body: ApplyConfigPutBody = ...,
    _auth: None = Depends(require_service_bearer),
):
    from app.documents.playbook.apply_mutations import save_country_apply_config

    raw = dict(body.config)
    raw["countryCode"] = country.strip().upper()
    return save_country_apply_config(raw)


@router.post("/document-playbook/apply-config")
async def mutate_document_apply_config(
    country: str = Query(..., min_length=2, max_length=2),
    body: ApplyConfigMutationBody = ...,
    _auth: None = Depends(require_service_bearer),
):
    from app.documents.playbook.apply_mutations import (
        remove_extraction_attribute,
        remove_extraction_doc,
        upsert_extraction_attribute,
        upsert_extraction_doc,
    )

    action = body.action
    if action == "upsertDoc":
        if not body.doc:
            raise HTTPException(status_code=400, detail="doc is required")
        return upsert_extraction_doc(country, body.doc)
    if action == "removeDoc":
        if not body.docType:
            raise HTTPException(status_code=400, detail="docType is required")
        return remove_extraction_doc(country, body.docType)
    if action == "upsertAttribute":
        if not body.docType or not body.attribute:
            raise HTTPException(status_code=400, detail="docType and attribute are required")
        return upsert_extraction_attribute(country, body.docType, body.attribute, body.attributeId)
    if action == "removeAttribute":
        if not body.docType or not body.attributeId:
            raise HTTPException(status_code=400, detail="docType and attributeId are required")
        return remove_extraction_attribute(country, body.docType, body.attributeId)
    raise HTTPException(status_code=400, detail="Unknown action")


@router.post("/documents/adjudicate", dependencies=[Depends(require_service_bearer)])
async def adjudicate_documents(body: AdjudicateRequest):
    existing = [doc.model_dump(by_alias=True) for doc in body.existing_documents]
    result = adjudicate_bundle(
        body.country_code,
        body.extractions,
        body.form_snapshot,
        existing,
    )
    corroboration = await corroborate_documents_async(
        country_code=body.country_code,
        extractions=body.extractions,
        form_snapshot=body.form_snapshot,
        adjudication=result,
    )
    payload = result.model_copy(update={"document_corroboration": corroboration}).as_dict()
    return payload


@router.post("/documents/adjudication-feedback", dependencies=[Depends(require_service_bearer)])
async def adjudication_feedback_route(body: dict):
    from app.documents.validation.feedback_store import (
        AdjudicationFeedbackRequest,
        record_adjudication_feedback,
    )

    parsed = AdjudicationFeedbackRequest.model_validate(body)
    response = record_adjudication_feedback(parsed)
    return response.model_dump(by_alias=True)
