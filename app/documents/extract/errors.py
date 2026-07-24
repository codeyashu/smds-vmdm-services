"""Extraction pipeline errors, mapped to HTTP status codes by the API layer."""

from __future__ import annotations


class ExtractionUnavailable(Exception):
    """No OCR or LLM provider is configured. Maps to 503."""


class ExtractionUpstreamError(Exception):
    """OCR/LLM transport failed, or the LLM response never parsed after one retry. Maps to 502."""
