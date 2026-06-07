from __future__ import annotations

import copy
from typing import Any


TEXT_BLOCK_TYPES = {"Text", "SectionHeader", "PageHeader", "PageFooter", "Footnote", "MarginalNote", "Reference", "Caption", "ListItem"}


def merge_external_ocr_into_middle_document(
    middle_payload: dict[str, Any],
    ocr_payload: dict[str, Any] | list[Any],
    *,
    backend: str,
    source: str | None = None,
    model: str | None = None,
    unmatched_policy: str = "append_text_blocks",
    min_containment: float = 0.20,
) -> dict[str, Any]:
    """Merge external OCR text boxes into Contexture Middle JSON spans.

    This is an offline bridge for PaddleOCR/MinerU/generic OCR JSON. It does not
    run OCR and does not render Markdown.
    """
    data = copy.deepcopy(middle_payload)
    data.setdefault("metadata", {})["ocr_import_source"] = source
    backends = data.setdefault("backends", {})
    backends["ocr"] = backend
    if model:
        backends["ocr_model"] = model

    pages_by_index = {
        int(page.get("index", pos)): page
        for pos, page in enumerate(data.get("pages") or [])
        if isinstance(page, dict)
    }
    ocr_pages = _extract_pages(ocr_payload)
    imported = 0
    unmatched = 0

    for fallback_index, page_payload in enumerate(ocr_pages):
        page_index = _resolve_page_index(page_payload, fallback_index)
        page = pages_by_index.get(page_index)
        if page is None:
            continue
        page.setdefault("provenance", []).append(_provenance(backend, "ocr", model=model, source=source))
        items = _extract_ocr_items(page_payload)
        for item_index, item in enumerate(items):
            if not item.get("text"):
                continue
            block = _best_block_for_item(page, item, min_containment=min_containment)
            if block is None:
                unmatched += 1
                if unmatched_policy == "append_text_blocks":
                    block = _append_ocr_text_block(page, item, item_index=item_index, backend=backend, model=model, source=source)
                elif unmatched_policy == "drop":
                    continue
                else:
                    raise ValueError("unmatched_policy must be append_text_blocks or drop")
            _append_span(block, item, backend=backend, model=model, source=source)
            imported += 1

    for page in pages_by_index.values():
        for block in page.get("blocks") or []:
            if isinstance(block, dict):
                _sort_spans_and_fill_text(block)

    data.setdefault("metadata", {})["ocr_import"] = {
        "backend": backend,
        "model": model,
        "source": source,
        "imported_spans": imported,
        "unmatched_items": unmatched,
        "unmatched_policy": unmatched_policy,
    }
    return data


def _extract_pages(payload: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        pages = []
        for item in payload:
            if isinstance(item, dict):
                pages.extend(_extract_pages(item))
        return pages
    if not isinstance(payload, dict):
        return []
    result = payload.get("res")
    if isinstance(result, dict):
        return [result]
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    for key in ("pages", "pdf_info", "page_info", "page_infos"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    if any(
        key in payload
        for key in (
            "rec_texts",
            "ocr_res",
            "ocr_results",
            "text_lines",
            "lines",
            "spans",
            "blocks",
            "para_blocks",
            "preproc_blocks",
            "parsing_res_list",
            "overall_ocr_res",
        )
    ):
        return [payload]
    return []


def _resolve_page_index(page_payload: dict[str, Any], fallback: int) -> int:
    for key in ("page_idx", "page_index", "page_id"):
        value = page_payload.get(key)
        if value is not None:
            return int(value)
    return fallback


def _extract_ocr_items(page_payload: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    rec_texts = page_payload.get("rec_texts")
    if isinstance(rec_texts, list):
        boxes = page_payload.get("rec_boxes") or page_payload.get("rec_polys") or page_payload.get("dt_polys")
        scores = page_payload.get("rec_scores") or page_payload.get("scores") or []
        if isinstance(boxes, list):
            for index, text in enumerate(rec_texts):
                box = boxes[index] if index < len(boxes) else None
                item = _ocr_item_from_parts(text=text, geometry=box, confidence=scores[index] if index < len(scores) else None)
                if item:
                    items.append(item)

    overall_ocr_res = page_payload.get("overall_ocr_res")
    if isinstance(overall_ocr_res, dict):
        items.extend(_extract_ocr_items(overall_ocr_res))

    for key in ("ocr_res", "ocr_results", "text_lines", "lines", "spans"):
        value = page_payload.get(key)
        if isinstance(value, list):
            items.extend(_extract_items_from_list(value))

    for key in ("blocks", "para_blocks", "preproc_blocks", "parsing_res_list"):
        value = page_payload.get(key)
        if isinstance(value, list):
            for block in value:
                if isinstance(block, dict):
                    items.extend(_extract_ocr_items(block))
    return items


def _extract_items_from_list(values: list[Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for value in values:
        if isinstance(value, dict):
            text = _first_value(value, ("text", "content", "html", "rec_text"))
            if text is not None:
                item = _ocr_item_from_parts(
                    text=text,
                    geometry=_first_value(value, ("bbox", "box", "coordinate", "poly", "polygon", "points")),
                    confidence=_first_value(value, ("confidence", "score", "prob", "rec_score")),
                    raw=value,
                )
                if item:
                    items.append(item)
            for key in ("spans", "lines"):
                nested = value.get(key)
                if isinstance(nested, list):
                    items.extend(_extract_items_from_list(nested))
        elif isinstance(value, list):
            item = _ocr_item_from_sequence(value)
            if item:
                items.append(item)
    return items


def _ocr_item_from_sequence(value: list[Any]) -> dict[str, Any] | None:
    if len(value) >= 2 and isinstance(value[0], list):
        confidence = None
        text = value[1]
        if isinstance(value[1], (list, tuple)) and value[1]:
            text = value[1][0]
            confidence = value[1][1] if len(value[1]) > 1 else None
        elif len(value) > 2:
            confidence = value[2]
        return _ocr_item_from_parts(text=text, geometry=value[0], confidence=confidence, raw={"raw": value})
    return None


def _ocr_item_from_parts(
    *,
    text: Any,
    geometry: Any,
    confidence: Any = None,
    raw: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    text_value = str(text or "").strip()
    if not text_value:
        return None
    polygon = _extract_polygon(geometry)
    bbox = _extract_bbox(geometry, polygon)
    conf = float(confidence) if isinstance(confidence, (int, float)) else None
    return {"text": text_value, "bbox": bbox, "polygon": polygon, "confidence": conf, "raw": raw or {}}


def _best_block_for_item(page: dict[str, Any], item: dict[str, Any], *, min_containment: float) -> dict[str, Any] | None:
    item_bbox = item.get("bbox")
    if not _valid_bbox(item_bbox):
        return _first_text_block(page)
    best_block = None
    best_score = 0.0
    for block in page.get("blocks") or []:
        if not isinstance(block, dict) or block.get("type") not in TEXT_BLOCK_TYPES:
            continue
        block_bbox = block.get("bbox")
        if not _valid_bbox(block_bbox):
            continue
        score = _containment_ratio(item_bbox, block_bbox)
        if score > best_score:
            best_score = score
            best_block = block
    return best_block if best_score >= min_containment else None


def _first_text_block(page: dict[str, Any]) -> dict[str, Any] | None:
    for block in page.get("blocks") or []:
        if isinstance(block, dict) and block.get("type") in TEXT_BLOCK_TYPES:
            return block
    return None


def _append_ocr_text_block(
    page: dict[str, Any],
    item: dict[str, Any],
    *,
    item_index: int,
    backend: str,
    model: str | None,
    source: str | None,
) -> dict[str, Any]:
    blocks = page.setdefault("blocks", [])
    page_index = int(page.get("index", 0))
    block = {
        "id": f"p{page_index}-ocr-{item_index}",
        "type": "Text",
        "page_index": page_index,
        "order": len(blocks),
        "text": "",
        "anchor_start": page_index,
        "anchor_end": page_index + 1,
        "bbox": item.get("bbox"),
        "polygon": item.get("polygon"),
        "confidence": item.get("confidence"),
        "spans": [],
        "children": [],
        "attrs": {"source": "external_ocr_unmatched"},
        "provenance": [_provenance(backend, "ocr_block", model=model, source=source, confidence=item.get("confidence"))],
    }
    blocks.append(block)
    return block


def _append_span(block: dict[str, Any], item: dict[str, Any], *, backend: str, model: str | None, source: str | None) -> None:
    block.setdefault("spans", []).append(
        {
            "text": item["text"],
            "bbox": item.get("bbox"),
            "polygon": item.get("polygon"),
            "confidence": item.get("confidence"),
            "attrs": {"raw": item.get("raw") or {}},
            "provenance": [_provenance(backend, "ocr", model=model, source=source, confidence=item.get("confidence"))],
        }
    )


def _sort_spans_and_fill_text(block: dict[str, Any]) -> None:
    spans = block.get("spans")
    if not isinstance(spans, list) or not spans:
        return
    spans.sort(key=lambda span: _bbox_sort_key(span.get("bbox") if isinstance(span, dict) else None))
    if not str(block.get("text") or "").strip():
        block["text"] = " ".join(str(span.get("text") or "").strip() for span in spans if isinstance(span, dict) and str(span.get("text") or "").strip())


def _provenance(
    backend: str,
    stage: str,
    *,
    model: str | None = None,
    source: str | None = None,
    confidence: float | None = None,
) -> dict[str, Any]:
    return {
        "backend": backend,
        "stage": stage,
        "model": model,
        "source": source,
        "confidence": confidence,
    }


def _extract_polygon(value: Any) -> list[list[float]] | None:
    if isinstance(value, list) and len(value) == 4 and all(isinstance(point, list) and len(point) == 2 for point in value):
        return [[float(point[0]), float(point[1])] for point in value]
    return None


def _extract_bbox(value: Any, polygon: list[list[float]] | None) -> list[float] | None:
    if isinstance(value, list) and len(value) == 4 and all(isinstance(item, (int, float)) for item in value):
        return [float(item) for item in value]
    if polygon:
        xs = [point[0] for point in polygon]
        ys = [point[1] for point in polygon]
        return [min(xs), min(ys), max(xs), max(ys)]
    return None


def _valid_bbox(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 4 and all(isinstance(item, (int, float)) for item in value) and value[2] > value[0] and value[3] > value[1]


def _containment_ratio(inner: list[float], outer: list[float]) -> float:
    ix0 = max(float(inner[0]), float(outer[0]))
    iy0 = max(float(inner[1]), float(outer[1]))
    ix1 = min(float(inner[2]), float(outer[2]))
    iy1 = min(float(inner[3]), float(outer[3]))
    intersection = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    inner_area = max(0.0, float(inner[2]) - float(inner[0])) * max(0.0, float(inner[3]) - float(inner[1]))
    return intersection / inner_area if inner_area else 0.0


def _bbox_sort_key(value: Any) -> tuple[float, float]:
    if _valid_bbox(value):
        return float(value[1]), float(value[0])
    return 0.0, 0.0


def _first_value(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in data:
            return data[key]
    return None
