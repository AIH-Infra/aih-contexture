from __future__ import annotations

import asyncio
import json
import inspect
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from aih_contexture.config.parser import ConfigParser
from aih_contexture.converters.ocr_direct_async import OcrDirectAsyncConverter
from aih_contexture.converters.vlm_direct_async import VlmDirectAsyncConverter
from aih_contexture.models import create_model_dict
from aih_contexture.middle.adapters import document_to_middle
from aih_contexture.middle.adapters.mineru_official import mineru_official_json_to_middle_document
from aih_contexture.middle.semantics import resolve_middle_for_rendering
from aih_contexture.middle.scholarly_markdown import render_middle_scholarly_markdown
from aih_contexture.middle.validation import validate_middle_json
from aih_contexture.postprocess import MarkdownPostprocessEngine
from aih_contexture.output import text_from_rendered
from aih_contexture.runtime.errors import ContextureConfigError
from aih_contexture.runtime.job import ContextureJob, ContextureResult
from aih_contexture.runtime.model_lifecycle import finish_run, prepare_for_run
from aih_contexture.runtime.vlm_middle import (
    middle_json_from_vlm_generalized_converter,
    middle_json_from_vlm_specialized_converter,
)


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
)

SUPPORTED_RUNTIME_MODES = (
    "pipeline",
    "vlm_generalized",
    "vlm_specialized",
    "markdown_postprocess",
)


def _should_emit_middle_json(config: dict[str, Any]) -> bool:
    return bool(config.get("emit_middle_json", False) or any(config.get(key, False) for key in MIDDLE_ARTIFACT_KEYS))


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


def run_job(job: ContextureJob, artifact_dict: dict[str, Any] | None = None) -> ContextureResult:
    config = dict(job.config)
    if job.page_range is not None:
        config["page_range"] = job.page_range

    output_format = job.output_formats[0] if job.output_formats else "markdown"
    config.setdefault("output_format", output_format)
    cache_policy = str(config.get("model_cache_policy") or "release_before_non_pipeline")
    if artifact_dict is not None:
        prepare_for_run(job, artifact_dict, cache_policy=cache_policy)

    try:
        with _materialized_input_path(job) as input_path:
            return _run_materialized_job(
                job,
                input_path=input_path,
                config=config,
                output_format=output_format,
                artifact_dict=artifact_dict,
            )
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
) -> ContextureResult:
    if job.mode == "pipeline":
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
            if document is not None:
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
                result.middle_json = resolve_middle_for_rendering(middle_json, config_dict)
        _copy_middle_debug_artifact_flags(config_dict, result)
        return result

    if job.mode == "vlm_generalized":
        converter = VlmDirectAsyncConverter(config)
        rendered = _await_if_needed(converter(input_path))
        result = _rendered_to_result(rendered, output_format)
        result.page_count = getattr(converter, "page_count", None) or 0
        if _should_emit_middle_json(config):
            middle_json = middle_json_from_vlm_generalized_converter(
                converter,
                source_name=input_path,
                source=input_path,
            )
            if middle_json is not None:
                result.middle_json = resolve_middle_for_rendering(middle_json, config)
        _copy_middle_debug_artifact_flags(config, result)
        return result

    if job.mode == "vlm_specialized":
        converter = OcrDirectAsyncConverter(config)
        rendered = _await_if_needed(converter(input_path))
        result = _rendered_to_result(rendered, output_format)
        result.page_count = getattr(converter, "page_count", None) or 0
        if _should_emit_middle_json(config):
            middle_json = middle_json_from_vlm_specialized_converter(
                converter,
                source_name=input_path,
                source=input_path,
            )
            if middle_json is not None:
                result.middle_json = resolve_middle_for_rendering(middle_json, config)
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

        result.metadata["markdown_postprocess"].update(processed.summary())
        result.page_count = result.page_count or 1
        return result

    supported = ", ".join(SUPPORTED_RUNTIME_MODES)
    raise ContextureConfigError(f"Unsupported runtime mode: {job.mode}. Supported modes: {supported}")


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
