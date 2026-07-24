"""Upload validation: MIME allowlist, size cap, and magic-byte sniff.

The declared multipart content-type is not trusted — the first bytes decide the real type.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings

# Magic byte signatures for the allowlisted types.
_SIGNATURES: list[tuple[bytes, str]] = [
    (b"%PDF-", "application/pdf"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
]


class UploadRejected(Exception):
    def __init__(self, message: str, status_code: int = 415):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class ValidatedUpload:
    content: bytes
    mime: str
    size: int


def sniff_mime(content: bytes) -> str | None:
    for sig, mime in _SIGNATURES:
        if content.startswith(sig):
            return mime
    return None


def validate_upload(content: bytes, settings: Settings) -> ValidatedUpload:
    size = len(content)
    if size == 0:
        raise UploadRejected("Empty file.", 400)
    if size > settings.max_file_bytes:
        raise UploadRejected(
            f"File exceeds {settings.max_file_bytes // (1024 * 1024)} MB limit.", 413
        )
    mime = sniff_mime(content)
    if mime is None or mime not in settings.allowed_mime:
        raise UploadRejected(
            f"Unsupported file type. Allowed: {', '.join(settings.allowed_mime)}.", 415
        )
    return ValidatedUpload(content=content, mime=mime, size=size)
