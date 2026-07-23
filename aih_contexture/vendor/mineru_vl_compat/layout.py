from __future__ import annotations

import re
from typing import Any


MINERU_VL_PROMPTS = {
    "layout": "\nLayout Detection:",
    "table": "\nTable Recognition:",
    "equation": "\nFormula Recognition:",
    "image": "\nImage Analysis:",
    "chart": "\nImage Analysis:",
    "default": "\nText Recognition:",
}

MINERU_VL_LAYOUT_RE = re.compile(
    r"<\|box_start\|>(\d+)\s+(\d+)\s+(\d+)\s+(\d+)"
    r"<\|box_end\|><\|ref_start\|>(\w+?)<\|ref_end\|>"
    r"(?:(<\|rotate_(?:up|right|down|left)\|>))?"
    r"(.*?)(?=<\|box_start\|>|$)",
    re.DOTALL,
)


def convert_mineru_vl_bbox(values: tuple[str, str, str, str]) -> list[float] | None:
    coords = [int(value) for value in values]
    if any(value < 0 or value > 1000 for value in coords):
        return None
    x1, y1, x2, y2 = coords
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    if x1 == x2 or y1 == y2:
        return None
    return [x1 / 1000, y1 / 1000, x2 / 1000, y2 / 1000]


def parse_mineru_vl_layout_tokens(text: str, page_size: tuple[int, int]) -> list[dict[str, Any]]:
    """Parse MinerU-VL official layout tokens into pixel-space block dicts."""
    width, height = page_size
    blocks: list[dict[str, Any]] = []
    for order, match in enumerate(MINERU_VL_LAYOUT_RE.finditer(text or "")):
        x1, y1, x2, y2, label, rotate_token, tail = match.groups()
        bbox_norm = convert_mineru_vl_bbox((x1, y1, x2, y2))
        if bbox_norm is None:
            continue
        px_bbox = [
            int(bbox_norm[0] * width),
            int(bbox_norm[1] * height),
            int(bbox_norm[2] * width),
            int(bbox_norm[3] * height),
        ]
        blocks.append(
            {
                "label": str(label or "").strip().lower(),
                "bbox": px_bbox,
                "order": order,
                "normalized_bbox": bbox_norm,
                "rotate": rotate_token,
                "tail": tail.strip() if isinstance(tail, str) else "",
            }
        )
    return blocks


def mineru_vl_type_for_label(label: str) -> str:
    normalized = str(label or "").strip().lower().replace("-", "_")
    if normalized == "equation":
        return "equation"
    if normalized in {"image", "chart"}:
        return "figure"
    if normalized in {"title", "section_header"}:
        return "section_header"
    if normalized == "header":
        return "page_header"
    if normalized == "footer":
        return "page_footer"
    if normalized in {"page_number", "table", "code", "footnote"}:
        return normalized
    if normalized in {"list", "list_item"}:
        return "list_group"
    if normalized in {"aside", "aside_text", "page_aside_text", "marginal", "marginal_note"}:
        return "marginal_annotation"
    return "text"


def mineru_vl_layout_label_for_ref(label: str) -> str:
    normalized = str(label or "").strip().lower().replace("-", "_")
    return {
        "title": "SectionHeader",
        "section_header": "SectionHeader",
        "header": "PageHeader",
        "footer": "PageFooter",
        "page_number": "PageFooter",
        "footnote": "Footnote",
        "table": "Table",
        "equation": "Equation",
        "formula": "Equation",
        "code": "Code",
        "image": "Picture",
        "chart": "Figure",
        "figure": "Figure",
        "caption": "Caption",
        "list": "ListItem",
        "list_item": "ListItem",
        "aside": "MarginalAnnotation",
        "aside_text": "MarginalAnnotation",
        "page_aside_text": "MarginalAnnotation",
        "marginal": "MarginalAnnotation",
        "marginal_note": "MarginalAnnotation",
        "text": "Text",
    }.get(normalized, "")
