from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Iterable

from aih_contexture.runtime.artifacts import save_middle_json_artifacts
from aih_contexture.runtime.job import ContextureResult
from aih_contexture.runtime.vlm_middle import save_vlm_middle_artifacts_for_converter
from aih_contexture.runtime.vlm_outputs import GeneralizedVlmOutput, SpecializedVlmOutput
from aih_contexture.middle.semantics.classical_marginalia import normalize_classical_marginalia_mode
from aih_contexture.middle.table_rendering import has_table_structure_tokens


WarningCallback = Callable[[str], None]


def _converter_classical_config(converter) -> dict:
    config = dict(getattr(converter, "config", {}) or {})
    for key, default in (("classical_marginalia_mode", "off"), ("classical_text_marginalia_mode", "separate"), ("generic_line_output_mode", "drop")):
        config.setdefault(key, getattr(converter, key, default))
    return config


def _classical_reading_markdown(
    markdown_text: str, *, converter, result: ContextureResult | None,
    mode: str, source_name: str, warn: WarningCallback | None = None,
) -> str:
    """Apply the same derived reading view in file and page-parallel UI paths."""
    if result is not None:
        config = dict(result.debug_artifacts)
    else:
        config = _converter_classical_config(converter)
        prefix = "vlm_" if mode == "vlm_generalized" else "ocr_"
        for output_key, filter_key in (
            ("include_page_header_comments", "filter_page_header"),
            ("include_page_footer_comments", "filter_page_footer"),
            ("include_margin_comments", "filter_margin_notes"),
            ("include_blockquote_markers", "filter_blockquote_markers"),
        ):
            config.setdefault(output_key, not bool(config.get(prefix + filter_key, getattr(converter, filter_key, False))))
    if (normalize_classical_marginalia_mode(config.get("classical_marginalia_mode")) == "off"
            and not has_table_structure_tokens(markdown_text) and not config.get('render_from_middle')):
        return markdown_text
    from aih_contexture.runtime.runner import _apply_middle_contract, _copy_middle_debug_artifact_flags
    from aih_contexture.runtime.vlm_middle import (
        middle_json_from_vlm_generalized_converter, middle_json_from_vlm_specialized_converter,
    )
    middle = result.middle_json if result is not None else None
    if middle is None and converter is not None:
        builder = middle_json_from_vlm_generalized_converter if mode == "vlm_generalized" else middle_json_from_vlm_specialized_converter
        middle = builder(converter, source_name=source_name, source=source_name)
    if middle is None:
        return markdown_text  # The mandatory-Middle check below reports this failure.
    target = result if result is not None else ContextureResult(markdown=markdown_text)
    _apply_middle_contract(target, middle, config, output_format="markdown")
    _copy_middle_debug_artifact_flags(config, target)
    if warn:
        for warning in target.warnings:
            warn(warning)
    return target.markdown if target.markdown is not None else markdown_text


class MissingMiddleJsonError(ValueError):
    """VLM 保存器成功返回时缺失强制的 Middle JSON 工件。"""


class MissingXmlOutputError(ValueError):
    """特化保存器在显式请求 XML 时未产出 XML 工件。"""


def _require_middle_json(output_dir: str, fname_base: str, *, mode: str) -> None:
    """任何成功返回都必须落盘 {fname_base}_middle.json（P0-2 硬契约）。"""
    middle_path = Path(output_dir) / f"{fname_base}_middle.json"
    if not middle_path.is_file() or middle_path.stat().st_size == 0:
        raise MissingMiddleJsonError(
            f"{mode}: mandatory Middle JSON artifact is missing or empty: {middle_path}. "
            "A successful VLM document output must always include Middle JSON; "
            "refusing to return success without it (result/converter produced no middle)."
        )


def _write_text(path: str | os.PathLike[str], text: str) -> str:
    path_str = os.fspath(path)
    from aih_contexture.runtime.artifacts import atomic_write_text
    atomic_write_text(path_str, text, encoding='utf-8')
    return path_str


def _markdown_to_html(markdown_text: str) -> str:
    import markdown2
    from aih_contexture.utils.markdown_regions import transform_prose_regions
    from aih_contexture.utils.reading_literals import escape_literal_angles

    markdown_text = transform_prose_regions(markdown_text, escape_literal_angles)
    return str(markdown2.markdown(markdown_text, extras=["tables", "fenced-code-blocks", "footnotes"]))


def _html_document(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <style>
        body {{ font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
        pre {{ background: #f5f5f5; padding: 10px; overflow-x: auto; }}
    </style>
</head>
<body>
{body}
</body>
</html>"""


def _append_reading_html(outputs, output_dir, basename, title):
    """An explicitly requested scholarly reading view uses its exact saved MD."""
    markdown = Path(output_dir) / (basename + '_middle_scholarly.md')
    if markdown.is_file():
        outputs.append(_write_text(markdown.with_suffix('.html'),
            _html_document(title, _markdown_to_html(markdown.read_text(encoding='utf-8-sig')))))


def _extend_middle_outputs(
    output_files: list[str],
    converter: GeneralizedVlmOutput | SpecializedVlmOutput,
    *,
    mode: str,
    output_dir: str,
    fname_base: str,
    source_name: str,
    emit_middle_report: bool,
    emit_middle_debug: bool,
    emit_middle_scholarly: bool,
    emit_middle_scholarly_report: bool,
    emit_layout_overlay: bool,
    emit_span_overlay: bool,
    emit_middle_full_json: bool = False,
    equation_output_mode: str = "humanities_safe",
) -> None:
    config = _converter_classical_config(converter)
    middle_outputs = save_vlm_middle_artifacts_for_converter(
        converter,
        mode=mode,
        output_dir=output_dir,
        fname_base=fname_base,
        source_name=source_name,
        source=source_name,
        emit_middle_report=emit_middle_report,
        emit_middle_debug=emit_middle_debug,
        emit_middle_scholarly=emit_middle_scholarly,
        emit_middle_scholarly_report=emit_middle_scholarly_report,
        emit_layout_overlay=emit_layout_overlay,
        emit_span_overlay=emit_span_overlay,
        emit_middle_full_json=emit_middle_full_json,
        equation_output_mode=equation_output_mode,
        classical_marginalia_mode=config["classical_marginalia_mode"],
        classical_text_marginalia_mode=config["classical_text_marginalia_mode"],
        generic_line_output_mode=config.get("generic_line_output_mode", "drop"),
    )
    _bind_saved_diagnostics(middle_outputs, output_dir, fname_base)
    output_files.extend(
        path for path in middle_outputs.values()
        if isinstance(path, str) and os.path.isfile(path)
    )


def _extend_middle_result_outputs(
    output_files: list[str],
    result: ContextureResult,
    *,
    output_dir: str,
    fname_base: str,
    emit_middle_report: bool,
    emit_middle_debug: bool,
    emit_middle_scholarly: bool,
    emit_middle_scholarly_report: bool,
    emit_layout_overlay: bool,
    emit_span_overlay: bool,
    emit_middle_full_json: bool,
    equation_output_mode: str = "humanities_safe",
) -> None:
    if result.middle_json is None:
        return
    flags = result.debug_artifacts
    middle_outputs = save_middle_json_artifacts(
        result.middle_json,
        output_dir,
        fname_base,
        emit_middle_report=emit_middle_report,
        emit_middle_debug=emit_middle_debug,
        emit_middle_scholarly=emit_middle_scholarly,
        emit_middle_scholarly_report=emit_middle_scholarly_report,
        emit_layout_overlay=emit_layout_overlay,
        emit_span_overlay=emit_span_overlay,
        emit_middle_full_json=emit_middle_full_json,
        include_page_header_comments=bool(flags.get("include_page_header_comments", True)),
        include_page_footer_comments=bool(flags.get("include_page_footer_comments", True)),
        include_margin_comments=bool(flags.get("include_margin_comments", True)),
        include_printed_page_comments=bool(flags.get("include_printed_page_comments", True)),
        include_page_separators=bool(flags.get("include_page_separators", True)),
        marginal_output_mode=flags.get("marginal_output_mode"),
        equation_output_mode=str(flags.get("equation_output_mode", equation_output_mode)),
        footnote_enabled=bool(flags.get("footnote_enabled", True)),
        superscript_policy=str(flags.get("superscript_policy", "footnote_safe")),
        include_blockquote_markers=bool(flags.get("include_blockquote_markers", True)),
        classical_marginalia_mode=flags.get("classical_marginalia_mode", "off"),
        classical_text_marginalia_mode=flags.get("classical_text_marginalia_mode", "separate"),
        generic_line_output_mode=flags.get("generic_line_output_mode"),
        emit_reading_diagnostics=bool(flags.get('emit_reading_diagnostics', False)),
        middle_geometry_profile=flags.get('middle_geometry_profile'),
    )
    _bind_saved_diagnostics(middle_outputs, output_dir, fname_base)
    output_files.extend(
        path for path in middle_outputs.values()
        if isinstance(path, str) and os.path.isfile(path)
    )


def _bind_saved_diagnostics(outputs, output_dir, basename):
    md = Path(output_dir) / (basename + '.md')
    if outputs.get('reading_diagnostics_path') and md.is_file():
        from aih_contexture.runtime.reading_diagnostics import bind_reading_diagnostics
        prior = outputs['reading_diagnostics_path']
        bound = bind_reading_diagnostics(prior, md)
        if bound != prior:
            outputs['reading_scholarly_diagnostics_path'] = prior
        outputs['reading_diagnostics_path'] = bound


def save_vlm_generalized_outputs(
    *,
    converter: GeneralizedVlmOutput | None = None,
    result: ContextureResult | None = None,
    markdown_text: str,
    output_dir: str,
    fname_base: str,
    file_name: str,
    output_formats: Iterable[str],
    emit_middle_json: bool = False,
    emit_middle_report: bool = False,
    emit_middle_debug: bool = False,
    emit_middle_scholarly: bool = False,
    emit_middle_scholarly_report: bool = False,
    emit_layout_overlay: bool = False,
    emit_span_overlay: bool = False,
    emit_middle_full_json: bool = False,
    warn: WarningCallback | None = None,
) -> list[str]:
    formats = set(output_formats or [])
    native_markdown_text = markdown_text
    markdown_text = _classical_reading_markdown(
        markdown_text, converter=converter, result=result, mode="vlm_generalized",
        source_name=file_name, warn=warn,
    )
    output_files: list[str] = []
    # Middle JSON is mandatory for every VLM document result.
    emit_middle_json = True

    if "markdown" in formats:
        output_files.append(_write_text(Path(output_dir) / f"{fname_base}.md", markdown_text))

    if "json" in formats:
        json_pages = result.page_outputs if result is not None else (converter.last_json_pages if converter else None)
        if json_pages:
            pages_data = []
            for idx, json_str in enumerate(json_pages):
                try:
                    page_obj = json.loads(json_str)
                    page_obj["page_index"] = idx
                    pages_data.append(page_obj)
                except json.JSONDecodeError:
                    if warn is not None:
                        warn(f"Failed to parse JSON for page {idx}")
                    continue
            json_data = {
                "filename": file_name,
                "format": "vlm_generalized",
                "num_pages": len(pages_data),
                "pages": pages_data,
            }
            diagnostics = result.diagnostics if result is not None else converter.last_json_diagnostics
            if diagnostics is not None:
                json_data["diagnostics"] = diagnostics
            response_metadata = result.response_metadata if result is not None else converter.last_response_metadata
            if response_metadata is not None:
                json_data["response_metadata"] = response_metadata
        else:
            json_data = {
                "filename": file_name,
                "markdown": native_markdown_text,
                "format": "vlm_generalized",
                "page_count": native_markdown_text.count("{") - 1,
            }

        json_path = Path(output_dir) / f"{fname_base}.json"
        output_files.append(_write_text(json_path, json.dumps(json_data, ensure_ascii=False, indent=2)))

    if "html" in formats:
        clean_html_pages = result.html_pages if result is not None else (converter.last_clean_html_pages if converter else None)
        html_content = "\n\n".join(clean_html_pages) if clean_html_pages else _markdown_to_html(native_markdown_text)
        output_files.append(_write_text(Path(output_dir) / f"{fname_base}.html", _html_document(file_name, html_content)))

    if emit_middle_json and result is not None:
        _extend_middle_result_outputs(
            output_files,
            result,
            output_dir=output_dir,
            fname_base=fname_base,
            emit_middle_report=emit_middle_report,
            emit_middle_debug=emit_middle_debug,
            emit_middle_scholarly=emit_middle_scholarly,
            emit_middle_scholarly_report=emit_middle_scholarly_report,
            emit_layout_overlay=emit_layout_overlay,
            emit_span_overlay=emit_span_overlay,
            emit_middle_full_json=emit_middle_full_json,
        )
    elif emit_middle_json and converter is not None:
        _extend_middle_outputs(
            output_files,
            converter,
            mode="vlm_generalized",
            output_dir=output_dir,
            fname_base=fname_base,
            source_name=file_name,
            emit_middle_report=emit_middle_report,
            emit_middle_debug=emit_middle_debug,
            emit_middle_scholarly=emit_middle_scholarly,
            emit_middle_scholarly_report=emit_middle_scholarly_report,
            emit_layout_overlay=emit_layout_overlay,
            emit_span_overlay=emit_span_overlay,
            emit_middle_full_json=emit_middle_full_json,
        )

    _require_middle_json(output_dir, fname_base, mode="vlm_generalized")
    if emit_middle_scholarly and 'html' in formats:
        _append_reading_html(output_files, output_dir, fname_base, file_name)
    return output_files


def save_vlm_specialized_outputs(
    *,
    converter=None,
    result: ContextureResult | None = None,
    markdown_text: str,
    output_dir: str,
    fname_base: str,
    file_name: str,
    output_formats: Iterable[str],
    emit_middle_json: bool = False,
    emit_middle_report: bool = False,
    emit_middle_debug: bool = False,
    emit_middle_scholarly: bool = False,
    emit_middle_scholarly_report: bool = False,
    emit_layout_overlay: bool = False,
    emit_span_overlay: bool = False,
    emit_middle_full_json: bool = False,
    warn: WarningCallback | None = None,
) -> list[str]:
    formats = set(output_formats or [])
    native_markdown_text = markdown_text
    markdown_text = _classical_reading_markdown(
        markdown_text, converter=converter, result=result, mode="vlm_specialized",
        source_name=file_name, warn=warn,
    )
    output_files: list[str] = []
    emit_middle_json = True

    # P0-3 硬契约：显式请求 XML 而无任何 XML 页时必须失败，不得静默跳过。
    xml_pages: list[str] | None = None
    if "xml" in formats:
        xml_pages = (
            converter.last_xml_pages
            if converter is not None
            else (result.xml_pages if result is not None else [])
        )
        if not xml_pages:
            raise MissingXmlOutputError(
                f"vlm_specialized: XML output was requested via output_formats but no XML pages "
                f"were produced (converter/result provided none); refusing to return success "
                f"without {Path(output_dir) / (fname_base + '.xml')}. "
                "If the backend does not support XML, do not request it in output_formats."
            )

    if "markdown" in formats:
        output_files.append(_write_text(Path(output_dir) / f"{fname_base}.md", markdown_text))

    if "json" in formats:
        chunks_data = result.page_outputs if result is not None else (converter.last_chunks if converter is not None else None)
        if chunks_data:
            json_data = {
                "filename": file_name,
                "format": "vlm_specialized",
                "num_pages": len(chunks_data),
                "pages": chunks_data,
            }
        else:
            json_data = {
                "filename": file_name,
                "markdown": native_markdown_text,
                "format": "vlm_specialized",
                "page_count": native_markdown_text.count("{") - 1,
            }
        output_files.append(
            _write_text(Path(output_dir) / f"{fname_base}.json", json.dumps(json_data, ensure_ascii=False, indent=2))
        )

    if "html" in formats:
        clean_html_pages = result.html_pages if result is not None else (converter.last_clean_html_pages if converter is not None else None)
        html_content = "\n\n".join(clean_html_pages) if clean_html_pages else _markdown_to_html(native_markdown_text)
        output_files.append(_write_text(Path(output_dir) / f"{fname_base}.html", _html_document(file_name, html_content)))

    if xml_pages:
        output_files.append(_write_text(Path(output_dir) / f"{fname_base}.xml", "\n\n".join(xml_pages)))

    if emit_middle_json and result is not None:
        _extend_middle_result_outputs(
            output_files,
            result,
            output_dir=output_dir,
            fname_base=fname_base,
            emit_middle_report=emit_middle_report,
            emit_middle_debug=emit_middle_debug,
            emit_middle_scholarly=emit_middle_scholarly,
            emit_middle_scholarly_report=emit_middle_scholarly_report,
            emit_layout_overlay=emit_layout_overlay,
            emit_span_overlay=emit_span_overlay,
            emit_middle_full_json=emit_middle_full_json,
        )
    elif emit_middle_json and converter is not None:
        _extend_middle_outputs(
            output_files,
            converter,
            mode="vlm_specialized",
            output_dir=output_dir,
            fname_base=fname_base,
            source_name=file_name,
            emit_middle_report=emit_middle_report,
            emit_middle_debug=emit_middle_debug,
            emit_middle_scholarly=emit_middle_scholarly,
            emit_middle_scholarly_report=emit_middle_scholarly_report,
            emit_layout_overlay=emit_layout_overlay,
            emit_span_overlay=emit_span_overlay,
            emit_middle_full_json=emit_middle_full_json,
        )

    searchable_pdf_path = (converter.last_searchable_pdf_path if converter is not None else (result.searchable_pdf_path if result is not None else None))
    if isinstance(searchable_pdf_path, str) and searchable_pdf_path and os.path.isfile(searchable_pdf_path):
        target_pdf = Path(output_dir) / f"{fname_base}.searchable.pdf"
        target_pdf.write_bytes(Path(searchable_pdf_path).read_bytes())
        output_files.append(str(target_pdf))

    _require_middle_json(output_dir, fname_base, mode="vlm_specialized")
    if emit_middle_scholarly and 'html' in formats:
        _append_reading_html(output_files, output_dir, fname_base, file_name)
    return output_files
