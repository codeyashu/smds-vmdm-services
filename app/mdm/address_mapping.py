"""Address search line + patches from external address select."""

from __future__ import annotations

from typing import Any


def build_postal_address_search_line(address: dict[str, Any]) -> str:
    subdivisions = address.get("subdivisions")
    subdivision_text = ""
    if isinstance(subdivisions, list):
        subdivision_text = " ".join(
            str(entry.get("subdivisionName") or "").strip()
            for entry in subdivisions
            if isinstance(entry, dict) and str(entry.get("subdivisionName") or "").strip()
        )

    parts = [
        address.get("unitNumber"),
        address.get("streetNumber"),
        address.get("streetName"),
        subdivision_text or None,
        address.get("cityName"),
        address.get("regionName"),
        address.get("postalCode"),
    ]
    cleaned = [str(p).strip() for p in parts if p is not None and str(p).strip()]
    if cleaned:
        return ", ".join(cleaned)
    postal = address.get("postalAddress")
    return str(postal).strip() if postal else ""


def extract_city_fields_from_select(result: dict[str, Any]) -> dict[str, str | None]:
    suggestion = None
    geo = result.get("geoCitySuggestions")
    if isinstance(geo, list) and geo and isinstance(geo[0], dict):
        suggestion = geo[0]

    geo_code = None
    if suggestion and isinstance(suggestion.get("city"), dict):
        codes = suggestion["city"].get("alternativeCodes")
        if isinstance(codes, list):
            for entry in codes:
                if not isinstance(entry, dict):
                    continue
                if entry.get("alternativeCodeType") in ("GEO", "GEO_ID"):
                    geo_code = entry.get("alternativeCode")
                    break

    sub_city = None
    subs = result.get("subdivisions")
    if isinstance(subs, list):
        for entry in subs:
            if isinstance(entry, dict) and entry.get("subdivisionLevelLabel") == "subCity":
                sub_city = entry.get("subdivisionName")
                break

    city_name = (
        str(result.get("cityName") or "").strip()
        or (
            str(suggestion.get("city", {}).get("cityName") or "").strip()
            if suggestion and isinstance(suggestion.get("city"), dict)
            else ""
        )
        or (str(sub_city).strip() if sub_city else "")
    ) or None

    region = result.get("region") if isinstance(result.get("region"), dict) else {}
    sug_region = suggestion.get("region") if suggestion and isinstance(suggestion.get("region"), dict) else {}

    return {
        "cityName": city_name,
        "cityCode": str(geo_code).strip() if geo_code else None,
        "regionCode": region.get("regionCode") or sug_region.get("regionCode"),
        "regionName": region.get("regionName") or sug_region.get("regionName"),
    }


def _region_dict(result: dict[str, Any]) -> dict[str, Any]:
    region = result.get("region")
    return region if isinstance(region, dict) else {}


def patches_from_select_address(base_path: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    patches: list[dict[str, Any]] = []

    def set_field(field: str, value: Any) -> None:
        if value is None or value == "":
            return
        patches.append({"path": f"{base_path}.{field}", "value": value})

    set_field("unitNumber", result.get("unitNumber"))
    set_field("streetNumber", result.get("streetNumber"))
    set_field("streetName", result.get("streetName"))

    city_fields = extract_city_fields_from_select(result)
    set_field("cityName", city_fields.get("cityName"))
    set_field("cityCode", city_fields.get("cityCode"))
    set_field("postalCode", result.get("postalCode"))
    set_field("latitude", result.get("latitude"))
    set_field("longitude", result.get("longitude"))
    set_field("regionCode", city_fields.get("regionCode") or _region_dict(result).get("regionCode"))
    set_field("regionName", city_fields.get("regionName") or _region_dict(result).get("regionName"))
    country = result.get("country")
    if isinstance(country, dict):
        set_field("iso2CountryCode", country.get("iso2CountryCode"))
    if result.get("subdivisions"):
        set_field("subdivisions", result.get("subdivisions"))
    if result.get("postalAddress"):
        set_field("postalAddress", result.get("postalAddress"))

    return patches
