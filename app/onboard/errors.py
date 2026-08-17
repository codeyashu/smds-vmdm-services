"""Typed error taxonomy for onboard stages and routes — mirrors the codes in the portal's
src/lib/agent-onboard/errors.ts so a failure means the same thing on both sides of the BFF.
"""

from __future__ import annotations

from typing import Any, Literal

OnboardErrorCode = Literal[
    "VALIDATION_FAILED",
    "DUPLICATE_BLOCK",
    "APPROVAL_REQUIRED",
    "RULE_SET_UNAVAILABLE",
    "UPSTREAM_UNAVAILABLE",
    "NOT_PERMITTED",
]

_HTTP_STATUS: dict[str, int] = {
    "VALIDATION_FAILED": 422,
    "DUPLICATE_BLOCK": 409,
    "APPROVAL_REQUIRED": 428,
    "RULE_SET_UNAVAILABLE": 503,
    "UPSTREAM_UNAVAILABLE": 503,
    "NOT_PERMITTED": 403,
}

_RETRYABLE: dict[str, bool] = {
    "VALIDATION_FAILED": False,
    "DUPLICATE_BLOCK": False,
    "APPROVAL_REQUIRED": False,
    "RULE_SET_UNAVAILABLE": False,
    "UPSTREAM_UNAVAILABLE": True,
    "NOT_PERMITTED": False,
}


class OnboardError(Exception):
    def __init__(self, code: OnboardErrorCode, message: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}

    @property
    def http_status(self) -> int:
        return _HTTP_STATUS[self.code]

    @property
    def retryable(self) -> bool:
        return _RETRYABLE[self.code]

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "detail": self.detail,
        }
