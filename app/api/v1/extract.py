"""Extraction endpoints.

The OCR + LLM backends are resolved from the provider factories, so this endpoint works the
same against a paid Azure stack or a free local one (PyMuPDF + Ollama). When no LLM provider
is available it returns 503 — the app still boots and the pure surface stays testable with
zero configuration. Wiring the real pipeline behind these providers is P0's networked step.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.config import get_settings
from app.core.logging import get_logger
from app.documents.ingestion.validate_upload import UploadRejected, validate_upload
from app.providers.llm.factory import get_llm_provider
from app.providers.ocr.factory import get_ocr_provider

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

    ocr = get_ocr_provider()
    llm = get_llm_provider()
    if ocr is None or llm is None:
        raise HTTPException(
            status_code=503,
            detail="No extraction backend available — configure an OCR and LLM provider "
            "(DOCAI_OCR_PROVIDER / DOCAI_LLM_PROVIDER).",
        )

    document_id = f"eph_{uuid.uuid4().hex[:12]}"
    log.info("extract.request", document_id=document_id, mime=validated.mime, size=validated.size)

    # P0-networked: from app.documents.extract.pipeline import run_extraction; return await run_extraction(...)
    raise HTTPException(status_code=501, detail="Extraction pipeline not yet wired (P0 networked step).")
