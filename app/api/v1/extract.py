"""Extraction endpoint — validates the upload, then runs it through the extraction pipeline
(OCR -> classify hint -> single LLM envelope call -> cross-checks -> portal-shaped patches).
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.config import get_settings
from app.core.logging import get_logger
from app.documents.extract.errors import ExtractionUnavailable, ExtractionUpstreamError
from app.documents.extract.pipeline import run_extraction
from app.documents.ingestion.validate_upload import UploadRejected, validate_upload

router = APIRouter(prefix="/v1", tags=["extract"])
log = get_logger()


@router.post("/extract")
async def extract(
    file: UploadFile = File(...),
    countryCode: str = Form(...),
    docType: str | None = Form(default=None),
):
    settings = get_settings()
    content = await file.read()
    try:
        validated = validate_upload(content, settings)
    except UploadRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    if countryCode.strip().upper() != "IN":
        raise HTTPException(status_code=422, detail="Only countryCode=IN is supported in phase 1.")

    try:
        result = await run_extraction(validated.content, validated.mime, countryCode)
    except ExtractionUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ExtractionUpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    log.info("extract.request", document_id=result.document_id, mime=validated.mime, size=validated.size)
    return result.as_dict()
