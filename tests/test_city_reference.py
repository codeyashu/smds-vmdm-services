"""City reference matching tests."""

from app.mdm.city_reference import map_city_option, pick_best_city_match, score_city_match


def _city(name: str, subdivision_code: str, geo_code: str) -> dict:
    return {
        "cityName": name,
        "subdivisionCode": subdivision_code,
        "subdivisionName": subdivision_code,
        "alternativeCodes": [{"alternativeCodeType": "GEO", "alternativeCode": geo_code}],
    }


def test_pick_best_city_match_exact_name():
    options = [map_city_option(_city("Mumbai", "MH", "GEO_MH"))]
    match = pick_best_city_match(options, "Mumbai")
    assert match is not None
    assert match["value"] == "GEO_MH"


def test_pick_best_city_match_disambiguates_by_region():
    options = [
        map_city_option(_city("Springfield", "IL", "GEO_IL")),
        map_city_option(_city("Springfield", "MO", "GEO_MO")),
    ]
    match = pick_best_city_match(options, "Springfield", region_code="MO")
    assert match is not None
    assert match["value"] == "GEO_MO"


def test_score_city_match_substring_label():
    option = map_city_option(_city("New Delhi", "DL", "GEO_DL"))
    score = score_city_match("New Delhi", option)
    assert score is not None
    assert score >= 60
