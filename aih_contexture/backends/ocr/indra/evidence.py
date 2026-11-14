"""Attach compact, page-local Indra confidence evidence to Pipeline documents."""
from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any, Literal

from aih_contexture.backends.ocr.indra.settings import IndraSettings
from aih_contexture.schema.document import Document

IndraStage = Literal["layout", "ocr"]


def clear_indra_evidence_stage(document: Document, *, stage: IndraStage) -> None:
    """Remove one stage's evidence without disturbing evidence from the other stage."""
    for page in document.pages:
        evidence = page.get_internal_metadata("indra")
        if not isinstance(evidence, dict):
            continue
        evidence.pop(stage, None)
        if not evidence:
            metadata = getattr(page, "_metadata", None)
            if isinstance(metadata, dict):
                metadata.pop("indra", None)


def attach_indra_evidence(
    document: Document,
    pages: Mapping[int, Mapping[str, Any]],
    *,
    stage: IndraStage,
    settings: IndraSettings,
    version: str | None,
) -> None:
    """Attach concise raw per-page confidence evidence for pages Indra actually ran.

    Layout confidence describes the evidence Indra's auxiliary layout pass observed;
    it does not measure the accuracy of the final PDF text.
    """
    if stage not in {"layout", "ocr"}:
        raise ValueError(f"Unsupported Indra evidence stage: {stage}")

    document_pages: dict[int, Any] = {}
    for position, page in enumerate(document.pages):
        page_id = getattr(page, "page_id", None)
        if page_id is not None:
            document_pages.setdefault(int(page_id), page)
        else:
            document_pages.setdefault(position, page)

    for source_index, indra_page in pages.items():
        page_group = document_pages.get(int(source_index))
        if page_group is None or not isinstance(indra_page, Mapping):
            continue

        record = make_indra_evidence(indra_page, stage=stage, settings=settings, version=version)
        current = page_group.get_internal_metadata("indra")
        evidence = dict(current) if isinstance(current, dict) else {}
        evidence[stage] = record
        page_group.set_internal_metadata("indra", evidence)


def make_indra_evidence(
    page: Mapping[str, Any],
    *,
    stage: IndraStage,
    settings: IndraSettings,
    version: str | None,
) -> dict[str, Any]:
    """Build the shared page evidence record used by Pipeline and direct Middle routes."""
    if stage not in {"layout", "ocr"}:
        raise ValueError(f"Unsupported Indra evidence stage: {stage}")

    lines = page.get("lines") or []
    confidences = []
    for line in lines:
        if not isinstance(line, Mapping):
            continue
        confidence = line.get("conf")
        if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
            numeric_confidence = float(confidence)
            if math.isfinite(numeric_confidence):
                confidences.append(numeric_confidence)

    line_confidence = {
        "lines": len(confidences),
        "mean": round(sum(confidences) / len(confidences), 4) if confidences else None,
        "min": round(min(confidences), 4) if confidences else None,
    }
    review_mean = _finite_or_none(settings.review_mean)
    review_min = _finite_or_none(settings.review_min)
    return {
        "source": page.get("source"),
        "model": page.get("model") or "indra-ocr",
        "version": version,
        "mode": page.get("mode") or settings.mode,
        "dpi": page.get("dpi") or settings.dpi,
        "rotation": page.get("rotation"),
        "skew": page.get("skew"),
        "vertical": page.get("vertical"),
        "line_confidence": line_confidence,
        "thresholds": {"mean": review_mean, "min": review_min},
        "text_used": stage == "ocr",
    }


def _finite_or_none(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
        return float(value)
    return None
