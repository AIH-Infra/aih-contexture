from __future__ import annotations

import asyncio
import json
import inspect
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from aih_contexture.config.parser import ConfigParser
from aih_contexture.converters.ocr_direct_async import OcrDirectAsyncConverter
from aih_contexture.converters.vlm_direct_async import VlmDirectAsyncConverter
from aih_contexture.models import create_model_dict
from aih_contexture.middle.adapters import document_to_middle, markdown_to_middle_document
from aih_contexture.middle.adapters.mineru_official import mineru_official_json_to_middle_document
from aih_contexture.middle.semantics import resolve_middle_for_rendering
from aih_contexture.middle.scholarly_markdown import render_middle_scholarly_markdown
from aih_contexture.middle.validation import validate_middle_json
from aih_contexture.postprocess import MarkdownPostprocessEngine
from aih_contexture.output import text_from_rendered
from aih_contexture.runtime.errors import ContextureConfigError
from aih_contexture.runtime.execution import ContextureExecutionContext
from aih_contexture.runtime.job import ContextureJob, ContextureResult, SUPPORTED_RUNTIME_MODES
from aih_contexture.runtime.model_lifecycle import finish_run, prepare_for_run
from aih_contexture.runtime.vlm_middle import (
    middle_json_from_vlm_generalized_converter,
    middle_json_from_vlm_specialized_converter,
)
from aih_contexture.structured_source import StructuredSourceConverter
from aih_contexture.structured_source.renderer import render_scholarly_html


MIDDLE_ARTIFACT_KEYS = (
    "emit_middle_report",
    "emit_middle_debug",
    "emit_middle_scholarly",
    "emit_middle_scholarly_report",
    "emit_layout_overlay",
    "emit_span_overlay",
    "emit_middle_full_json",
)

MIDDLE_ARTIFACT_RENDER_KEYS = (
    "include_page_header_comments",
    "include_page_footer_comments",
    "include_margin_comments",
    "marginal_output_mode",
    "equation_output_mode",
    "footnote_enabled",
    "superscript_policy",
    "include_blockquote_markers",
    "include_printed_page_comments",
    "include_page_separators",
)

def _should_emit_middle_json(config: dict[str, Any]) -> bool:
    # Middle JSON is the canonical Contexture representation and is mandatory
    # for every successful document conversion. The legacy flag is retained
    # only for input compatibility.
    return True


def _copy_middle_debug_artifact_flags(config: dict[str, Any], result: ContextureResult) -> None:
    for key in MIDDLE_ARTIFACT_KEYS:
        if config.get(key, False):
            result.debug_artifacts[key] = True
    for key in MIDDLE_ARTIFACT_RENDER_KEYS:
        if key in config:
            result.debug_artifacts[key] = (
                config[key]
                if key in {"marginal_output_mode", "equation_output_mode", "superscript_policy"}
                else bool(config[key])
            )



def _apply_middle_contract(
    result: ContextureResult,
    middle_json: dict[str, Any],
    config: dict[str, Any],
    *,
    output_format: str,
) -> None:
    resolved = resolve_middle_for_rendering(middle_json, config)
    validation = validate_middle_json(resolved)
    result.middle_json = resolved
    result.metadata["middle_validation"] = {
        "ok": validation.ok,
        "summary": validation.summary,
        "errors": [{"path": issue.path, "message": issue.message} for issue in validation.errors],
        "warnings": [{"path": issue.path, "message": issue.message} for issue in validation.warnings],
    }
    if not validation.ok:
        details = "; ".join(f"{issue.path}: {issue.message}" for issue in validation.errors[:5])
        raise ContextureConfigError(f"Generated Middle JSON failed validation: {details}")
    if config.get("render_from_middle", False):
        if output_format != "markdown":
            raise ContextureConfigError("render_from_middle currently supports Markdown output only")
        result.markdown = render_middle_scholarly_markdown(
            resolved,
            include_provenance_comments=bool(config.get("middle_rerender_include_provenance", False)),
            include_printed_page_comments=bool(config.get("include_printed_page_comments", True)),
            include_page_header_comments=bool(config.get("include_page_header_comments", True)),
            include_page_footer_comments=bool(config.get("include_page_footer_comments", True)),
            include_margin_comments=bool(config.get("include_margin_comments", True)),
            include_page_separators=bool(config.get("include_page_separators", True)),
            marginal_output_mode=config.get("marginal_output_mode"),
            equation_output_mode=config.get("equation_output_mode", "humanities_safe"),
            footnote_enabled=bool(config.get("footnote_enabled", True)),
            superscript_policy=config.get("superscript_policy", "footnote_safe"),
        )
        result.metadata["rendered_from_middle"] = True

def _rendered_to_result(rendered: Any, output_format: str) -> ContextureResult:
    if isinstance(rendered, str):
        result = ContextureResult()
        if output_format == "html":
            result.html = rendered
        elif output_format == "json":
            result.json_text = rendered
        elif output_format == "chunks":
            result.chunks = rendered
        else:
            result.markdown = rendered
        return result

    text, _, images = text_from_rendered(rendered)
    metadata = getattr(rendered, "metadata", None) or {}
    result = ContextureResult(images=images, metadata=metadata)
    if output_format == "markdown":
        result.markdown = text
    elif output_format == "html":
        result.html = text
    elif output_format == "json":
        result.json_text = text
    elif output_format == "chunks":
        result.chunks = text
    return result


def _await_if_needed(value: Any) -> Any:
    if not inspect.isawaitable(value):
        return value
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(value)
    raise ContextureConfigError("run_job cannot synchronously await while an event loop is already running")


@contextmanager
def _materialized_input_path(job: ContextureJob):
    if job.input_path:
        yield job.input_path
        return

    if not job.input_bytes:
        raise ContextureConfigError("run_job requires input_path or input_bytes")

    suffix = Path(job.input_name or "").suffix or ".pdf"
    fd, tmp_name = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(job.input_bytes)
        yield tmp_name
    finally:
        try:
            os.remove(tmp_name)
        except OSError:
            pass


def _read_text_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _read_json_file(path: str) -> dict[str, Any]:
    payload = _read_json_payload(path)
    if not isinstance(payload, dict):
        raise ContextureConfigError("markdown_postprocess input JSON must be an object")
    return payload


def _read_json_payload(path: str) -> Any:
    return json.loads(_read_text_file(path))


def _markdown_postprocess_input_kind(job: ContextureJob, input_path: str, config: dict[str, Any]) -> str:
    kind = str(config.get("markdown_postprocess_input_kind") or "").strip().lower()
    if kind in {"markdown", "middle_json", "mineru_json"}:
        return kind
    input_name = (job.input_name or input_path or "").lower()
    if input_name.endswith(".json") or input_name.endswith(".middle.json"):
        return "middle_json"
    return "markdown"


def run_job(
    job: ContextureJob,
    artifact_dict: dict[str, Any] | None = None,
    *,
    execution_context: ContextureExecutionContext | None = None,
) -> ContextureResult:
    context = execution_context or ContextureExecutionContext()
    context.raise_if_cancelled()
    config = dict(job.config)
    if job.page_range is not None:
        config["page_range"] = job.page_range

    output_format = job.output_formats[0] if job.output_formats else "markdown"
    config.setdefault("output_format", output_format)
    if job.mode == "vlm_generalized" and context.checkpoint_dir:
        config.setdefault("vlm_direct_checkpoint_dir", context.checkpoint_dir)
        checkpoint_name = context.checkpoint_name or Path(job.input_name or job.input_path or "vlm_job").stem
        config.setdefault("vlm_direct_checkpoint_name", checkpoint_name)
    cache_policy = str(config.get("model_cache_policy") or "release_before_non_pipeline")
    if artifact_dict is not None:
        prepare_for_run(job, artifact_dict, cache_policy=cache_policy)

    try:
        context.emit({"event": "job_started", "stage": "starting", "mode": job.mode})
        with _materialized_input_path(job) as input_path:
            result = _run_materialized_job(
                job,
                input_path=input_path,
                config=config,
                output_format=output_format,
                artifact_dict=artifact_dict,
                execution_context=context,
            )
        context.emit(
            {
                "event": "job_done",
                "stage": "completed",
                "mode": job.mode,
                "page_count": result.page_count,
                "failed_pages": list(result.failed_pages),
            }
        )
        return result
    finally:
        if artifact_dict is not None:
            finish_run(job, artifact_dict, cache_policy=cache_policy)


def _run_materialized_job(
    job: ContextureJob,
    *,
    input_path: str,
    config: dict[str, Any],
    output_format: str,
    artifact_dict: dict[str, Any] | None,
    execution_context: ContextureExecutionContext,
) -> ContextureResult:
    execution_context.raise_if_cancelled()
    if job.mode == "structured_source":
        if any(format_name not in {"markdown", "json", "html", "source_package"} for format_name in job.output_formats):
            raise ContextureConfigError(
                "structured_source supports markdown, json, html, and source_package outputs only"
            )
        converter = StructuredSourceConverter(config)
        converted = converter.convert_bytes(
            Path(input_path).read_bytes(),
            job.input_name or Path(input_path).name,
        )
        result = ContextureResult(
            markdown=converted.markdown,
            html=render_scholarly_html(converted.document),
            json_text=json.dumps(converted.document, ensure_ascii=False, indent=2),
            page_count=0,
            middle_json=markdown_to_middle_document(
                converted.markdown,
                source_name=job.input_name or Path(input_path).name,
                backend="structured_source",
                page_count=1,
            ),
            structured_document=converted.document,
            metadata={
                "structured_source": {
                    "document_id": converted.document["id"],
                    "profile": converted.document["source"]["profile"],
                    "package_path": converted.package_path,
                    "statistics": {
                        key: len(converted.document[key])
                        for key in ("blocks", "structures", "navigations", "indexes", "anchors", "relations")
                    },
                }
            },
        )
        if converted.package_path:
            result.structured_artifacts["source_package"] = {
                "path": converted.package_path,
                "manifest": converted.package_manifest,
            }
        return result

    if job.mode == "pipeline":
        if str(config.get("layout_backend") or "").strip().lower().replace("-", "_") == "none":
            return _run_text_layer_pipeline(job, input_path, config, execution_context)
        options = dict(config)
        options["output_format"] = output_format
        parser = ConfigParser(options)
        config_dict = parser.generate_config_dict()
        models = artifact_dict if artifact_dict is not None else create_model_dict()
        converter_cls = parser.get_converter_cls()
        converter = converter_cls(
            config=config_dict,
            artifact_dict=models,
            processor_list=parser.get_processors(),
            renderer=parser.get_renderer(),
            llm_service=parser.get_llm_service(),
        )
        rendered = converter(input_path)
        result = _rendered_to_result(rendered, output_format)
        result.page_count = getattr(converter, "page_count", None) or 0
        if _should_emit_middle_json(config_dict):
            document = getattr(converter, "last_document", None)
            if document is None:
                raise ContextureConfigError("Pipeline did not produce mandatory Middle JSON source document")
            ocr_backend = (
                "none"
                if config_dict.get("disable_ocr", False)
                else config_dict.get("ocr_backend")
            )
            middle_json = document_to_middle(
                document,
                layout_backend=config_dict.get("layout_backend"),
                layout_model=_layout_model_from_config(config_dict),
                ocr_backend=ocr_backend,
                source_name=input_path,
            ).to_dict()
            _apply_middle_contract(result, middle_json, config_dict, output_format=output_format)
        _copy_middle_debug_artifact_flags(config_dict, result)
        return result

    if job.mode == "vlm_generalized":
        converter = VlmDirectAsyncConverter(config, progress_callback=execution_context.emit)
        rendered = _await_if_needed(converter(input_path))
        result = _rendered_to_result(rendered, output_format)
        json_pages = converter.last_json_pages or []
        if isinstance(rendered, str):
            result.markdown = rendered
        result.page_outputs = list(json_pages)
        result.html_pages = converter.last_clean_html_pages or []
        result.page_count = getattr(converter, "page_count", None) or len(json_pages)
        result.diagnostics = converter.last_json_diagnostics or []
        result.response_metadata = converter.last_response_metadata
        result.failed_pages = _failed_pages_from_diagnostics(result.diagnostics)
        checkpoint_path = converter.checkpoint_path
        if checkpoint_path:
            result.checkpoint = {
                "kind": "page_reuse",
                "path": checkpoint_path,
                "resume_enabled": bool(converter.resume_checkpoint),
                "exists": os.path.exists(checkpoint_path),
            }
        if _should_emit_middle_json(config):
            middle_json = middle_json_from_vlm_generalized_converter(
                converter,
                source_name=input_path,
                source=input_path,
            )
            if middle_json is None:
                raise ContextureConfigError("VLM generalized did not produce mandatory Middle JSON")
            _apply_middle_contract(result, middle_json, config, output_format=output_format)
        _copy_middle_debug_artifact_flags(config, result)
        return result

    if job.mode == "vlm_specialized":
        converter = OcrDirectAsyncConverter(config, progress_callback=execution_context.emit)
        rendered = _await_if_needed(converter(input_path))
        result = _rendered_to_result(rendered, output_format)
        chunks = converter.last_chunks or []
        if isinstance(rendered, str):
            result.markdown = rendered
        result.page_outputs = list(chunks)
        result.html_pages = converter.last_clean_html_pages or []
        result.page_count = getattr(converter, "page_count", None) or len(chunks)
        result.diagnostics = _specialized_diagnostics(chunks)
        result.failed_pages = _failed_pages_from_diagnostics(result.diagnostics)
        result.xml_pages = list(getattr(converter, "last_xml_pages", []) or [])
        result.searchable_pdf_path = getattr(converter, "last_searchable_pdf_path", None)
        if _should_emit_middle_json(config):
            middle_json = middle_json_from_vlm_specialized_converter(
                converter,
                source_name=input_path,
                source=input_path,
            )
            if middle_json is None:
                raise ContextureConfigError("VLM specialized did not produce mandatory Middle JSON")
            _apply_middle_contract(result, middle_json, config, output_format=output_format)
        _copy_middle_debug_artifact_flags(config, result)
        return result

    if job.mode == "markdown_postprocess":
        engine = MarkdownPostprocessEngine(config)
        input_kind = _markdown_postprocess_input_kind(job, input_path, config)
        result = ContextureResult(metadata={"markdown_postprocess": {"input_kind": input_kind}})

        if input_kind in {"middle_json", "mineru_json"}:
            if input_kind == "mineru_json":
                middle_json = mineru_official_json_to_middle_document(
                    _read_json_payload(input_path),
                    source_name=job.input_name or Path(input_path).name,
                    source=input_path,
                    file_name=job.input_name or Path(input_path).name,
                )
            else:
                middle_json = _read_json_file(input_path)
            middle_json = resolve_middle_for_rendering(middle_json, config)
            validation = validate_middle_json(middle_json)
            base_markdown = render_middle_scholarly_markdown(
                middle_json,
                include_provenance_comments=bool(config.get("middle_rerender_include_provenance", False)),
                include_printed_page_comments=bool(config.get("middle_rerender_include_printed_page_comments", True)),
                include_page_header_comments=bool(config.get("middle_rerender_include_page_header_comments", True)),
                include_page_footer_comments=bool(config.get("middle_rerender_include_page_footer_comments", True)),
                include_margin_comments=bool(config.get("middle_rerender_include_margin_comments", True)),
                include_page_separators=bool(config.get("middle_rerender_include_page_separators", True)),
                equation_output_mode=config.get("middle_rerender_equation_output_mode", config.get("equation_output_mode", "humanities_safe")),
            )
            processed = engine.process(base_markdown)
            result.markdown = processed.markdown
            result.middle_json = middle_json
            result.page_count = len(middle_json.get("pages") or [])
            result.metadata["middle_validation"] = {
                "ok": validation.ok,
                "summary": validation.summary,
                "errors": [
                    {"path": issue.path, "message": issue.message}
                    for issue in validation.errors
                ],
                "warnings": [
                    {"path": issue.path, "message": issue.message}
                    for issue in validation.warnings
                ],
            }
        else:
            processed = engine.process(_read_text_file(input_path))
            result.markdown = processed.markdown
            result.middle_json = markdown_to_middle_document(
                result.markdown,
                source_name=job.input_name or Path(input_path).name,
                backend="markdown_postprocess",
                page_count=1,
            )
            validation = validate_middle_json(result.middle_json)
            result.metadata["middle_validation"] = {
                "ok": validation.ok,
                "summary": validation.summary,
                "errors": [{"path": issue.path, "message": issue.message} for issue in validation.errors],
                "warnings": [{"path": issue.path, "message": issue.message} for issue in validation.warnings],
            }
            if not validation.ok:
                raise ContextureConfigError("Markdown postprocess did not produce valid Middle JSON")

        result.metadata["markdown_postprocess"].update(processed.summary())
        result.page_count = result.page_count or 1
        return result

    supported = ", ".join(SUPPORTED_RUNTIME_MODES)
    raise ContextureConfigError(f"Unsupported runtime mode: {job.mode}. Supported modes: {supported}")


def _run_text_layer_pipeline(
    job: ContextureJob,
    input_path: str,
    config: dict[str, Any],
    execution_context: ContextureExecutionContext,
) -> ContextureResult:
    if any(format_name != "markdown" for format_name in job.output_formats):
        raise ContextureConfigError("layout_backend='none' supports Markdown output only")

    from aih_contexture.converters.text_layer import TextLayerMarkdownConverter
    from aih_contexture.runtime.pipeline_preprocess import (
        apply_pipeline_pdf_preprocess,
        cleanup_pipeline_preprocess,
        normalize_ocr_preprocess_backend,
    )

    selected_ocr = str(config.get("ocr_backend") or "none").strip().lower().replace("-", "_")
    preprocess_backend = normalize_ocr_preprocess_backend(config.get("ocr_preprocess_backend"))
    if selected_ocr == "chrome_screenai" and preprocess_backend == "none":
        preprocess_backend = "chrome_screenai_searchable_pdf"
    if preprocess_backend == "none" and not bool(config.get("disable_ocr", False)) and selected_ocr != "none":
        raise ContextureConfigError(
            "layout_backend='none' requires disable_ocr/ocr_backend='none' or Chrome ScreenAI preprocessing"
        )
    if preprocess_backend not in {"none", "chrome_screenai_searchable_pdf"}:
        raise ContextureConfigError(
            "layout_backend='none' supports only embedded text or Chrome ScreenAI searchable-PDF preprocessing"
        )

    preprocess_result = None
    preprocess_output_dir: str | None = None
    effective_path = input_path
    try:
        if preprocess_backend != "none":
            preprocess_output_dir = tempfile.mkdtemp(prefix="aih_contexture_text_layer_")
            preprocess_config = {
                **config,
                "ocr_preprocess_backend": preprocess_backend,
                "disable_ocr": True,
            }
            preprocess_result = apply_pipeline_pdf_preprocess(
                file_path=input_path,
                output_dir=preprocess_output_dir,
                fname_base=Path(job.input_name or input_path).stem,
                config=preprocess_config,
            )
            effective_path = preprocess_result.effective_file_path

        execution_context.emit({"event": "text_layer_started", "stage": "extracting", "mode": "pipeline"})
        converter = TextLayerMarkdownConverter(config)
        markdown = converter(effective_path)
        diagnostics = converter.last_diagnostics
        recommendation = converter.last_recommendation
        warnings = []
        if recommendation.get("recommend_screenai"):
            warnings.append(
                "Embedded text quality is weak across this document; consider Chrome ScreenAI preprocessing."
            )
        execution_context.emit(
            {
                "event": "text_layer_done",
                "stage": "completed",
                "mode": "pipeline",
                "page_count": converter.page_count,
                "failed_pages": [],
            }
        )
        middle_json = markdown_to_middle_document(
            markdown,
            source_name=job.input_name or Path(input_path).name,
            backend="text_layer",
            page_count=converter.page_count,
        )
        return ContextureResult(
            markdown=markdown,
            middle_json=middle_json,
            page_count=converter.page_count,
            diagnostics=diagnostics,
            failed_pages=[],
            warnings=warnings,
            metadata={
                "text_layer": {
                    "strategy": "screenai_text" if preprocess_backend != "none" else "embedded_text",
                    "layout_backend": "none",
                    "ocr_preprocess_backend": preprocess_backend,
                    "printed_pages": converter.last_printed_pages,
                    "printed_page_summary": converter.last_printed_page_summary,
                    "recommendation": recommendation,
                }
            },
        )
    finally:
        cleanup_pipeline_preprocess(preprocess_result)
        if preprocess_output_dir:
            shutil.rmtree(preprocess_output_dir, ignore_errors=True)


def _failed_pages_from_diagnostics(diagnostics: list[dict[str, Any]]) -> list[int]:
    failed_pages: list[int] = []
    for diagnostic in diagnostics:
        if diagnostic.get("ok", True):
            continue
        page_number = diagnostic.get("page_number")
        try:
            page_number = int(page_number)
        except (TypeError, ValueError):
            continue
        if page_number > 0 and page_number not in failed_pages:
            failed_pages.append(page_number)
    return failed_pages


def _specialized_diagnostics(chunks: list[Any]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks, start=1):
        if not isinstance(chunk, dict) or not chunk.get("error"):
            continue
        error = chunk["error"]
        page_number = error.get("page", index) if isinstance(error, dict) else index
        diagnostics.append(
            {
                "page_number": page_number,
                "ok": False,
                "error_kind": "specialized_vlm_error",
                "error": error,
            }
        )
    return diagnostics


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
    return None
