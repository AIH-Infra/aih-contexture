from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from aih_contexture.middle.schema import MiddleBlock, MiddlePage


def drop_mineru_aggregate_duplicates(page: MiddlePage) -> None:
    """Drop a MinerU aggregate list duplicated by split page blocks.

    MinerU may expose one aggregate ``list`` block together with the same
    content as several discarded or auxiliary blocks. The aggregate is safe
    to remove only when geometry and text both prove that the split blocks
    cover the same content.
    """
    blocks = list(page.blocks)
    component_blocks = [
        block
        for block in blocks
        if block.type in {"Text", "Footnote", "Reference"}
        and _valid_bbox(block.bbox)
        and str(block.text or "").strip()
    ]
    if len(component_blocks) < 2:
        return

    kept: list[MiddleBlock] = []
    for block in blocks:
        is_aggregate = (
            block.type == "ListItem"
            and str(block.attrs.get("raw_label") or "").strip().lower() == "list"
            and _valid_bbox(block.bbox)
        )
        if not is_aggregate:
            kept.append(block)
            continue

        overlapping = [
            item
            for item in component_blocks
            if item is not block
            and _horizontal_overlap_ratio(block.bbox, item.bbox) >= 0.6
            and _vertical_overlap_ratio(block.bbox, item.bbox) >= 0.7
        ]
        if len(overlapping) < 2:
            kept.append(block)
            continue

        overlapping.sort(key=lambda item: (float(item.bbox[1]), item.order))
        top = min(float(item.bbox[1]) for item in overlapping)
        bottom = max(float(item.bbox[3]) for item in overlapping)
        aggregate_top = float(block.bbox[1])
        aggregate_bottom = float(block.bbox[3])
        aggregate_height = aggregate_bottom - aggregate_top
        if aggregate_height <= 0:
            kept.append(block)
            continue

        overlap_top = max(aggregate_top, top)
        overlap_bottom = min(aggregate_bottom, bottom)
        coverage = max(0.0, overlap_bottom - overlap_top) / aggregate_height
        aggregate_text = _normalize_duplicate_text(block.text)
        component_text = _normalize_duplicate_text(" ".join(item.text for item in overlapping))
        similarity = SequenceMatcher(None, aggregate_text, component_text, autojunk=False).ratio()
        aggregate_tokens = set(aggregate_text.split())
        component_tokens = set(component_text.split())
        token_coverage = len(aggregate_tokens & component_tokens) / max(1, len(aggregate_tokens))
        if coverage < 0.75 or (similarity < 0.68 and token_coverage < 0.82):
            kept.append(block)

    page.blocks = kept


def _valid_bbox(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 4 and float(value[3]) > float(value[1])


def _horizontal_overlap_ratio(first: list[float], second: list[float]) -> float:
    overlap = max(0.0, min(float(first[2]), float(second[2])) - max(float(first[0]), float(second[0])))
    return overlap / max(1.0, min(float(first[2]) - float(first[0]), float(second[2]) - float(second[0])))


def _vertical_overlap_ratio(first: list[float], second: list[float]) -> float:
    overlap = max(0.0, min(float(first[3]), float(second[3])) - max(float(first[1]), float(second[1])))
    return overlap / max(1.0, float(second[3]) - float(second[1]))


def _normalize_duplicate_text(value: Any) -> str:
    return re.sub(r"\W+", " ", str(value or "").lower(), flags=re.UNICODE).strip()
