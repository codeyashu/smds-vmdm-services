"""Structured logging with a PII guard.

These documents carry PAN, GSTIN, and bank-account numbers. Logs must NEVER contain
extracted values, filenames, or OCR text — only doc type, page counts, latency, confidence.
The redactor drops any key that looks like a value carrier and masks identifier-shaped strings.
"""

from __future__ import annotations

import logging
import re

import structlog

_ID_LIKE = re.compile(r"\b([A-Z]{5}[0-9]{4}[A-Z]|[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z])\b")

_BLOCKED_KEYS = frozenset(
    {"value", "values", "snippet", "text", "ocr_text", "filename", "file_name", "patches", "raw"}
)


def _redact(_logger, _method, event_dict: dict) -> dict:
    for key in list(event_dict.keys()):
        if key in _BLOCKED_KEYS:
            event_dict[key] = "<redacted>"
        elif isinstance(event_dict[key], str):
            event_dict[key] = _ID_LIKE.sub("<id>", event_dict[key])
    return event_dict


def configure_logging(level: int = logging.INFO) -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            _redact,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "docai"):
    return structlog.get_logger(name)
