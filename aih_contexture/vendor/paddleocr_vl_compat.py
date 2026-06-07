from __future__ import annotations

import re
from typing import Any


PADDLE_VL_PROMPTS = {
    "ocr": "OCR:",
    "layout_detection": "Layout Detection:",
    "table": "Table Recognition:",
    "chart": "Chart Recognition:",
    "formula": "Formula Recognition:",
    "seal": "Seal Recognition:",
    "spotting": "Spotting:",
}

PADDLE_LOC_SCALE = 1000

_PADDLE_LOC_RE = re.compile(r"<\|LOC_(\d+)\|>")
_PADDLE_LOC_LINE_RE = re.compile(r"^(?P<text>.*?)(?P<locs>(?:<\|LOC_\d+\|>){4,})\s*$")
_PADDLE_SUPERSCRIPT_FOOTNOTE_RE = re.compile(
    r"^\s*(?:\\\(\s*\^\s*\{?\d+\}?\s*\\\)|<sup>\s*\d+\s*</sup>|\^\d+|[¹²³⁴⁵⁶⁷⁸⁹⁰]+)",
    re.IGNORECASE,
)
_PAGE_NUMBER_RE = re.compile(r"^\s*(?:\d{1,4}|[ivxlcdmIVXLCDM]{1,12})\s*$")
_HEADING_NUMBER_RE = re.compile(r"^\s*(?:(\d+(?:\.\d+){0,5})|([IVXLCDM]+)|([A-Z]))[.)]?\s+\S+")
_SENTENCE_END_RE = re.compile(r"[.;:,]\s*$")


def paddle_prompt_label_to_block_label(prompt_label: str | None) -> str:
    return {
        "ocr": "text",
        "layout_detection": "text",
        "formula": "equation",
        "table": "table",
        "chart": "figure",
        "seal": "seal",
        "spotting": "text",
    }.get(str(prompt_label or "").strip().lower(), "text")


def parse_paddle_vl_loc_blocks(
    text: str,
    *,
    width: int,
    height: int,
    prompt_label: str,
    prompt: str,
) -> list[dict[str, Any]]:
    """Parse PaddleOCR-VL prompt-only LOC token output into block dictionaries.

    Paddle's VLM component emits polygon locations in a 0..1000 coordinate
    system. The returned ``bbox`` is scaled to the exact image/crop passed to
    the VLM call, while ``normalized_bbox`` preserves the LOC-1000 box.
    """
    blocks: list[dict[str, Any]] = []
    in_footnotes = False
    fallback_label = paddle_prompt_label_to_block_label(prompt_label)
    for order, raw_line in enumerate((text or "").splitlines()):
        line = raw_line.strip()
        if not line:
            continue
        match = _PADDLE_LOC_LINE_RE.match(line)
        if not match:
            continue
        loc_values = [int(value) for value in _PADDLE_LOC_RE.findall(match.group("locs"))]
        norm_bbox = loc_values_to_bbox(loc_values)
        if norm_bbox is None:
            continue
        clean = match.group("text").strip()
        if not clean:
            continue

        label = fallback_label
        heading_level: int | None = None
        inference_reason: str | None = None
        if str(prompt_label).strip().lower() in {"ocr", "spotting", "layout_detection"}:
            label, in_footnotes, heading_level, inference_reason = classify_paddle_loc_ocr_line(
                clean,
                norm_bbox=norm_bbox,
                in_footnotes=in_footnotes,
            )

        block: dict[str, Any] = {
            "type": label,
            "label": label,
            "text": clean,
            "bbox": loc_bbox_to_pixel_bbox(norm_bbox, width=width, height=height),
            "normalized_bbox": norm_bbox,
            "loc_bbox_1000": norm_bbox,
            "raw_prompt_label": prompt_label,
            "raw_query": prompt,
            "order": order,
            "raw": {"paddle_loc_line": raw_line},
        }
        if heading_level is not None:
            block["heading_level"] = heading_level
            block["heading_level_source"] = "paddle_loc_heuristic"
        if inference_reason:
            block["inference_reason"] = inference_reason
        blocks.append(block)
    return blocks


def segment_paddle_vl_loc_blocks(
    blocks: list[dict[str, Any]],
    *,
    modern_print: bool = True,
) -> list[dict[str, Any]]:
    """Convert Paddle line-level LOC OCR into conservative Middle-ready blocks.

    The parser above intentionally returns one block per LOC line for backward
    compatibility. This segmenter performs the modern-print recovery layer:
    preserve page furniture, group footnote continuations, and merge body lines
    into paragraphs while keeping original lines as nested spans.
    """
    if not modern_print or not blocks:
        return blocks
    loc_blocks = [block for block in blocks if isinstance(block, dict) and block.get("loc_bbox_1000")]
    if len(loc_blocks) < 2:
        return blocks
    if _looks_like_vertical_rl_page(loc_blocks):
        return [_as_conservative_text_line(block, writing_mode="vertical-rl") for block in blocks]

    demoted = _demote_low_confidence_loc_roles(loc_blocks)
    segmented: list[dict[str, Any]] = []
    text_group: list[dict[str, Any]] = []
    current_footnote: list[dict[str, Any]] = []
    previous_text: dict[str, Any] | None = None
    median_height = _median_line_height(demoted)

    def flush_text() -> None:
        nonlocal text_group, previous_text
        if text_group:
            segmented.append(_merge_loc_group(text_group, "text", raw_role="paragraph"))
        text_group = []
        previous_text = None

    def flush_footnote() -> None:
        nonlocal current_footnote
        if current_footnote:
            segmented.append(_merge_loc_group(current_footnote, "footnote", raw_role="footnote_entry"))
        current_footnote = []

    for block in demoted:
        label = str(block.get("label") or block.get("type") or "text").strip().lower()
        if label == "footnote":
            flush_text()
            if current_footnote and _starts_new_footnote(str(block.get("text") or "")):
                flush_footnote()
            current_footnote.append(block)
            continue

        flush_footnote()
        if label == "text":
            if previous_text is not None and not _should_merge_text_lines(previous_text, block, median_height=median_height):
                flush_text()
            text_group.append(block)
            previous_text = block
            continue

        flush_text()
        structural = dict(block)
        structural.setdefault("attrs", {})
        structural["attrs"] = {
            **(structural.get("attrs") if isinstance(structural.get("attrs"), dict) else {}),
            "classification_confidence": _classification_confidence(structural),
            "classification_reason": structural.get("inference_reason"),
        }
        segmented.append(structural)

    flush_text()
    flush_footnote()
    return segmented


def loc_values_to_bbox(loc_values: list[int]) -> list[int] | None:
    if len(loc_values) < 4:
        return None
    points = list(zip(loc_values[0::2], loc_values[1::2]))
    if not points:
        return None
    xs = [max(0, min(PADDLE_LOC_SCALE, point[0])) for point in points]
    ys = [max(0, min(PADDLE_LOC_SCALE, point[1])) for point in points]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    if x0 == x1 or y0 == y1:
        return None
    return [x0, y0, x1, y1]


def loc_bbox_to_pixel_bbox(norm_bbox: list[int] | tuple[int, int, int, int], *, width: int, height: int) -> list[int]:
    x0, y0, x1, y1 = norm_bbox
    return [
        round(x0 * width / PADDLE_LOC_SCALE),
        round(y0 * height / PADDLE_LOC_SCALE),
        round(x1 * width / PADDLE_LOC_SCALE),
        round(y1 * height / PADDLE_LOC_SCALE),
    ]


def _looks_like_vertical_rl_page(blocks: list[dict[str, Any]]) -> bool:
    candidates = 0
    vertical = 0
    for block in blocks:
        bbox = block.get("loc_bbox_1000") or block.get("normalized_bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        x0, y0, x1, y1 = bbox
        width = max(1, int(x1) - int(x0))
        height = max(1, int(y1) - int(y0))
        candidates += 1
        if height >= 240 and height >= width * 5:
            vertical += 1
    return candidates >= 5 and vertical / candidates >= 0.6


def _as_conservative_text_line(block: dict[str, Any], *, writing_mode: str) -> dict[str, Any]:
    item = dict(block)
    item["label"] = "text"
    item["type"] = "text"
    attrs = item.get("attrs") if isinstance(item.get("attrs"), dict) else {}
    item["attrs"] = {
        **attrs,
        "writing_mode": writing_mode,
        "candidate_roles": [str(block.get("label") or block.get("type") or "text")],
        "classification_confidence": "low",
        "classification_reason": "vertical_text_conservative_fallback",
    }
    return item


def _demote_low_confidence_loc_roles(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen_body = False
    seen_heading = False
    for index, block in enumerate(blocks):
        item = dict(block)
        label = str(item.get("label") or item.get("type") or "text").strip().lower()
        text = str(item.get("text") or "").strip()
        bbox = item.get("loc_bbox_1000") or item.get("normalized_bbox") or [0, 0, 0, 0]
        y0 = int(bbox[1]) if isinstance(bbox, list) and len(bbox) == 4 else 0
        should_demote = False
        reason = ""

        if label in {"page_header", "section_header"} and _looks_like_front_matter_metadata(text):
            should_demote = True
            reason = "front_matter_metadata_not_page_furniture_or_heading"
        elif label == "section_header":
            if _looks_like_front_matter_metadata(text):
                should_demote = True
                reason = "front_matter_metadata_not_heading"
            elif y0 <= 330 and seen_heading and _looks_like_author_or_date_line(text):
                should_demote = True
                reason = "first_page_bibliographic_line_after_title"
            elif _weak_heading_without_context(blocks, index):
                should_demote = True
                reason = "weak_heading_without_context"
            elif y0 <= 260:
                # A top title is allowed, but mark it as a strong document-title
                # candidate only when it is not obvious page furniture.
                if not seen_heading and not seen_body and _looks_like_document_title_line(text):
                    item["heading_level"] = 1
                    item["heading_level_source"] = "paddle_loc_heuristic"
                else:
                    item.setdefault("heading_level", 2)
                    item.setdefault("heading_level_source", "paddle_loc_heuristic")
                seen_heading = True

        if should_demote:
            item["label"] = "text"
            item["type"] = "text"
            attrs = item.get("attrs") if isinstance(item.get("attrs"), dict) else {}
            item["attrs"] = {
                **attrs,
                "candidate_roles": [label],
                "classification_confidence": "low",
                "classification_reason": reason,
            }
        elif label not in {"page_header", "page_footer", "page_number"}:
            if label == "text" and y0 > 120:
                seen_body = True
            if label == "section_header":
                seen_heading = True
        result.append(item)
    return result


def _weak_heading_without_context(blocks: list[dict[str, Any]], index: int) -> bool:
    block = blocks[index]
    text = str(block.get("text") or "").strip()
    if _HEADING_NUMBER_RE.match(text):
        return False
    bbox = block.get("loc_bbox_1000") or block.get("normalized_bbox") or [0, 0, 0, 0]
    if not isinstance(bbox, list) or len(bbox) != 4:
        return True
    x0, y0, x1, y1 = bbox
    words = text.split()
    if len(words) == 1 and y0 <= 700:
        return False
    if ":" in text and len(words) <= 12 and y0 <= 260:
        return False
    previous_gap = _vertical_gap(blocks[index - 1], block) if index > 0 else 999
    next_gap = _vertical_gap(block, blocks[index + 1]) if index + 1 < len(blocks) else 999
    centered = abs(((x0 + x1) / 2) - 500) <= 180
    return not (centered or previous_gap >= 22 or next_gap >= 22)


def _looks_like_front_matter_metadata(text: str) -> bool:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    lower = cleaned.lower()
    if not cleaned:
        return False
    metadata_patterns = (
        r"\bdoi\b",
        r"\bissn\b",
        r"\bisbn\b",
        r"\bpublished\b",
        r"\bcopyright\b",
        r"\b©\b",
        r"\bspringer science\b",
        r"\bvol(?:ume)?\.?\s*\d+",
        r"\bno\.?\s*\d+",
        r"^\s*\d{4}\s*$",
        r"^\s*\d{1,4}\s*[:]\s*\d{1,4}(?:[-–]\d{1,4})?\s*$",
    )
    return any(re.search(pattern, lower, re.IGNORECASE) for pattern in metadata_patterns)


def _looks_like_author_or_date_line(text: str) -> bool:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if _looks_like_front_matter_metadata(cleaned):
        return True
    words = cleaned.split()
    if 1 < len(words) <= 5 and not re.search(r"[.;:!?]", cleaned):
        capitalized = sum(1 for word in words if word[:1].isupper())
        return capitalized >= max(1, len(words) - 1)
    return False


def _looks_like_document_title_line(text: str) -> bool:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    words = cleaned.split()
    if _looks_like_front_matter_metadata(cleaned):
        return False
    if ":" in cleaned and 3 <= len(words) <= 14:
        return True
    if len(words) >= 4 and not _SENTENCE_END_RE.search(cleaned):
        return True
    return False


def _median_line_height(blocks: list[dict[str, Any]]) -> float:
    heights: list[int] = []
    for block in blocks:
        bbox = block.get("loc_bbox_1000") or block.get("normalized_bbox")
        if isinstance(bbox, list) and len(bbox) == 4:
            heights.append(max(1, int(bbox[3]) - int(bbox[1])))
    if not heights:
        return 14.0
    heights.sort()
    return float(heights[len(heights) // 2])


def _vertical_gap(a: dict[str, Any], b: dict[str, Any]) -> int:
    a_bbox = a.get("loc_bbox_1000") or a.get("normalized_bbox") or [0, 0, 0, 0]
    b_bbox = b.get("loc_bbox_1000") or b.get("normalized_bbox") or [0, 0, 0, 0]
    if not isinstance(a_bbox, list) or not isinstance(b_bbox, list) or len(a_bbox) != 4 or len(b_bbox) != 4:
        return 0
    return int(b_bbox[1]) - int(a_bbox[3])


def _should_merge_text_lines(a: dict[str, Any], b: dict[str, Any], *, median_height: float) -> bool:
    a_bbox = a.get("loc_bbox_1000") or a.get("normalized_bbox")
    b_bbox = b.get("loc_bbox_1000") or b.get("normalized_bbox")
    if not isinstance(a_bbox, list) or not isinstance(b_bbox, list) or len(a_bbox) != 4 or len(b_bbox) != 4:
        return True
    ax0, _ay0, ax1, ay1 = a_bbox
    bx0, by0, bx1, _by1 = b_bbox
    gap = int(by0) - int(ay1)
    if gap < 0:
        return False
    if gap > max(34, median_height * 2.2):
        return False
    if abs(int(ax0) - int(bx0)) > 85 and abs(int(ax1) - int(bx1)) > 120:
        return False
    return True


def _starts_new_footnote(text: str) -> bool:
    return bool(_PADDLE_SUPERSCRIPT_FOOTNOTE_RE.match(text or ""))


def _classification_confidence(block: dict[str, Any]) -> str:
    reason = str(block.get("inference_reason") or "")
    if reason in {"top_edge_page_number", "bottom_edge_page_number", "leading_footnote_marker"}:
        return "high"
    if reason:
        return "medium"
    return "low"


def _merge_loc_group(group: list[dict[str, Any]], label: str, *, raw_role: str) -> dict[str, Any]:
    if not group:
        return {"label": label, "type": label, "text": ""}
    texts = [str(item.get("text") or "").strip() for item in group if str(item.get("text") or "").strip()]
    separator = "\n" if label == "footnote" else " "
    merged_text = separator.join(texts).strip()
    bbox = _union_bbox([item.get("bbox") for item in group])
    norm_bbox = _union_bbox([item.get("loc_bbox_1000") or item.get("normalized_bbox") for item in group])
    first = group[0]
    lines = []
    raw_lines = []
    for item in group:
        raw = item.get("raw") if isinstance(item.get("raw"), dict) else {}
        raw_line = raw.get("paddle_loc_line")
        if isinstance(raw_line, str):
            raw_lines.append(raw_line)
        lines.append(
            {
                "spans": [
                    {
                        "text": str(item.get("text") or ""),
                        "bbox": item.get("bbox"),
                        "label": item.get("label"),
                        "loc_bbox_1000": item.get("loc_bbox_1000"),
                        "normalized_bbox": item.get("normalized_bbox"),
                        "raw": raw,
                    }
                ]
            }
        )
    attrs = {
        "raw_lines": raw_lines,
        "classification_confidence": "medium" if label == "text" else _classification_confidence(first),
        "classification_reason": first.get("inference_reason"),
        "paddle_loc_segment_role": raw_role,
    }
    if label == "footnote":
        marker = _footnote_marker_text(texts[0] if texts else "")
        if marker:
            attrs["original_marker"] = marker
    return {
        "label": label,
        "type": label,
        "text": merged_text,
        "bbox": bbox,
        "normalized_bbox": norm_bbox,
        "loc_bbox_1000": norm_bbox,
        "raw_prompt_label": first.get("raw_prompt_label"),
        "raw_query": first.get("raw_query"),
        "order": first.get("order", 0),
        "lines": lines,
        "attrs": attrs,
        "raw": {
            "paddle_loc_segment_role": raw_role,
            "source_line_count": len(group),
            "raw_lines": raw_lines,
        },
    }


def _union_bbox(values: list[Any]) -> list[Any] | None:
    bboxes = [value for value in values if isinstance(value, list) and len(value) == 4]
    if not bboxes:
        return None
    return [
        min(float(bbox[0]) for bbox in bboxes),
        min(float(bbox[1]) for bbox in bboxes),
        max(float(bbox[2]) for bbox in bboxes),
        max(float(bbox[3]) for bbox in bboxes),
    ]


def _footnote_marker_text(text: str) -> str | None:
    match = _PADDLE_SUPERSCRIPT_FOOTNOTE_RE.match(text or "")
    if not match:
        return None
    return match.group(0).strip()


def classify_paddle_loc_ocr_line(
    text: str,
    *,
    norm_bbox: list[int],
    in_footnotes: bool,
) -> tuple[str, bool, int | None, str | None]:
    x0, y0, x1, y1 = norm_bbox
    stripped = text.strip()
    starts_footnote = bool(_PADDLE_SUPERSCRIPT_FOOTNOTE_RE.match(stripped))

    if y1 <= 85 and _PAGE_NUMBER_RE.fullmatch(stripped):
        return "page_number", in_footnotes, None, "top_edge_page_number"
    if y0 >= 915 and _PAGE_NUMBER_RE.fullmatch(stripped):
        return "page_number", in_footnotes, None, "bottom_edge_page_number"

    if y0 >= 930 and _looks_like_footer_line(stripped, starts_footnote=starts_footnote):
        return "page_footer", False, None, "bottom_edge_footer"

    if y1 <= 75 and (x0 <= 120 or x1 >= 880) and looks_like_running_header_text(stripped):
        return "page_header", in_footnotes, None, "top_edge_running_header"

    if starts_footnote:
        return "footnote", True, None, "leading_footnote_marker"
    if in_footnotes and y0 >= 560 and not _looks_like_footer_line(stripped, starts_footnote=False):
        return "footnote", True, None, "continued_footnote_zone"

    heading_level = infer_heading_level_from_text_and_label(
        text=stripped,
        raw_label="section_header" if _looks_like_heading_line(stripped, norm_bbox=norm_bbox) else None,
        bbox=[float(x0), float(y0), float(x1), float(y1)],
        page_height=float(PADDLE_LOC_SCALE),
    )
    if heading_level is not None:
        return "section_header", in_footnotes, heading_level, "heading_shape"

    return "text", in_footnotes, None, None


def find_paddle_layout_results(data: Any) -> list[Any]:
    if not isinstance(data, dict):
        return []
    candidates: list[Any] = [data, data.get("raw")]
    if isinstance(data.get("raw"), dict):
        candidates.extend([data["raw"].get("response"), data["raw"].get("result")])
    for candidate in candidates:
        result = paddle_layout_results_from_candidate(candidate)
        if result:
            return result
    return []


def paddle_layout_results_from_candidate(candidate: Any) -> list[Any]:
    if not isinstance(candidate, dict):
        return []
    value = candidate.get("layoutParsingResults")
    if isinstance(value, list):
        return value
    result = candidate.get("result")
    if isinstance(result, dict):
        value = result.get("layoutParsingResults")
        if isinstance(value, list):
            return value
        nested = result.get("result")
        if isinstance(nested, dict):
            value = nested.get("layoutParsingResults")
            if isinstance(value, list):
                return value
    return []


def extract_paddle_pruned_blocks(pruned_result: Any) -> list[dict[str, Any]]:
    if isinstance(pruned_result, list):
        return [_normalize_official_block(item) for item in pruned_result if isinstance(item, dict)]
    if not isinstance(pruned_result, dict):
        return []
    block_keys = (
        "blocks",
        "layout_bboxes",
        "boxes",
        "bboxes",
        "layout",
        "regions",
        "parsing_res_list",
        "res",
    )
    for key in block_keys:
        value = pruned_result.get(key)
        if isinstance(value, list):
            return [
                _normalize_official_block(dict(item, block_source=item.get("block_source", key)))
                for item in value
                if isinstance(item, dict)
            ]
    if any(key in pruned_result for key in ("label", "type", "bbox", "block_bbox", "text", "content", "block_content")):
        return [_normalize_official_block(dict(pruned_result, block_source=pruned_result.get("block_source", "prunedResult")))]
    return []


def paddle_heading_attrs(raw_label: Any, text: str = "", bbox: list[float] | None = None, page_height: float | None = None) -> dict[str, Any]:
    level = infer_heading_level_from_text_and_label(
        text=text,
        raw_label=str(raw_label or ""),
        bbox=bbox,
        page_height=page_height,
    )
    if level is None:
        return {}
    raw = str(raw_label or "").strip().lower().replace("-", "_").replace(" ", "_")
    role = "unknown"
    source = "heuristic"
    if raw in {"doc_title", "doctitle", "document_title"}:
        role = "doc_title"
        source = "paddle_label"
    elif raw in {"title"}:
        role = "title"
        source = "paddle_label" if level == 1 else "paddle_label_context"
    elif raw in {"paragraph_title", "section_header", "sectionheader", "heading"}:
        role = "section_title"
        source = "paddle_label"
    return {
        "heading_level": level,
        "heading_level_source": source,
        "raw_heading_level": level,
        "title_role": role,
    }


def infer_heading_level_from_text_and_label(
    *,
    text: str,
    raw_label: str | None,
    bbox: list[float] | None = None,
    page_height: float | None = None,
) -> int | None:
    raw = str(raw_label or "").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in {"doc_title", "doctitle", "document_title"}:
        return 1
    if raw == "title":
        if _is_top_band(bbox, page_height, frac=0.25):
            return 1
        return 2
    if raw in {"paragraph_title", "section_header", "sectionheader", "heading"}:
        numbered = _heading_level_from_numbering(text)
        return numbered or 2
    return None


def _normalize_official_block(item: dict[str, Any]) -> dict[str, Any]:
    block = dict(item)
    raw_label = block.get("block_label") or block.get("label") or block.get("type")
    normalized = _normalize_paddle_label(raw_label)
    if normalized:
        block.setdefault("label", normalized)
        block.setdefault("type", normalized)
    bbox = block.get("block_bbox") or block.get("bbox") or block.get("coordinate")
    attrs = paddle_heading_attrs(raw_label, text=str(block.get("block_content") or block.get("text") or ""), bbox=bbox)
    if attrs:
        block.update({key: value for key, value in attrs.items() if key not in block})
    return block


def _normalize_paddle_label(raw_label: Any) -> str | None:
    raw = str(raw_label or "").strip()
    if not raw:
        return None
    compact = raw.replace("-", "_").replace(" ", "_")
    lower = compact.lower()
    official = {
        "doctitle": "doc_title",
        "doc_title": "doc_title",
        "document_title": "doc_title",
        "title": "title",
        "paragraph_title": "paragraph_title",
        "header": "page_header",
        "footer": "page_footer",
        "number": "page_number",
        "page_number": "page_number",
        "formula": "formula",
        "table": "table",
        "figure": "figure",
        "chart": "chart",
        "algorithm": "algorithm",
        "reference": "reference",
        "content": "text",
        "text": "text",
    }
    return official.get(lower, lower)


def _looks_like_footer_line(text: str, *, starts_footnote: bool) -> bool:
    cleaned = _strip_leading_note_marker(text)
    if not cleaned or len(cleaned) > 80:
        return False
    if starts_footnote and _SENTENCE_END_RE.search(cleaned):
        return False
    if len(cleaned.split()) <= 3 and not re.search(r"[.;:]", cleaned):
        return True
    return False


def _looks_like_heading_line(text: str, *, norm_bbox: list[int]) -> bool:
    x0, y0, x1, y1 = norm_bbox
    del x0, x1
    cleaned = text.strip()
    if not cleaned or len(cleaned) > 90 or y0 > 650:
        return False
    if _looks_like_front_matter_metadata(cleaned):
        return False
    if _SENTENCE_END_RE.search(cleaned):
        return False
    if _HEADING_NUMBER_RE.match(cleaned):
        return True
    words = cleaned.split()
    if len(words) > 8:
        return False
    has_lower = any(ch.islower() for ch in cleaned)
    if ":" in cleaned and len(words) <= 8 and y0 <= 220:
        return True
    if len(words) <= 5 and has_lower and y1 - y0 <= 35:
        return True
    return False


def looks_like_running_header_text(text: str) -> bool:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned or len(cleaned) > 90:
        return False
    if _PAGE_NUMBER_RE.fullmatch(cleaned):
        return False
    if _PADDLE_SUPERSCRIPT_FOOTNOTE_RE.match(cleaned):
        return False
    if _SENTENCE_END_RE.search(cleaned):
        return False
    lower = cleaned.lower()
    if lower in {"abstract", "keywords", "introduction", "conclusion", "references", "bibliography"}:
        return False
    words = cleaned.split()
    if len(words) > 9:
        return False
    return any(ch.isalpha() for ch in cleaned)


def _heading_level_from_numbering(text: str) -> int | None:
    match = _HEADING_NUMBER_RE.match(text or "")
    if not match:
        return None
    numeric = match.group(1)
    if numeric:
        return max(1, min(6, numeric.count(".") + 1))
    return 1


def _strip_leading_note_marker(text: str) -> str:
    return re.sub(r"^\s*(?:\\\(\^\{\d+\}\\\)|\^\d+|[⁰¹²³⁴⁵⁶⁷⁸⁹¹²³⁴⁵⁶⁷⁸⁹]+)\s*", "", text or "").strip()


def _is_top_band(bbox: list[float] | None, page_height: float | None, *, frac: float) -> bool:
    if not bbox or not isinstance(page_height, (int, float)) or page_height <= 0:
        return False
    return float(bbox[1]) <= float(page_height) * frac
