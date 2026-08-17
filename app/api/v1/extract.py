"""Extraction endpoint — validates the upload, then runs it through the extraction pipeline
(OCR -> classify hint -> single LLM envelope call -> cross-checks -> portal-shaped patches).
"""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.core.auth import require_service_bearer
from app.core.config import get_settings
from app.core.logging import get_logger
from app.documents.extract.errors import ExtractionUnavailable, ExtractionUpstreamError
from app.documents.extract.pipeline import run_extraction
from app.documents.extract.supported_countries import is_supported_extraction_country
from app.documents.ingestion.validate_upload import UploadRejected, validate_upload

router = APIRouter(prefix="/v1", tags=["extract"])
log = get_logger()


def _ensure_supported_country(country_code: str) -> str:
    normalized = country_code.strip().upper()
    if not is_supported_extraction_country(normalized):
        raise HTTPException(
            status_code=422,
            detail=f"countryCode={normalized} is not supported. Supported: IN, CN, AE, US, GB.",
        )
    return normalized


@router.post("/extract/batch", dependencies=[Depends(require_service_bearer)])
async def extract_batch(
    files: list[UploadFile] = File(...),
    countryCode: str = Form(...),
    docTypeHint: str | None = Form(default=None),
):
    settings = get_settings()
    normalized_country = _ensure_supported_country(countryCode)
    if len(files) > settings.max_batch_files:
        raise HTTPException(
            status_code=413,
            detail=f"At most {settings.max_batch_files} files per batch.",
        )

    results: list[dict] = []
    seen_hashes: dict[str, str] = {}
    for upload in files:
        content = await upload.read()
        content_hash = hashlib.sha256(content).hexdigest()
        if content_hash in seen_hashes:
            prior_id = seen_hashes[content_hash]
            results.append(
                {
                    "documentId": prior_id,
                    "docType": "UNKNOWN",
                    "docTypeConfidence": 0.0,
                    "patches": [],
                    "crossChecks": [],
                    "warnings": [f"Duplicate upload skipped (identical to {prior_id})."],
                    "unmapped": [],
                }
            )
            continue

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
            result = await run_extraction(
                validated.content,
                validated.mime,
                normalized_country,
                doc_type_hint=docTypeHint,
                filename=upload.filename,
            )
            seen_hashes[content_hash] = result.document_id
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

    normalized_country = _ensure_supported_country(countryCode)

    try:
        result = await run_extraction(
            validated.content,
            validated.mime,
            normalized_country,
            doc_type_hint=docType,
            filename=file.filename,
        )
    except ExtractionUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ExtractionUpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    log.info("extract.request", document_id=result.document_id, mime=validated.mime, size=validated.size)
    return result.as_dict()
