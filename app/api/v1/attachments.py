"""Vendor attachment API — migrated from portal BFF."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response

from app.attachments.store import (
    delete_attachment,
    list_attachments,
    patch_attachment_extraction_cache,
    read_attachment_file,
    save_attachment,
)
from app.core.auth import require_service_bearer

router = APIRouter(prefix="/v1", tags=["attachments"], dependencies=[Depends(require_service_bearer)])


@router.get("/attachments")
async def list_route(scopeKey: str = Query(..., min_length=1)) -> dict[str, Any]:
    items = await list_attachments(scopeKey)
    return {"items": items}


@router.post("/attachments")
async def upload_route(
    scopeKey: str = Form(...),
    file: UploadFile = File(...),
    docTypeHint: str | None = Form(default=None),
    classifiedDocType: str | None = Form(default=None),
    status: str | None = Form(default=None),
) -> dict[str, Any]:
    content = await file.read()
    try:
        record = await save_attachment(
            scopeKey,
            file.filename or "upload",
            file.content_type or "application/octet-stream",
            content,
            doc_type_hint=docTypeHint,
            classified_doc_type=classifiedDocType,
            status=status or "attached",
        )
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    return record


@router.get("/attachments/{record_id}")
async def read_route(
    record_id: str,
    scopeKey: str = Query(..., min_length=1),
) -> Response:
    try:
        content, record = await read_attachment_file(scopeKey, record_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Attachment not found") from None
    return Response(
        content=content,
        media_type=str(record.get("mimeType") or "application/octet-stream"),
        headers={"Content-Disposition": f'inline; filename="{record.get("filename") or "file"}"'},
    )


@router.delete("/attachments/{record_id}")
async def delete_route(record_id: str, scopeKey: str = Query(..., min_length=1)) -> dict[str, Any]:
    ok = await delete_attachment(scopeKey, record_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return {"deleted": True}


@router.put("/attachments/{record_id}/extraction-cache")
async def patch_extraction_cache_route(
    record_id: str,
    scopeKey: str = Query(..., min_length=1),
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cache = (body or {}).get("extractionCache")
    if not isinstance(cache, dict):
        raise HTTPException(status_code=400, detail="extractionCache object required")
    record = await patch_attachment_extraction_cache(scopeKey, record_id, cache)
    if not record:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return {"item": record}
