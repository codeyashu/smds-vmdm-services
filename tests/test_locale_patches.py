from app.documents.extract.schemas.locale import (
    CnBusinessLicenseExtraction,
    CnExtractionEnvelope,
    LocaleNameField,
)
from app.documents.mapping.locale_patches import patches_from_cn_envelope


def test_cn_business_license_emits_native_and_romanized_legal_name():
    envelope = CnExtractionEnvelope(
        doc_type="CN_BUSINESS_LICENSE",
        doc_type_confidence=0.95,
        business_license=CnBusinessLicenseExtraction(
            uscc="91310000MA1FL1RD1C",
            legal_name=LocaleNameField(
                native="上海物流有限公司",
                romanized="Shanghai Logistics Co., Ltd.",
            ),
            confidence=0.9,
        ),
    )
    patches, _ = patches_from_cn_envelope(envelope)
    legal = next(patch for patch in patches if patch.path == "legalName")
    assert legal.native_value == "上海物流有限公司"
    assert legal.romanized_value == "Shanghai Logistics Co., Ltd."
    assert legal.pre_selected is False
    assert legal.field_policy == "native_required"
