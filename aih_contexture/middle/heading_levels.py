from __future__ import annotations

from typing import Any

from aih_contexture.middle.schema import MiddleBlock, MiddleDocument
from aih_contexture.vendor.paddleocr_vl_compat import infer_heading_level_from_text_and_label


def normalize_middle_heading_levels(document: MiddleDocument) -> MiddleDocument:
    """Ensure SectionHeader blocks carry a renderer-ready heading level."""
    for page in document.pages:
        page_height = page.height
        for block in page.blocks:
            _normalize_block_heading(block, page_height=page_height)
    return document


def _normalize_block_heading(block: MiddleBlock, *, page_height: float | None) -> None:
    if block.type == "SectionHeader":
        attrs = block.attrs
        level = _explicit_level(attrs)
        source = attrs.get("heading_level_source")
        if level is None:
            raw_label = attrs.get("raw_label") or attrs.get("raw_block_type")
            raw = attrs.get("raw")
            if isinstance(raw, dict):
                raw_label = raw_label or raw.get("block_label") or raw.get("label") or raw.get("type")
                level = _explicit_level(raw)
            if level is None:
                level = infer_heading_level_from_text_and_label(
                    text=block.text or "",
                    raw_label=str(raw_label or ""),
                    bbox=block.bbox,
                    page_height=page_height,
                )
            if source is None:
                source = "upstream" if level is not None and raw_label else "default"
        level = _clamp_heading_level(level or 2)
        attrs["heading_level"] = level
        attrs.setdefault("heading_level_source", source or "default")
        attrs.setdefault("raw_heading_level", level)
        attrs.setdefault("title_role", _title_role(attrs.get("raw_label") or attrs.get("raw_block_type")))

    for child in block.children:
        _normalize_block_heading(child, page_height=page_height)


def _explicit_level(attrs: dict[str, Any]) -> int | None:
    for key in ("heading_level", "raw_heading_level", "text_level", "level"):
        value = attrs.get(key)
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            return _clamp_heading_level(number)
    return None


def _clamp_heading_level(level: int) -> int:
    return max(1, min(6, int(level)))


def _title_role(raw_label: Any) -> str:
    raw = str(raw_label or "").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in {"doc_title", "doctitle", "document_title"}:
        return "doc_title"
    if raw in {"title"}:
        return "title"
    if raw in {"paragraph_title", "section_header", "sectionheader", "heading"}:
        return "section_title"
    return "unknown"
