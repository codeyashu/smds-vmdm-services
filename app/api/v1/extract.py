"""Extraction endpoint — validates the upload, then runs it through the extraction pipeline
(OCR -> classify hint -> single LLM envelope call -> cross-checks -> portal-shaped patches).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.core.auth import require_service_bearer
from app.core.config import get_settings
from app.core.logging import get_logger
from app.documents.extract.errors import ExtractionUnavailable, ExtractionUpstreamError
from app.documents.extract.pipeline import run_extraction
from app.documents.ingestion.validate_upload import UploadRejected, validate_upload

router = APIRouter(prefix="/v1", tags=["extract"])
log = get_logger()


@router.post("/extract/batch", dependencies=[Depends(require_service_bearer)])
async def extract_batch(
    files: list[UploadFile] = File(...),
    countryCode: str = Form(...),
    docTypeHint: str | None = Form(default=None),
):
    settings = get_settings()
    if countryCode.strip().upper() != "IN":
        raise HTTPException(status_code=422, detail="Only countryCode=IN is supported in phase 1.")
    if len(files) > settings.max_batch_files:
        raise HTTPException(
            status_code=413,
            detail=f"At most {settings.max_batch_files} files per batch.",
        )

    results: list[dict] = []
    for upload in files:
        content = await upload.read()
        try:
            validated = validate_upload(content, settings)
        except UploadRejected as exc:
            results.append(
                {
                    "documentId": "",
                    "docType": "UNKNOWN",
                    "docTypeConfidence": 0.0,
                    "patches": [],
                    "crossChecks": [],
                    "warnings": [exc.message],
                    "unmapped": [],
                }
            )
            continue

        try:
            result = await run_extraction(validated.content, validated.mime, countryCode)
            results.append(result.as_dict())
        except (ExtractionUnavailable, ExtractionUpstreamError) as exc:
            results.append(
                {
                    "documentId": "",
                    "docType": "UNKNOWN",
                    "docTypeConfidence": 0.0,
                    "patches": [],
                    "crossChecks": [],
                    "warnings": [str(exc)],
                    "unmapped": [],
                }
            )

    log.info("extract.batch", file_count=len(files), result_count=len(results), doc_type_hint=docTypeHint)
    return {"results": results}


@router.post("/extract", dependencies=[Depends(require_service_bearer)])
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
