"""Address mapping helpers."""

from app.mdm.address_mapping import build_postal_address_search_line, patches_from_select_address


def test_build_postal_address_search_line_joins_parts():
    line = build_postal_address_search_line(
        {
            "streetNumber": "12",
            "streetName": "Main Road",
            "cityName": "Mumbai",
            "postalCode": "400001",
        }
    )
    assert "12" in line
    assert "Mumbai" in line


def test_patches_from_select_address_maps_city_code():
    patches = patches_from_select_address(
        "postalAddresses.0",
        {
            "streetName": "Main",
            "cityName": "Mumbai",
            "postalCode": "400001",
            "geoCitySuggestions": [
                {
                    "city": {
                        "cityName": "Mumbai",
                        "alternativeCodes": [{"alternativeCodeType": "GEO", "alternativeCode": "CITY123"}],
                    }
                }
            ],
        },
    )
    paths = {p["path"] for p in patches}
    assert "postalAddresses.0.cityCode" in paths
    assert "postalAddresses.0.cityName" in paths
