"""Resolve semantic bindings to concrete ingest paths — soft-fail to _unmapped."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.documents.mapping.field_paths import address_path, tax_number_path
from app.documents.playbook.types import FieldBinding


@dataclass(frozen=True)
class ResolvedBinding:
    path: str
    logical_field_id: str
    label: str
    needs_resolution: str | None = None
    writable: bool = True
    warning: str | None = None


def _address_index_for_role(role: str) -> int:
    # India primary postal row is index 0 (BILL_TO / primary address in ingest model).
    if role == "primary":
        return 0
    return 0


def resolve_binding(binding: FieldBinding, *, bank_path_prefix: str = "vendorBankAccounts") -> ResolvedBinding:
    bind = binding.bind
    kind = bind.get("kind")

    if kind == "taxSlot":
        tax_code = str(bind.get("taxTypeCode") or bind.get("tax_type_code") or "")
        try:
            path = tax_number_path(tax_code)
        except ValueError:
            path = f"_unmapped.{binding.logical_field_id}"
            return ResolvedBinding(
                path=path,
                logical_field_id=binding.logical_field_id,
                label=binding.label,
                needs_resolution=binding.needs_resolution,
                writable=False,
                warning=f"Unknown tax slot {tax_code}",
            )
        return ResolvedBinding(
            path=path,
            logical_field_id=binding.logical_field_id,
            label=binding.label,
            needs_resolution=binding.needs_resolution,
        )

    if kind == "scalar":
        path = str(bind.get("formPath") or bind.get("form_path") or "")
        if not path:
            path = f"_unmapped.{binding.logical_field_id}"
        return ResolvedBinding(
            path=path,
            logical_field_id=binding.logical_field_id,
            label=binding.label,
            needs_resolution=binding.needs_resolution,
        )

    if kind == "address":
        role = str(bind.get("role") or "primary")
        field = str(bind.get("field") or "")
        idx = _address_index_for_role(role)
        path = f"postalAddresses.{idx}.{field}" if field else f"_unmapped.{binding.logical_field_id}"
        return ResolvedBinding(
            path=path,
            logical_field_id=binding.logical_field_id,
            label=binding.label,
            needs_resolution=binding.needs_resolution or ("cityCode" if field == "cityName" else None),
        )

    if kind == "bank":
        index = int(bind.get("index") or 0)
        field = str(bind.get("field") or "")
        path = f"{bank_path_prefix}.{index}.{field}" if field else f"_unmapped.{binding.logical_field_id}"
        needs = binding.needs_resolution
        if field == "ifsc" and not needs:
            needs = "bankingInstitutionCode"
        return ResolvedBinding(
            path=path,
            logical_field_id=binding.logical_field_id,
            label=binding.label,
            needs_resolution=needs,
        )

    if kind == "unmapped":
        key = str(bind.get("key") or binding.logical_field_id)
        return ResolvedBinding(
            path=f"_unmapped.{key}",
            logical_field_id=binding.logical_field_id,
            label=binding.label,
            writable=False,
        )

    return ResolvedBinding(
        path=f"_unmapped.{binding.logical_field_id}",
        logical_field_id=binding.logical_field_id,
        label=binding.label,
        writable=False,
        warning=f"Unknown bind kind {kind}",
    )


def path_for_logical_field(
    bindings: dict[str, FieldBinding],
    logical_field_id: str,
    *,
    bank_path_prefix: str = "vendorBankAccounts",
) -> ResolvedBinding | None:
    binding = bindings.get(logical_field_id)
    if binding is None:
        return None
    return resolve_binding(binding, bank_path_prefix=bank_path_prefix)


def reverse_map_path_to_logical(
    bindings: dict[str, FieldBinding],
    path: str,
    *,
    bank_path_prefix: str = "vendorBankAccounts",
) -> str | None:
    for logical_id, binding in bindings.items():
        resolved = resolve_binding(binding, bank_path_prefix=bank_path_prefix)
        if resolved.path == path:
            return logical_id
    return None


def read_nested_value(data: dict[str, Any], path: str) -> Any:
    parts = path.split(".")
    cur: Any = data
    for part in parts:
        if not isinstance(cur, dict):
            return None
        if part.isdigit():
            return None
        cur = cur.get(part)
    return cur
