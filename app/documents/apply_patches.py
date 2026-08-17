"""Apply document field options with city/bank resolution."""

from __future__ import annotations

import re
from typing import Any

from app.mdm.bank_master import resolve_bank_from_ifsc
from app.mdm.city_reference import resolve_city_reference_patches
from app.mdm.nested_payload import read_nested_value, set_nested_value

_ADDRESS_BASE_RE = re.compile(r"^(postalAddresses\.\d+)")


def _address_base_path(field_path: str) -> str | None:
    match = _ADDRESS_BASE_RE.match(field_path)
    return match.group(1) if match else None


def _city_name_for_resolution(
    option: dict[str, Any],
    selected: list[dict[str, Any]],
    form_state: dict[str, Any],
) -> str:
    path = str(option.get("path") or "")
    base = _address_base_path(path)
    if not base:
        return str(option.get("incomingValue") or "")

    if path.endswith(".cityName"):
        return str(option.get("incomingValue") or "")

    city_option = next((row for row in selected if row.get("path") == f"{base}.cityName"), None)
    if city_option and city_option.get("incomingValue"):
        return str(city_option["incomingValue"])

    from_state = read_nested_value(form_state, f"{base}.cityName")
    if from_state:
        return str(from_state)
    return str(option.get("incomingValue") or "")


def _city_match_hints(
    base_path: str,
    selected: list[dict[str, Any]],
    form_state: dict[str, Any],
) -> dict[str, str | None]:
    region_option = next((row for row in selected if row.get("path") == f"{base_path}.regionCode"), None)
    region_from_state = read_nested_value(form_state, f"{base_path}.regionCode")
    region_code = None
    if region_option and region_option.get("incomingValue"):
        region_code = str(region_option["incomingValue"])
    elif region_from_state:
        region_code = str(region_from_state)

    region_name_option = next((row for row in selected if row.get("path") == f"{base_path}.regionName"), None)
    region_name_from_state = read_nested_value(form_state, f"{base_path}.regionName")
    region_name = None
    if region_name_option and region_name_option.get("incomingValue"):
        region_name = str(region_name_option["incomingValue"])
    elif region_name_from_state:
        region_name = str(region_name_from_state)

    return {"region_code": region_code, "region_name": region_name}


async def apply_document_options(
    form_state: dict[str, Any],
    selected: list[dict[str, Any]],
    *,
    country_code: str,
    remap_path: str | None = None,
) -> dict[str, Any]:
    next_state = dict(form_state)
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    def effective(path: str) -> str:
        if remap_path == "edit_bank_accounts" and path.startswith("vendorBankAccounts."):
            return path.replace("vendorBankAccounts.", "bankAccounts.", 1)
        return path

    for option in selected:
        target_path = effective(str(option.get("path") or ""))
        label = str(option.get("label") or target_path)
        needs = option.get("needsResolution") or option.get("needs_resolution")

        if needs == "cityCode":
            base_path = _address_base_path(target_path)
            if not base_path:
                skipped.append(
                    {
                        "path": target_path,
                        "label": label,
                        "reason": "Could not resolve city — invalid address path",
                    }
                )
                continue
            try:
                city_name = _city_name_for_resolution(option, selected, next_state)
                hints = _city_match_hints(base_path, selected, next_state)
                fields = {"cityName": city_name}
                if hints.get("region_code"):
                    fields["regionCode"] = hints["region_code"]
                if hints.get("region_name"):
                    fields["regionName"] = hints["region_name"]
                patches = await resolve_city_reference_patches(base_path, country_code, fields)
                city_code_applied = False
                for patch in patches:
                    next_state = set_nested_value(next_state, patch["path"], patch["value"])
                    applied.append(
                        {
                            "path": patch["path"],
                            "value": patch["value"],
                            "sourceDocType": option.get("sourceDocType"),
                            "sourceDocTypeLabel": option.get("sourceDocTypeLabel"),
                        }
                    )
                    if patch["path"].endswith(".cityCode") and patch.get("value"):
                        city_code_applied = True
                if not city_code_applied:
                    skipped.append(
                        {
                            "path": target_path,
                            "label": label,
                            "reason": f"City \"{city_name}\" not found in reference data — city name applied only",
                        }
                    )
            except Exception:  # noqa: BLE001
                skipped.append({"path": target_path, "label": label, "reason": "City reference lookup failed"})
            continue

        if needs == "bankingInstitutionCode":
            try:
                ifsc = str(option.get("incomingValue") or "")
                resolved = await resolve_bank_from_ifsc(country_code, ifsc)
                if not resolved:
                    skipped.append(
                        {
                            "path": target_path,
                            "label": label,
                            "reason": f"No bank master match for IFSC {ifsc}",
                        }
                    )
                    continue
                bank_base = target_path.replace(".ifsc", "")
                entries: list[tuple[str, str]] = [
                    (f"{bank_base}.bankingInstitutionCode", resolved["bankingInstitutionCode"]),
                ]
                for key in ("bankName", "swiftCode", "bankBranchName", "iso2CountryCode"):
                    if resolved.get(key):
                        field = {
                            "bankName": "bankName",
                            "swiftCode": "swiftCode",
                            "bankBranchName": "bankBranchName",
                            "iso2CountryCode": "iso2CountryCode",
                        }[key]
                        entries.append((f"{bank_base}.{field}", resolved[key]))
                for path, value in entries:
                    next_state = set_nested_value(next_state, path, value)
                    applied.append(
                        {
                            "path": path,
                            "value": value,
                            "sourceDocType": option.get("sourceDocType"),
                            "sourceDocTypeLabel": option.get("sourceDocTypeLabel"),
                        }
                    )
            except Exception:  # noqa: BLE001
                skipped.append({"path": target_path, "label": label, "reason": "Bank master lookup failed"})
            continue

        value = option.get("incomingValue")
        next_state = set_nested_value(next_state, target_path, value)
        applied.append(
            {
                "path": target_path,
                "value": value,
                "sourceDocType": option.get("sourceDocType"),
                "sourceDocTypeLabel": option.get("sourceDocTypeLabel"),
            }
        )

    return {"formState": next_state, "applied": applied, "skipped": skipped}
