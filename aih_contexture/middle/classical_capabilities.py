"""Model-independent evidence availability for classical marginalia."""

from __future__ import annotations

from aih_contexture.middle.storage import decode_middle_storage

import math
from typing import Any


# Coordinates smaller than this are commonly normalized to the 0..1 range,
# thumbnails, or missing defaults. They are not useful for locating a page's
# body band. The upper bound also rejects corrupt dimensions while allowing
# large scanned pages (including high-resolution raster coordinates).
_MIN_PAGE_DIMENSION = 32.0
_MAX_PAGE_DIMENSION = 100_000.0
_PAGE_EDGE_TOLERANCE = 1.0


def classical_margin_side(page: dict, block: dict | None = None, item: dict | None = None) -> str | None:
    """Return a supported horizontal side, or leave the note unqualified."""
    block, item = block or {}, item or {}
    attrs = block.get('attrs') if isinstance(block.get('attrs'), dict) else {}
    raw = attrs.get('raw') if isinstance(attrs.get('raw'), dict) else {}
    aliases = {
        'left':'left','left_margin':'left','margin_left':'left','marginal_left':'left','marginal_note_left':'left',
        'right':'right','right_margin':'right','margin_right':'right','marginal_right':'right','marginal_note_right':'right',
    }
    explicit = {aliases[v] for value in (attrs.get('side'), attrs.get('placement'), attrs.get('position_type'),
        attrs.get('raw_label'), raw.get('label'), raw.get('placement'), raw.get('position'))
        if (v := str(value or '').strip().lower().replace('-', '_')) in aliases}
    if len(explicit) > 1:
        return None
    box = item.get('bbox') if item.get('bbox') is not None else block.get('bbox')
    geometry = None
    if classical_bbox_is_trustworthy(box, page, block):
        center = (float(box[0])+float(box[2]))/2
        width = float(page['width'])
        geometry = 'left' if center <= width*.25 else 'right' if center >= width*.75 else None
    if explicit and geometry and geometry not in explicit:
        return None
    return next(iter(explicit)) if explicit else geometry


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _page_dimensions(page: dict[str, Any]) -> tuple[float, float] | None:
    width = _finite_number(page.get("width"))
    height = _finite_number(page.get("height"))
    if width is None or height is None:
        return None
    if not (
        _MIN_PAGE_DIMENSION <= width <= _MAX_PAGE_DIMENSION
        and _MIN_PAGE_DIMENSION <= height <= _MAX_PAGE_DIMENSION
    ):
        return None
    return width, height


def _valid_bbox(box: Any, *, width: float, height: float) -> bool:
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return False
    values = [_finite_number(value) for value in box]
    if any(value is None for value in values):
        return False
    x0, y0, x1, y1 = values
    assert x0 is not None and y0 is not None and x1 is not None and y1 is not None
    # A local normalized box on an otherwise physical page is not a tiny
    # physical annotation. Never infer a destructive edit from this ambiguity.
    if max(abs(value) for value in values) <= 2.0:
        return False
    return (
        -_PAGE_EDGE_TOLERANCE <= x0 < x1 <= width + _PAGE_EDGE_TOLERANCE
        and -_PAGE_EDGE_TOLERANCE <= y0 < y1 <= height + _PAGE_EDGE_TOLERANCE
    )


def _coordinate_space(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    attrs = item.get("attrs") if isinstance(item.get("attrs"), dict) else {}
    raw = item.get("coordinate_space")
    if raw is None:
        raw = attrs.get("coordinate_space")
    if raw is None:
        return None  # Legacy Middle coordinates are in the parent page's units.
    aliases = {"px": "pixels", "pixel": "pixels", "pt": "points", "point": "points"}
    return aliases.get(str(raw).strip().lower(), str(raw).strip().lower())


def classical_bbox_is_trustworthy(box: Any, page: Any, block: Any = None) -> bool:
    """Use the same coordinate rules for body availability and each candidate."""
    dimensions = _page_dimensions(page)
    page_space, block_space = _coordinate_space(page), _coordinate_space(block)
    if page_space not in {None, "pixels", "points", "page"}:
        return False
    if block_space is not None and block_space not in {page_space or "page", "page"}:
        return False
    return dimensions is not None and _valid_bbox(box, width=dimensions[0], height=dimensions[1])


def classical_marginalia_capabilities(data: dict[str, Any]) -> dict[str, Any]:
    """Summarize whether pages have trustworthy geometry for margin analysis.

    Geometry is considered usable only when a page has plausible physical
    dimensions and at least one wide, text-bearing body block with a valid
    finite bounding box. This deliberately fails closed for default-zero,
    normalized, non-finite, and out-of-page coordinates.
    """
    data = decode_middle_storage(data)

    raw_pages = data.get("pages")
    pages = raw_pages if isinstance(raw_pages, list) else []
    geometry_pages = 0
    valid_bbox_blocks = 0
    invalid_bbox_blocks = 0

    for page in pages:
        if not isinstance(page, dict):
            continue
        dimensions = _page_dimensions(page)
        if dimensions is None:
            continue
        width, height = dimensions
        has_body = False
        blocks = page.get("blocks")
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if not isinstance(block, dict):
                continue
            box = block.get("bbox")
            if not classical_bbox_is_trustworthy(box, page, block):
                if box is not None:
                    invalid_bbox_blocks += 1
                continue
            valid_bbox_blocks += 1
            x0, _, x1, _ = (float(value) for value in box)
            attrs = block.get("attrs") if isinstance(block.get("attrs"), dict) else {}
            footnote_like = "footnote" in str(attrs.get("semantic_role") or "").lower() or bool(attrs.get("footnote_id"))
            if (
                block.get("type") in {"Text", "ListItem", "ComplexRegion"}
                and not footnote_like
                and str(block.get("text") or "").strip()
                and x1 - x0 >= width * 0.2
            ):
                has_body = True
        if has_body:
            geometry_pages += 1

    page_count = len(pages)
    status = (
        "unavailable"
        if geometry_pages == 0
        else "available"
        if geometry_pages == page_count
        else "partial"
    )
    return {
        "status": status,
        "page_count": page_count,
        "geometry_pages": geometry_pages,
        "valid_bbox_blocks": valid_bbox_blocks,
        "invalid_bbox_blocks": invalid_bbox_blocks,
        "reason": "missing_trustworthy_body_geometry" if geometry_pages == 0 else None,
    }
