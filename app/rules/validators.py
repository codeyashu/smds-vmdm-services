"""The v2 validator registry.

Generalizes the existing in-repo idiom at ``app/documents/validation/identifiers.py:63-76``
(``_VALIDATORS`` dict + ``validate_identifier_kind``, already wiring ``pan``/``gstin``/
``ifsc``/``iban`` via ``schwifty``) rather than duplicating it — this registry *wraps* those
functions so fixing a validator there fixes it here too, and adds the metadata (``kind``,
``description``, ``countries``) the authoring UI and the LLM grounding catalog need
(design plan §B.6, §D.1).

An author picks ``validator: gstin`` instead of pasting a regex — the checksum logic lives
in tested Python, not an untestable pattern string, and it generalizes across every country
using it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from app.documents.validation.identifiers import (
    IdentifierValidation,
    validate_gstin,
    validate_iban,
    validate_ifsc,
    validate_pan,
)


@dataclass(frozen=True)
class ValidatorSpec:
    name: str
    kind: str  # "single-field" | "cross-field"
    fn: Callable[..., IdentifierValidation]
    description: str
    countries: list[str] | None = field(default=None)


def _validate_email(value: str) -> IdentifierValidation:
    v = (value or "").strip()
    ok = bool(re.match(r"^[a-zA-Z0-9+_.-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", v))
    return IdentifierValidation(ok, v, None if ok else "Not a valid email address.")


def _validate_phone_e164(value: str) -> IdentifierValidation:
    v = re.sub(r"[\s-]", "", (value or ""))
    ok = bool(re.match(r"^\+[1-9]\d{6,14}$", v))
    return IdentifierValidation(ok, v, None if ok else "Phone must be E.164 (+countrycode...).")


def _validate_luhn(value: str) -> IdentifierValidation:
    v = re.sub(r"\s", "", (value or ""))
    if not v.isdigit():
        return IdentifierValidation(False, v, "Luhn value must be numeric.")
    digits = [int(d) for d in v]
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    ok = checksum % 10 == 0
    return IdentifierValidation(ok, v, None if ok else "Luhn checksum failed.")


def _validate_bic(value: str) -> IdentifierValidation:
    v = (value or "").strip().upper()
    ok = bool(re.match(r"^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$", v))
    return IdentifierValidation(ok, v, None if ok else "BIC must be 8 or 11 alphanumeric characters.")


_REGISTRY: dict[str, ValidatorSpec] = {
    spec.name: spec
    for spec in (
        ValidatorSpec("pan", "single-field", validate_pan, "India PAN (LLLLLNNNNL)", ["IN"]),
        ValidatorSpec("gstin", "single-field", validate_gstin, "India GSTIN", ["IN"]),
        ValidatorSpec("ifsc", "single-field", validate_ifsc, "India bank IFSC code", ["IN"]),
        ValidatorSpec("iban", "single-field", validate_iban, "IBAN (via schwifty checksum)", None),
        ValidatorSpec("bic", "single-field", _validate_bic, "SWIFT/BIC bank identifier code", None),
        ValidatorSpec("email", "single-field", _validate_email, "Email address shape", None),
        ValidatorSpec("phone_e164", "single-field", _validate_phone_e164, "E.164 phone number", None),
        ValidatorSpec("luhn", "single-field", _validate_luhn, "Luhn checksum (card/ID numbers)", None),
    )
}


def get_validator(name: str) -> ValidatorSpec | None:
    return _REGISTRY.get(name)


def list_validators() -> list[ValidatorSpec]:
    return sorted(_REGISTRY.values(), key=lambda s: s.name)


def validator_catalog() -> list[dict]:
    """Serializable form for ``config/rules/catalog/validators.json`` — consumed by the
    authoring UI's picker and by ``verify_rules.py`` to reject unknown validator names at
    load time (an ``applyValidator`` effect referencing a name not in this registry)."""
    return [
        {"name": s.name, "kind": s.kind, "description": s.description, "countries": s.countries}
        for s in list_validators()
    ]


def run_validator(name: str, value: str) -> IdentifierValidation:
    spec = get_validator(name)
    if spec is None:
        raise KeyError(f"unknown validator {name!r}; not in the registry")
    return spec.fn(value)
