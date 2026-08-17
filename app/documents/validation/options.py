"""Flatten extraction results into adjudication field options."""

from __future__ import annotations

from typing import Any

from app.documents.playbook.binding_resolver import reverse_map_path_to_logical
from app.documents.playbook.types import CountryPlaybook
from app.documents.validation.types import FieldOption


def _format_display(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def flatten_extractions_to_options(
    playbook: CountryPlaybook,
    extractions: list[dict[str, Any]],
) -> list[FieldOption]:
    binding_map = playbook.binding_map()
    options: list[FieldOption] = []

    for extraction in extractions:
        doc_type = str(extraction.get("docType") or "UNKNOWN")
        document_id = str(extraction.get("documentId") or "")
        doc_entry = playbook.doc_map().get(doc_type)
        writable = doc_entry.writable if doc_entry else False

        for patch in extraction.get("patches") or []:
            path = str(patch.get("path") or "")
            if not path:
                continue
            logical_id = reverse_map_path_to_logical(binding_map, path) or ""
            if logical_id and doc_entry and logical_id not in doc_entry.attributes:
                # Path maps to a known logical field not listed for this doc — still surface.
                pass

            binding = binding_map.get(logical_id)
            label = patch.get("label") or (binding.label if binding else path.split(".")[-1])
            value = patch.get("value")
            needs = patch.get("needs_resolution") or patch.get("needsResolution")
            if binding and binding.needs_resolution:
                needs = binding.needs_resolution

            incoming_display = _format_display(value)
            if needs == "cityCode":
                incoming_display = f"{incoming_display} (will resolve to city code)"
            elif needs == "bankingInstitutionCode":
                incoming_display = f"{incoming_display} (will resolve via bank master)"

            option_key = f"{doc_type}:{path}"
            pre_selected = bool(patch.get("pre_selected") or patch.get("preSelected"))
            if path.startswith("_unmapped") or not writable:
                pre_selected = False
            if needs:
                pre_selected = False

            options.append(
                FieldOption(
                    optionKey=option_key,
                    path=path,
                    label=str(label),
                    logicalFieldId=logical_id or None,
                    sourceLabel=doc_type,
                    documentId=document_id or None,
                    incomingValue=value,
                    incomingDisplay=incoming_display,
                    confidence=float(patch.get("confidence") or 0.0),
                    preSelected=pre_selected,
                    needsResolution=needs,
                    evidenceSnippet=(
                        patch.get("evidence", {}).get("snippet")
                        if isinstance(patch.get("evidence"), dict)
                        else None
                    ),
                    regexOk=bool(patch.get("regex_ok") if "regex_ok" in patch else patch.get("regexOk", True)),
                )
            )

    return options
