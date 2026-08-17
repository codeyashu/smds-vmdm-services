#!/usr/bin/env python3
"""Live extract + adjudicate for Archive case folders."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

BASE_URL = "http://localhost:8000"
BEARER = "dev-token"
ARCHIVE = Path("/Users/rahul.singh2/Downloads/Archive")
CASES = ["case1", "case2", "case3"]


def extract_batch(case_dir: Path) -> list[dict]:
    pdfs = sorted(case_dir.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"No PDFs in {case_dir}")

    files = [("files", (p.name, p.read_bytes(), "application/pdf")) for p in pdfs]
    with httpx.Client(timeout=300.0) as client:
        r = client.post(
            f"{BASE_URL}/v1/extract/batch",
            headers={"Authorization": f"Bearer {BEARER}"},
            data={"countryCode": "IN"},
            files=files,
        )
    r.raise_for_status()
    return r.json()["results"]


def adjudicate(extractions: list[dict]) -> dict:
    payload_extractions = [
        {
            "documentId": e.get("documentId") or f"doc_{i}",
            "docType": e.get("docType", "UNKNOWN"),
            "patches": e.get("patches") or [],
            "warnings": e.get("warnings") or [],
        }
        for i, e in enumerate(extractions)
        if e.get("docType") != "UNKNOWN" or e.get("patches")
    ]
    with httpx.Client(timeout=60.0) as client:
        r = client.post(
            f"{BASE_URL}/v1/documents/adjudicate",
            headers={"Authorization": f"Bearer {BEARER}", "Content-Type": "application/json"},
            json={"countryCode": "IN", "extractions": payload_extractions, "formSnapshot": {}},
        )
    r.raise_for_status()
    return r.json()


def summarize_case(name: str, extractions: list[dict], adjudication: dict) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {name}")
    print(f"{'=' * 60}")

    for i, ext in enumerate(extractions):
        patches = ext.get("patches") or []
        paths = [p.get("path") for p in patches]
        print(f"\n  [{i + 1}] docType={ext.get('docType')} conf={ext.get('docTypeConfidence', 0):.2f}")
        for w in ext.get("warnings") or []:
            print(f"      WARN: {w}")
        if paths:
            print(f"      patches ({len(paths)}): {', '.join(paths[:6])}{'...' if len(paths) > 6 else ''}")
        else:
            print("      patches: (none)")
        unmapped = ext.get("unmapped") or []
        if unmapped:
            print(f"      unmapped: {unmapped}")

    cot = adjudication.get("cotTrace") or []
    conflicts = adjudication.get("conflicts") or []
    checks = [c for c in (adjudication.get("bundleChecks") or []) if c.get("status") not in ("pass", "skip")]
    verdicts = adjudication.get("fieldVerdicts") or []

    print(f"\n  Adjudication: playbook v{adjudication.get('playbookVersion')} | cot={len(cot)} steps")
    if conflicts:
        print(f"  Conflicts: {[c.get('path') for c in conflicts]}")
    if checks:
        print(f"  Bundle checks:")
        for c in checks:
            print(f"    - {c.get('id')}: {c.get('status')} — {c.get('message', '')[:80]}")
    print(f"  Verdicts: {[(v.get('path'), v.get('action')) for v in verdicts[:8]]}")
    if cot:
        print(f"  CoT sample:")
        for step in cot[:8]:
            print(f"    [{step.get('kind')}] {step.get('message', '')[:100]}")
        if len(cot) > 8:
            print(f"    ... +{len(cot) - 8} more steps")


def main() -> None:
    ready = httpx.get(f"{BASE_URL}/ready", timeout=10).json()
    print(f"Service ready: extractionAvailable={ready.get('extractionAvailable')} ocr={ready.get('ocrProvider')} llm={ready.get('llmProvider')}")
    if not ready.get("extractionAvailable"):
        sys.exit("Extraction not available — configure OCR + LLM")

    for case in CASES:
        case_dir = ARCHIVE / case
        extractions = extract_batch(case_dir)
        adjudication = adjudicate(extractions)
        summarize_case(case, extractions, adjudication)

    print("\nDone.")


if __name__ == "__main__":
    main()
