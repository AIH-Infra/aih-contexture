from __future__ import annotations

from typing import Any

from aih_contexture.middle.adapters import (
    ocr_direct_outputs_to_middle_document,
    vlm_json_document_to_middle_document,
)
from aih_contexture.runtime.artifacts import save_middle_json_artifacts
from aih_contexture.runtime.vlm_outputs import GeneralizedVlmOutput, SpecializedVlmOutput


def middle_json_from_vlm_generalized_converter(
    converter: GeneralizedVlmOutput,
    *,
    source_name: str,
    source: str,
    backend: str = "vlm_generalized",
) -> dict[str, Any] | None:
    json_pages = converter.last_json_pages
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
    converter: SpecializedVlmOutput,
    *,
    source_name: str,
    source: str,
) -> dict[str, Any] | None:
    chunks = converter.last_chunks
    if not chunks:
        return None

    return ocr_direct_outputs_to_middle_document(
        chunks,
        backend=str(getattr(converter, "backend", "vlm_specialized")),
        model=getattr(converter, "model", None),
        source_name=source_name,
        source=source,
        printed_pages=converter.last_printed_pages,
    ).to_dict()


def save_vlm_middle_artifacts_for_converter(
    converter: GeneralizedVlmOutput | SpecializedVlmOutput,
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
    emit_middle_full_json: bool = False,
    equation_output_mode: str = "humanities_safe",
    classical_marginalia_mode: str = "off",
    classical_text_marginalia_mode: str = "separate",
    generic_line_output_mode: str | None = None,
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

    config = getattr(converter, "config", {}) or {}
    prefix = "vlm_" if mode == "vlm_generalized" else "ocr_"
    def include(output_key: str, filter_key: str) -> bool:
        filtered = config.get(prefix + filter_key, getattr(converter, filter_key, False))
        return bool(config.get(output_key, not bool(filtered)))

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
        emit_middle_full_json=emit_middle_full_json,
        emit_reading_diagnostics=bool(config.get('emit_reading_diagnostics', False)),
        middle_geometry_profile=config.get('middle_geometry_profile'),
        equation_output_mode=equation_output_mode,
        include_page_header_comments=include("include_page_header_comments", "filter_page_header"),
        include_page_footer_comments=include("include_page_footer_comments", "filter_page_footer"),
        include_margin_comments=include("include_margin_comments", "filter_margin_notes"),
        include_blockquote_markers=include("include_blockquote_markers", "filter_blockquote_markers"),
        classical_marginalia_mode=classical_marginalia_mode,
        classical_text_marginalia_mode=classical_text_marginalia_mode,
        generic_line_output_mode=(generic_line_output_mode if generic_line_output_mode is not None
                                  else config.get('generic_line_output_mode')),
    )
