"""Requirements SQLite store — seeding and memoization. Isolated per test via conftest."""

from __future__ import annotations

from sqlmodel import Session, select

from app.requirements.models import DocumentRequirement
from app.requirements.store import get_engine


def test_get_engine_seeds_in_defaults():
    engine = get_engine()
    with Session(engine) as session:
        rows = session.exec(select(DocumentRequirement).where(DocumentRequirement.country_code == "IN")).all()

    doc_types = {r.doc_type for r in rows}
    assert {"IN_PAN_CARD", "IN_GST_CERTIFICATE", "IN_CANCELLED_CHEQUE"} <= doc_types

    mandatory = {r.doc_type for r in rows if r.is_mandatory}
    assert {"IN_PAN_CARD", "IN_GST_CERTIFICATE", "IN_CANCELLED_CHEQUE"} <= mandatory

    optional = {r.doc_type for r in rows if not r.is_mandatory}
    assert {"IN_UDYAM_CERTIFICATE", "IN_CERTIFICATE_OF_INCORPORATION"} <= optional


def test_get_engine_does_not_reseed_on_second_call():
    engine1 = get_engine()
    with Session(engine1) as session:
        count_before = len(session.exec(select(DocumentRequirement)).all())

    engine2 = get_engine()
    assert engine1 is engine2
    with Session(engine2) as session:
        count_after = len(session.exec(select(DocumentRequirement)).all())

    assert count_before == count_after
