from __future__ import annotations

from typing import Any

from aih_contexture.middle.labels import normalize_block_type
from aih_contexture.middle.schema import MiddleBlock, MiddleDocument, MiddlePage, MiddleProvenance


def external_layout_document_to_middle_document(
    payload: dict[str, Any] | list[Any],
    *,
    backend: str,
    source_name: str | None = None,
    source: str | None = None,
    model: str | None = None,
    block_source: str = "auto",
) -> MiddleDocument:
    pages_data = _extract_pages(payload)
    pages = [
        external_layout_page_to_middle_page(
            page_data,
            page_index=index if _first_value(page_data, ("page_idx", "page_index")) is None else None,
            backend=backend,
            source=source,
            model=model,
            block_source=block_source,
        )
        for index, page_data in enumerate(pages_data)
    ]
    return MiddleDocument(
        source_name=source_name,
        pages=sorted(pages, key=lambda page: page.index),
        metadata={
            "import_source": "external_layout_json",
            "source": source,
            "block_source": block_source,
        },
        backends={"layout": backend, "layout_model": model},
    )


def external_layout_page_to_middle_page(
    page_data: dict[str, Any],
    *,
    page_index: int | None = None,
    backend: str,
    source: str | None = None,
    model: str | None = None,
    block_source: str = "auto",
) -> MiddlePage:
    raw_page_index = _first_non_none_value(page_data, ("page_idx", "page_index"))
    resolved_page_index = int(page_index if page_index is not None else (0 if raw_page_index is None else raw_page_index))
    blocks_data = _extract_blocks(page_data, block_source=block_source)
    page_size = _extract_page_size(page_data)
    blocks = []

    for order, block_data in enumerate(blocks_data):
        raw_label = _first_value(block_data, ("label", "type", "layout_label", "category", "block_type", "block_label"))
        polygon = _extract_polygon(block_data)
        bbox = _extract_bbox(block_data, polygon)
        canonical_type = normalize_block_type(str(raw_label) if raw_label is not None else None)
        confidence = _extract_confidence(block_data)
        attrs = {
            "raw_label": raw_label,
            "raw": {
                key: value
                for key, value in block_data.items()
                if key not in {"text", "content", "html"}
            },
        }
        if canonical_type == "Text" and str(raw_label or "").strip().lower().replace("-", "_") == "vertical_text":
            attrs["orientation"] = "vertical"
        if canonical_type == "ComplexRegion" and raw_label:
            attrs["unmapped_label"] = raw_label
        raw_order = _first_non_none_value(block_data, ("order", "position", "block_order", "block_id"))

        blocks.append(
            MiddleBlock(
                id=str(block_data.get("id") or block_data.get("index") or f"p{resolved_page_index}-b{order}"),
                type=canonical_type,
                page_index=resolved_page_index,
                order=order if raw_order is None else int(raw_order),
                text=_extract_text(block_data),
                bbox=bbox,
                polygon=polygon,
                confidence=confidence,
                attrs=attrs,
                provenance=[
                    MiddleProvenance(
                        backend=backend,
                        stage="layout",
                        raw_label=str(raw_label) if raw_label is not None else None,
                        model=model,
                        confidence=confidence,
                        source=source,
                    )
                ],
            )
        )

    return MiddlePage(
        index=resolved_page_index,
        width=page_size[0],
        height=page_size[1],
        blocks=sorted(blocks, key=lambda block: (block.order, block.id)),
        provenance=[MiddleProvenance(backend=backend, stage="layout", model=model, source=source)],
    )


def _extract_pages(payload: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        pages = []
        for item in payload:
            if not isinstance(item, dict):
                continue
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
    if any(key in payload for key in ("blocks", "layout_bboxes", "boxes", "para_blocks", "preproc_blocks", "parsing_res_list")):
        return [payload]
    return []


def _extract_blocks(page_data: dict[str, Any], *, block_source: str = "auto") -> list[dict[str, Any]]:
    keys = (
        "blocks",
        "layout_bboxes",
        "boxes",
        "bboxes",
        "layout",
        "regions",
        "para_blocks",
        "preproc_blocks",
        "discarded_blocks",
        "parsing_res_list",
    )
    normalized_source = block_source.strip().lower().replace("-", "_")

    if normalized_source == "auto":
        selected_keys = keys
        merge = False
    elif normalized_source == "all":
        selected_keys = keys
        merge = True
    elif normalized_source in keys:
        selected_keys = (normalized_source,)
        merge = False
    else:
        raise ValueError(
            f"Unknown external layout block_source: {block_source}. "
            "Use auto, all, blocks, layout_bboxes, boxes, bboxes, layout, regions, para_blocks, preproc_blocks, discarded_blocks, or parsing_res_list."
        )

    if merge:
        merged = []
        for key in selected_keys:
            value = page_data.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        block = dict(item)
                        block.setdefault("block_source", key)
                        merged.append(block)
        return merged

    for key in selected_keys:
        value = page_data.get(key)
        if isinstance(value, list):
            return [dict(item, block_source=item.get("block_source", key)) for item in value if isinstance(item, dict)]
    return []


def _extract_page_size(page_data: dict[str, Any]) -> tuple[float | None, float | None]:
    for width_key, height_key in (("width", "height"), ("page_width", "page_height")):
        if width_key in page_data and height_key in page_data:
            return float(page_data[width_key]), float(page_data[height_key])
    page_size = page_data.get("page_size")
    if isinstance(page_size, list) and len(page_size) == 2:
        return float(page_size[0]), float(page_size[1])
    bbox = page_data.get("page_bbox") or page_data.get("image_bbox")
    if isinstance(bbox, list) and len(bbox) == 4:
        return float(bbox[2]) - float(bbox[0]), float(bbox[3]) - float(bbox[1])
    return None, None


def _extract_polygon(block_data: dict[str, Any]) -> list[list[float]] | None:
    polygon = _first_value(block_data, ("polygon", "poly", "points"))
    if isinstance(polygon, list) and len(polygon) == 4 and all(isinstance(point, list) and len(point) == 2 for point in polygon):
        return [[float(point[0]), float(point[1])] for point in polygon]
    return None


def _extract_bbox(block_data: dict[str, Any], polygon: list[list[float]] | None) -> list[float] | None:
    bbox = _first_value(block_data, ("bbox", "layout_bbox", "coordinate", "box", "block_bbox"))
    if isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(value, (int, float)) for value in bbox):
        return [float(value) for value in bbox]
    if polygon:
        xs = [point[0] for point in polygon]
        ys = [point[1] for point in polygon]
        return [min(xs), min(ys), max(xs), max(ys)]
    return None


def _extract_confidence(block_data: dict[str, Any]) -> float | None:
    value = _first_value(block_data, ("confidence", "score", "prob"))
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _extract_text(block_data: dict[str, Any]) -> str:
    direct = _first_value(block_data, ("text", "content", "html", "block_content"))
    if direct is not None:
        return str(direct)

    pieces: list[str] = []
    for line in block_data.get("lines", []) or []:
        if not isinstance(line, dict):
            continue
        line_text = _first_value(line, ("text", "content"))
        if line_text is not None:
            pieces.append(str(line_text))
            continue
        span_texts = []
        for span in line.get("spans", []) or []:
            if isinstance(span, dict):
                span_text = _first_value(span, ("text", "content", "html"))
                if span_text is not None:
                    span_texts.append(str(span_text))
        if span_texts:
            pieces.append("".join(span_texts))
    return "\n".join(pieces)


def _first_value(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in data:
            return data[key]
    return None


def _first_non_none_value(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None
