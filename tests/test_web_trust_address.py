from app.web_trust.address_review import review_bill_to_address


def test_bill_to_address_complete_in():
    review = review_bill_to_address(
        {
            "contactAddressPurposeCode": "BILL_TO",
            "streetNumber": "12",
            "streetName": "MG Road",
            "cityName": "Mumbai",
            "postalCode": "400001",
            "iso2CountryCode": "IN",
        },
        country="IN",
        tax_ids=["27AAPFU0939F1ZV"],
    )
    assert review["completenessScore"] >= 85
    assert review["extracted"]["contactAddressPurposeCode"] == "BILL_TO"


def test_bill_to_address_missing_street_scores_low():
    review = review_bill_to_address(
        {
            "contactAddressPurposeCode": "BILL_TO",
            "cityName": "Mumbai",
            "postalCode": "400001",
            "iso2CountryCode": "IN",
        },
        country="IN",
        tax_ids=[],
    )
    assert review["completenessScore"] < 70
    assert any("incomplete" in note.lower() for note in review["limitations"])
