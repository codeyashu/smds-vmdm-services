"""Build portal extraction-config shape from document playbook."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.documents.playbook.binding_resolver import resolve_binding
from app.documents.playbook.config_store import load_country_playbook
from app.documents.playbook.types import CountryPlaybook


def _binding_needs_resolution(binding) -> str | None:
    needs = binding.needs_resolution
    if needs:
        return needs
    bind = binding.bind
    if bind.get("kind") == "address" and bind.get("field") == "cityName":
        return "cityCode"
    if bind.get("kind") == "bank" and bind.get("field") == "ifsc":
        return "bankingInstitutionCode"
    return None


def playbook_to_apply_config(playbook: CountryPlaybook) -> dict[str, Any]:
    binding_by_id = {b.logical_field_id: b for b in playbook.bindings}
    documents: list[dict[str, Any]] = []

    for doc in playbook.documents:
        attributes: list[dict[str, Any]] = []
        for attr_id in doc.attributes:
            binding = binding_by_id.get(attr_id)
            if not binding:
                continue
            resolved = resolve_binding(binding)
            attributes.append(
                {
                    "id": attr_id,
                    "label": binding.label,
                    "formPath": resolved.path if not resolved.path.startswith("_unmapped") else binding.label,
                    "enabled": True,
                    "mandatory": False,
                    "writable": doc.writable and resolved.writable and not resolved.path.startswith("_unmapped"),
                    "needsResolution": _binding_needs_resolution(binding),
                }
            )
        documents.append(
            {
                "docType": doc.doc_type,
                "writable": doc.writable,
                "attributes": attributes,
            }
        )

    return {
        "countryCode": playbook.country_code,
        "documents": documents,
        "multiSourceFields": dict(playbook.multi_source_fields),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "document-playbook",
        "playbookVersion": playbook.version,
    }


def load_apply_config(country_code: str) -> dict[str, Any] | None:
    from app.documents.playbook.apply_overlay_store import load_apply_overlay

    overlay = load_apply_overlay(country_code)
    if overlay is not None:
        return overlay.as_dict()

    playbook = load_country_playbook(country_code)
    if playbook is None:
        return None
    return playbook_to_apply_config(playbook)
