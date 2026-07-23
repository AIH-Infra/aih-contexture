from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal

from aih_contexture.middle.schema import CANONICAL_BLOCK_TYPES, SCHEMA_VERSION

Severity = Literal["error", "warning"]


@dataclass(frozen=True, slots=True)
class MiddleValidationIssue:
    severity: Severity
    path: str
    message: str


@dataclass(slots=True)
class MiddleValidationReport:
    issues: list[MiddleValidationIssue] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def errors(self) -> list[MiddleValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[MiddleValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_middle_json(data: dict[str, Any]) -> MiddleValidationReport:
    report = MiddleValidationReport(summary=summarize_middle_json(data))

    if data.get("schema_version") != SCHEMA_VERSION:
        _add(report, "error", "$.schema_version", f"expected {SCHEMA_VERSION!r}")

    pages = data.get("pages")
    if not isinstance(pages, list):
        _add(report, "error", "$.pages", "must be a list")
        return report

    declared_page_count = data.get("page_count")
    if declared_page_count is not None and declared_page_count != len(pages):
        _add(report, "error", "$.page_count", "does not match number of pages")

    seen_pages = set()
    seen_block_ids = set()
    for page_pos, page in enumerate(pages):
        path = f"$.pages[{page_pos}]"
        if not isinstance(page, dict):
            _add(report, "error", path, "page must be an object")
            continue
        _validate_page(page, path, report, seen_pages, seen_block_ids)

    return report


def summarize_middle_json(data: dict[str, Any]) -> dict[str, Any]:
    pages = data.get("pages") if isinstance(data, dict) else None
    if not isinstance(pages, list):
        return {
            "page_count": 0,
            "block_count": 0,
            "block_types": {},
            "backends": data.get("backends", {}) if isinstance(data, dict) else {},
        }

    block_types: dict[str, int] = {}
    block_count = 0
    span_count = 0
    blocks_with_spans = 0
    pages_with_blocks = 0
    for page in pages:
        blocks = page.get("blocks", []) if isinstance(page, dict) else []
        if blocks:
            pages_with_blocks += 1
        for block in blocks:
            if not isinstance(block, dict):
                continue
            block_count += 1
            block_type = str(block.get("type", ""))
            block_types[block_type] = block_types.get(block_type, 0) + 1
            spans = block.get("spans")
            if isinstance(spans, list) and spans:
                blocks_with_spans += 1
                span_count += sum(1 for span in spans if isinstance(span, dict))

    return {
        "schema_version": data.get("schema_version"),
        "source_name": data.get("source_name"),
        "page_count": len(pages),
        "pages_with_blocks": pages_with_blocks,
        "block_count": block_count,
        "span_count": span_count,
        "blocks_with_spans": blocks_with_spans,
        "block_types": dict(sorted(block_types.items())),
        "backends": data.get("backends", {}),
    }


def _validate_page(
    page: dict[str, Any],
    path: str,
    report: MiddleValidationReport,
    seen_pages: set[int],
    seen_block_ids: set[str],
) -> None:
    index = page.get("index")
    if not isinstance(index, int):
        _add(report, "error", f"{path}.index", "must be an integer")
        return
    if index in seen_pages:
        _add(report, "error", f"{path}.index", f"duplicate page index {index}")
    seen_pages.add(index)

    if page.get("anchor_start") != index:
        _add(report, "error", f"{path}.anchor_start", "must equal page index")
    if page.get("anchor_end") != index + 1:
        _add(report, "error", f"{path}.anchor_end", "must equal page index + 1")

    page_width = _validate_dimension(page.get("width"), f"{path}.width", report)
    page_height = _validate_dimension(page.get("height"), f"{path}.height", report)
    _validate_provenance(page.get("provenance"), f"{path}.provenance", report, required=False)

    blocks = page.get("blocks", [])
    if not isinstance(blocks, list):
        _add(report, "error", f"{path}.blocks", "must be a list")
        return

    seen_orders = set()
    previous_order = -1
    for block_pos, block in enumerate(blocks):
        block_path = f"{path}.blocks[{block_pos}]"
        if not isinstance(block, dict):
            _add(report, "error", block_path, "block must be an object")
            continue
        previous_order = _validate_block(
            block,
            block_path,
            page_index=index,
            page_width=page_width,
            page_height=page_height,
            previous_order=previous_order,
            seen_orders=seen_orders,
            seen_block_ids=seen_block_ids,
            report=report,
        )


def _validate_block(
    block: dict[str, Any],
    path: str,
    *,
    page_index: int,
    page_width: float | None,
    page_height: float | None,
    previous_order: int,
    seen_orders: set[int],
    seen_block_ids: set[str],
    report: MiddleValidationReport,
) -> int:
    block_id = block.get("id")
    if not block_id:
        _add(report, "error", f"{path}.id", "must be present")
    elif not isinstance(block_id, str):
        _add(report, "error", f"{path}.id", "must be a string")
    elif block_id in seen_block_ids:
        _add(report, "error", f"{path}.id", f"duplicate block id {block_id!r}")
    else:
        seen_block_ids.add(block_id)

    block_type = block.get("type")
    if block_type not in CANONICAL_BLOCK_TYPES:
        _add(report, "error", f"{path}.type", f"unknown canonical block type: {block_type!r}")

    block_page_index = block.get("page_index")
    if block_page_index != page_index:
        _add(report, "error", f"{path}.page_index", "must match parent page index")

    order = block.get("order")
    if not isinstance(order, int):
        _add(report, "error", f"{path}.order", "must be an integer")
    else:
        if order in seen_orders:
            _add(report, "warning", f"{path}.order", f"duplicate order {order}")
        if order < previous_order:
            _add(report, "warning", f"{path}.order", "blocks are not sorted by order")
        seen_orders.add(order)
        previous_order = order

    anchor_start = block.get("anchor_start")
    anchor_end = block.get("anchor_end")
    if not isinstance(anchor_start, int) or not isinstance(anchor_end, int):
        _add(report, "error", f"{path}.anchors", "anchor_start and anchor_end must be integers")
    elif not (anchor_start <= page_index < anchor_end):
        _add(report, "error", f"{path}.anchors", "must wrap the block page_index")

    _validate_confidence(block.get("confidence"), f"{path}.confidence", report, required=False)
    _validate_bbox(
        block.get("bbox"),
        f"{path}.bbox",
        report,
        required=False,
        page_width=page_width,
        page_height=page_height,
    )
    _validate_polygon(block.get("polygon"), f"{path}.polygon", report, required=False)

    _validate_provenance(block.get("provenance"), f"{path}.provenance", report, required=True)
    _validate_spans(
        block.get("spans", []),
        f"{path}.spans",
        report,
        page_width=page_width,
        page_height=page_height,
    )

    return previous_order


def _validate_spans(
    value: Any,
    path: str,
    report: MiddleValidationReport,
    *,
    page_width: float | None,
    page_height: float | None,
) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        _add(report, "error", path, "must be a list")
        return
    for span_pos, span in enumerate(value):
        span_path = f"{path}[{span_pos}]"
        if not isinstance(span, dict):
            _add(report, "error", span_path, "span must be an object")
            continue
        text = span.get("text")
        if not isinstance(text, str):
            _add(report, "error", f"{span_path}.text", "must be a string")
        elif not text.strip():
            _add(report, "warning", f"{span_path}.text", "is empty")
        _validate_bbox(
            span.get("bbox"),
            f"{span_path}.bbox",
            report,
            required=False,
            page_width=page_width,
            page_height=page_height,
        )
        _validate_polygon(span.get("polygon"), f"{span_path}.polygon", report, required=False)
        _validate_confidence(span.get("confidence"), f"{span_path}.confidence", report, required=False)
        _validate_provenance(span.get("provenance"), f"{span_path}.provenance", report, required=True)


def _validate_dimension(value: Any, path: str, report: MiddleValidationReport) -> float | None:
    if value is None:
        return None
    if not _is_number(value):
        _add(report, "error", path, "must be a finite number")
        return None
    numeric = float(value)
    if numeric <= 0:
        _add(report, "error", path, "must be positive")
        return None
    return numeric


def _validate_bbox(
    bbox: Any,
    path: str,
    report: MiddleValidationReport,
    *,
    required: bool,
    page_width: float | None = None,
    page_height: float | None = None,
) -> None:
    if bbox is None:
        if required:
            _add(report, "error", path, "must be present")
        return
    if not isinstance(bbox, list) or len(bbox) != 4 or not all(_is_number(v) for v in bbox):
        _add(report, "error", path, "must be [x0, y0, x1, y1]")
        return
    if bbox[2] < bbox[0] or bbox[3] < bbox[1]:
        _add(report, "error", path, "must have x1 >= x0 and y1 >= y0")
        return
    if bbox[2] == bbox[0] or bbox[3] == bbox[1]:
        _add(report, "warning", path, "has zero width or height")
    if page_width is not None and (bbox[0] < 0 or bbox[2] > page_width):
        _add(report, "warning", path, "extends outside page width")
    if page_height is not None and (bbox[1] < 0 or bbox[3] > page_height):
        _add(report, "warning", path, "extends outside page height")


def _validate_polygon(polygon: Any, path: str, report: MiddleValidationReport, *, required: bool) -> None:
    if polygon is None:
        if required:
            _add(report, "error", path, "must be present")
        return
    if not isinstance(polygon, list) or len(polygon) != 4:
        _add(report, "error", path, "must contain four points")
        return
    for point_pos, point in enumerate(polygon):
        if not isinstance(point, list) or len(point) != 2 or not all(_is_number(v) for v in point):
            _add(report, "error", f"{path}[{point_pos}]", "must be [x, y]")


def _validate_confidence(value: Any, path: str, report: MiddleValidationReport, *, required: bool) -> None:
    if value is None:
        if required:
            _add(report, "error", path, "must be present")
        return
    if not _is_number(value):
        _add(report, "error", path, "must be a finite number")
        return
    numeric = float(value)
    if numeric < 0 or numeric > 1:
        _add(report, "warning", path, "should be normalized to the [0, 1] range")


def _validate_provenance(value: Any, path: str, report: MiddleValidationReport, *, required: bool) -> None:
    if value is None:
        if required:
            _add(report, "warning", path, "should include backend provenance")
        return
    if not isinstance(value, list):
        _add(report, "error", path, "must be a list")
        return
    if not value:
        if required:
            _add(report, "warning", path, "should include backend provenance")
        return
    for item_pos, item in enumerate(value):
        item_path = f"{path}[{item_pos}]"
        if not isinstance(item, dict):
            _add(report, "error", item_path, "must be an object")
            continue
        if not item.get("backend"):
            _add(report, "warning", f"{item_path}.backend", "should identify the backend")
        if not item.get("stage"):
            _add(report, "warning", f"{item_path}.stage", "should identify the processing stage")
        _validate_confidence(item.get("confidence"), f"{item_path}.confidence", report, required=False)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _add(report: MiddleValidationReport, severity: Severity, path: str, message: str) -> None:
    report.issues.append(MiddleValidationIssue(severity=severity, path=path, message=message))
