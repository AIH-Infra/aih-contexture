from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any, TextIO

from aih_contexture.converters.pdf import PdfConverter
from aih_contexture.logger import get_logger
from aih_contexture.middle.adapters import document_to_middle
from aih_contexture.middle.debug_markdown import render_middle_debug_markdown
from aih_contexture.middle.schema import MiddleDocument
from aih_contexture.middle.semantics import resolve_middle_for_rendering
from aih_contexture.middle.scholarly_markdown import render_middle_scholarly_markdown
from aih_contexture.middle.validation import validate_middle_json
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
from aih_contexture.runtime.job import ContextureResult
from aih_contexture.runtime.run_summary import utc_now_iso, write_document_summary
from aih_contexture.settings import settings

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
        os.replace(temp_path, destination)
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
    os.makedirs(output_dir, exist_ok=True)
    if result.middle_json is None:
        raise ValueError("ContextureResult is missing mandatory Middle JSON")
    text, ext = text_from_contexture_result(result, output_format)
    text = text.encode(settings.OUTPUT_ENCODING, errors="replace").decode(
        settings.OUTPUT_ENCODING
    )

    output_path = os.path.join(output_dir, f"{fname_base}.{ext}")
    atomic_write_text(output_path, text, encoding=settings.OUTPUT_ENCODING)

    metadata_to_write = dict(result.metadata or {})
    if result.middle_json is not None:
        result.middle_json = resolve_middle_for_rendering(
            result.middle_json,
            {
                "footnote_enabled": bool(result.debug_artifacts.get("footnote_enabled", True)),
                "superscript_policy": str(result.debug_artifacts.get("superscript_policy", "footnote_safe")),
            },
        )
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
            include_printed_page_comments=bool(result.debug_artifacts.get("include_printed_page_comments", True)),
            include_page_header_comments=bool(result.debug_artifacts.get("include_page_header_comments", True)),
            include_page_footer_comments=bool(result.debug_artifacts.get("include_page_footer_comments", True)),
            include_margin_comments=bool(result.debug_artifacts.get("include_margin_comments", True)),
            marginal_output_mode=result.debug_artifacts.get("marginal_output_mode"),
            equation_output_mode=result.debug_artifacts.get("equation_output_mode", "humanities_safe"),
            footnote_enabled=bool(result.debug_artifacts.get("footnote_enabled", True)),
            superscript_policy=str(result.debug_artifacts.get("superscript_policy", "footnote_safe")),
            include_blockquote_markers=bool(result.debug_artifacts.get("include_blockquote_markers", True)),
            include_page_separators=bool(result.debug_artifacts.get("include_page_separators", True)),
        )

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
    include_page_header_comments: bool = True,
    include_page_footer_comments: bool = True,
    include_margin_comments: bool = True,
    marginal_output_mode: str | None = None,
    equation_output_mode: str = "humanities_safe",
    footnote_enabled: bool = True,
    superscript_policy: str = "footnote_safe",
    include_blockquote_markers: bool = True,
    include_printed_page_comments: bool = True,
    include_page_separators: bool = True,
) -> dict[str, str]:
    os.makedirs(output_dir, exist_ok=True)
    resolved_middle_json = resolve_middle_for_rendering(
        middle_json,
        {
            "footnote_enabled": footnote_enabled,
            "superscript_policy": superscript_policy,
        },
    )
    compact_middle_json = compact_middle_json_for_storage(resolved_middle_json)
    middle_json_path = os.path.join(output_dir, f"{fname_base}_middle.json")
    atomic_write_text(
        middle_json_path,
        json.dumps(compact_middle_json, ensure_ascii=False, separators=(",", ":")),
        encoding=settings.OUTPUT_ENCODING,
    )

    outputs = {
        "middle_json_path": middle_json_path,
    }
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
        middle_scholarly_text = render_middle_scholarly_markdown(
            compact_middle_json,
            include_printed_page_comments=include_printed_page_comments,
            include_page_header_comments=include_page_header_comments,
            include_page_footer_comments=include_page_footer_comments,
            include_margin_comments=include_margin_comments,
            marginal_output_mode=marginal_output_mode,
            equation_output_mode=equation_output_mode,
            footnote_enabled=footnote_enabled,
            superscript_policy=superscript_policy,
            include_blockquote_markers=include_blockquote_markers,
            include_page_separators=include_page_separators,
        )

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


def compact_middle_json_for_storage(middle_json: dict[str, Any]) -> dict[str, Any]:
    """Return a storage-friendly Middle JSON payload.

    The full in-memory Middle object can contain word-level spans with geometry,
    font attributes and provenance. That is useful for span overlays, but it is
    far too large for the regular *_middle.json artifact whose main jobs are
    validation, inspection and Markdown re-rendering.
    """
    if not isinstance(middle_json, dict):
        return middle_json

    middle_json = resolve_middle_for_rendering(middle_json)

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


def _compact_page(page: dict[str, Any]) -> dict[str, Any]:
    keep = ("index", "width", "height", "printed_page", "anchor_start", "anchor_end")
    compact = {key: _compact_value(page.get(key)) for key in keep if _keep_value(page.get(key))}
    attrs = _compact_attrs(page.get("attrs"), keep_keys={
        "layout_sliced",
        "ocr_errors_detected",
        "machine_page_number",
        "page_header_text",
        "page_footer_text",
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
    attrs = _compact_attrs(block.get("attrs"), keep_keys={
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
        if _keep_value(val) and key not in {"images", "image_data", "debug_images", "page_images"}
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


def _compact_value(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 4)
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


def process_pipeline_job(job: dict[str, Any]) -> dict[str, Any]:
    from aih_contexture.runtime.progress_events import emit_progress_event, set_progress_context

    start = time.time()
    file_path = job["file_path"]
    source_file_path = file_path
    file_name = job["file_name"]
    out_dir_final = job["output_dir"]
    output_formats = job["output_formats"]
    fname_base = job["fname_base"]
    batch_jobs = job["batch_jobs"]
    if _is_text_layer_pipeline_job(batch_jobs):
        return _process_text_layer_pipeline_job(job)
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

    for path in (markdown_path, html_path):
        if path and os.path.exists(path):
            os.remove(path)

    renderer_map = {
        "markdown": MarkdownRenderer,
        "json": JSONRenderer,
        "html": HTMLRenderer,
        "chunks": ChunkRenderer,
    }
    file_outputs = []
    preprocess_result = None
    sidecar_pool = SidecarRuntimePool()

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
        artifacts = create_model_dict()
        emit_progress_event("stage_completed", "model_loading", message="Models loaded")
        preprocess_config = dict(batch_jobs[0].get("config_dict", {}) or {}) if batch_jobs else {}
        emit_progress_event("stage_changed", "preprocess", message="Preprocessing PDF")
        preprocess_result = apply_pipeline_pdf_preprocess(
            file_path=file_path,
            output_dir=out_dir_final,
            fname_base=fname_base,
            config=preprocess_config,
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
                middle_pages.extend(batch_middle.pages)
                middle_backends.update(batch_middle.backends)

            saved_batch_images = False
            emit_progress_event("stage_changed", "render", message=f"Rendering batch {bidx + 1}/{total_batches}")
            for fmt in output_formats:
                renderer = renderer_map[fmt](render_config_dict)
                rendered = renderer(document)
                text, _, images = text_from_rendered(rendered)

                if not merged_metadata and getattr(rendered, "metadata", None) is not None:
                    merged_metadata = dict(rendered.metadata or {})
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

                if fmt == "markdown":
                    append_text(markdown_path, text)
                    if not saved_batch_images:
                        save_images(images, out_dir_final)
                        saved_batch_images = True
                elif fmt == "html":
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

                del renderer, rendered, text, images

            del document, converter
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
            middle_outputs = save_middle_json_artifacts(
                middle_document.to_dict(),
                out_dir_final,
                fname_base,
                emit_middle_report=emit_middle_report,
                emit_middle_debug=emit_middle_debug,
                emit_middle_scholarly=emit_middle_scholarly,
                emit_middle_scholarly_report=emit_middle_scholarly_report,
                emit_layout_overlay=emit_layout_overlay,
                emit_span_overlay=emit_span_overlay,
                emit_middle_full_json=emit_middle_full_json,
                marginal_output_mode=marginal_output_mode,
                equation_output_mode=equation_output_mode,
                footnote_enabled=bool(batch_jobs[0].get("config_dict", {}).get("footnote_enabled", True)) if batch_jobs else True,
                superscript_policy=str(batch_jobs[0].get("config_dict", {}).get("superscript_policy", "footnote_safe")) if batch_jobs else "footnote_safe",
            )
            for key, output_format in (
                ("middle_json_path", "middle_json"),
                ("middle_report_path", "middle_report"),
                ("middle_debug_path", "middle_debug"),
                ("middle_scholarly_path", "middle_scholarly"),
                ("middle_scholarly_report_path", "middle_scholarly_report"),
                ("middle_full_json_path", "middle_full_json"),
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
    elapsed = time.time() - started
    summary_path = write_document_summary(
        output_dir=output_dir, source_name=file_name, processing_id=str(job.get("processing_id") or "0000"),
        file_index=job.get("file_index"), mode="pipeline", strategy="text_layer",
        models={"ocr": "none", "layout": "none"}, config=config,
        started_at=datetime.fromtimestamp(started).astimezone().isoformat(timespec="seconds"),
        finished_at=utc_now_iso(), elapsed_seconds=elapsed, status="succeeded",
        page_count=result.page_count, output_paths=[markdown_path, middle_path],
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
        "file_outputs": [
            {"format": "markdown", "path": markdown_path, "name": os.path.basename(markdown_path)},
            {"format": "middle_json", "path": middle_path, "name": os.path.basename(middle_path)},
        ],
        "elapsed_seconds": elapsed,
        "backend_summary": _backend_summary_from_batch_jobs(job["batch_jobs"]),
        "warnings": result.warnings,
        "metadata": result.metadata,
        "summary_path": summary_path,
        "error": None,
        "traceback": None,
    }


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
