"""City reference matching — port of portal match-city-reference.ts."""

from __future__ import annotations

from typing import Any

from app.mdm.reference_data import get_cities_for_country

CITY_CODE_ALT_TYPE = "GEO"
MIN_MATCH_SCORE = 60


def _normalize(value: str) -> str:
    return value.strip().lower()


def _city_name_from_option(option: dict[str, Any]) -> str:
    raw = option.get("raw") if isinstance(option.get("raw"), dict) else {}
    label = str(option.get("label") or "")
    return str(raw.get("cityName") or "").strip() or label.split(",")[0].strip() or label


def map_city_option(item: dict[str, Any]) -> dict[str, Any]:
    alt_codes = item.get("alternativeCodes")
    code_entry = None
    if isinstance(alt_codes, list):
        for entry in alt_codes:
            if isinstance(entry, dict) and entry.get("alternativeCodeType") == CITY_CODE_ALT_TYPE:
                code_entry = entry
                break
    value = code_entry.get("alternativeCode") if code_entry else item.get("cityName")
    return {
        "label": item.get("cityName"),
        "value": value,
        "raw": item,
    }


def score_city_match(
    target: str,
    option: dict[str, Any],
    *,
    region_code: str | None = None,
    region_name: str | None = None,
) -> int | None:
    normalized_target = _normalize(target)
    if not normalized_target:
        return None

    city_name = _normalize(_city_name_from_option(option))
    label = _normalize(str(option.get("label") or ""))

    score: int | None = None
    if city_name == normalized_target or label == normalized_target:
        score = 100
    elif city_name.startswith(f"{normalized_target} ") or city_name.startswith(normalized_target):
        score = 85
    elif normalized_target in label:
        score = 60

    if score is None:
        return None

    raw = option.get("raw") if isinstance(option.get("raw"), dict) else {}
    if region_code:
        hint_region = region_code.strip().upper()
        option_region = str(raw.get("subdivisionCode") or "").strip().upper()
        if option_region == hint_region:
            score += 25
        elif option_region:
            score -= 40

    if region_name:
        hint_name = _normalize(region_name)
        option_name = _normalize(str(raw.get("subdivisionName") or ""))
        if option_name and (
            option_name == hint_name or hint_name in option_name or option_name in hint_name
        ):
            score += 10

    return score


def pick_best_city_match(
    candidates: list[dict[str, Any]],
    city_name: str,
    *,
    region_code: str | None = None,
    region_name: str | None = None,
) -> dict[str, Any] | None:
    if not city_name.strip():
        return None

    scored: list[tuple[dict[str, Any], int]] = []
    for option in candidates:
        score = score_city_match(
            city_name,
            option,
            region_code=region_code,
            region_name=region_name,
        )
        if score is not None:
            scored.append((option, score))

    if not scored:
        return None
    scored.sort(key=lambda row: row[1], reverse=True)
    best_option, best_score = scored[0]
    if best_score < MIN_MATCH_SCORE:
        return None
    return best_option


def resolved_fields_from_city_match(option: dict[str, Any]) -> dict[str, str | None]:
    raw = option.get("raw") if isinstance(option.get("raw"), dict) else {}
    return {
        "cityCode": str(option.get("value") or ""),
        "regionCode": raw.get("subdivisionCode"),
        "regionName": raw.get("subdivisionName"),
        "cityName": str(raw.get("cityName") or option.get("label") or ""),
    }


def city_field_patches(base_path: str, fields: dict[str, Any]) -> list[dict[str, Any]]:
    patches: list[dict[str, Any]] = []
    for field in ("cityName", "cityCode", "regionCode", "regionName"):
        value = fields.get(field)
        if value is None or value == "":
            continue
        patches.append({"path": f"{base_path}.{field}", "value": value})
    return patches


async def resolve_city_reference_patches(
    base_path: str,
    iso_country_code: str | None,
    fields: dict[str, Any],
) -> list[dict[str, Any]]:
    country = (iso_country_code or "").strip().upper()
    if not country or len(country) != 2:
        return city_field_patches(base_path, fields)

    resolved = dict(fields)
    if not resolved.get("cityCode") and resolved.get("cityName"):
        try:
            cities = await get_cities_for_country(country)
            options = [map_city_option(row) for row in cities if isinstance(row, dict)]
            match = pick_best_city_match(
                options,
                str(resolved.get("cityName") or ""),
                region_code=resolved.get("regionCode"),
                region_name=resolved.get("regionName"),
            )
            if match:
                resolved = {**resolved, **resolved_fields_from_city_match(match)}
        except Exception:  # noqa: BLE001
            pass

    return city_field_patches(base_path, resolved)
