"""Upload validation — pure, no network."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.documents.ingestion.validate_upload import UploadRejected, sniff_mime, validate_upload

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_sniff_mime_recognises_pdf_jpeg_png_docx():
    assert sniff_mime(b"%PDF-1.4 ...") == "application/pdf"
    assert sniff_mime(b"\xff\xd8\xff\xe0...") == "image/jpeg"
    assert sniff_mime(b"\x89PNG\r\n\x1a\n...") == "image/png"
    assert sniff_mime(b"PK\x03\x04...") == DOCX_MIME


def test_sniff_mime_returns_none_for_unrecognised_bytes():
    assert sniff_mime(b"not a real document") is None


def test_validate_upload_accepts_docx_by_default():
    content = b"PK\x03\x04" + b"0" * 100
    validated = validate_upload(content, Settings())
    assert validated.mime == DOCX_MIME


def test_validate_upload_rejects_empty_file():
    with pytest.raises(UploadRejected) as exc_info:
        validate_upload(b"", Settings())
    assert exc_info.value.status_code == 400


def test_validate_upload_rejects_oversize():
    with pytest.raises(UploadRejected) as exc_info:
        validate_upload(b"%PDF-" + b"0" * 100, Settings(max_file_bytes=10))
    assert exc_info.value.status_code == 413


def test_validate_upload_rejects_unrecognised_type():
    with pytest.raises(UploadRejected) as exc_info:
        validate_upload(b"not a real document", Settings())
    assert exc_info.value.status_code == 415
