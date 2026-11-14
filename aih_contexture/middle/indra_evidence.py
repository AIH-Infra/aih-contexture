"""Preserve Indra observations and derive optional review data from those observations."""
from __future__ import annotations

import copy
import math
from typing import Any, Iterable


def collect_indra_evidence(pages: Iterable[Any]) -> dict[str, Any]:
    records = []
    for page in pages:
        if isinstance(page, dict):
            index, attrs = page.get("index"), page.get("attrs") or {}
            stages = attrs.get("indra")
        else:
            index = getattr(page, "index", getattr(page, "page_id", None))
            getter = getattr(page, "get_internal_metadata", None)
            attrs = getattr(page, "attrs", {}) or {}
            stages = getter("indra") if callable(getter) else attrs.get("indra")
        if not stages and "indra_source" in attrs and isinstance(attrs.get("line_confidence"), dict):
            # Historical native Indra Middle already retained these observations.
            stages = {"ocr": {"source": attrs["indra_source"], "line_confidence": attrs["line_confidence"],
                              "text_used": True}}
        if isinstance(index, int) and isinstance(stages, dict) and stages:
            records.append({"page_index": index, "stages": copy.deepcopy(stages)})
    return {"pages": sorted(records, key=lambda item: item["page_index"])} if records else {}


def indra_review_from_document(document: dict[str, Any]) -> dict[str, Any]:
    """Review Indra's recognition confidence, never the accuracy of another text source."""
    evidence = collect_indra_evidence(document.get("pages") or [])
    indra_metadata = (document.get("metadata") or {}).get("indra") or {}
    indra_metadata = indra_metadata if isinstance(indra_metadata, dict) else {}
    legacy_review = indra_metadata.get("review") or {}
    legacy_thresholds = indra_metadata.get("thresholds") or (legacy_review.get("thresholds") if isinstance(legacy_review, dict) else {}) or {}
    legacy_thresholds = legacy_thresholds if isinstance(legacy_thresholds, dict) else {}
    stages: dict[str, list[dict[str, Any]]] = {}
    for page in evidence.get("pages", []):
        for stage, observation in page["stages"].items():
            if stage not in {"layout", "ocr"} or not isinstance(observation, dict):
                continue
            confidence = observation.get("line_confidence")
            confidence = confidence if isinstance(confidence, dict) else {}
            thresholds = observation.get("thresholds", legacy_thresholds)
            thresholds = thresholds if isinstance(thresholds, dict) else {}
            mean, lowest = _number(confidence.get("mean")), _number(confidence.get("min"))
            mean_limit = _number(thresholds.get("mean"), 0.92)
            min_limit = _number(thresholds.get("min"), 0.60)
            reasons = []
            if observation.get("source") == "error":
                reasons.append("unreadable")
            if observation.get("missing_text_layer") and observation.get("detected_lines", 0) > 0:
                reasons.append("missing_text_layer")
            if mean is not None and mean < mean_limit:
                reasons.append("low_mean_line_confidence")
            if lowest is not None and lowest < min_limit:
                reasons.append("low_min_line_confidence")
            if reasons:
                stages.setdefault(stage, []).append({
                    "page_index": page["page_index"], "source": observation.get("source"),
                    "text_used": observation.get("text_used", stage == "ocr"),
                    "mean": mean, "min": lowest,
                    "thresholds": {"mean": mean_limit, "min": min_limit}, "reasons": reasons,
                })
    return {"stages": stages, "note": "Indra line confidence is not calibrated accuracy. Layout-stage text is auxiliary and does not score the final text source."} if evidence else {}


def _number(value, default=None):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else default


def strip_indra_review(metadata: dict[str, Any]) -> None:
    """Clean only our legacy derived review, retaining recognition/configuration evidence."""
    if isinstance(metadata.get("indra"), dict) and "review" in metadata["indra"]:
        review = metadata["indra"]["review"]
        metadata["indra"] = {key: value for key, value in metadata["indra"].items() if key != "review"}
        if isinstance(review, dict) and isinstance(review.get("thresholds"), dict):
            metadata["indra"].setdefault("thresholds", copy.deepcopy(review["thresholds"]))
