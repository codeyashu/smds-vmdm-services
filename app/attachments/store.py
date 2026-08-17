"""Vendor attachment filesystem store — migrated from portal attachment-store."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_FILE_BYTES = 10 * 1024 * 1024


def _store_root() -> Path:
    env = os.getenv("VENDOR_ATTACHMENT_STORE_PATH")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "data" / "vendor-attachments"


def _scope_dir(scope_key: str) -> Path:
    safe = "".join(c if c.isalnum() or c in ":_-" else "_" for c in scope_key)
    return _store_root() / safe


def _index_path(scope_key: str) -> Path:
    return _scope_dir(scope_key) / "index.json"


def _file_path(scope_key: str, record_id: str, filename: str) -> Path:
    ext = Path(filename).suffix
    return _scope_dir(scope_key) / "files" / f"{record_id}{ext}"


async def list_attachments(scope_key: str) -> list[dict[str, Any]]:
    path = _index_path(scope_key)
    if not path.is_file():
        return []
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        return []
    return sorted(records, key=lambda r: str(r.get("createdAt") or ""), reverse=True)


async def get_attachment(scope_key: str, record_id: str) -> dict[str, Any] | None:
    for row in await list_attachments(scope_key):
        if row.get("id") == record_id:
            return row
    return None


async def save_attachment(
    scope_key: str,
    filename: str,
    mime_type: str,
    content: bytes,
    *,
    doc_type_hint: str | None = None,
    classified_doc_type: str | None = None,
    status: str = "attached",
    page_count: int | None = None,
) -> dict[str, Any]:
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("File exceeds 10 MB limit")

    record_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    record: dict[str, Any] = {
        "id": record_id,
        "scopeKey": scope_key,
        "filename": filename,
        "mimeType": mime_type,
        "sizeBytes": len(content),
        "createdAt": now,
        "status": status,
    }
    if doc_type_hint:
        record["docTypeHint"] = doc_type_hint
    if classified_doc_type:
        record["classifiedDocType"] = classified_doc_type
    if page_count is not None:
        record["pageCount"] = page_count

    scope = _scope_dir(scope_key)
    scope.mkdir(parents=True, exist_ok=True)
    (scope / "files").mkdir(exist_ok=True)
    _file_path(scope_key, record_id, filename).write_bytes(content)

    records = await list_attachments(scope_key)
    records.append(record)
    _index_path(scope_key).write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    return record


async def read_attachment_file(scope_key: str, record_id: str) -> tuple[bytes, dict[str, Any]]:
    record = await get_attachment(scope_key, record_id)
    if not record:
        raise FileNotFoundError(record_id)
    path = _file_path(scope_key, record_id, str(record.get("filename") or "file"))
    if not path.is_file():
        raise FileNotFoundError(record_id)
    return path.read_bytes(), record


async def delete_attachment(scope_key: str, record_id: str) -> bool:
    records = await list_attachments(scope_key)
    record = next((r for r in records if r.get("id") == record_id), None)
    if not record:
        return False
    path = _file_path(scope_key, record_id, str(record.get("filename") or "file"))
    if path.is_file():
        path.unlink()
    remaining = [r for r in records if r.get("id") != record_id]
    _index_path(scope_key).write_text(json.dumps(remaining, indent=2) + "\n", encoding="utf-8")
    return True


async def patch_attachment_extraction_cache(
    scope_key: str,
    record_id: str,
    extraction_cache: dict[str, Any],
) -> dict[str, Any] | None:
    records = await list_attachments(scope_key)
    updated: list[dict[str, Any]] = []
    found: dict[str, Any] | None = None
    for row in records:
        if row.get("id") == record_id:
            merged = {**row, "extractionCache": extraction_cache, "status": "extracted"}
            updated.append(merged)
            found = merged
        else:
            updated.append(row)
    if not found:
        return None
    _index_path(scope_key).write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
    return found
