"""Evidence summary helpers for field verdicts."""

from __future__ import annotations

from app.documents.validation.types import FieldOption


def format_accept_summary(opt: FieldOption) -> str:
    pct = int(round(opt.confidence * 100))
    snippet = f' — "{opt.evidence_snippet}"' if opt.evidence_snippet else ""
    return (
        f"{opt.label}: {opt.incoming_display} from {opt.source_label} "
        f"({pct}% confidence{snippet}) — consistent across documents."
    )


def format_conflict_summary(opt: FieldOption | None, label: str, candidates: str) -> str:
    if opt and opt.evidence_snippet:
        return (
            f"{label} differs across documents ({candidates}). "
            f"Suggested: {opt.incoming_display} from {opt.source_label} — \"{opt.evidence_snippet}\"."
        )
    return (
        f"{label} differs across documents ({candidates}). "
        "Choose the value that matches the supplier's registration."
    )


def format_authority_summary(opt: FieldOption, authority_reason: str) -> str:
    snippet = f' Page excerpt: "{opt.evidence_snippet}".' if opt.evidence_snippet else ""
    return f"{opt.label} from {opt.source_label} ({opt.incoming_display}) — {authority_reason}.{snippet}"
