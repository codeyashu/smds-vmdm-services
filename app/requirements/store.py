"""SQLite-backed store for the document-requirements rule engine.

Not the vendor-document store — this table holds doc *type* configuration
(country -> which document types are expected), never an uploaded file's bytes.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

from app.requirements.models import DocumentRequirement

_IN_SEED: list[dict] = [
    {"country_code": "IN", "doc_type": "IN_PAN_CARD", "label": "PAN card", "is_mandatory": True, "sort_order": 1},
    {
        "country_code": "IN",
        "doc_type": "IN_GST_CERTIFICATE",
        "label": "GST registration certificate (REG-06)",
        "is_mandatory": True,
        "sort_order": 2,
    },
    {
        "country_code": "IN",
        "doc_type": "IN_CANCELLED_CHEQUE",
        "label": "Cancelled cheque / bank letter",
        "is_mandatory": True,
        "sort_order": 3,
    },
    {
        "country_code": "IN",
        "doc_type": "IN_UDYAM_CERTIFICATE",
        "label": "Udyam / MSME registration certificate",
        "is_mandatory": False,
        "sort_order": 4,
    },
    {
        "country_code": "IN",
        "doc_type": "IN_CERTIFICATE_OF_INCORPORATION",
        "label": "Certificate of Incorporation",
        "is_mandatory": False,
        "sort_order": 5,
    },
]

_engine = None


def _db_path() -> str:
    path = os.getenv("DOCAI_DB_PATH", "./data/docai.db")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return path


def _seed_defaults(engine) -> None:
    with Session(engine) as session:
        existing = session.exec(select(DocumentRequirement).where(DocumentRequirement.country_code == "IN")).first()
        if existing is not None:
            return
        for row in _IN_SEED:
            session.add(DocumentRequirement(**row))
        session.commit()


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(f"sqlite:///{_db_path()}", connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(_engine)
        _seed_defaults(_engine)
    return _engine


def reset_engine_for_tests() -> None:
    """Forces the next get_engine() call to open a fresh engine — used between tests so
    each gets its own isolated SQLite file (see tests/conftest.py)."""
    global _engine
    _engine = None
