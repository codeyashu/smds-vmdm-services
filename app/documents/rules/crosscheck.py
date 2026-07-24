"""Deterministic cross-checks over extracted values (plan §1.3).

Pure functions, no network, no Azure. These are the primary defence against a hallucinated
LLM value: an identifier that fails an internal consistency check is flagged so the portal
never pre-selects it. Nothing here mutates input.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.documents.rules.in_patterns import (
    GSTIN_ANY_RE,
    IFSC_RE,
    PAN_RE,
    is_natural_person,
    normalize_identifier,
    pan_from_gstin,
    region_for_gstin,
)

CheckStatus = Literal["pass", "warn", "fail", "skip"]


@dataclass(frozen=True)
class CrossCheck:
    id: str
    status: CheckStatus
    message: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {"id": self.id, "status": self.status, "message": self.message}


def check_gstin_contains_pan(gstin: str | None, pan: str | None) -> CrossCheck:
    """GSTIN chars 3-12 must equal the standalone PAN when both are present."""
    if not gstin or not pan:
        return CrossCheck("gstin_contains_pan", "skip")
    embedded = pan_from_gstin(gstin)
    if embedded is None:
        return CrossCheck(
            "gstin_contains_pan",
            "warn",
            "Could not read a PAN out of the GSTIN — verify the GSTIN.",
        )
    if embedded == normalize_identifier(pan):
        return CrossCheck("gstin_contains_pan", "pass")
    return CrossCheck(
        "gstin_contains_pan",
        "fail",
        f"GSTIN embeds PAN {embedded}, but the PAN document reads "
        f"{normalize_identifier(pan)} — they must match.",
    )


def check_gstin_state_vs_region(gstin: str | None, region_code: str | None) -> CrossCheck:
    """GSTIN state code (chars 1-2) must agree with the address region."""
    if not gstin or not region_code:
        return CrossCheck("gstin_state_vs_address_region", "skip")
    derived = region_for_gstin(gstin)
    if derived is None:
        return CrossCheck("gstin_state_vs_address_region", "skip")
    if derived.upper() == region_code.strip().upper():
        return CrossCheck("gstin_state_vs_address_region", "pass")
    return CrossCheck(
        "gstin_state_vs_address_region",
        "warn",
        f"GSTIN state code implies region {derived}, address reads "
        f"{region_code.strip().upper()}.",
    )


def check_pan_entity_type(pan: str | None, claimed_natural_person: bool | None) -> CrossCheck:
    """PAN 4th char determines natural-person; warn if a claimed value disagrees."""
    if not pan:
        return CrossCheck("pan_entity_type", "skip")
    derived = is_natural_person(pan)
    if derived is None:
        return CrossCheck("pan_entity_type", "warn", "PAN 4th character is unrecognised.")
    if claimed_natural_person is None or claimed_natural_person == derived:
        return CrossCheck("pan_entity_type", "pass")
    return CrossCheck(
        "pan_entity_type",
        "warn",
        f"PAN 4th character implies isNaturalPerson={derived}, "
        f"but the document/context says {claimed_natural_person}.",
    )


def check_ifsc_shape(ifsc: str | None) -> CrossCheck:
    if not ifsc:
        return CrossCheck("ifsc_shape", "skip")
    v = normalize_identifier(ifsc)
    if IFSC_RE.match(v):
        return CrossCheck("ifsc_shape", "pass")
    return CrossCheck(
        "ifsc_shape",
        "fail",
        "IFSC must be 4 letters, then 0, then 6 alphanumerics (e.g. HDFC0001234).",
    )


def check_pan_shape(pan: str | None) -> CrossCheck:
    if not pan:
        return CrossCheck("pan_shape", "skip")
    return CrossCheck(
        "pan_shape",
        "pass" if PAN_RE.match(normalize_identifier(pan)) else "fail",
        None if PAN_RE.match(normalize_identifier(pan)) else "PAN must match LLLLLNNNNL.",
    )


def check_gstin_shape(gstin: str | None) -> CrossCheck:
    if not gstin:
        return CrossCheck("gstin_shape", "skip")
    return CrossCheck(
        "gstin_shape",
        "pass" if GSTIN_ANY_RE.match(normalize_identifier(gstin)) else "fail",
        None if GSTIN_ANY_RE.match(normalize_identifier(gstin)) else "GSTIN shape not recognised.",
    )


@dataclass(frozen=True)
class ExtractedIdentity:
    """The minimal set the cross-checks operate on, pulled from one or more documents."""

    pan: str | None = None
    gstin: str | None = None
    ifsc: str | None = None
    region_code: str | None = None
    is_natural_person: bool | None = None


def run_all(identity: ExtractedIdentity) -> list[CrossCheck]:
    """Run every applicable check. `skip` results are dropped from the returned list."""
    checks = [
        check_pan_shape(identity.pan),
        check_gstin_shape(identity.gstin),
        check_ifsc_shape(identity.ifsc),
        check_gstin_contains_pan(identity.gstin, identity.pan),
        check_gstin_state_vs_region(identity.gstin, identity.region_code),
        check_pan_entity_type(identity.pan, identity.is_natural_person),
    ]
    return [c for c in checks if c.status != "skip"]


def has_blocking_failure(checks: list[CrossCheck]) -> bool:
    return any(c.status == "fail" for c in checks)
