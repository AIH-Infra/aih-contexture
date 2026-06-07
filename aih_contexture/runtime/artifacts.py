from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any

from aih_contexture.converters.pdf import PdfConverter
from aih_contexture.logger import get_logger
from aih_contexture.middle.adapters import document_to_middle
from aih_contexture.middle.debug_markdown import render_middle_debug_markdown
from aih_contexture.middle.schema import MiddleDocument
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
from aih_contexture.runtime.job import ContextureResult
from aih_contexture.settings import settings

logger = get_logger()


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
    with open(meta_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(meta, ensure_ascii=False, indent=2))


def save_images(images_dict: dict, out_dir: str):
    if not images_dict:
        return

    for img_name, img in images_dict.items():
        try:
            img = convert_if_not_rgb(img)
            img.save(os.path.join(out_dir, img_name), settings.OUTPUT_IMAGE_FORMAT)
        except Exception:
            logger.exception("Failed to save image artifact: %s", img_name)


def save_contexture_result(
    result: ContextureResult,
    output_dir: str,
    fname_base: str,
    output_format: str,
) -> dict[str, str]:
    os.makedirs(output_dir, exist_ok=True)
    text, ext = text_from_contexture_result(result, output_format)
    text = text.encode(settings.OUTPUT_ENCODING, errors="replace").decode(
        settings.OUTPUT_ENCODING
    )

    output_path = os.path.join(output_dir, f"{fname_base}.{ext}")
    with open(output_path, "w+", encoding=settings.OUTPUT_ENCODING) as f:
        f.write(text)

    meta_path = os.path.join(output_dir, f"{fname_base}_meta.json")
    with open(meta_path, "w+", encoding=settings.OUTPUT_ENCODING) as f:
        f.write(json.dumps(result.metadata, indent=2))

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
            include_printed_page_comments=bool(result.debug_artifacts.get("include_printed_page_comments", True)),
            include_page_header_comments=bool(result.debug_artifacts.get("include_page_header_comments", True)),
            include_page_footer_comments=bool(result.debug_artifacts.get("include_page_footer_comments", True)),
            include_margin_comments=bool(result.debug_artifacts.get("include_margin_comments", True)),
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
    include_page_header_comments: bool = True,
    include_page_footer_comments: bool = True,
    include_margin_comments: bool = True,
    include_printed_page_comments: bool = True,
    include_page_separators: bool = True,
) -> dict[str, str]:
    os.makedirs(output_dir, exist_ok=True)
    middle_json_path = os.path.join(output_dir, f"{fname_base}_middle.json")
    with open(middle_json_path, "w+", encoding=settings.OUTPUT_ENCODING) as f:
        f.write(json.dumps(middle_json, ensure_ascii=False, indent=2))

    outputs = {
        "middle_json_path": middle_json_path,
    }
    if emit_middle_report:
        report = validate_middle_json(middle_json)
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
        with open(middle_report_path, "w+", encoding=settings.OUTPUT_ENCODING) as f:
            f.write(json.dumps(report_payload, ensure_ascii=False, indent=2))
        outputs["middle_report_path"] = middle_report_path

    if emit_middle_debug:
        middle_debug_path = os.path.join(output_dir, f"{fname_base}_middle_debug.md")
        with open(middle_debug_path, "w+", encoding=settings.OUTPUT_ENCODING) as f:
            f.write(render_middle_debug_markdown(middle_json))
        outputs["middle_debug_path"] = middle_debug_path

    middle_scholarly_text = None
    middle_scholarly_path = os.path.join(output_dir, f"{fname_base}_middle_scholarly.md")
    if emit_middle_scholarly or emit_middle_scholarly_report:
        middle_scholarly_text = render_middle_scholarly_markdown(
            middle_json,
            include_printed_page_comments=include_printed_page_comments,
            include_page_header_comments=include_page_header_comments,
            include_page_footer_comments=include_page_footer_comments,
            include_margin_comments=include_margin_comments,
            include_page_separators=include_page_separators,
        )

    if emit_middle_scholarly and middle_scholarly_text is not None:
        with open(middle_scholarly_path, "w+", encoding=settings.OUTPUT_ENCODING) as f:
            f.write(middle_scholarly_text)
        outputs["middle_scholarly_path"] = middle_scholarly_path

    if emit_middle_scholarly_report and middle_scholarly_text is not None:
        scholarly_report = evaluate_scholarly_markdown_text(
            middle_scholarly_text,
            source_path=middle_scholarly_path,
        )
        middle_scholarly_report_path = os.path.join(output_dir, f"{fname_base}_middle_scholarly_report.json")
        with open(middle_scholarly_report_path, "w+", encoding=settings.OUTPUT_ENCODING) as f:
            f.write(json.dumps(scholarly_report, ensure_ascii=False, indent=2))
        outputs["middle_scholarly_report_path"] = middle_scholarly_report_path
    source_pdf = middle_json.get("source_name")
    if emit_layout_overlay:
        overlay_dir = os.path.join(output_dir, f"{fname_base}_layout_overlay")
        overlay_pdf = os.path.join(output_dir, f"{fname_base}_layout_overlay.pdf")
        overlay = render_middle_layout_overlay(
            middle_json,
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
            middle_json,
            source_pdf=source_pdf,
            output_dir=span_overlay_dir,
            output_pdf=span_overlay_pdf,
        )
        if span_overlay.get("ok"):
            outputs["span_overlay_dir"] = span_overlay_dir
            if span_overlay.get("pdf"):
                outputs["span_overlay_pdf_path"] = str(span_overlay["pdf"])

    return outputs


def merge_json_batches(output_path: str, batch_paths: list[str], metadata: dict):
    with open(output_path, "w", encoding="utf-8") as out_f:
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
            try:
                os.remove(batch_path)
            except OSError:
                pass
        out_f.write('\n  ],\n')
        out_f.write('  "block_type": "Document",\n')
        out_f.write('  "metadata": ')
        out_f.write(json.dumps(metadata, ensure_ascii=False, indent=2))
        out_f.write('\n}')


def merge_chunk_batches(output_path: str, batch_paths: list[str], metadata: dict):
    with open(output_path, "w", encoding="utf-8") as out_f:
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
            try:
                os.remove(batch_path)
            except OSError:
                pass
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


def process_pipeline_job(job: dict[str, Any]) -> dict[str, Any]:
    start = time.time()
    file_path = job["file_path"]
    file_name = job["file_name"]
    out_dir_final = job["output_dir"]
    output_formats = job["output_formats"]
    fname_base = job["fname_base"]
    batch_jobs = job["batch_jobs"]
    total_batches = len(batch_jobs)
    backend_summary = _backend_summary_from_batch_jobs(batch_jobs)

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
    )
    emit_middle_json = any(
        any(bool(batch_job.get("config_dict", {}).get(key, False)) for key in middle_artifact_keys)
        for batch_job in batch_jobs
    )
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
    middle_pages = []
    middle_backends = {}

    for path in (markdown_path, html_path):
        if path and os.path.exists(path):
            os.remove(path)

    artifacts = create_model_dict()
    renderer_map = {
        "markdown": MarkdownRenderer,
        "json": JSONRenderer,
        "html": HTMLRenderer,
        "chunks": ChunkRenderer,
    }
    file_outputs = []

    for bidx, batch_job in enumerate(batch_jobs):
        batch_label = batch_job["label"]
        logger.info("[pipeline-worker] batch %s/%s: %s", bidx + 1, total_batches, batch_label)

        config_dict = batch_job["config_dict"]
        converter = PdfConverter(config=config_dict, artifact_dict=artifacts)
        document = converter.build_document(file_path)
        if emit_middle_json:
            ocr_backend = (
                "none"
                if config_dict.get("disable_ocr", False)
                else config_dict.get("ocr_backend")
            )
            batch_middle = document_to_middle(
                document,
                layout_backend=config_dict.get("layout_backend"),
                layout_model=_layout_model_from_config(config_dict),
                ocr_backend=ocr_backend,
                source_name=file_path,
            )
            middle_pages.extend(batch_middle.pages)
            middle_backends.update(batch_middle.backends)

        saved_batch_images = False
        for fmt in output_formats:
            renderer = renderer_map[fmt](config_dict)
            rendered = renderer(document)
            text, _, images = text_from_rendered(rendered)

            if not merged_metadata and getattr(rendered, "metadata", None) is not None:
                merged_metadata = rendered.metadata
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
                with open(batch_json_path, "w", encoding="utf-8") as f:
                    f.write(text)
                json_batch_paths.append(batch_json_path)
            elif fmt == "chunks":
                batch_chunks_path = os.path.join(out_dir_final, f"{fname_base}_chunks.json.batch{bidx:04d}")
                with open(batch_chunks_path, "w", encoding="utf-8") as f:
                    f.write(text)
                chunks_batch_paths.append(batch_chunks_path)

            del renderer, rendered, text, images

        del document, converter

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
            source_name=file_path,
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
        )
        for key, output_format in (
            ("middle_json_path", "middle_json"),
            ("middle_report_path", "middle_report"),
            ("middle_debug_path", "middle_debug"),
            ("middle_scholarly_path", "middle_scholarly"),
            ("middle_scholarly_report_path", "middle_scholarly_report"),
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

    result_key = f"{file_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    elapsed = time.time() - start
    return {
        "success": True,
        "file_name": file_name,
        "result_key": result_key,
        "file_outputs": file_outputs,
        "elapsed_seconds": elapsed,
        "backend_summary": backend_summary,
        "error": None,
        "traceback": None,
    }


def _backend_summary_from_batch_jobs(batch_jobs: list[dict[str, Any]]) -> dict[str, Any]:
    layout_backends = []
    layout_models = []
    ocr_backends = []
    disable_ocr_values = []
    for batch_job in batch_jobs:
        config = batch_job.get("config_dict", {}) or {}
        layout = config.get("layout_backend")
        if layout and layout not in layout_backends:
            layout_backends.append(layout)
        layout_model = _layout_model_from_config(config)
        if layout_model and layout_model not in layout_models:
            layout_models.append(layout_model)
        ocr = "none" if config.get("disable_ocr", False) else config.get("ocr_backend")
        if ocr and ocr not in ocr_backends:
            ocr_backends.append(ocr)
        if config.get("disable_ocr", False) not in disable_ocr_values:
            disable_ocr_values.append(bool(config.get("disable_ocr", False)))

    return {
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
    if layout_backend == "paddle_pp_doclayout_v3":
        return "PP-DocLayoutV3"
    if layout_backend == "paddle_pp_doclayout_plus_l":
        return "PP-DocLayout_plus-L"
    return None
