from __future__ import annotations

import json
from typing import Any

from aih_contexture.middle.labels import normalize_block_type
from aih_contexture.middle.schema import MiddleBlock, MiddleDocument, MiddlePage, MiddleProvenance, MiddleSpan


def vlm_json_document_to_middle_document(
    payload: dict[str, Any] | list[Any] | str,
    *,
    backend: str = "vlm_generalized",
    model: str | None = None,
    source_name: str | None = None,
    source: str | None = None,
) -> MiddleDocument:
    """Normalize VLM JSON page output into Contexture Middle JSON.

    This adapter accepts the JSON page shape produced by VLM direct mode:
    a page object with ``printed_page_number``, ``page_width``,
    ``page_height`` and ``regions``. It also accepts a list of page objects or
    JSON strings, and document wrappers with ``pages`` or ``json_pages``.
    """
    pages_data = _extract_pages(payload)
    if not pages_data:
        raise ValueError(
            "Unsupported or empty VLM JSON: expected pages/regions from structured VLM output. "
            "For Markdown-only exports, import the Markdown file through markdown_postprocess instead."
        )
    pages = [
        vlm_json_page_to_middle_page(
            page_data,
            page_index=index if _first_non_none_value(page_data, ("page_index", "page_idx", "page_number")) is None else None,
            backend=backend,
            model=model,
            source=source,
        )
        for index, page_data in enumerate(pages_data)
    ]
    return MiddleDocument(
        source_name=source_name,
        pages=sorted(pages, key=lambda page: page.index),
        metadata={
            "import_source": "vlm_json",
            "source": source,
        },
        backends={"vlm": backend, "vlm_model": model},
    )


def vlm_json_page_to_middle_page(
    page_data: dict[str, Any],
    *,
    page_index: int | None = None,
    backend: str = "vlm_generalized",
    model: str | None = None,
    source: str | None = None,
) -> MiddlePage:
    raw_page_index = _first_non_none_value(page_data, ("page_index", "page_idx"))
    raw_page_number = page_data.get("page_number")
    if page_index is not None:
        resolved_page_index = int(page_index)
    elif raw_page_index is not None:
        resolved_page_index = int(raw_page_index)
    elif raw_page_number is not None:
        resolved_page_index = max(0, int(raw_page_number) - 1)
    else:
        resolved_page_index = 0

    width, height = _extract_page_size(page_data)
    provenance = MiddleProvenance(backend=backend, stage="vlm_parse", model=model, source=source)
    blocks = [
        _region_to_middle_block(
            region,
            page_index=resolved_page_index,
            order=order,
            backend=backend,
            model=model,
            source=source,
        )
        for order, region in enumerate(_extract_regions(page_data))
    ]
    for block, region in zip(blocks, _extract_regions(page_data)):
        space = region.get("coordinate_space")
        if space is None:
            space = page_data.get("coordinate_space")
        if space is not None:
            _normalize_declared_geometry(block, str(space).lower(), width, height)

    attrs = {}
    if page_data.get("coordinate_space") is not None:
        declared = str(page_data["coordinate_space"]).lower()
        attrs["coordinate_space"] = "page" if declared in {"normalized", "normalized_1000"} and width and height else declared
    if raw_page_number is not None:
        attrs["raw_page_number"] = raw_page_number
    if page_data.get("error"):
        attrs["error"] = page_data.get("error")
    if page_data.get("diagnostic"):
        attrs["diagnostic"] = page_data.get("diagnostic")

    return MiddlePage(
        index=resolved_page_index,
        width=width,
        height=height,
        printed_page=_text(page_data.get("printed_page_number")),
        blocks=sorted(blocks, key=lambda block: (block.order, block.id)),
        attrs=attrs,
        provenance=[provenance],
    )


def _region_to_middle_block(
    region: dict[str, Any],
    *,
    page_index: int,
    order: int,
    backend: str,
    model: str | None,
    source: str | None,
) -> MiddleBlock:
    raw_label = _first_value(region, ("label", "type", "block_type", "category"))
    raw_label_text = str(raw_label) if raw_label is not None else None
    canonical_type = normalize_block_type(raw_label_text)
    confidence = _extract_confidence(region)
    polygon = _extract_polygon(region)
    bbox = _extract_bbox(region, polygon)
    text = _text(_first_value(region, ("text", "content", "html", "markdown")))
    raw_id = _first_non_none_value(region, ("id", "region_id", "block_id", "index"))
    block_id = f"p{page_index}-v{order}" if raw_id is None else f"p{page_index}-{raw_id}"

    attrs = {
        "raw_label": raw_label,
        "raw": {
            key: value
            for key, value in region.items()
            if key not in {"text", "content", "html", "markdown"}
        },
    }
    normalized_label = (raw_label_text or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized_label in {"marginal_note_left", "marginal_note_right"}:
        attrs["side"] = "left" if normalized_label.endswith("_left") else "right"
    if canonical_type == "ComplexRegion" and raw_label_text:
        attrs["unmapped_label"] = raw_label_text

    provenance = MiddleProvenance(
        backend=backend,
        stage="vlm_parse",
        raw_label=raw_label_text,
        model=model,
        confidence=confidence,
        source=source,
    )
    spans = []
    if text:
        spans.append(
            MiddleSpan(
                text=text,
                bbox=bbox,
                polygon=polygon,
                confidence=confidence,
                attrs={"source": "vlm_region_text"},
                provenance=[
                    MiddleProvenance(
                        backend=backend,
                        stage="vlm_text",
                        raw_label=raw_label_text,
                        model=model,
                        confidence=confidence,
                        source=source,
                    )
                ],
            )
        )

    return MiddleBlock(
        id=str(block_id),
        type=canonical_type,
        page_index=page_index,
        order=order,
        text=text,
        bbox=bbox,
        polygon=polygon,
        confidence=confidence,
        spans=spans,
        attrs=attrs,
        provenance=[provenance],
    )


def _normalize_declared_geometry(block: MiddleBlock, space: str, width: float | None, height: float | None) -> None:
    block.attrs["coordinate_space"] = space
    scale = {"normalized": 1.0, "normalized_1000": 1000.0}.get(space)
    if scale is None or not width or not height:
        return
    def box(value):
        return [value[0] * width / scale, value[1] * height / scale,
                value[2] * width / scale, value[3] * height / scale] if value else value
    block.bbox = box(block.bbox)
    if block.polygon:
        block.polygon = [[x * width / scale, y * height / scale] for x, y in block.polygon]
    for span in block.spans:
        span.bbox = box(span.bbox)
        if span.polygon:
            span.polygon = [[x * width / scale, y * height / scale] for x, y in span.polygon]
    block.attrs.update(coordinate_space="page", coordinate_transform={"from": space, "width": width, "height": height})


def _extract_pages(payload: dict[str, Any] | list[Any] | str) -> list[dict[str, Any]]:
    parsed = _parse_item(payload)
    if isinstance(parsed, list):
        pages: list[dict[str, Any]] = []
        for item in parsed:
            pages.extend(_extract_pages(item))
        return pages
    if not isinstance(parsed, dict):
        raise ValueError("Unsupported VLM JSON page: expected a structured regions object")
    for key in ("pages", "json_pages"):
        value = parsed.get(key)
        if isinstance(value, list):
            return _extract_pages(value)
    if isinstance(parsed.get("res"), dict):
        return _extract_pages(parsed["res"])
    if isinstance(parsed.get("regions"), list):
        return [parsed]
    raise ValueError("Unsupported VLM JSON page: missing regions; import Markdown-only exports as Markdown")


def _parse_item(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _extract_regions(page_data: dict[str, Any]) -> list[dict[str, Any]]:
    regions = page_data.get("regions")
    if not isinstance(regions, list):
        return []
    return [region for region in regions if isinstance(region, dict)]


def _extract_page_size(page_data: dict[str, Any]) -> tuple[float | None, float | None]:
    width = _first_non_none_value(page_data, ("page_width", "width"))
    height = _first_non_none_value(page_data, ("page_height", "height"))
    numeric_width = _positive_float(width)
    numeric_height = _positive_float(height)
    return numeric_width, numeric_height


def _extract_polygon(data: dict[str, Any]) -> list[list[float]] | None:
    polygon = _first_value(data, ("polygon", "poly", "points"))
    if isinstance(polygon, list) and len(polygon) == 4 and all(_is_point(point) for point in polygon):
        return [[float(point[0]), float(point[1])] for point in polygon]
    if isinstance(polygon, list) and len(polygon) == 8 and all(isinstance(value, (int, float)) for value in polygon):
        return [[float(polygon[i]), float(polygon[i + 1])] for i in range(0, 8, 2)]
    return None


def _extract_bbox(data: dict[str, Any], polygon: list[list[float]] | None) -> list[float] | None:
    bbox = _first_value(data, ("bbox", "box", "coordinate", "coordinates", "layout_bbox", "block_bbox"))
    if isinstance(bbox, dict):
        values = [bbox.get("x0"), bbox.get("y0"), bbox.get("x1"), bbox.get("y1")]
        if all(isinstance(value, (int, float)) for value in values):
            return [float(value) for value in values]
    if isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(value, (int, float)) for value in bbox):
        return [float(value) for value in bbox]
    if polygon:
        xs = [point[0] for point in polygon]
        ys = [point[1] for point in polygon]
        return [min(xs), min(ys), max(xs), max(ys)]
    return None


def _extract_confidence(data: dict[str, Any]) -> float | None:
    value = _first_value(data, ("confidence", "score", "prob", "probability"))
    if isinstance(value, (int, float)):
        return float(value)
    return None


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


def _positive_float(value: Any) -> float | None:
    if isinstance(value, (int, float)) and float(value) > 0:
        return float(value)
    return None


def _is_point(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 2 and all(isinstance(item, (int, float)) for item in value)


def _text(value: Any) -> str:
    return "" if value is None else str(value)
