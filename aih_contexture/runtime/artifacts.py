from __future__ import annotations

from aih_contexture.middle.storage import decode_middle_storage
from aih_contexture.middle.storage import middle_json_text

import json
import copy
import hashlib
import os
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TextIO

from aih_contexture.converters.pdf import PdfConverter
from aih_contexture.logger import get_logger
from aih_contexture.middle.adapters import document_to_middle
from aih_contexture.middle.debug_markdown import render_middle_debug_markdown
from aih_contexture.middle.schema import MiddleDocument
from aih_contexture.middle.semantics import resolve_middle_for_rendering
from aih_contexture.middle.scholarly_markdown import render_middle_scholarly_markdown
from aih_contexture.middle.semantics.classical_marginalia import (
    METADATA_KEY as CLASSICAL_MARGINALIA_METADATA_KEY,
    middle_source_fingerprint,
    resolve_classical_marginalia,
    normalize_classical_marginalia_mode,
    normalize_classical_text_marginalia_mode,
)
from aih_contexture.middle.validation import validate_middle_json, require_middle_for_publication
from aih_contexture.middle.classical_capabilities import classical_marginalia_capabilities
from aih_contexture.middle.table_rendering import table_review_records
from aih_contexture.middle.reading_structure import READING_BLOCK_ATTRS, bind_available_image_resources
from aih_contexture.evaluation.layout_overlay import (
    render_middle_layout_overlay,
    render_middle_span_overlay,
)
from aih_contexture.evaluation.scholarly_markdown import evaluate_scholarly_markdown_text
from aih_contexture.models import create_model_dict
from aih_contexture.output import convert_if_not_rgb, text_from_rendered
from aih_contexture.renderers.chunk import ChunkRenderer
from aih_contexture.renderers.html import HTMLRenderer
from aih_contexture.renderers.json import JSONRenderer
from aih_contexture.renderers.markdown import MarkdownRenderer
from aih_contexture.runtime.pipeline_preprocess import (
    apply_pipeline_pdf_preprocess,
    cleanup_pipeline_preprocess,
    normalize_ocr_preprocess_backend,
)
from aih_contexture.backends.sidecar_pool import SidecarRuntimePool
from aih_contexture.runtime.job import ContextureResult, normalize_page_range
from aih_contexture.runtime.file_lock import retry_windows_io
from aih_contexture.runtime.run_summary import utc_now_iso, write_document_summary
from aih_contexture.settings import settings
from aih_contexture.utils.gc_pause import with_paused_gc
from aih_contexture.utils.storage_numbers import STORAGE_DECIMALS

logger = get_logger()


@contextmanager
def atomic_text_writer(path: str, *, encoding: str = "utf-8") -> Iterator[TextIO]:
    """Write a text artifact completely before replacing its destination."""

    destination = os.path.abspath(path)
    output_dir = os.path.dirname(destination)
    os.makedirs(output_dir, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix=f".{os.path.basename(destination)}.",
        suffix=".tmp",
        dir=output_dir,
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as stream:
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        retry_windows_io(lambda: os.replace(temp_path, destination), stage=f"artifact replace {destination}")
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise


def atomic_write_text(path: str, content: str, *, encoding: str = "utf-8") -> None:
    with atomic_text_writer(path, encoding=encoding) as stream:
        stream.write(content)


def append_text(path: str | None, content: str):
    if not path or not content:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(content)


def write_meta_once(meta: dict, out_dir: str, fname_base: str):
    if not meta:
        return
    meta_path = os.path.join(out_dir, f"{fname_base}_meta.json")
    if os.path.exists(meta_path):
        return
    atomic_write_text(meta_path, json.dumps(meta, ensure_ascii=False, indent=2))


def update_meta_semantic_resolution(out_dir: str, fname_base: str, semantic_resolution: dict[str, Any] | None):
    if not semantic_resolution:
        return
    meta_path = os.path.join(out_dir, f"{fname_base}_meta.json")
    meta = {}
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                meta = loaded
        except (OSError, json.JSONDecodeError):
            meta = {}
    meta["semantic_resolution"] = semantic_resolution
    atomic_write_text(meta_path, json.dumps(meta, ensure_ascii=False, indent=2))


def save_images(images_dict: dict, out_dir: str):
    if not images_dict:
        return

    for img_name, img in images_dict.items():
        output_path = os.path.abspath(os.path.join(out_dir, img_name))
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            prefix=f".{os.path.basename(output_path)}.",
            suffix=".tmp",
            dir=os.path.dirname(output_path),
        )
        os.close(fd)
        try:
            img = convert_if_not_rgb(img)
            img.save(temp_path, settings.OUTPUT_IMAGE_FORMAT)
            os.replace(temp_path, output_path)
        except Exception:
            logger.exception("Failed to save image artifact: %s", img_name)
            try:
                os.remove(temp_path)
            except OSError:
                pass


def write_pipeline_checkpoint(result_path: str | None, payload: dict[str, Any]) -> None:
    if not result_path:
        return
    atomic_write_text(result_path, json.dumps(payload, ensure_ascii=False, indent=2))


def pipeline_checkpoint_payload(
    *,
    file_name: str,
    result_key: str | None,
    started_at: float,
    backend_summary: dict[str, Any] | None,
    completed_batches: list[str],
    current_batch: str | None,
    total_batches: int,
    file_outputs: list[dict[str, Any]],
    output_formats: list[str],
    markdown_path: str | None,
    html_path: str | None,
    json_batch_paths: list[str],
    chunks_batch_paths: list[str],
    error: str | None = None,
) -> dict[str, Any]:
    partial_outputs = _existing_partial_outputs(
        file_outputs=file_outputs,
        output_formats=output_formats,
        markdown_path=markdown_path,
        html_path=html_path,
        json_batch_paths=json_batch_paths,
        chunks_batch_paths=chunks_batch_paths,
    )
    return {
        "success": False,
        "partial": True,
        "file_name": file_name,
        "result_key": result_key,
        "file_outputs": partial_outputs,
        "elapsed_seconds": time.time() - started_at,
        "backend_summary": backend_summary or {},
        "completed_batches": list(completed_batches),
        "current_batch": current_batch,
        "total_batches": total_batches,
        "error": error or "Pipeline worker checkpoint; processing did not finish.",
        "traceback": None,
    }


def _existing_partial_outputs(
    *,
    file_outputs: list[dict[str, Any]],
    output_formats: list[str],
    markdown_path: str | None,
    html_path: str | None,
    json_batch_paths: list[str],
    chunks_batch_paths: list[str],
) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(format_name: str, path: str | None) -> None:
        if not path or not os.path.exists(path):
            return
        normalized = os.path.abspath(path)
        if normalized in seen:
            return
        seen.add(normalized)
        outputs.append({"format": format_name, "path": path, "name": os.path.basename(path)})

    for item in file_outputs:
        path = item.get("path") if isinstance(item, dict) else None
        if path and os.path.exists(path):
            add(str(item.get("format") or "artifact"), str(path))
    if "markdown" in output_formats:
        add("markdown_partial", markdown_path)
    if "html" in output_formats:
        add("html_partial", html_path)
    for path in json_batch_paths:
        add("json_batch", path)
    for path in chunks_batch_paths:
        add("chunks_batch", path)
    return outputs


def save_contexture_result(
    result: ContextureResult,
    output_dir: str,
    fname_base: str,
    output_format: str,
) -> dict[str, str]:
    if result.middle_json is None:
        raise ValueError("ContextureResult is missing mandatory Middle JSON")
    require_middle_for_publication(result.middle_json)
    os.makedirs(output_dir, exist_ok=True)
    text, ext = text_from_contexture_result(result, output_format)
    text = text.encode(settings.OUTPUT_ENCODING, errors="replace").decode(
        settings.OUTPUT_ENCODING
    )

    output_path = os.path.join(output_dir, f"{fname_base}.{ext}")
    atomic_write_text(output_path, text, encoding=settings.OUTPUT_ENCODING)

    metadata_to_write = dict(result.metadata or {})
    from aih_contexture.middle.indra_evidence import strip_indra_review
    strip_indra_review(metadata_to_write)
    metadata_to_write.pop('reading_page_manifest', None)
    if output_format == 'markdown' and result.middle_json is not None:
        from aih_contexture.middle.reading_pages import rebind_page_manifest
        bound_manifest = rebind_page_manifest(text,
            (result.middle_json.get('metadata') or {}).get('reading_page_manifest'))
        if bound_manifest is not None:
            metadata_to_write['reading_page_manifest'] = bound_manifest
    for key in ('reading_review', 'classical_marginalia_review', 'reading_diagnostics',
                'middle_validation', 'classical_marginalia'):
        metadata_to_write.pop(key, None)
    postprocess_metadata = metadata_to_write.get('markdown_postprocess')
    if isinstance(postprocess_metadata, dict):
        metadata_to_write['markdown_postprocess'] = {key: postprocess_metadata[key]
            for key in ('input_kind', 'enabled', 'rerender_only') if key in postprocess_metadata}
    if result.middle_json is not None:
        semantic_resolution = (
            result.middle_json.get("metadata", {}).get("semantic_resolution")
            if isinstance(result.middle_json.get("metadata"), dict)
            else None
        )
        if semantic_resolution:
            metadata_to_write["semantic_resolution"] = semantic_resolution

    meta_path = os.path.join(output_dir, f"{fname_base}_meta.json")
    atomic_write_text(
        meta_path,
        json.dumps(metadata_to_write, indent=2, ensure_ascii=False),
        encoding=settings.OUTPUT_ENCODING,
    )

    middle_outputs = {}
    if result.middle_json is not None:
        middle_outputs = save_middle_json_artifacts(
            result.middle_json,
            output_dir,
            fname_base,
            emit_middle_report=bool(result.debug_artifacts.get("emit_middle_report", False)),
            emit_middle_debug=bool(result.debug_artifacts.get("emit_middle_debug", False)),
            emit_middle_scholarly=bool(result.debug_artifacts.get("emit_middle_scholarly", False)),
            emit_middle_scholarly_report=bool(result.debug_artifacts.get("emit_middle_scholarly_report", False)),
            emit_layout_overlay=bool(result.debug_artifacts.get("emit_layout_overlay", False)),
            emit_span_overlay=bool(result.debug_artifacts.get("emit_span_overlay", False)),
            emit_middle_full_json=bool(result.debug_artifacts.get("emit_middle_full_json", False)),
            include_printed_page_comments=result.debug_artifacts.get("include_printed_page_comments"),
            include_provenance_comments=result.debug_artifacts.get("include_provenance_comments"),
            include_page_header_comments=result.debug_artifacts.get("include_page_header_comments"),
            include_page_footer_comments=result.debug_artifacts.get("include_page_footer_comments"),
            include_margin_comments=result.debug_artifacts.get("include_margin_comments"),
            marginal_output_mode=result.debug_artifacts.get("marginal_output_mode"),
            equation_output_mode=result.debug_artifacts.get("equation_output_mode"),
            footnote_enabled=result.debug_artifacts.get("footnote_enabled"),
            superscript_policy=result.debug_artifacts.get("superscript_policy"),
            include_blockquote_markers=result.debug_artifacts.get("include_blockquote_markers"),
            include_page_separators=result.debug_artifacts.get("include_page_separators"),
            classical_marginalia_mode=result.debug_artifacts.get("classical_marginalia_mode"),
            classical_text_marginalia_mode=result.debug_artifacts.get("classical_text_marginalia_mode"),
            generic_line_output_mode=result.debug_artifacts.get("generic_line_output_mode"),
            classical_pdf_words_by_page=result.debug_artifacts.get("classical_pdf_words_by_page"),
            classical_evidence=result.debug_artifacts.get("classical_evidence"),
            emit_reading_diagnostics=bool(result.debug_artifacts.get('emit_reading_diagnostics', False)),
            middle_geometry_profile=result.debug_artifacts.get('middle_geometry_profile'),
        )

    if output_format == 'markdown' and middle_outputs.get('reading_diagnostics_path'):
        from aih_contexture.runtime.reading_diagnostics import bind_reading_diagnostics
        prior_diagnostic = middle_outputs['reading_diagnostics_path']
        bound_diagnostic = bind_reading_diagnostics(prior_diagnostic, output_path)
        if bound_diagnostic != prior_diagnostic:
            middle_outputs['reading_scholarly_diagnostics_path'] = prior_diagnostic
        middle_outputs['reading_diagnostics_path'] = bound_diagnostic
        if isinstance(result.metadata.get('markdown_postprocess'), dict):
            diagnostic_path = middle_outputs['reading_diagnostics_path']
            with open(diagnostic_path, encoding='utf-8') as diagnostic_file:
                diagnostic_payload = json.load(diagnostic_file)
            diagnostic_payload['postprocess'] = result.metadata['markdown_postprocess']
            atomic_write_text(diagnostic_path, json.dumps(diagnostic_payload, ensure_ascii=False, indent=2), encoding='utf-8')
    save_images(result.images, output_dir)
    output = {"format": output_format, "path": output_path, "name": os.path.basename(output_path)}
    output.update(middle_outputs)
    return output


def text_from_contexture_result(result: ContextureResult, output_format: str) -> tuple[str, str]:
    if output_format == "markdown":
        return result.markdown or "", "md"
    if output_format == "html":
        return result.html or "", "html"
    if output_format == "json":
        return result.json_text or "", "json"
    if output_format == "chunks":
        return result.chunks or "", "json"
    raise ValueError(f"Invalid output format: {output_format}")


@with_paused_gc
def save_middle_json_artifacts(
    middle_json: dict[str, Any],
    output_dir: str,
    fname_base: str,
    *,
    emit_middle_report: bool = False,
    emit_middle_debug: bool = False,
    emit_middle_scholarly: bool = False,
    emit_middle_scholarly_report: bool = False,
    emit_layout_overlay: bool = False,
    emit_span_overlay: bool = False,
    emit_middle_full_json: bool = False,
    include_page_header_comments: bool | None = None,
    include_page_footer_comments: bool | None = None,
    include_margin_comments: bool | None = None,
    marginal_output_mode: str | None = None,
    equation_output_mode: str | None = None,
    footnote_enabled: bool | None = None,
    superscript_policy: str | None = None,
    include_blockquote_markers: bool | None = None,
    include_printed_page_comments: bool | None = None,
    include_provenance_comments: bool | None = None,
    include_page_separators: bool | None = None,
    classical_marginalia_mode: str | None = None,
    classical_text_marginalia_mode: str | None = None,
    generic_line_output_mode: str | None = None,
    classical_pdf_words_by_page: dict[int, list[dict[str, Any]]] | None = None,
    classical_evidence: dict[str, Any] | None = None,
    render_config: dict[str, Any] | None = None,
    emit_reading_diagnostics: bool = False,
    middle_geometry_profile: str | None = None,
) -> dict[str, str]:
    from aih_contexture.runtime.middle_rerender import prepare_middle_rerender
    reading_config = {**(render_config or {}), **{
        key: value for key, value in {
            'include_page_header_comments': include_page_header_comments,
            'include_page_footer_comments': include_page_footer_comments,
            'include_margin_comments': include_margin_comments,
            'marginal_output_mode': marginal_output_mode,
            'equation_output_mode': equation_output_mode,
            'footnote_enabled': footnote_enabled,
            'superscript_policy': superscript_policy,
            'include_blockquote_markers': include_blockquote_markers,
            'include_printed_page_comments': include_printed_page_comments,
            'include_provenance_comments': include_provenance_comments,
            'include_page_separators': include_page_separators,
            'classical_marginalia_mode': classical_marginalia_mode,
            'classical_text_marginalia_mode': classical_text_marginalia_mode,
            'generic_line_output_mode': generic_line_output_mode,
            'classical_pdf_words_by_page': classical_pdf_words_by_page,
            'classical_evidence': classical_evidence,
            'middle_geometry_profile': middle_geometry_profile,
        }.items() if value is not None
    }}
    middle_json = _apply_geometry_profile(
        middle_json, reading_config,
        emit_span_overlay=emit_span_overlay, emit_middle_full_json=emit_middle_full_json,
    )
    needs_reading = emit_middle_scholarly or emit_middle_scholarly_report
    plan = prepare_middle_rerender(middle_json, reading_config, _render_markdown=needs_reading)
    resolved_middle_json = plan.document
    classical_marginalia_mode = plan.options['classical_marginalia_mode']
    classical_text_marginalia_mode = plan.options['classical_text_marginalia_mode']
    os.makedirs(output_dir, exist_ok=True)
    compact_middle_json = _compact_resolved_middle_json_for_storage(resolved_middle_json, publication_ready=True)
    require_middle_for_publication(compact_middle_json)
    middle_json_path = os.path.join(output_dir, f"{fname_base}_middle.json")
    atomic_write_text(
        middle_json_path,
        middle_json_text(compact_middle_json, compress=(render_config or {}).get('middle_storage_compression', True) is not False),
        encoding=settings.OUTPUT_ENCODING,
    )

    outputs = {
        "middle_json_path": middle_json_path,
    }
    from aih_contexture.runtime.reading_diagnostics import reading_diagnostics_enabled, write_reading_diagnostics
    if emit_reading_diagnostics or reading_diagnostics_enabled(render_config):
        outputs['reading_diagnostics_path'] = write_reading_diagnostics(
            plan.diagnostics, output_dir, fname_base,
            markdown=plan.markdown if emit_middle_scholarly else None,
            markdown_name=f'{fname_base}_middle_scholarly.md')
    if emit_middle_full_json:
        middle_full_json_path = os.path.join(output_dir, f"{fname_base}_middle_full.json")
        atomic_write_text(
            middle_full_json_path,
            json.dumps(resolved_middle_json, ensure_ascii=False, separators=(",", ":")),
            encoding=settings.OUTPUT_ENCODING,
        )
        outputs["middle_full_json_path"] = middle_full_json_path

    if emit_middle_report:
        report = validate_middle_json(compact_middle_json)
        report_payload = {
            "ok": report.ok,
            "summary": report.summary,
            "errors": [
                {"path": issue.path, "message": issue.message}
                for issue in report.errors
            ],
            "warnings": [
                {"path": issue.path, "message": issue.message}
                for issue in report.warnings
            ],
        }
        middle_report_path = os.path.join(output_dir, f"{fname_base}_middle_report.json")
        atomic_write_text(
            middle_report_path,
            json.dumps(report_payload, ensure_ascii=False, indent=2),
            encoding=settings.OUTPUT_ENCODING,
        )
        outputs["middle_report_path"] = middle_report_path

    if emit_middle_debug:
        middle_debug_path = os.path.join(output_dir, f"{fname_base}_middle_debug.md")
        atomic_write_text(
            middle_debug_path,
            render_middle_debug_markdown(compact_middle_json),
            encoding=settings.OUTPUT_ENCODING,
        )
        outputs["middle_debug_path"] = middle_debug_path

    middle_scholarly_text = None
    middle_scholarly_path = os.path.join(output_dir, f"{fname_base}_middle_scholarly.md")
    if emit_middle_scholarly or emit_middle_scholarly_report:
        # Publish from the representation that was actually saved, so ordinary
        # save/reload and first export exercise the same projection.
        middle_scholarly_text = plan.markdown

    if emit_middle_scholarly and middle_scholarly_text is not None:
        atomic_write_text(
            middle_scholarly_path,
            middle_scholarly_text,
            encoding=settings.OUTPUT_ENCODING,
        )
        outputs["middle_scholarly_path"] = middle_scholarly_path

    if emit_middle_scholarly_report and middle_scholarly_text is not None:
        scholarly_report = evaluate_scholarly_markdown_text(
            middle_scholarly_text,
            source_path=middle_scholarly_path,
            validate_classical_locators=classical_marginalia_mode == "page_locators",
        )
        middle_scholarly_report_path = os.path.join(output_dir, f"{fname_base}_middle_scholarly_report.json")
        atomic_write_text(
            middle_scholarly_report_path,
            json.dumps(scholarly_report, ensure_ascii=False, indent=2),
            encoding=settings.OUTPUT_ENCODING,
        )
        outputs["middle_scholarly_report_path"] = middle_scholarly_report_path
    source_pdf = resolved_middle_json.get("source_name")
    if emit_layout_overlay:
        overlay_dir = os.path.join(output_dir, f"{fname_base}_layout_overlay")
        overlay_pdf = os.path.join(output_dir, f"{fname_base}_layout_overlay.pdf")
        overlay = render_middle_layout_overlay(
            compact_middle_json,
            source_pdf=source_pdf,
            output_dir=overlay_dir,
            output_pdf=overlay_pdf,
        )
        if overlay.get("ok"):
            outputs["layout_overlay_dir"] = overlay_dir
            if overlay.get("pdf"):
                outputs["layout_overlay_pdf_path"] = str(overlay["pdf"])
    if emit_span_overlay:
        span_overlay_dir = os.path.join(output_dir, f"{fname_base}_span_overlay")
        span_overlay_pdf = os.path.join(output_dir, f"{fname_base}_span_overlay.pdf")
        span_overlay = render_middle_span_overlay(
            resolved_middle_json,
            source_pdf=source_pdf,
            output_dir=span_overlay_dir,
            output_pdf=span_overlay_pdf,
        )
        if span_overlay.get("ok"):
            outputs["span_overlay_dir"] = span_overlay_dir
            if span_overlay.get("pdf"):
                outputs["span_overlay_pdf_path"] = str(span_overlay["pdf"])

    return outputs


def _apply_geometry_profile(middle_json, reading_config, *, emit_span_overlay, emit_middle_full_json):
    """Drop word spans up front when lean is requested and nothing needs them."""
    from aih_contexture.middle.geometry_profile import (
        CONFIG_KEY, LEAN, is_lean_middle, lean_blockers, normalize_geometry_profile, strip_word_spans,
    )
    from aih_contexture.runtime.middle_rerender import effective_reading_options
    if (normalize_geometry_profile(reading_config.get(CONFIG_KEY)) != LEAN
            or not isinstance(middle_json, dict) or is_lean_middle(middle_json)):
        return middle_json
    blockers = lean_blockers(
        effective_reading_options(middle_json, reading_config),
        emit_span_overlay=emit_span_overlay, emit_middle_full_json=emit_middle_full_json,
    )
    if blockers:
        logger.warning('Lean Middle geometry not applied; word spans are required by: %s', ', '.join(blockers))
        return middle_json
    return strip_word_spans(middle_json)


def compact_middle_json_for_storage(middle_json: dict[str, Any]) -> dict[str, Any]:
    """Return a storage-friendly Middle JSON payload.

    Preserve a thin word-span representation (text, exact offsets, geometry,
    font size and source stage) whenever the recognizer supplies it. Markdown
    re-rendering needs this evidence to separate overlapping body/margin text.
    Rich overlay-only attributes remain in the optional full artifact.
    """
    middle_json = decode_middle_storage(middle_json)
    if not isinstance(middle_json, dict):
        return middle_json

    metadata = middle_json.get("metadata") if isinstance(middle_json, dict) else None
    classical_resolution = (
        metadata.get(CLASSICAL_MARGINALIA_METADATA_KEY)
        if isinstance(metadata, dict)
        else None
    )
    classical_cache_matches = (
        isinstance(classical_resolution, dict)
        and classical_resolution.get("completed") is True
        and classical_resolution.get("source_fingerprint")
        == middle_source_fingerprint(middle_json)
    )
    # Re-resolving Middle semantics after classical edits are cached can make
    # the analysis fingerprint stale. Production callers normalize Middle
    # before analysis; for an already matching analysis cache, preserve its
    # exact source projection through compact storage.
    if not classical_cache_matches:
        semantic_config = {}
        if isinstance(metadata, dict):
            previous = metadata.get('semantic_resolution') or {}
            semantic_config.update({key: previous[key] for key in (
                'footnote_enabled', 'marginal_detection_enabled', 'superscript_policy',
            ) if key in previous})
            if previous.get('profile'):
                semantic_config['semantic_profile'] = previous['profile']
            semantic_config.update(metadata.get('reading_render_options') or {})
        middle_json = resolve_middle_for_rendering(middle_json, semantic_config)

    return _compact_resolved_middle_json_for_storage(middle_json)


def _compact_resolved_middle_json_for_storage(middle_json, *, publication_ready=False):
    """Private projection for a just-resolved, exclusively owned transaction."""
    if not publication_ready:
        from aih_contexture.runtime.reading_diagnostics import publication_document
        middle_json = publication_document(middle_json)
    compact: dict[str, Any] = {}
    for key in ("schema_version", "source_name", "page_count", "backends"):
        if key in middle_json:
            compact[key] = _compact_value(middle_json.get(key))
    metadata = _compact_metadata(middle_json.get("metadata"))
    if metadata:
        compact["metadata"] = metadata

    pages = middle_json.get("pages")
    if isinstance(pages, list):
        compact["pages"] = [_compact_page(page) for page in pages if isinstance(page, dict)]
    else:
        compact["pages"] = []
    if "page_count" not in compact:
        compact["page_count"] = len(compact["pages"])
    return compact


def write_classical_marginalia_sidecar(
    middle_json: dict[str, Any], output_dir: str, fname_base: str
) -> dict[str, str]:
    """Write page-level classical analysis as JSONL and a hash-bearing manifest."""
    pages = middle_json.get("pages", []) if isinstance(middle_json, dict) else []
    records = []
    for page in pages if isinstance(pages, list) else []:
        if not isinstance(page, dict):
            continue
        analysis = (page.get("attrs") or {}).get("classical_marginalia")
        if not isinstance(analysis, dict):
            continue
        records.append(
            json.dumps(
                {"page_index": page.get("index"), "analysis": analysis},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
    if not records:
        return {}

    os.makedirs(output_dir, exist_ok=True)
    sidecar_name = f"{fname_base}_classical_marginalia.jsonl"
    sidecar_path = os.path.join(output_dir, sidecar_name)
    content = "\n".join(records) + "\n"
    atomic_write_text(sidecar_path, content, encoding=settings.OUTPUT_ENCODING)
    metadata = middle_json.get("metadata") or {}
    resolution = metadata.get("classical_marginalia_resolution") or {}
    with open(sidecar_path, "rb") as sidecar_file:
        sidecar_sha256 = hashlib.sha256(sidecar_file.read()).hexdigest()
    manifest = {
        "schema": "contexture-classical-marginalia/0.1",
        "source_name": middle_json.get("source_name"),
        "source_id": metadata.get("source_id") or middle_json.get("source_name"),
        "source_sha256": metadata.get("source_sha256") or metadata.get("source_hash"),
        "source_fingerprint": resolution.get("source_fingerprint"),
        "analysis_version": resolution.get("version"),
        "config_signature": resolution.get("config_signature"),
        "page_count": len(records),
        "components": [
            {
                "path": sidecar_name,
                "sha256": sidecar_sha256,
                "record_count": len(records),
            }
        ],
    }
    manifest_name = f"{fname_base}_classical_manifest.json"
    manifest_path = os.path.join(output_dir, manifest_name)
    atomic_write_text(
        manifest_path,
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding=settings.OUTPUT_ENCODING,
    )
    return {
        "classical_marginalia_sidecar_path": sidecar_path,
        "classical_marginalia_manifest_path": manifest_path,
    }


def _compact_page(page: dict[str, Any]) -> dict[str, Any]:
    keep = ("index", "width", "height", "printed_page", "anchor_start", "anchor_end")
    compact = {key: _compact_value(page.get(key)) for key in keep if _keep_value(page.get(key))}
    attrs = _compact_attrs(page.get("attrs"), keep_keys={
        "layout_sliced",
        "ocr_errors_detected",
        "machine_page_number",
        "page_header_text",
        "page_footer_text",
        "classical_marginalia",
        "reading_folio",
        "coordinate_space", "logical_pages", "input_frame_index", "logical_page_mapping", "error", "diagnostic",
        "line_confidence", "indra_source", "indra_rotation", "indra_skew", "indra_vertical", "indra_note",
        "indra",
    })
    if attrs:
        compact["attrs"] = attrs
    blocks = page.get("blocks")
    compact["blocks"] = [_compact_block(block) for block in blocks if isinstance(block, dict)] if isinstance(blocks, list) else []
    provenance = _compact_provenance(page.get("provenance"), page_level=True)
    if provenance:
        compact["provenance"] = provenance
    return compact


def _compact_block(block: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "id",
        "type",
        "page_index",
        "order",
        "text",
        "anchor_start",
        "anchor_end",
        "bbox",
        "confidence",
    )
    compact = {key: _compact_value(block.get(key)) for key in keep if _keep_value(block.get(key))}
    from aih_contexture.middle.native_geometry import compact_native_spans
    native_spans = compact_native_spans(block)
    if native_spans:
        compact['spans'] = _compact_value(native_spans)
    attrs = _compact_attrs(block.get("attrs"), keep_keys=READING_BLOCK_ATTRS | {
        "side",
        "position",
        "placement",
        "heading_level",
        "heading_level_source",
        "raw_heading_level",
        "raw_block_type",
        "raw_label",
        "style",
        "source",
        "semantic_role",
        "marker",
        "marker_normalized",
        "footnote_confidence",
        "footnote_evidence",
        "excluded_from",
        "inline_marks",
        "normalization",
        "semantic_warnings",
        "marginal_confidence",
        "coordinate_space", "coordinate_transform", "logical_page_index", "logical_printed_page", "input_frame_index",
        "ocr_failure", "ocr_bbox_precision", "ocr_prompt_label",
        "native_polygon", "native_reading_order",
    })
    if attrs:
        compact["attrs"] = attrs
    provenance = _compact_provenance(block.get("provenance"), page_level=False)
    if provenance:
        compact["provenance"] = provenance
    children = block.get("children")
    if isinstance(children, list) and children:
        compact_children = [_compact_block(child) for child in children if isinstance(child, dict)]
        if compact_children:
            compact["children"] = compact_children
    return compact


def _compact_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        key: _compact_value(val)
        for key, val in value.items()
        if _keep_value(val) and key not in {"images", "image_data", "debug_images", "page_images",
                                          'reading_review', 'classical_marginalia_review', 'reading_diagnostics'}
    }


def _compact_attrs(value: Any, *, keep_keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        key: _compact_value(val)
        for key, val in value.items()
        if key in keep_keys and _keep_value(val)
    }


def _compact_provenance(value: Any, *, page_level: bool) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    output: list[dict[str, Any]] = []
    keep_keys = ("backend", "stage", "raw_label", "model", "confidence")
    if page_level:
        keep_keys = ("backend", "stage", "model")
    for item in value:
        if not isinstance(item, dict):
            continue
        compact = {key: _compact_value(item.get(key)) for key in keep_keys if _keep_value(item.get(key))}
        if compact and compact not in output:
            output.append(compact)
    return output[:2]


_COMPACT_LEAF_TYPES = frozenset({str, int, bool, type(None)})


def _compact_value(value: Any) -> Any:
    # Exact leaf types are returned inline; this runs over every stored span.
    kind = type(value)
    if kind in _COMPACT_LEAF_TYPES:
        return value
    if kind is float:
        return round(value, STORAGE_DECIMALS)
    if kind is dict:
        return {key: val if type(val) in _COMPACT_LEAF_TYPES else _compact_value(val)
                for key, val in value.items() if _keep_value(val)}
    if kind is list:
        return [item if type(item) in _COMPACT_LEAF_TYPES else _compact_value(item) for item in value]
    if isinstance(value, float):
        from aih_contexture.utils.storage_numbers import storage_number
        return storage_number(value)
    if isinstance(value, list):
        return [_compact_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _compact_value(val) for key, val in value.items() if _keep_value(val)}
    return value


def _keep_value(value: Any) -> bool:
    return value not in (None, "", [], {})


def merge_json_batches(output_path: str, batch_paths: list[str], metadata: dict):
    with atomic_text_writer(output_path) as out_f:
        out_f.write('{\n  "children": [\n')
        first_child = True
        for batch_path in batch_paths:
            with open(batch_path, "r", encoding="utf-8") as f:
                batch_data = json.load(f)
            for child in batch_data.get("children", []):
                if not first_child:
                    out_f.write(',\n')
                out_f.write(json.dumps(child, ensure_ascii=False, indent=2))
                first_child = False
        out_f.write('\n  ],\n')
        out_f.write('  "block_type": "Document",\n')
        out_f.write('  "metadata": ')
        out_f.write(json.dumps(metadata, ensure_ascii=False, indent=2))
        out_f.write('\n}')
    for batch_path in batch_paths:
        try:
            os.remove(batch_path)
        except OSError:
            pass


def merge_chunk_batches(output_path: str, batch_paths: list[str], metadata: dict):
    with atomic_text_writer(output_path) as out_f:
        out_f.write('{\n  "blocks": [\n')
        first_block = True
        page_info_items = []
        for batch_path in batch_paths:
            with open(batch_path, "r", encoding="utf-8") as f:
                batch_data = json.load(f)
            for block in batch_data.get("blocks", []):
                if not first_block:
                    out_f.write(',\n')
                out_f.write(json.dumps(block, ensure_ascii=False, indent=2))
                first_block = False
            page_info_items.extend(batch_data.get("page_info", {}).items())
        out_f.write('\n  ],\n')
        out_f.write('  "page_info": {\n')
        for idx, (page_key, page_value) in enumerate(page_info_items):
            if idx > 0:
                out_f.write(',\n')
            out_f.write(f'    {json.dumps(page_key, ensure_ascii=False)}: ')
            out_f.write(json.dumps(page_value, ensure_ascii=False, indent=2))
        out_f.write('\n  },\n')
        out_f.write('  "metadata": ')
        out_f.write(json.dumps(metadata, ensure_ascii=False, indent=2))
        out_f.write('\n}')
    for batch_path in batch_paths:
        try:
            os.remove(batch_path)
        except OSError:
            pass


def _uniform_classical_batch_config(batch_jobs: list[dict[str, Any]]) -> tuple[str, str]:
    def value(config, key, normalize):
        aliases = [normalize(config[name]) for name in (key, 'middle_rerender_'+key)
                   if config.get(name) is not None]
        if len(set(aliases)) > 1:
            raise ValueError(f'Conflicting render options for {key}')
        return aliases[0] if aliases else normalize(None)
    modes = set()
    for item in batch_jobs:
        config = item.get('config_dict', {})
        modes.add((value(config, 'classical_marginalia_mode', normalize_classical_marginalia_mode),
                   value(config, 'classical_text_marginalia_mode', normalize_classical_text_marginalia_mode)))
    if len(modes) > 1:
        raise ValueError("Chunks of one document must use the same classical marginalia configuration")
    return next(iter(modes), ("off", "separate"))


def finalize_pipeline_reading_markdown(
    middle_json: dict[str, Any], markdown_path: str, config: dict[str, Any],
) -> bool:
    """Replace partial batch text once, using the same saved-Middle service.

    Legacy rendering remains the default when no reading projection is asked
    for. Batch checkpoint files remain available until the full export exists.
    """
    from aih_contexture.middle.table_rendering import has_table_structure_tokens
    from aih_contexture.runtime.middle_rerender import prepare_middle_rerender
    mode = normalize_classical_marginalia_mode(config.get('classical_marginalia_mode')
            or config.get('middle_rerender_classical_marginalia_mode'))
    needs_projection = bool(config.get('render_from_middle')) or mode != 'off'
    if not needs_projection and os.path.isfile(markdown_path):
        with open(markdown_path, encoding=settings.OUTPUT_ENCODING) as stream:
            needs_projection = has_table_structure_tokens(stream.read())
    if not needs_projection:
        return False
    plan = prepare_middle_rerender(middle_json, config)
    atomic_write_text(markdown_path, plan.markdown, encoding=settings.OUTPUT_ENCODING)
    return True


def _uniform_reading_batch_options(batch_jobs: list[dict[str, Any]]) -> dict[str, Any]:
    from aih_contexture.runtime.middle_rerender import normalize_reading_render_options
    first = None
    for batch in batch_jobs:
        options = normalize_reading_render_options(batch.get('config_dict', {}))
        if options['marginal_output_mode'] is None:
            options['marginal_output_mode'] = 'line_markers' if options['include_margin_comments'] else 'plain'
        if first is not None and options != first:
            raise ValueError('Chunks of one document must use the same reading render configuration')
        first = options
    return first or normalize_reading_render_options({})


def process_pipeline_job(job: dict[str, Any], *, artifacts=None, sidecar_pool=None) -> dict[str, Any]:
    from aih_contexture.runtime.progress_events import emit_progress_event, set_progress_context

    start = time.time()
    file_path = job["file_path"]
    source_file_path = file_path
    file_name = job["file_name"]
    out_dir_final = job["output_dir"]
    output_formats = job["output_formats"]
    fname_base = job["fname_base"]
    batch_jobs = job["batch_jobs"]
    classical_marginalia_mode, classical_text_marginalia_mode = _uniform_classical_batch_config(batch_jobs)
    _uniform_reading_batch_options(batch_jobs)
    if _is_text_layer_pipeline_job(batch_jobs):
        return _process_text_layer_pipeline_job(job)
    from aih_contexture.runtime.indra_pipeline import is_indra_direct, process_indra_pipeline_job
    if batch_jobs and all(is_indra_direct(batch.get("config_dict", {})) for batch in batch_jobs):
        return process_indra_pipeline_job(job)
    total_batches = len(batch_jobs)
    batch_page_counts = [_pipeline_batch_page_count(batch_job) for batch_job in batch_jobs]
    document_total_pages = sum(batch_page_counts)
    checkpoint_path = job.get("_pipeline_result_json")
    result_key = f"{file_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    completed_batches: list[str] = []
    set_progress_context(
        file_name=file_name,
        total_batches=total_batches,
        document_total_pages=document_total_pages,
        batch_page_offset=0,
    )
    emit_progress_event(
        "file_started",
        "starting",
        file_name=file_name,
        current=0,
        total=document_total_pages,
        unit="pages",
        absolute_progress=True,
        message=f"Starting {file_name}",
    )

    os.makedirs(out_dir_final, exist_ok=True)

    markdown_path = os.path.join(out_dir_final, f"{fname_base}.md") if "markdown" in output_formats else None
    html_path = os.path.join(out_dir_final, f"{fname_base}.html") if "html" in output_formats else None
    json_batch_paths = []
    chunks_batch_paths = []
    merged_metadata = {}
    middle_artifact_keys = (
        "emit_middle_json",
        "emit_middle_report",
        "emit_middle_debug",
        "emit_middle_scholarly",
        "emit_middle_scholarly_report",
        "emit_layout_overlay",
        "emit_span_overlay",
        "emit_middle_full_json",
    )
    # Middle JSON is a mandatory artifact for every successful Pipeline job.
    emit_middle_json = True
    emit_middle_report = any(
        bool(batch_job.get("config_dict", {}).get("emit_middle_report", False))
        for batch_job in batch_jobs
    )
    emit_middle_debug = any(
        bool(batch_job.get("config_dict", {}).get("emit_middle_debug", False))
        for batch_job in batch_jobs
    )
    emit_middle_scholarly = any(
        bool(batch_job.get("config_dict", {}).get("emit_middle_scholarly", False))
        for batch_job in batch_jobs
    )
    emit_middle_scholarly_report = any(
        bool(batch_job.get("config_dict", {}).get("emit_middle_scholarly_report", False))
        for batch_job in batch_jobs
    )
    emit_layout_overlay = any(
        bool(batch_job.get("config_dict", {}).get("emit_layout_overlay", False))
        for batch_job in batch_jobs
    )
    emit_span_overlay = any(
        bool(batch_job.get("config_dict", {}).get("emit_span_overlay", False))
        for batch_job in batch_jobs
    )
    emit_middle_full_json = any(
        bool(batch_job.get("config_dict", {}).get("emit_middle_full_json", False))
        for batch_job in batch_jobs
    )
    marginal_output_mode = next(
        (
            batch_job.get("config_dict", {}).get("marginal_output_mode")
            for batch_job in batch_jobs
            if batch_job.get("config_dict", {}).get("marginal_output_mode")
        ),
        None,
    )
    equation_output_mode = next(
        (
            batch_job.get("config_dict", {}).get("equation_output_mode")
            for batch_job in batch_jobs
            if batch_job.get("config_dict", {}).get("equation_output_mode")
        ),
        "humanities_safe",
    )
    middle_pages = []
    middle_backends = {}
    available_image_names: set[str] = set()

    for path in (markdown_path, html_path):
        if path and os.path.exists(path):
            os.remove(path)

    file_outputs = []
    preprocess_result = None
    owns_sidecar_pool = sidecar_pool is None
    if owns_sidecar_pool:
        sidecar_pool = SidecarRuntimePool()
    parallel_outputs = None

    try:
        write_pipeline_checkpoint(
            checkpoint_path,
            pipeline_checkpoint_payload(
                file_name=file_name,
                result_key=result_key,
                started_at=start,
                backend_summary=None,
                completed_batches=completed_batches,
                current_batch=None,
                total_batches=total_batches,
                file_outputs=file_outputs,
                output_formats=output_formats,
                markdown_path=markdown_path,
                html_path=html_path,
                json_batch_paths=json_batch_paths,
                chunks_batch_paths=chunks_batch_paths,
                error="Pipeline worker started; no batch completed yet.",
            ),
        )
        emit_progress_event("stage_changed", "model_loading", message="Loading models")
        if artifacts is None:
            artifacts = create_model_dict()
        emit_progress_event("stage_completed", "model_loading", message="Models loaded")
        preprocess_config = dict(batch_jobs[0].get("config_dict", {}) or {}) if batch_jobs else {}
        batch_ranges = [
            normalize_page_range((batch.get("config_dict") or {}).get("page_range"))
            for batch in batch_jobs
        ]
        preprocess_pages = (
            sorted({page for pages in batch_ranges for page in pages})
            if batch_ranges and all(pages is not None for pages in batch_ranges)
            else None
        )
        emit_progress_event("stage_changed", "preprocess", message="Preprocessing PDF")
        preprocess_result = apply_pipeline_pdf_preprocess(
            file_path=file_path,
            output_dir=out_dir_final,
            fname_base=fname_base,
            config=preprocess_config,
            page_indices=preprocess_pages,
        )
        file_path = preprocess_result.effective_file_path
        emit_progress_event("stage_completed", "preprocess", message="PDF preprocessing completed")
        backend_summary = _backend_summary_from_batch_jobs(batch_jobs)
        if preprocess_result.exported_artifact_path:
            file_outputs.append(
                {
                    "format": "searchable_pdf",
                    "path": preprocess_result.exported_artifact_path,
                    "name": os.path.basename(preprocess_result.exported_artifact_path),
                }
            )

        completed_page_count = 0
        batch_kwargs = dict(
            file_path=file_path,
            source_file_path=source_file_path,
            output_formats=output_formats,
            emit_middle_json=emit_middle_json,
            total_batches=total_batches,
        )
        parallel_workers = _pipeline_job_workers(job, batch_jobs, document_total_pages)
        if parallel_workers > 1:
            from aih_contexture.runtime.pipeline_parallel import iter_parallel_batch_outputs

            emit_progress_event(
                "stage_changed",
                "batch",
                message=f"Running {total_batches} batches in {parallel_workers} worker processes",
            )
            parallel_outputs = iter_parallel_batch_outputs(
                batch_jobs, parallel_workers,
                progress_contexts=[
                    dict(file_name=file_name, document_total_pages=document_total_pages,
                         batch_index=index + 1, total_batches=total_batches,
                         batch_label=batch["label"], batch_page_count=batch_page_counts[index],
                         parallel_batch=True)
                    for index, batch in enumerate(batch_jobs)
                ],
                **batch_kwargs,
            )
        for bidx, batch_job in enumerate(batch_jobs):
            batch_label = batch_job["label"]
            batch_page_count = batch_page_counts[bidx]
            set_progress_context(
                batch_index=bidx + 1,
                total_batches=total_batches,
                batch_label=batch_label,
                batch_page_offset=completed_page_count,
                batch_page_count=batch_page_count,
            )
            emit_progress_event(
                "batch_started",
                "batch",
                batch_index=bidx + 1,
                total_batches=total_batches,
                current=0,
                total=batch_page_count,
                unit="pages",
                message=f"Processing pages {batch_label}",
            )
            logger.debug("[pipeline-worker] batch %s/%s: %s", bidx + 1, total_batches, batch_label)
            write_pipeline_checkpoint(
                checkpoint_path,
                pipeline_checkpoint_payload(
                    file_name=file_name,
                    result_key=result_key,
                    started_at=start,
                    backend_summary=backend_summary,
                    completed_batches=completed_batches,
                    current_batch=batch_label,
                    total_batches=total_batches,
                    file_outputs=file_outputs,
                    output_formats=output_formats,
                    markdown_path=markdown_path,
                    html_path=html_path,
                    json_batch_paths=json_batch_paths,
                    chunks_batch_paths=chunks_batch_paths,
                    error=f"Pipeline worker was processing batch {bidx + 1}/{total_batches}: {batch_label}.",
                ),
            )

            if parallel_outputs is not None:
                batch_output = next(parallel_outputs)
            else:
                batch_output = build_pipeline_batch_output(
                    bidx, batch_job, artifacts=artifacts, sidecar_pool=sidecar_pool, **batch_kwargs,
                )
            if emit_middle_json:
                middle_pages.extend(batch_output.middle_pages)
                middle_backends.update(batch_output.middle_backends)

            config_dict = batch_job["config_dict"]
            if not merged_metadata and batch_output.metadata is not None:
                merged_metadata = dict(batch_output.metadata)
                merged_metadata.setdefault(
                    "semantic_resolution",
                    {
                        "version": "footnote-superscript/0.2",
                        "footnote_enabled": bool(config_dict.get("footnote_enabled", True)),
                        "marginal_detection_enabled": True,
                        "superscript_policy": str(config_dict.get("superscript_policy", "footnote_safe")),
                        "footnote_reference_mode": "evidence_based",
                        "alphabetic_marker_policy": "strong_only",
                        "long_numeric_marker_policy": "strong_only",
                    },
                )
                write_meta_once(merged_metadata, out_dir_final, fname_base)

            saved_batch_images = False
            for fmt, text, images in batch_output.rendered:
                if fmt == "markdown":
                    available_image_names.update(images)
                    append_text(markdown_path, text)
                    if not saved_batch_images:
                        save_images(images, out_dir_final)
                        saved_batch_images = True
                elif fmt == "html":
                    available_image_names.update(images)
                    append_text(html_path, text)
                    if not saved_batch_images:
                        save_images(images, out_dir_final)
                        saved_batch_images = True
                elif fmt == "json":
                    batch_json_path = os.path.join(out_dir_final, f"{fname_base}.json.batch{bidx:04d}")
                    atomic_write_text(batch_json_path, text)
                    json_batch_paths.append(batch_json_path)
                elif fmt == "chunks":
                    batch_chunks_path = os.path.join(out_dir_final, f"{fname_base}_chunks.json.batch{bidx:04d}")
                    atomic_write_text(batch_chunks_path, text)
                    chunks_batch_paths.append(batch_chunks_path)

            del batch_output
            completed_batches.append(batch_label)
            emit_progress_event(
                "batch_completed",
                "batch",
                batch_index=bidx + 1,
                total_batches=total_batches,
                current=batch_page_count,
                total=batch_page_count,
                unit="pages",
                message=f"Completed pages {batch_label}",
            )
            completed_page_count += batch_page_count
            write_pipeline_checkpoint(
                checkpoint_path,
                pipeline_checkpoint_payload(
                    file_name=file_name,
                    result_key=result_key,
                    started_at=start,
                    backend_summary=backend_summary,
                    completed_batches=completed_batches,
                    current_batch=None,
                    total_batches=total_batches,
                    file_outputs=file_outputs,
                    output_formats=output_formats,
                    markdown_path=markdown_path,
                    html_path=html_path,
                    json_batch_paths=json_batch_paths,
                    chunks_batch_paths=chunks_batch_paths,
                    error=f"Pipeline worker completed {len(completed_batches)}/{total_batches} batches.",
                ),
            )

        emit_progress_event(
            "stage_changed",
            "saving",
            current=document_total_pages,
            total=document_total_pages,
            unit="pages",
            absolute_progress=True,
            message="Merging and saving outputs",
        )
        if "markdown" in output_formats and markdown_path:
            file_outputs.append({"format": "markdown", "path": markdown_path, "name": os.path.basename(markdown_path)})

        if "html" in output_formats and html_path:
            file_outputs.append({"format": "html", "path": html_path, "name": os.path.basename(html_path)})

        from aih_contexture.middle.indra_evidence import collect_indra_evidence
        indra = collect_indra_evidence(middle_pages)
        if indra:
            # Other metadata follows the legacy first-batch policy. Indra's
            # observations must cover every processed source page.
            merged_metadata["indra"] = indra
            atomic_write_text(os.path.join(out_dir_final, f"{fname_base}_meta.json"),
                              json.dumps(merged_metadata, ensure_ascii=False, indent=2))

        if "json" in output_formats:
            jp = os.path.join(out_dir_final, f"{fname_base}.json")
            merge_json_batches(jp, json_batch_paths, merged_metadata)
            file_outputs.append({"format": "json", "path": jp, "name": os.path.basename(jp)})

        if "chunks" in output_formats:
            cp = os.path.join(out_dir_final, f"{fname_base}_chunks.json")
            merge_chunk_batches(cp, chunks_batch_paths, merged_metadata)
            file_outputs.append({"format": "chunks", "path": cp, "name": os.path.basename(cp)})

        if emit_middle_json:
            middle_document = MiddleDocument(
                source_name=source_file_path,
                pages=middle_pages,
                metadata=merged_metadata,
                backends=middle_backends,
            )
            from aih_contexture.middle.schema import reading_middle_dict
            middle_source = middle_document.to_dict() if (emit_middle_full_json or emit_span_overlay) else reading_middle_dict(middle_document)
            middle_outputs = save_middle_json_artifacts(
                bind_available_image_resources(middle_source, available_image_names),
                out_dir_final,
                fname_base,
                emit_middle_report=emit_middle_report,
                emit_middle_debug=emit_middle_debug,
                emit_middle_scholarly=emit_middle_scholarly,
                emit_middle_scholarly_report=emit_middle_scholarly_report,
                emit_layout_overlay=emit_layout_overlay,
                emit_span_overlay=emit_span_overlay,
                emit_middle_full_json=emit_middle_full_json,
                render_config=batch_jobs[0].get('config_dict', {}) if batch_jobs else {},
            )
            for key, output_format in (
                ("middle_json_path", "middle_json"),
                ("middle_report_path", "middle_report"),
                ("middle_debug_path", "middle_debug"),
                ("middle_scholarly_path", "middle_scholarly"),
                ("middle_scholarly_report_path", "middle_scholarly_report"),
                ("middle_full_json_path", "middle_full_json"),
                ("classical_marginalia_sidecar_path", "classical_marginalia_sidecar"),
                ("classical_marginalia_manifest_path", "classical_marginalia_manifest"),
            ):
                if key in middle_outputs:
                    path = middle_outputs[key]
                    file_outputs.append({"format": output_format, "path": path, "name": os.path.basename(path)})
            if "layout_overlay_pdf_path" in middle_outputs:
                file_outputs.append({
                    "format": "layout_overlay",
                    "path": middle_outputs["layout_overlay_pdf_path"],
                    "name": os.path.basename(middle_outputs["layout_overlay_pdf_path"]),
                })
            if "span_overlay_pdf_path" in middle_outputs:
                file_outputs.append({
                    "format": "span_overlay",
                    "path": middle_outputs["span_overlay_pdf_path"],
                    "name": os.path.basename(middle_outputs["span_overlay_pdf_path"]),
                })
            middle_json_path = middle_outputs.get("middle_json_path")
            if middle_json_path and os.path.exists(middle_json_path):
                try:
                    with open(middle_json_path, "r", encoding=settings.OUTPUT_ENCODING) as f:
                        saved_middle = json.load(f)
                    semantic_resolution = saved_middle.get("metadata", {}).get("semantic_resolution")
                    if isinstance(semantic_resolution, dict):
                        merged_metadata["semantic_resolution"] = semantic_resolution
                        update_meta_semantic_resolution(out_dir_final, fname_base, semantic_resolution)
                except (OSError, json.JSONDecodeError):
                    logger.exception("Failed to update semantic_resolution in meta artifact")
            if markdown_path:
                # Publishing failures must propagate to the worker checkpoint,
                # rather than being swallowed as an optional metadata error.
                with open(middle_outputs['middle_json_path'], encoding=settings.OUTPUT_ENCODING) as stream:
                    final_middle = json.load(stream)
                finalize_pipeline_reading_markdown(
                    final_middle, markdown_path,
                    batch_jobs[0].get('config_dict', {}) if batch_jobs else {},
                )
            diagnostic_path = middle_outputs.get("reading_diagnostics_path")
            if diagnostic_path:
                if markdown_path:
                    from aih_contexture.runtime.reading_diagnostics import bind_reading_diagnostics
                    bound_path = bind_reading_diagnostics(diagnostic_path, markdown_path)
                    if bound_path != diagnostic_path:
                        file_outputs.append({"format": "reading_scholarly_diagnostics", "path": diagnostic_path,
                                             "name": os.path.basename(diagnostic_path)})
                    diagnostic_path = bound_path
                file_outputs.append({"format": "reading_diagnostics", "path": diagnostic_path,
                                     "name": os.path.basename(diagnostic_path)})

        elapsed = time.time() - start
        summary_path = write_document_summary(
            output_dir=out_dir_final,
            source_name=file_name,
            processing_id=str(job.get("processing_id") or "0000"),
            file_index=job.get("file_index"),
            mode="pipeline",
            strategy="middle_first",
            models=backend_summary or {},
            config=(batch_jobs[0].get("config_dict", {}) if batch_jobs else {}),
            started_at=datetime.fromtimestamp(start).astimezone().isoformat(timespec="seconds"),
            finished_at=utc_now_iso(),
            elapsed_seconds=elapsed,
            status="succeeded",
            page_count=document_total_pages,
            output_paths=[item.get("path") for item in file_outputs if item.get("path")],
            source_path=source_file_path,
        )
        emit_progress_event(
            "file_completed",
            "completed",
            current=document_total_pages,
            total=document_total_pages,
            unit="pages",
            absolute_progress=True,
            elapsed_seconds=elapsed,
            message=f"Completed {file_name}",
        )
        return {
            "success": True,
            "file_name": file_name,
            "result_key": result_key,
            "file_outputs": file_outputs,
            "summary_path": summary_path,
            "elapsed_seconds": elapsed,
            "backend_summary": backend_summary,
            "error": None,
            "traceback": None,
        }
    finally:
        if parallel_outputs is not None:
            parallel_outputs.close()
        if owns_sidecar_pool:
            sidecar_pool.close_all()
        cleanup_pipeline_preprocess(preprocess_result)


def _is_text_layer_pipeline_job(batch_jobs: list[dict[str, Any]]) -> bool:
    if not batch_jobs:
        return False
    return all(
        str((batch_job.get("config_dict") or {}).get("layout_backend") or "")
        .strip()
        .lower()
        .replace("-", "_")
        == "none"
        for batch_job in batch_jobs
    )


def _process_text_layer_pipeline_job(job: dict[str, Any]) -> dict[str, Any]:
    """Use runtime.run_job for the GUI worker's model-free text-layer route."""
    from aih_contexture.runtime.job import ContextureJob
    from aih_contexture.runtime.progress_events import emit_progress_event, set_progress_context
    from aih_contexture.runtime.runner import run_job

    started = time.time()
    file_path = job["file_path"]
    file_name = job["file_name"]
    output_dir = job["output_dir"]
    fname_base = job["fname_base"]
    output_formats = list(job["output_formats"])
    config = dict(job["batch_jobs"][0].get("config_dict") or {})
    result_key = f"{file_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    set_progress_context(file_name=file_name, total_batches=1)
    emit_progress_event("file_started", "starting", file_name=file_name, message=f"Starting {file_name}")
    emit_progress_event("stage_changed", "extracting", message="Extracting embedded PDF text")
    result = run_job(
        ContextureJob(
            input_path=file_path,
            input_name=file_name,
            mode="pipeline",
            output_formats=output_formats,
            page_range=config.get("page_range"),
            config=config,
        )
    )
    markdown_path = os.path.join(output_dir, f"{fname_base}.md")
    atomic_write_text(markdown_path, result.markdown or "")
    middle_path = os.path.join(output_dir, f"{fname_base}_middle.json")
    if result.middle_json is None:
        raise ValueError("Text-layer pipeline result is missing mandatory Middle JSON")
    atomic_write_text(
        middle_path,
        json.dumps(result.middle_json, ensure_ascii=False, indent=2),
    )
    file_outputs = [
        {"format": "markdown", "path": markdown_path, "name": os.path.basename(markdown_path)},
        {"format": "middle_json", "path": middle_path, "name": os.path.basename(middle_path)},
    ]
    output_paths = [markdown_path, middle_path]
    if "json" in output_formats:
        json_path = os.path.join(output_dir, f"{fname_base}.json")
        atomic_write_text(json_path, result.json_text or "")
        file_outputs.append({"format": "json", "path": json_path, "name": os.path.basename(json_path)})
        output_paths.append(json_path)
    if "html" in output_formats:
        html_path = os.path.join(output_dir, f"{fname_base}.html")
        atomic_write_text(html_path, result.html or "")
        file_outputs.append({"format": "html", "path": html_path, "name": os.path.basename(html_path)})
        output_paths.append(html_path)
    elapsed = time.time() - started
    summary_path = write_document_summary(
        output_dir=output_dir, source_name=file_name, processing_id=str(job.get("processing_id") or "0000"),
        file_index=job.get("file_index"), mode="pipeline", strategy="text_layer",
        models={"ocr": "none", "layout": "none"}, config=config,
        started_at=datetime.fromtimestamp(started).astimezone().isoformat(timespec="seconds"),
        finished_at=utc_now_iso(), elapsed_seconds=elapsed, status="succeeded",
        page_count=result.page_count, output_paths=output_paths,
        warnings=result.warnings, source_path=file_path,
    )
    emit_progress_event(
        "file_completed",
        "completed",
        current=result.page_count,
        total=result.page_count,
        unit="pages",
        absolute_progress=True,
        elapsed_seconds=elapsed,
        message=f"Completed {file_name}",
    )
    return {
        "success": True,
        "file_name": file_name,
        "result_key": result_key,
        "file_outputs": file_outputs,
        "elapsed_seconds": elapsed,
        "backend_summary": _backend_summary_from_batch_jobs(job["batch_jobs"]),
        "warnings": result.warnings,
        "metadata": result.metadata,
        "summary_path": summary_path,
        "error": None,
        "traceback": None,
    }


_PIPELINE_RENDERERS = {
    "markdown": MarkdownRenderer,
    "json": JSONRenderer,
    "html": HTMLRenderer,
    "chunks": ChunkRenderer,
}


@dataclass(slots=True)
class PipelineBatchOutput:
    """One rendered page batch; picklable so worker processes can return it."""

    index: int
    rendered: list[tuple[str, str, dict[str, Any]]]
    metadata: dict[str, Any] | None
    middle_pages: list[Any]
    middle_backends: dict[str, Any]


def build_pipeline_batch_output(
    index: int,
    batch_job: dict[str, Any],
    *,
    artifacts: Any,
    sidecar_pool: SidecarRuntimePool,
    file_path: str,
    source_file_path: str,
    output_formats: list[str],
    emit_middle_json: bool,
    total_batches: int,
) -> PipelineBatchOutput:
    from aih_contexture.runtime.progress_events import emit_progress_event

    config_dict = dict(batch_job["config_dict"])
    config_dict["_sidecar_runtime_pool"] = sidecar_pool
    preprocess_backend = normalize_ocr_preprocess_backend(config_dict.get("ocr_preprocess_backend"))
    if preprocess_backend != "none":
        config_dict["disable_ocr"] = True
        config_dict["force_ocr"] = False
    render_config_dict = {
        key: value for key, value in config_dict.items() if not str(key).startswith("_")
    }

    converter = PdfConverter(config=config_dict, artifact_dict=artifacts)
    document = converter.build_document(file_path)
    middle_pages: list[Any] = []
    middle_backends: dict[str, Any] = {}
    if emit_middle_json:
        selected_ocr_backend = str(config_dict.get("ocr_backend") or "")
        if config_dict.get("disable_ocr", False):
            ocr_backend = "chrome_screenai" if (preprocess_backend != "none" and selected_ocr_backend == "chrome_screenai") else "none"
        else:
            ocr_backend = config_dict.get("ocr_backend")
        batch_middle = document_to_middle(
            document,
            layout_backend=config_dict.get("layout_backend"),
            layout_model=_layout_model_from_config(config_dict),
            ocr_backend=ocr_backend,
            ocr_preprocess_backend=preprocess_backend if preprocess_backend != "none" else None,
            source_name=source_file_path,
        )
        middle_pages = list(batch_middle.pages)
        middle_backends = dict(batch_middle.backends)

    emit_progress_event("stage_changed", "render", message=f"Rendering batch {index + 1}/{total_batches}")
    rendered_outputs: list[tuple[str, str, dict[str, Any]]] = []
    metadata = None
    for fmt in output_formats:
        renderer = _PIPELINE_RENDERERS[fmt](render_config_dict)
        rendered = renderer(document)
        text, _, images = text_from_rendered(rendered)
        if metadata is None and getattr(rendered, "metadata", None) is not None:
            metadata = dict(rendered.metadata or {})
        rendered_outputs.append((fmt, text, images if fmt in ("markdown", "html") else {}))
        del renderer, rendered, images

    del document, converter
    return PipelineBatchOutput(index, rendered_outputs, metadata, middle_pages, middle_backends)


def _pipeline_job_workers(job: dict[str, Any], batch_jobs: list[dict[str, Any]], total_pages: int) -> int:
    """Recheck automatic budgets and retain the requested manual concurrency."""
    from aih_contexture.runtime.pipeline_parallelism import (
        MANUAL, describe_plan, layout_batch_size_for, resolve_pipeline_parallelism,
    )

    requested = int(job.get("pipeline_workers") or 1)
    if requested <= 1 or len(batch_jobs) <= 1:
        return 1
    config = batch_jobs[0].get("config_dict") or {}
    plan = resolve_pipeline_parallelism(
        layout_backend=config.get("layout_backend"),
        ocr_backend="none" if config.get("disable_ocr") else config.get("ocr_backend"),
        layout_batch_size=layout_batch_size_for(config),
        layout_quality=config.get("surya_layout_quality"),
        mode=job.get("pipeline_performance_mode") or MANUAL,
        workers=requested,
        pages_per_batch=_pipeline_batch_page_count(batch_jobs[0]),
        total_pages=total_pages,
    )
    for note in plan.notes:
        logger.warning("[pipeline-worker] %s", note)
    logger.info("[pipeline-worker] parallel plan: %s", describe_plan(plan))
    return min(requested, plan.workers, len(batch_jobs))


def _pipeline_batch_page_count(batch_job: dict[str, Any]) -> int:
    page_range = str((batch_job.get("config_dict") or {}).get("page_range") or "")
    try:
        start_text, end_text = page_range.split("-", 1)
        return max(0, int(end_text) - int(start_text) + 1)
    except (TypeError, ValueError):
        label = str(batch_job.get("label") or "")
        try:
            start_text, end_text = label.split("-", 1)
            return max(0, int(end_text) - int(start_text) + 1)
        except (TypeError, ValueError):
            return 0


def _backend_summary_from_batch_jobs(batch_jobs: list[dict[str, Any]]) -> dict[str, Any]:
    preprocess_backends = []
    layout_backends = []
    layout_models = []
    ocr_backends = []
    disable_ocr_values = []
    for batch_job in batch_jobs:
        config = batch_job.get("config_dict", {}) or {}
        preprocess = normalize_ocr_preprocess_backend(config.get("ocr_preprocess_backend"))
        if preprocess != "none" and preprocess not in preprocess_backends:
            preprocess_backends.append(preprocess)
        layout = config.get("layout_backend")
        if layout and layout not in layout_backends:
            layout_backends.append(layout)
        layout_model = _layout_model_from_config(config)
        if layout_model and layout_model not in layout_models:
            layout_models.append(layout_model)
        effective_disable_ocr = bool(config.get("disable_ocr", False)) or preprocess != "none"
        requested_ocr = config.get("ocr_backend")
        if effective_disable_ocr and requested_ocr == "chrome_screenai" and preprocess != "none":
            ocr = "chrome_screenai"
        else:
            ocr = "none" if effective_disable_ocr else requested_ocr
        if ocr and ocr not in ocr_backends:
            ocr_backends.append(ocr)
        if effective_disable_ocr not in disable_ocr_values:
            disable_ocr_values.append(effective_disable_ocr)

    return {
        "ocr_preprocess_backends": preprocess_backends,
        "layout_backends": layout_backends,
        "layout_models": layout_models,
        "ocr_backends": ocr_backends,
        "disable_ocr": disable_ocr_values,
    }


def _layout_model_from_config(config: dict[str, Any]) -> str | None:
    if config.get("external_layout_model"):
        return str(config["external_layout_model"])
    if config.get("paddle_layout_model_name"):
        return str(config["paddle_layout_model_name"])
    layout_backend = str(config.get("layout_backend") or "").strip().lower()
    if layout_backend == "mineru_vl_layout":
        return str(config.get("mineru_vl_model") or "MinerU-VL")
    if layout_backend == "paddle_pp_doclayout_v3":
        return "PP-DocLayoutV3"
    if layout_backend == "paddle_pp_doclayout_plus_l":
        return "PP-DocLayout_plus-L"
    if layout_backend == "mineru_pp_doclayout_v2_direct":
        return "PP-DocLayoutV2"
    if layout_backend == "surya":
        return "surya"
    if layout_backend == "surya2_layout":
        return "surya2"
    if layout_backend == "vlm_layout":
        return str(config.get("vlm_layout_model") or "vlm_layout")
    # 未知后端交给调用方回退到 layout_backends，避免整条布局信息丢失。
    return None
