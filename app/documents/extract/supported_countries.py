"""Supported extraction countries and locale metadata."""

from __future__ import annotations

from dataclasses import dataclass

SUPPORTED_EXTRACTION_COUNTRIES = frozenset({"IN", "CN", "AE", "US", "GB"})


@dataclass(frozen=True)
class LocaleCountryProfile:
    country_code: str
    default_script: str
    locale_charset_code: str | None
    locale_charset_name: str | None
    dual_record: bool


LOCALE_COUNTRY_PROFILES: dict[str, LocaleCountryProfile] = {
    "CN": LocaleCountryProfile("CN", "zh", "C", "Chinese", True),
    "AE": LocaleCountryProfile("AE", "ar", "A", "Arabic", True),
    "US": LocaleCountryProfile("US", "en", None, None, False),
    "GB": LocaleCountryProfile("GB", "en", None, None, False),
}


def is_supported_extraction_country(country: str) -> bool:
    return country.strip().upper() in SUPPORTED_EXTRACTION_COUNTRIES


def locale_profile(country: str) -> LocaleCountryProfile | None:
    return LOCALE_COUNTRY_PROFILES.get(country.strip().upper())
