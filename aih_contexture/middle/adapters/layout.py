from __future__ import annotations

from typing import Any

from aih_contexture.middle.labels import normalize_block_type
from aih_contexture.middle.schema import MiddleBlock, MiddlePage, MiddleProvenance


def layout_result_to_middle_page(
    layout_result: Any,
    *,
    page_index: int,
    backend: str,
    source: str | None = None,
    model: str | None = None,
) -> MiddlePage:
    image_bbox = list(getattr(layout_result, "image_bbox", []) or [])
    width = image_bbox[2] - image_bbox[0] if len(image_bbox) == 4 else None
    height = image_bbox[3] - image_bbox[1] if len(image_bbox) == 4 else None
    blocks = []

    bboxes = list(getattr(layout_result, "bboxes", []) or [])
    ordered_boxes = sorted(
        enumerate(bboxes),
        key=lambda item: (getattr(item[1], "position", item[0]), item[0]),
    )
    for order, (_, box) in enumerate(ordered_boxes):
        raw_label = getattr(box, "label", None)
        block_type = normalize_block_type(raw_label)
        polygon = _box_polygon(box)
        top_k = dict(getattr(box, "top_k", {}) or {})
        confidence = max(top_k.values()) if top_k else None
        attrs = {
            "raw_label": raw_label,
            "top_k": top_k,
        }
        if block_type == "Text" and str(raw_label or "").strip().lower().replace("-", "_") == "vertical_text":
            attrs["orientation"] = "vertical"
        if block_type == "ComplexRegion" and raw_label:
            attrs["unmapped_label"] = raw_label

        blocks.append(
            MiddleBlock(
                id=f"p{page_index}-b{order}",
                type=block_type,
                page_index=page_index,
                order=order,
                polygon=polygon,
                bbox=_polygon_to_bbox(polygon),
                confidence=confidence,
                attrs=attrs,
                provenance=[
                    MiddleProvenance(
                        backend=backend,
                        stage="layout",
                        raw_label=raw_label,
                        model=model,
                        confidence=confidence,
                        source=source,
                    )
                ],
            )
        )

    return MiddlePage(
        index=page_index,
        width=width,
        height=height,
        blocks=blocks,
        attrs={"sliced": bool(getattr(layout_result, "sliced", False))},
        provenance=[MiddleProvenance(backend=backend, stage="layout", model=model, source=source)],
    )


def _box_polygon(box: Any) -> list[list[float]] | None:
    polygon = getattr(box, "polygon", None)
    if not polygon:
        return None
    return [[float(point[0]), float(point[1])] for point in polygon]


def _polygon_to_bbox(polygon: list[list[float]] | None) -> list[float] | None:
    if not polygon:
        return None
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    return [min(xs), min(ys), max(xs), max(ys)]
