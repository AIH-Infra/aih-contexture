"""Indra pages -> Contexture Middle JSON.

Indra reports boxes in image pixels at its render DPI, on the page as it turned it upright (``rotation`` quarter
turns) and straightened, except vertical pages, which stay as they are. Everything leaves here in PDF points on
the page as the PDF shows it, so anchors, page sizes and boxes agree with the other backends.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from aih_contexture.middle.schema import (
    MiddleBlock,
    MiddleDocument,
    MiddlePage,
    MiddleProvenance,
    MiddleSpan,
)

BACKEND_LAYOUT = "indra_layout"
BACKEND_OCR = "indra_ocr"
LABEL_TYPES = {
    "Text": "Text",
    "Section-Header": "SectionHeader",
    "Page-Header": "PageHeader",
    "Page-Footer": "PageFooter",
    "Footnote": "Footnote",
    "Caption": "Caption",
    "Table": "Table",
    "Picture": "Picture",
    "Equation": "Equation",
    "Formula": "Equation",
    "List-Group": "Text",  # lines with bullets; item boundaries are not recoverable, the raw label stays in provenance
}


def box_to_page_points(box: Iterable[float], *, dpi: float, rotation: int, page_width: float, page_height: float) -> list[float]:
    """A box in the pixels of the turned-upright page -> points on the page as the PDF shows it.

    ``rotation`` is Indra's ``Page.rotation`` (90 x quarter turns it undid, counter-clockwise content turn).
    It turned the image with ``np.rot90(image, -k)``, so a point (x, y) of the page became (h - y, x) for k = 1,
    (w - x, h - y) for k = 2 and (y, w - x) for k = 3, where w and h are the page's own size.
    """
    scale = 72.0 / dpi
    x0, y0, x1, y1 = (float(value) * scale for value in list(box)[:4])
    quarter = (int(rotation) // 90) % 4
    if quarter == 1:
        x0, y0, x1, y1 = y0, page_height - x1, y1, page_height - x0
    elif quarter == 2:
        x0, y0, x1, y1 = page_width - x1, page_height - y1, page_width - x0, page_height - y0
    elif quarter == 3:
        x0, y0, x1, y1 = page_width - y1, x0, page_width - y0, x1
    return [round(min(x0, x1), 2), round(min(y0, y1), 2), round(max(x0, x1), 2), round(max(y0, y1), 2)]


def _area(box: list[float]) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _centre_in(box: list[float], outer: list[float]) -> bool:
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return outer[0] <= cx <= outer[2] and outer[1] <= cy <= outer[3]


def _provenance(stage: str, version: str | None, raw_label: str | None = None, confidence: float | None = None) -> list[MiddleProvenance]:
    return [MiddleProvenance(backend=BACKEND_OCR if stage == "ocr" else BACKEND_LAYOUT, stage=stage,
                             raw_label=raw_label, model=f"indra-ocr {version}" if version else "indra-ocr", confidence=confidence)]


def page_to_middle(
    page: Mapping[str, Any],
    *,
    index: int,
    width: float,
    height: float,
    version: str | None = None,
) -> MiddlePage:
    dpi = float(page.get("dpi") or 200)
    rotation = 0 if page.get("vertical") else int(page.get("rotation") or 0)

    def points(box: Iterable[float]) -> list[float]:
        return box_to_page_points(box, dpi=dpi, rotation=rotation, page_width=width, page_height=height)

    blocks = [
        {"label": str(block.get("type") or "Text"), "bbox": points(block["bbox"]), "text": str(block.get("content") or "")}
        for block in page.get("blocks") or []
    ]
    lines = [
        {"bbox": points(line["bbox"]), "text": str(line.get("text") or ""), "conf": line.get("conf")}
        for line in page.get("lines") or []
    ]
    # Each line belongs to the smallest block holding its centre; a line outside every block gets a block of its own.
    owner: dict[int, int] = {}
    for position, line in enumerate(lines):
        holders = [i for i, block in enumerate(blocks) if _centre_in(line["bbox"], block["bbox"])]
        if holders:
            owner[position] = min(holders, key=lambda i: _area(blocks[i]["bbox"]))
    orphans = [position for position in range(len(lines)) if position not in owner]

    middle_blocks: list[MiddleBlock] = []
    for order, block in enumerate(blocks):
        kind = LABEL_TYPES.get(block["label"], "Text")
        members = [lines[p] for p in sorted(p for p, o in owner.items() if o == order)]
        confidences = [m["conf"] for m in members if isinstance(m["conf"], (int, float))]
        spans = [
            MiddleSpan(text=m["text"], bbox=m["bbox"], confidence=m["conf"], provenance=_provenance("ocr", version, confidence=m["conf"]))
            for m in members
        ] if kind not in {"Picture"} else []
        item = MiddleBlock(
            id=f"/page/{index}/{kind}/{order}",
            type=kind,
            page_index=index,
            order=order,
            text="" if kind == "Picture" else block["text"],
            bbox=block["bbox"],
            confidence=sum(confidences) / len(confidences) if confidences else None,
            spans=spans,
            provenance=_provenance("layout", version, raw_label=block["label"]),
        )
        if kind == "Table":
            item.attrs["table_html"] = block["text"]
        middle_blocks.append(item)
    for extra, position in enumerate(orphans):
        line = lines[position]
        order = len(middle_blocks)
        middle_blocks.append(MiddleBlock(
            id=f"/page/{index}/Text/{order}", type="Text", page_index=index, order=order, text=line["text"], bbox=line["bbox"],
            confidence=line["conf"] if isinstance(line["conf"], (int, float)) else None,
            spans=[MiddleSpan(text=line["text"], bbox=line["bbox"], confidence=line["conf"], provenance=_provenance("ocr", version, confidence=line["conf"]))],
            attrs={"indra_orphan_line": True}, provenance=_provenance("layout", version, raw_label="(line outside every block)"),
        ))

    confidences = [line["conf"] for line in lines if isinstance(line["conf"], (int, float))]
    attrs: dict[str, Any] = {
        "indra_source": page.get("source"),
        "indra_rotation": int(page.get("rotation") or 0),
        "indra_skew": float(page.get("skew") or 0.0),
        "indra_vertical": bool(page.get("vertical")),
        "indra_seconds": page.get("seconds"),
        "line_confidence": {
            "lines": len(confidences),
            "mean": round(sum(confidences) / len(confidences), 4) if confidences else None,
            "min": round(min(confidences), 4) if confidences else None,
        },
    }
    if page.get("note"):
        attrs["indra_note"] = page["note"]
    return MiddlePage(
        index=index, width=width, height=height, blocks=middle_blocks, attrs=attrs,
        provenance=[MiddleProvenance(backend=BACKEND_OCR, stage="document", model=f"indra-ocr {version}" if version else "indra-ocr")],
    )


def review_summary(
    pages: Mapping[int, Mapping[str, Any]], *, review_mean: float = 0.92, review_min: float = 0.60,
) -> dict[str, Any]:
    """Where each page's text came from and which pages Indra itself was unsure about (candidates for another backend).

    A page is flagged when its mean line confidence is below ``review_mean`` or its worst line below ``review_min``,
    or when Indra could not read it at all. Pages read straight from a trusted text layer carry confidence 1.0.
    """
    sources: dict[str, list[int]] = {}
    flagged: list[dict[str, Any]] = []
    for index in sorted(pages):
        page = pages[index]
        source = str(page.get("source") or "unknown")
        sources.setdefault(source, []).append(index)
        confidences = [line["conf"] for line in page.get("lines") or [] if isinstance(line.get("conf"), (int, float))]
        mean = sum(confidences) / len(confidences) if confidences else None
        worst = min(confidences) if confidences else None
        reasons = []
        if source == "error":
            reasons.append("unreadable")
        if mean is not None and mean < review_mean:
            reasons.append(f"mean confidence {mean:.3f} < {review_mean}")
        if worst is not None and worst < review_min:
            reasons.append(f"lowest line {worst:.3f} < {review_min}")
        if reasons:
            flagged.append({"page_index": index, "mean": None if mean is None else round(mean, 4),
                            "min": None if worst is None else round(worst, 4), "reasons": reasons})
    return {
        "pages_by_source": sources,
        "review_pages": flagged,
        "thresholds": {"mean": review_mean, "min": review_min},
    }


def pages_to_middle(
    pages: Mapping[int, Mapping[str, Any]],
    *,
    page_sizes: Mapping[int, tuple[float, float]],
    source_name: str | None = None,
    version: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Indra pages keyed by their index in the source PDF -> a Middle JSON dict (pages in index order)."""
    middle_pages = [
        page_to_middle(pages[index], index=index, width=page_sizes[index][0], height=page_sizes[index][1], version=version)
        for index in sorted(pages)
    ]
    document = MiddleDocument(
        pages=middle_pages,
        source_name=source_name,
        metadata=dict(metadata or {}),
        backends={"layout": BACKEND_LAYOUT, "ocr": BACKEND_OCR, "ocr_model": f"indra-ocr {version}" if version else "indra-ocr"},
    )
    return document.to_dict()
