"""Address reconciliation tests."""

from __future__ import annotations

from app.documents.validation.address_reconcile import reconcile_address_candidates


def test_ranks_operational_candidate_on_empty_form():
    candidates = [
        {
            "candidateKey": "IN_GST_CERTIFICATE:principal_pob",
            "addressRole": "principal_pob",
            "label": "Principal",
            "fullAddressText": "61-B, VELAMPALAYAM, Tiruppur, 641652",
            "fields": {"cityName": "Tiruppur", "postalCode": "641652"},
            "sourceDocType": "IN_GST_CERTIFICATE",
            "confidence": 0.95,
        },
        {
            "candidateKey": "IN_ADDRESS_PROOF:operational",
            "addressRole": "operational",
            "label": "Address proof",
            "fullAddressText": "D.NO.61B, VELAMPALAYAM MAIN ROAD, Avinashi, 641652",
            "fields": {"cityName": "Avinashi", "postalCode": "641652", "streetName": "VELAMPALAYAM MAIN ROAD"},
            "sourceDocType": "IN_ADDRESS_PROOF",
            "confidence": 0.98,
        },
    ]
    result = reconcile_address_candidates(candidates, {})
    ranked = result["ranked"]
    assert len(ranked) == 2
    assert result["selectedCandidateKey"] == ranked[0]["candidateKey"]


def test_matches_form_postal_code():
    candidates = [
        {
            "candidateKey": "IN_GST_CERTIFICATE:apob:1",
            "addressRole": "additional_pob",
            "label": "Additional 1",
            "fullAddressText": "2/131, m nathampalayam, Avinashi, Tiruppur, 641654",
            "fields": {"cityName": "Tiruppur", "postalCode": "641654"},
            "sourceDocType": "IN_GST_CERTIFICATE",
            "confidence": 0.95,
        }
    ]
    form = {"postalAddresses": [{"postalCode": "641652", "cityName": "Avinashi"}]}
    result = reconcile_address_candidates(candidates, form)
    assert result["alignmentScore"] >= 0
