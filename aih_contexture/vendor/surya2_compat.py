from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from typing import Any


SURYA2_PROMPTS = {
    "layout": 'Output the layout of this image as JSON. Each entry is a dict with "label", "bbox", and "count" fields. Bbox is x0 y0 x1 y1, normalized 0-1000. Return only the JSON array with no explanation.',
    "ocr": "OCR this block image to HTML.",
    "table": "OCR this table image to HTML.",
}

SURYA2_BBOX_SCALE = 1000


_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)


def parse_surya2_layout_json(text: str, *, page_size: tuple[int, int]) -> list[dict[str, Any]]:
    """Parse Surya 2 layout JSON into pixel-bbox block dictionaries."""
    data = _extract_json_array(text)
    if not isinstance(data, list):
        return []
    blocks: list[dict[str, Any]] = []
    for order, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        raw_label = str(item.get("label") or "").strip()
        if not raw_label:
            continue
        if raw_label.lower().replace("_", "-") == "blank-page":
            continue
        norm_bbox = parse_surya2_bbox(item.get("bbox"))
        if norm_bbox is None:
            continue
        bbox = surya2_bbox_to_pixel_bbox(norm_bbox, page_size=page_size)
        blocks.append(
            {
                "label": surya2_type_for_label(raw_label),
                "type": surya2_type_for_label(raw_label),
                "raw_label": raw_label,
                "bbox": bbox,
                "normalized_bbox": norm_bbox,
                "loc_bbox_1000": norm_bbox,
                "order": int(item.get("count", order)) if _intlike(item.get("count")) else order,
                "raw": dict(item),
            }
        )
    return blocks


def parse_surya2_bbox(value: Any) -> list[int] | None:
    if isinstance(value, str):
        parts = re.findall(r"-?\d+(?:\.\d+)?", value)
        if len(parts) != 4:
            return None
        coords = [round(float(part)) for part in parts]
    elif isinstance(value, (list, tuple)) and len(value) == 4:
        if not all(isinstance(part, (int, float)) for part in value):
            return None
        coords = [round(float(part)) for part in value]
    else:
        return None
    x0, y0, x1, y1 = [max(0, min(SURYA2_BBOX_SCALE, coord)) for coord in coords]
    if x1 <= x0 or y1 <= y0:
        return None
    return [x0, y0, x1, y1]


def surya2_bbox_to_pixel_bbox(
    norm_bbox: list[int] | tuple[int, int, int, int],
    *,
    page_size: tuple[int, int],
) -> list[int]:
    width, height = page_size
    x0, y0, x1, y1 = norm_bbox
    return [
        round(x0 * width / SURYA2_BBOX_SCALE),
        round(y0 * height / SURYA2_BBOX_SCALE),
        round(x1 * width / SURYA2_BBOX_SCALE),
        round(y1 * height / SURYA2_BBOX_SCALE),
    ]


def surya2_label_for_contexture(raw_label: str) -> str:
    raw = str(raw_label or "").strip()
    compact = raw.replace(" ", "-").replace("_", "-")
    lower = compact.lower()
    mapping = {
        "text": "Text",
        "caption": "Caption",
        "footnote": "Footnote",
        "equation-block": "Equation",
        "chemical-block": "Equation",
        "list-group": "ListItem",
        "page-header": "PageHeader",
        "page-footer": "PageFooter",
        "image": "Picture",
        "figure": "Figure",
        "diagram": "Figure",
        "section-header": "SectionHeader",
        "table": "Table",
        "table-of-contents": "TableOfContents",
        "complex-block": "ComplexRegion",
        "code-block": "Code",
        "form": "Form",
        "bibliography": "Reference",
    }
    return mapping.get(lower, raw.title().replace("-", "").replace("_", ""))


def surya2_type_for_label(raw_label: str) -> str:
    contexture_label = surya2_label_for_contexture(raw_label)
    mapping = {
        "Text": "text",
        "Caption": "caption",
        "Footnote": "footnote",
        "Equation": "equation",
        "ListItem": "list_item",
        "PageHeader": "page_header",
        "PageFooter": "page_footer",
        "Picture": "figure",
        "Figure": "figure",
        "SectionHeader": "section_header",
        "Table": "table",
        "TableOfContents": "table_of_contents",
        "ComplexRegion": "complex_region",
        "Code": "code",
        "Form": "form",
        "Reference": "reference",
    }
    return mapping.get(contexture_label, "text")


def html_to_plain_text(value: str, *, preserve_table_html: bool = False) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if preserve_table_html and "<table" in text.lower():
        return text
    parser = _TextHTMLParser()
    parser.feed(text)
    parser.close()
    return parser.text()


def normalize_surya2_ocr_block(
    block: dict[str, Any],
    *,
    html_text: str,
    raw_response: dict[str, Any] | None = None,
    raw_prompt: str | None = None,
) -> dict[str, Any]:
    item = dict(block)
    canonical_type = str(item.get("type") or surya2_type_for_label(str(item.get("raw_label") or item.get("label") or "")))
    preserve_table = canonical_type == "table"
    item["html"] = html_text
    item["text"] = html_to_plain_text(html_text, preserve_table_html=preserve_table)
    item["label"] = canonical_type
    item["type"] = canonical_type
    item["official_protocol"] = "surya2_layout_block_html"
    if raw_prompt is not None:
        item["raw_prompt"] = raw_prompt
    if raw_response is not None:
        item["raw_response"] = raw_response
    return item


def _extract_json_array(text: str) -> Any:
    raw = str(text or "").strip()
    if not raw:
        return None
    fence = _FENCE_RE.search(raw)
    if fence:
        raw = fence.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    start = raw.find("[")
    end = raw.rfind("]")
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _intlike(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, str):
        return value.strip().isdigit()
    return False


class _TextHTMLParser(HTMLParser):
    _block_tags = {"br", "p", "div", "li", "tr", "table", "thead", "tbody", "tfoot", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "img":
            alt = dict(attrs).get("alt")
            if alt:
                self._parts.append(str(alt))
        if tag.lower() in self._block_tags:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._block_tags:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if data:
            self._parts.append(data)

    def text(self) -> str:
        value = html.unescape("".join(self._parts))
        lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
        lines = [line for line in lines if line]
        return "\n".join(lines).strip()
