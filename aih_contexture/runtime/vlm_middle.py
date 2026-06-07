from __future__ import annotations

from typing import Any

from aih_contexture.middle.adapters import (
    ocr_direct_outputs_to_middle_document,
    vlm_json_document_to_middle_document,
)
from aih_contexture.runtime.artifacts import save_middle_json_artifacts


def middle_json_from_vlm_generalized_converter(
    converter: Any,
    *,
    source_name: str,
    source: str,
    backend: str = "vlm_generalized",
) -> dict[str, Any] | None:
    json_pages = getattr(converter, "_last_json_pages", None)
    if not json_pages:
        return None

    return vlm_json_document_to_middle_document(
        {"json_pages": json_pages},
        backend=backend,
        model=getattr(converter, "model", None),
        source_name=source_name,
        source=source,
    ).to_dict()


def middle_json_from_vlm_specialized_converter(
    converter: Any,
    *,
    source_name: str,
    source: str,
) -> dict[str, Any] | None:
    chunks = getattr(converter, "_last_chunks", None)
    if not chunks:
        return None

    return ocr_direct_outputs_to_middle_document(
        chunks,
        backend=str(getattr(converter, "backend", "vlm_specialized")),
        model=getattr(converter, "model", None),
        source_name=source_name,
        source=source,
        printed_pages=getattr(converter, "_last_printed_pages", None),
    ).to_dict()


def save_vlm_middle_artifacts_for_converter(
    converter: Any,
    *,
    mode: str,
    output_dir: str,
    fname_base: str,
    source_name: str,
    source: str,
    emit_middle_report: bool = False,
    emit_middle_debug: bool = False,
    emit_middle_scholarly: bool = False,
    emit_middle_scholarly_report: bool = False,
    emit_layout_overlay: bool = False,
    emit_span_overlay: bool = False,
) -> dict[str, str]:
    if mode == "vlm_generalized":
        middle_json = middle_json_from_vlm_generalized_converter(
            converter,
            source_name=source_name,
            source=source,
        )
    elif mode == "vlm_specialized":
        middle_json = middle_json_from_vlm_specialized_converter(
            converter,
            source_name=source_name,
            source=source,
        )
    else:
        middle_json = None

    if middle_json is None:
        return {}

    include_page_header_comments = True
    include_page_footer_comments = True
    include_margin_comments = True
    if mode == "vlm_generalized":
        config = getattr(converter, "config", {}) or {}
        include_page_header_comments = not bool(config.get("vlm_filter_page_header", False))
        include_page_footer_comments = not bool(config.get("vlm_filter_page_footer", False))
        include_margin_comments = not bool(config.get("vlm_filter_margin_notes", False))
    elif mode == "vlm_specialized":
        include_page_header_comments = not bool(getattr(converter, "filter_page_header", False))
        include_page_footer_comments = not bool(getattr(converter, "filter_page_footer", False))
        include_margin_comments = not bool(getattr(converter, "filter_margin_notes", False))

    return save_middle_json_artifacts(
        middle_json,
        output_dir,
        fname_base,
        emit_middle_report=emit_middle_report,
        emit_middle_debug=emit_middle_debug,
        emit_middle_scholarly=emit_middle_scholarly,
        emit_middle_scholarly_report=emit_middle_scholarly_report,
        emit_layout_overlay=emit_layout_overlay,
        emit_span_overlay=emit_span_overlay,
        include_page_header_comments=include_page_header_comments,
        include_page_footer_comments=include_page_footer_comments,
        include_margin_comments=include_margin_comments,
    )
