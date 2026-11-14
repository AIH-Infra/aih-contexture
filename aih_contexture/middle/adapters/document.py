from __future__ import annotations

from typing import Any
from copy import deepcopy

from aih_contexture.middle.heading_levels import normalize_middle_heading_levels
from aih_contexture.middle.labels import normalize_block_type
from aih_contexture.middle.schema import (
    MiddleBlock,
    MiddleDocument,
    MiddlePage,
    MiddleProvenance,
    MiddleSpan,
)
from aih_contexture.schema import BlockTypes
from aih_contexture.utils.footnote_markers import match_leading_footnote_marker


def document_to_middle(
    document: Any,
    *,
    layout_backend: str | None = None,
    layout_model: str | None = None,
    ocr_backend: str | None = None,
    ocr_preprocess_backend: str | None = None,
    source_name: str | None = None,
) -> MiddleDocument:
    pages = []
    for page in getattr(document, "pages", []) or []:
        pages.append(
            _page_to_middle(
                page,
                document=document,
                layout_backend=layout_backend,
                layout_model=layout_model,
                ocr_backend=ocr_backend,
                source_name=source_name,
            )
        )

    backends = {
        "layout": layout_backend,
        "ocr": ocr_backend,
    }
    if ocr_preprocess_backend:
        backends["ocr_preprocess"] = ocr_preprocess_backend
    if layout_model:
        backends["layout_model"] = layout_model

    document = MiddleDocument(
        source_name=source_name or getattr(document, "filepath", None),
        pages=pages,
        backends=backends,
    )
    from aih_contexture.middle.indra_evidence import collect_indra_evidence
    indra = collect_indra_evidence(pages)
    if indra:
        document.metadata["indra"] = indra
    return normalize_middle_heading_levels(document)


def _page_to_middle(
    page: Any,
    *,
    document: Any,
    layout_backend: str | None,
    layout_model: str | None,
    ocr_backend: str | None,
    source_name: str | None,
) -> MiddlePage:
    page_index = int(getattr(page, "page_id", 0))
    page_polygon = getattr(page, "polygon", None)
    page_metadata = dict(getattr(page, "_internal_metadata", {}) or {})
    getter = getattr(page, "get_internal_metadata", None)
    indra_evidence = getter("indra") if callable(getter) else None
    blocks = []
    source_blocks = []

    structure = list(getattr(page, "structure", []) or [])
    for order, block_id in enumerate(structure):
        block = page.get_block(block_id)
        if getattr(block, "removed", False):
            continue
        blocks.append(
            _block_to_middle(
                block,
                document=document,
                order=order,
                layout_backend=layout_backend,
                layout_model=layout_model,
                ocr_backend=ocr_backend,
            )
        )
        source_blocks.append(block)

    page_height = getattr(page_polygon, "height", None)
    _infer_bold_text_footnotes(
        blocks,
        source_blocks=source_blocks,
        document=document,
        page_height=page_height,
    )

    return MiddlePage(
        index=page_index,
        width=getattr(page_polygon, "width", None),
        height=page_height,
        printed_page=_text_or_none(page_metadata.get("printed_page_number")),
        blocks=blocks,
        attrs={
            "layout_sliced": bool(getattr(page, "layout_sliced", False)),
            "ocr_errors_detected": bool(getattr(page, "ocr_errors_detected", False)),
            "machine_page_number": page_metadata.get("machine_page_number"),
            "page_header_text": page_metadata.get("page_header_text"),
            "page_footer_text": page_metadata.get("page_footer_text"),
            **({"indra": deepcopy(indra_evidence)} if indra_evidence else {}),
        },
        provenance=[
            MiddleProvenance(
                backend=layout_backend or "unknown",
                stage="document",
                model=layout_model,
                source=source_name or getattr(document, "filepath", None),
            )
        ],
    )


def _infer_bold_text_footnotes(
    blocks: list[MiddleBlock],
    *,
    source_blocks: list[Any],
    document: Any,
    page_height: float | None,
) -> None:
    """Recover text-layer footnotes missed by layout classification.

    Some modern publisher PDFs label a lower-page footnote as ``Text`` while
    retaining a bold leading marker span. Treat only that narrow combination
    as an inferred Footnote; ordinary numbered body paragraphs remain Text.
    """
    if not isinstance(page_height, (int, float)) or page_height <= 0:
        return

    for middle_block, source_block in zip(blocks, source_blocks):
        if middle_block.type != "Text":
            continue
        marker = match_leading_footnote_marker(middle_block.text or "")
        if marker is None or marker.style == "alpha":
            continue
        if not middle_block.bbox or float(middle_block.bbox[1]) < float(page_height) * 0.5:
            continue

        try:
            spans = source_block.contained_blocks(document, (BlockTypes.Span,))
        except Exception:
            spans = []
        first_span = next((span for span in spans if str(getattr(span, "text", "")).strip()), None)
        formats = set(getattr(first_span, "formats", []) or []) if first_span is not None else set()
        font_weight = float(getattr(first_span, "font_weight", 0) or 0) if first_span is not None else 0.0
        if "bold" not in formats and font_weight < 600:
            continue

        middle_block.type = "Footnote"
        middle_block.attrs.update(
            {
                "inferred_type": "Footnote",
                "raw_block_type_before_inference": "Text",
                "footnote_evidence": ["leading_marker", "bold_marker", "lower_page_region"],
            }
        )


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _block_to_middle(
    block: Any,
    *,
    document: Any,
    order: int,
    layout_backend: str | None,
    layout_model: str | None,
    ocr_backend: str | None,
) -> MiddleBlock:
    block_type = getattr(block, "block_type", None)
    block_label = getattr(block_type, "name", None) or str(block_type or "")
    block_metadata = dict(getattr(block, "_metadata", {}) or {})
    native_raw_label = block_metadata.get("raw_label") or block_metadata.get("backend_label")
    native_canonical_type = normalize_block_type(str(native_raw_label)) if native_raw_label else None
    if native_canonical_type and native_canonical_type != "ComplexRegion":
        raw_label = str(native_raw_label)
        canonical_type = native_canonical_type
    else:
        raw_label = block_label
        canonical_type = normalize_block_type(block_label)
    polygon = getattr(getattr(block, "polygon", None), "polygon", None)
    bbox = getattr(getattr(block, "polygon", None), "bbox", None)
    top_k = _normalize_top_k(getattr(block, "top_k", None))
    confidence = max(top_k.values()) if top_k else None
    page_index = int(getattr(block, "page_id", 0))

    attrs = {
        "source": getattr(block, "source", None),
        "ignore_for_output": bool(getattr(block, "ignore_for_output", False)),
        "top_k": top_k,
    }
    for key in (
        "raw_label",
        "backend_label",
        "label_source",
        "native_layout_backend",
        "native_polygon",
        "native_reading_order",
        "marginal_source",
        "marginal_subtype",
        "position_type",
        "original_block_type",
        "block_source",
        "ocr_backend",
        "ocr_failure",
        "ocr_prompt_label",
        "ocr_bbox_precision",
    ):
        if key in block_metadata:
            attrs[key] = block_metadata[key]
    heading_level = getattr(block, "heading_level", None)
    if canonical_type == "SectionHeader" and heading_level is not None:
        attrs["heading_level"] = heading_level
        attrs["heading_level_source"] = "document_block"
        attrs["raw_heading_level"] = heading_level
    if block_label != canonical_type:
        attrs["raw_block_type"] = block_label
    if native_raw_label and str(native_raw_label) != block_label:
        attrs["native_raw_label"] = str(native_raw_label)

    from aih_contexture.middle.reading_structure import source_block_reading_attrs
    attrs.update(source_block_reading_attrs(block, document, canonical_type))

    return MiddleBlock(
        id=str(getattr(block, "id", f"p{page_index}-b{order}")),
        type=canonical_type,
        page_index=page_index,
        order=order,
        text=_safe_raw_text(block, document),
        polygon=polygon,
        bbox=bbox,
        confidence=confidence,
        spans=_block_spans_to_middle(
            block,
            document=document,
            ocr_backend=ocr_backend,
        ),
        attrs=attrs,
        provenance=[
            MiddleProvenance(
                backend=layout_backend or "unknown",
                stage="layout",
                raw_label=raw_label,
                model=layout_model,
                confidence=confidence,
            ),
            MiddleProvenance(
                backend=ocr_backend or "unknown",
                stage="ocr",
                raw_label=raw_label,
            ),
        ],
    )


def _safe_raw_text(block: Any, document: Any) -> str:
    if _has_ignored_spans(block, document):
        return _raw_text_without_ignored(block, document).strip()
    try:
        return (block.raw_text(document) or "").strip()
    except Exception:
        return ""


def _has_ignored_spans(block: Any, document: Any) -> bool:
    try:
        spans = block.contained_blocks(document, (BlockTypes.Span,))
    except Exception:
        return bool(getattr(block, "ignore_for_output", False))
    return any(bool(getattr(span, "ignore_for_output", False)) for span in spans)


def _raw_text_without_ignored(block: Any, document: Any) -> str:
    if bool(getattr(block, "ignore_for_output", False)):
        return ""
    block_type = getattr(block, "block_type", None)
    if block_type == BlockTypes.Span:
        return str(getattr(block, "text", "") or "")
    structure = list(getattr(block, "structure", []) or [])
    if not structure:
        return ""
    text = ""
    for child_id in structure:
        child = document.get_block(child_id)
        if child is None:
            continue
        text += _raw_text_without_ignored(child, document)
        if getattr(child, "block_type", None) == BlockTypes.Line and not text.endswith("\n"):
            text += "\n"
    return text


def _block_spans_to_middle(
    block: Any,
    *,
    document: Any,
    ocr_backend: str | None,
) -> list[MiddleSpan]:
    try:
        spans = block.contained_blocks(document, (BlockTypes.Span,))
    except Exception:
        return []

    middle_spans = []
    for span in spans:
        if getattr(span, "removed", False) or getattr(span, "ignore_for_output", False):
            continue
        polygon = getattr(getattr(span, "polygon", None), "polygon", None)
        bbox = getattr(getattr(span, "polygon", None), "bbox", None)
        attrs = {
            "font": getattr(span, "font", None),
            "font_weight": getattr(span, "font_weight", None),
            "font_size": getattr(span, "font_size", None),
            "formats": list(getattr(span, "formats", []) or []),
            "minimum_position": getattr(span, "minimum_position", None),
            "maximum_position": getattr(span, "maximum_position", None),
            "has_superscript": bool(getattr(span, "has_superscript", False)),
            "has_subscript": bool(getattr(span, "has_subscript", False)),
            "url": getattr(span, "url", None),
            "text_extraction_method": getattr(span, "text_extraction_method", None),
        }
        middle_spans.append(
            MiddleSpan(
                text=str(getattr(span, "text", "") or ""),
                polygon=polygon,
                bbox=bbox,
                attrs=attrs,
                provenance=[
                    MiddleProvenance(
                        backend=ocr_backend or getattr(span, "text_extraction_method", None) or "unknown",
                        stage="span",
                        raw_label="Span",
                    )
                ],
            )
        )
    return middle_spans


def _normalize_top_k(top_k: Any) -> dict[str, float]:
    if not top_k:
        return {}
    normalized = {}
    for key, value in dict(top_k).items():
        label = getattr(key, "name", None) or str(key)
        normalized[label] = float(value)
    return normalized
