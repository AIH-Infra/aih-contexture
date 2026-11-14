from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from aih_contexture.postprocess import MarkdownPostprocessEngine
from aih_contexture.evaluation.scholarly_markdown import evaluate_scholarly_markdown_text
from aih_contexture.middle.adapters.markdown import markdown_to_middle_document
from aih_contexture.runtime.artifacts import (
    atomic_write_text,
    compact_middle_json_for_storage,
)
from aih_contexture.runtime.run_summary import ensure_processing_id, utc_now_iso, write_document_summary
from aih_contexture.scripts.ui.task_outputs import get_output_folder, register_document_summary, record_processed_outputs
from aih_contexture.middle.adapters.mineru_official import (
    default_source_name_from_json_path,
    mineru_official_json_to_middle_document,
)
from aih_contexture.middle.debug_markdown import render_middle_debug_markdown
from aih_contexture.middle.validation import require_middle_for_publication
from aih_contexture.runtime.middle_rerender import prepare_middle_rerender
from aih_contexture.settings import settings
from aih_contexture.runtime.subprocess_stream import finish_terminal_progress, render_terminal_progress
from aih_contexture.runtime.console_text import safe_endpoint_for_log


def read_markdown_input(file_obj: Any, upload_mode: str) -> tuple[str, str]:
    if upload_mode == "上传文件" and not isinstance(file_obj, os.PathLike):
        return file_obj.name, file_obj.getvalue().decode("utf-8")

    file_name = getattr(file_obj, 'name', None) or os.path.basename(os.fspath(file_obj))
    with open(file_obj, "r", encoding="utf-8", newline="") as f:
        return file_name, f.read()


def validate_markdown_llm_result(result: Any, *, enable_llm: bool) -> dict[str, Any]:
    llm_meta = result.metadata.get("llm", {}) if isinstance(result.metadata, dict) else {}
    llm_status = llm_meta.get("status")
    skipped_reason = llm_meta.get("skipped_reason")

    if enable_llm and not llm_meta.get("invoked") and llm_status not in {"no_review_needed"}:
        raise RuntimeError(
            "LLM 修正模式未真正调用模型；需要检查 Base URL、模型名称和适配链路。"
            f" provider={llm_meta.get('provider')!r}, endpoint={safe_endpoint_for_log(llm_meta.get('base_url'))!r}, model={llm_meta.get('model')!r}, skipped_reason={skipped_reason!r}, status={llm_status!r}"
        )

    if (
        enable_llm
        and llm_meta.get("invoked")
        and skipped_reason
        and llm_meta.get("accepted_decision_count", 0) == 0
        and skipped_reason not in {"no_ambiguous_spans"}
    ):
        raise RuntimeError(
            "LLM 已调用但其结果被跳过；需要检查模型返回内容与报告。"
            f" skipped_reason={skipped_reason!r}, status={llm_status!r}"
        )

    return llm_meta


def build_markdown_postprocess_engine(
    *,
    enabled: bool,
    review_only: bool,
    enable_cleanup: bool,
    enable_printed_page_repair: bool,
    enable_llm: bool,
    llm_provider: str,
    llm_base_url: str | None,
    llm_model: str | None,
    llm_api_key: str | None,
    llm_timeout: int,
    llm_max_retries: int,
    strict_null_policy: bool = True,
) -> MarkdownPostprocessEngine:
    return MarkdownPostprocessEngine(
        {
            "markdown_postprocess_enabled": enabled,
            "markdown_postprocess_review_only": review_only,
            "markdown_postprocess_enable_cleanup": enable_cleanup,
            "markdown_postprocess_enable_printed_page_repair": enable_printed_page_repair,
            "markdown_postprocess_enable_llm": enable_llm,
            "markdown_postprocess_llm_provider": llm_provider,
            "markdown_postprocess_llm_base_url": llm_base_url,
            "markdown_postprocess_llm_model": llm_model,
            "markdown_postprocess_llm_api_key": llm_api_key,
            "markdown_postprocess_llm_timeout": llm_timeout,
            "markdown_postprocess_llm_max_retries": llm_max_retries,
            "markdown_postprocess_strict_null_policy": strict_null_policy,
        }
    )


def read_json_input(file_obj: Any, upload_mode: str) -> tuple[str, dict[str, Any]]:
    file_name, data = read_json_payload_input(file_obj, upload_mode)
    if not isinstance(data, dict):
        raise ValueError("JSON 根节点必须是对象")
    from aih_contexture.middle.adapters.pipeline_json import is_pipeline_render_json, pipeline_json_to_middle_document
    if is_pipeline_render_json(data):
        source_dir = Path(file_obj).parent if upload_mode != '上传文件' else None
        data = pipeline_json_to_middle_document(data, source_name=file_name, source_dir=source_dir)
    return file_name, data


def read_json_payload_input(file_obj: Any, upload_mode: str) -> tuple[str, Any]:
    if upload_mode == "上传文件" and not isinstance(file_obj, os.PathLike):
        file_name = file_obj.name
        raw_text = file_obj.getvalue().decode("utf-8")
    else:
        file_name = getattr(file_obj, 'name', None) or os.path.basename(os.fspath(file_obj))
        with open(file_obj, "r", encoding="utf-8") as f:
            raw_text = f.read()

    from aih_contexture.middle.storage import decode_middle_storage
    data = decode_middle_storage(json.loads(raw_text))
    return file_name, data


def process_markdown_file(
    file_obj: Any,
    *,
    upload_mode: str,
    engine: Any,
    output_dir: str | os.PathLike[str],
    review_only: bool,
    enable_llm: bool,
    emit_reading_diagnostics: bool = False,
) -> dict[str, Any]:
    file_name, markdown_text = read_markdown_input(file_obj, upload_mode)
    result = engine.process(markdown_text)
    llm_meta = validate_markdown_llm_result(result, enable_llm=enable_llm)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    fname_base = Path(file_name).stem
    report_path = output_path / f"{fname_base}.postprocess_report.json"
    if emit_reading_diagnostics:
        report_path.write_text(json.dumps(result.summary(), ensure_ascii=False, indent=2), encoding="utf-8")

    suffix = ".page_repaired.review.md" if review_only else ".page_repaired.md"
    markdown_path = output_path / f"{fname_base}{suffix}"
    output_markdown = markdown_text if review_only else result.markdown
    markdown_path.write_text(output_markdown, encoding="utf-8", newline="")

    # P1-1: Middle JSON 必须由最终落盘的 Markdown 生成，保证 Middle 与正式输出一致。
    middle_path = output_path / f"{fname_base}_middle.json"
    middle = markdown_to_middle_document(output_markdown, source_name=file_name, backend="markdown_postprocess")
    middle_path.write_text(json.dumps(middle, ensure_ascii=False, indent=2) + "\n", encoding=settings.OUTPUT_ENCODING)

    return {
        "file_name": file_name,
        "output_path": str(markdown_path),
        "report_path": str(report_path) if emit_reading_diagnostics else None,
        "output_paths": [str(markdown_path), str(middle_path)] + ([str(report_path)] if emit_reading_diagnostics else []),
        "llm_meta": llm_meta,
        "page_count": len(middle.get("pages", []) or []),
    }


def process_middle_json_file(
    file_obj: Any,
    *,
    upload_mode: str,
    output_dir: str | os.PathLike[str],
    include_provenance_comments: bool | None = None,
    include_printed_page_comments: bool | None = None,
    include_page_header_comments: bool | None = None,
    include_page_footer_comments: bool | None = None,
    include_margin_comments: bool | None = None,
    include_page_separators: bool | None = None,
    marginal_output_mode: str | None = None,
    classical_marginalia_mode: str | None = None,
    classical_text_marginalia_mode: str | None = None,
    generic_line_output_mode: str | None = None,
    equation_output_mode: str | None = None,
    engine: Any | None = None,
    apply_markdown_postprocess: bool = False,
    review_only: bool = True,
    enable_llm: bool = False,
    emit_diagnostics: bool = False,
    emit_reading_diagnostics: bool = False,
) -> dict[str, Any]:
    file_name, middle_json = read_json_input(file_obj, upload_mode)
    if upload_mode != '上传文件':
        from aih_contexture.middle.reading_structure import copy_existing_reading_resources
        copy_existing_reading_resources(middle_json, Path(file_obj).parent, output_dir)
    return _process_middle_json_payload(
        file_name=file_name,
        middle_json=middle_json,
        output_dir=output_dir,
        fname_base=f"{Path(file_name).stem}.middle_rerendered",
        include_provenance_comments=include_provenance_comments,
        include_printed_page_comments=include_printed_page_comments,
        include_page_header_comments=include_page_header_comments,
        include_page_footer_comments=include_page_footer_comments,
        include_margin_comments=include_margin_comments,
        include_page_separators=include_page_separators,
        marginal_output_mode=marginal_output_mode,
        classical_marginalia_mode=classical_marginalia_mode,
        classical_text_marginalia_mode=classical_text_marginalia_mode,
        generic_line_output_mode=generic_line_output_mode,
        equation_output_mode=equation_output_mode,
        engine=engine,
        apply_markdown_postprocess=apply_markdown_postprocess,
        review_only=review_only,
        enable_llm=enable_llm,
        emit_diagnostics=emit_diagnostics,
        emit_reading_diagnostics=emit_reading_diagnostics,
    )


def process_mineru_json_file(
    file_obj: Any,
    *,
    upload_mode: str,
    output_dir: str | os.PathLike[str],
    include_provenance_comments: bool | None = None,
    include_printed_page_comments: bool | None = None,
    include_page_header_comments: bool | None = None,
    include_page_footer_comments: bool | None = None,
    include_margin_comments: bool | None = None,
    include_page_separators: bool | None = None,
    marginal_output_mode: str | None = None,
    classical_marginalia_mode: str | None = None,
    classical_text_marginalia_mode: str | None = None,
    generic_line_output_mode: str | None = None,
    equation_output_mode: str | None = None,
    engine: Any | None = None,
    apply_markdown_postprocess: bool = False,
    review_only: bool = True,
    enable_llm: bool = False,
    emit_diagnostics: bool = False,
    emit_reading_diagnostics: bool = False,
) -> dict[str, Any]:
    file_name, mineru_payload = read_json_payload_input(file_obj, upload_mode)
    source = None if upload_mode == "上传文件" else os.fspath(file_obj)
    source_name = default_source_name_from_json_path(file_name)
    middle_json = mineru_official_json_to_middle_document(
        mineru_payload,
        source_name=source_name,
        source=source,
        file_name=file_name,
    )
    result = _process_middle_json_payload(
        file_name=file_name,
        middle_json=middle_json,
        output_dir=output_dir,
        fname_base=f"{Path(file_name).stem}.mineru_imported",
        include_provenance_comments=include_provenance_comments,
        include_printed_page_comments=include_printed_page_comments,
        include_page_header_comments=include_page_header_comments,
        include_page_footer_comments=include_page_footer_comments,
        include_margin_comments=include_margin_comments,
        include_page_separators=include_page_separators,
        marginal_output_mode=marginal_output_mode,
        classical_marginalia_mode=classical_marginalia_mode,
        classical_text_marginalia_mode=classical_text_marginalia_mode,
        generic_line_output_mode=generic_line_output_mode,
        equation_output_mode=equation_output_mode,
        engine=engine,
        apply_markdown_postprocess=apply_markdown_postprocess,
        review_only=review_only,
        enable_llm=enable_llm,
        emit_diagnostics=emit_diagnostics,
        emit_reading_diagnostics=emit_reading_diagnostics,
    )
    result["mineru_import"] = middle_json.get("metadata", {})
    return result


def _process_middle_json_payload(
    *,
    file_name: str,
    middle_json: dict[str, Any],
    output_dir: str | os.PathLike[str],
    fname_base: str,
    include_provenance_comments: bool | None = None,
    include_printed_page_comments: bool | None = None,
    include_page_header_comments: bool | None = None,
    include_page_footer_comments: bool | None = None,
    include_margin_comments: bool | None = None,
    include_page_separators: bool | None = None,
    marginal_output_mode: str | None = None,
    classical_marginalia_mode: str | None = None,
    classical_text_marginalia_mode: str | None = None,
    generic_line_output_mode: str | None = None,
    equation_output_mode: str | None = None,
    engine: Any | None = None,
    apply_markdown_postprocess: bool = False,
    review_only: bool = True,
    enable_llm: bool = False,
    emit_diagnostics: bool = False,
    emit_reading_diagnostics: bool = False,
) -> dict[str, Any]:
    if apply_markdown_postprocess and engine is None:
        raise ValueError("启用 Markdown 后处理时必须提供 engine")

    plan = prepare_middle_rerender(middle_json, {
        'emit_reading_diagnostics': emit_reading_diagnostics or emit_diagnostics,
        "include_provenance_comments": include_provenance_comments,
        "include_printed_page_comments": include_printed_page_comments,
        "include_page_header_comments": include_page_header_comments,
        "include_page_footer_comments": include_page_footer_comments,
        "include_margin_comments": include_margin_comments,
        "include_page_separators": include_page_separators,
        "marginal_output_mode": marginal_output_mode,
        "classical_marginalia_mode": classical_marginalia_mode,
        "classical_text_marginalia_mode": classical_text_marginalia_mode,
        "generic_line_output_mode": generic_line_output_mode,
        "equation_output_mode": equation_output_mode,
    })

    from aih_contexture.runtime.artifacts import _compact_resolved_middle_json_for_storage
    compact_middle_json = _compact_resolved_middle_json_for_storage(plan.document, publication_ready=True)
    require_middle_for_publication(compact_middle_json)
    validation_payload = plan.validation
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    middle_json_path = output_path / f"{fname_base}_middle.json"
    rendered_markdown = plan.markdown

    scholarly_report = None
    middle_report_path: Path | None = None
    middle_debug_path: Path | None = None
    middle_scholarly_report_path: Path | None = None
    if emit_diagnostics:
        middle_report_path = output_path / f"{fname_base}_middle_report.json"
        middle_report_path.write_text(
            json.dumps(validation_payload, ensure_ascii=False, indent=2),
            encoding=settings.OUTPUT_ENCODING,
        )

        middle_debug_path = output_path / f"{fname_base}_middle_debug.md"
        middle_debug_path.write_text(
            render_middle_debug_markdown(compact_middle_json),
            encoding=settings.OUTPUT_ENCODING,
        )

        scholarly_report = evaluate_scholarly_markdown_text(
            rendered_markdown,
            source_path=str(output_path / f"{fname_base}.md"),
            validate_classical_locators=classical_marginalia_mode == "page_locators",
        )
        middle_scholarly_report_path = output_path / f"{fname_base}_middle_scholarly_report.json"
        middle_scholarly_report_path.write_text(
            json.dumps(scholarly_report, ensure_ascii=False, indent=2),
            encoding=settings.OUTPUT_ENCODING,
        )

    markdown_text = rendered_markdown
    postprocess_report_path: Path | None = None
    llm_meta: dict[str, Any] = {}

    if apply_markdown_postprocess:
        if engine is None:
            raise ValueError("启用 Markdown 后处理时必须提供 engine")
        postprocess_result = engine.process(rendered_markdown)
        llm_meta = validate_markdown_llm_result(postprocess_result, enable_llm=enable_llm)
        if emit_reading_diagnostics or emit_diagnostics:
            plan.diagnostics['postprocess'] = postprocess_result.summary()
        markdown_text = rendered_markdown if review_only else postprocess_result.markdown

    suffix = ".page_repaired.review.md" if apply_markdown_postprocess and review_only else ".md"
    if apply_markdown_postprocess and not review_only:
        suffix = ".page_repaired.md"
    markdown_path = output_path / f"{fname_base}{suffix}"
    atomic_write_text(os.fspath(markdown_path), markdown_text, encoding="utf-8")
    from aih_contexture.middle.reading_pages import rebind_page_manifest
    manifest = rebind_page_manifest(markdown_text, plan.document.get('metadata', {}).get('reading_page_manifest'))
    if manifest is not None:
        compact_middle_json.setdefault('metadata', {})['reading_page_manifest'] = manifest
    else:
        compact_middle_json.get('metadata', {}).pop('reading_page_manifest', None)
    if apply_markdown_postprocess:
        from aih_contexture.middle.reading_pages import reading_text
        compact_middle_json.setdefault('metadata', {})['reading_postprocess'] = {
            'version': 1, 'applied': not review_only,
            'source_sha256': hashlib.sha256(reading_text(rendered_markdown).encode('utf-8')).hexdigest(),
            'output_sha256': hashlib.sha256(reading_text(markdown_text).encode('utf-8')).hexdigest(),
        }
    from aih_contexture.middle.storage import middle_json_text
    atomic_write_text(os.fspath(middle_json_path),
        middle_json_text(compact_middle_json),
        encoding=settings.OUTPUT_ENCODING)

    output_paths = [
        str(middle_json_path),
        str(markdown_path),
    ]
    diagnostic_path = None
    if emit_reading_diagnostics or emit_diagnostics:
        from aih_contexture.runtime.reading_diagnostics import write_reading_diagnostics
        diagnostic_path = write_reading_diagnostics(
            plan.diagnostics, output_path, fname_base, markdown=markdown_text,
            markdown_name=markdown_path.name)
        output_paths.append(diagnostic_path)
    for optional_path in (middle_report_path, middle_debug_path, middle_scholarly_report_path):
        if optional_path is not None:
            output_paths.append(str(optional_path))
    if postprocess_report_path is not None:
        output_paths.append(str(postprocess_report_path))

    return {
        "file_name": file_name,
        "output_path": str(markdown_path),
        "report_path": str(postprocess_report_path or middle_report_path or middle_json_path),
        "output_paths": output_paths,
        "llm_meta": llm_meta,
        "middle_validation": validation_payload,
        "scholarly_report": scholarly_report,
        "apply_markdown_postprocess": apply_markdown_postprocess,
        "warnings": plan.warnings,
        "effective_render_options": plan.options,
        "reading_diagnostics_path": diagnostic_path,
    }


def run_markdown_postprocess_batch(
    *,
    st: Any,
    uploaded_files: list[Any],
    upload_mode: str,
    output_dir: str | os.PathLike[str],
    input_kind: str,
    review_only: bool,
    enable_llm: bool,
    enable_cleanup: bool,
    enable_printed_page_repair: bool,
    llm_provider: str,
    llm_base_url: str | None,
    llm_model: str | None,
    llm_api_key: str | None,
    llm_timeout: int,
    llm_max_retries: int,
    middle_rerender_include_provenance: bool | None = None,
    middle_rerender_include_printed_page_comments: bool | None = None,
    middle_rerender_include_page_header_comments: bool | None = None,
    middle_rerender_include_page_footer_comments: bool | None = None,
    middle_rerender_include_margin_comments: bool | None = None,
    middle_rerender_include_page_separators: bool | None = None,
    middle_rerender_marginal_output_mode: str | None = None,
    middle_rerender_classical_marginalia_mode: str | None = None,
    middle_rerender_classical_text_marginalia_mode: str | None = None,
    middle_rerender_generic_line_output_mode: str | None = None,
    middle_rerender_equation_output_mode: str | None = None,
    middle_rerender_apply_postprocess: bool = False,
    cancel: Any | None = None,
    ctx: dict[str, Any] | None = None,
    emit_reading_diagnostics: bool = False,
) -> list[str]:
    if input_kind not in {"markdown", "middle_json", "mineru_json"}:
        raise ValueError(f"不支持的 Markdown 后处理输入类型：{input_kind}")
    apply_engine = input_kind == "markdown" or middle_rerender_apply_postprocess
    effective_llm = bool(enable_llm and apply_engine)
    engine = build_markdown_postprocess_engine(
        enabled=True,
        review_only=review_only,
        enable_cleanup=enable_cleanup,
        enable_printed_page_repair=enable_printed_page_repair,
        enable_llm=effective_llm,
        llm_provider=llm_provider,
        llm_base_url=llm_base_url,
        llm_model=llm_model,
        llm_api_key=llm_api_key,
        llm_timeout=llm_timeout,
        llm_max_retries=llm_max_retries,
    ) if apply_engine else None

    work_ctx = ctx if ctx is not None else {}
    processing_id = ensure_processing_id(work_ctx, output_dir)
    work_ctx["mode"] = "markdown_postprocess"
    work_ctx.setdefault("batch_started_at", utc_now_iso())
    work_ctx["models"] = {"llm": llm_model} if effective_llm and llm_model else {}
    run_config = {
        "input_kind": input_kind, "review_only": review_only, "enable_llm": effective_llm,
        "middle_rerender_classical_marginalia_mode": middle_rerender_classical_marginalia_mode,
        "middle_rerender_classical_text_marginalia_mode": middle_rerender_classical_text_marginalia_mode,
        "middle_rerender_generic_line_output_mode": middle_rerender_generic_line_output_mode,
        "middle_rerender_marginal_output_mode": middle_rerender_marginal_output_mode,
        "middle_rerender_equation_output_mode": middle_rerender_equation_output_mode,
        "middle_rerender_apply_postprocess": middle_rerender_apply_postprocess,
        'emit_reading_diagnostics': emit_reading_diagnostics,
    }
    all_output_paths_for_zip: list[str] = []
    total_files = len(uploaded_files)

    def _source_info(file_obj: Any) -> dict[str, Any]:
        """Use disk paths or the supplied legacy upload bytes for provenance."""
        if isinstance(file_obj, os.PathLike):
            return {"source_path": os.fspath(file_obj)}
        if upload_mode != "上传文件":
            try:
                return {"source_path": os.fspath(file_obj)}
            except (TypeError, ValueError):
                return {}
        getvalue = getattr(file_obj, "getvalue", None)
        if callable(getvalue):
            payload = getvalue()
            return {"source_size_bytes": len(payload), "source_sha256": hashlib.sha256(payload).hexdigest()}
        return {}

    def _write_status_summary(
        *,
        file_index: int,
        display_name: str,
        status: str,
        file_started_at: str,
        file_started_clock: float,
        output_paths: list[str],
        errors: list[str],
        warnings: list[str],
        info: dict[str, Any],
        page_count: int | None = None,
        file_output_dir: str,
    ) -> str:
        finished_at = utc_now_iso()
        summary_path = write_document_summary(
            output_dir=file_output_dir,
            source_name=display_name, processing_id=processing_id,
            file_index=file_index + 1, mode="markdown_postprocess", strategy="rerender_and_repair",
            models=work_ctx.get("models") or {},
            config=run_config,
            started_at=file_started_at, finished_at=finished_at,
            elapsed_seconds=time.perf_counter() - file_started_clock,
            status=status, page_count=page_count,
            output_paths=output_paths, warnings=warnings, errors=errors,
            **info,
        )
        register_document_summary(work_ctx, summary_path)
        return summary_path

    for file_index, file_obj in enumerate(uploaded_files):
        uploaded_name = getattr(file_obj, "name", None)
        display_name = str(uploaded_name or os.path.basename(os.fspath(file_obj)))
        file_started_clock = time.perf_counter()
        file_started_at = utc_now_iso()
        source_info = _source_info(file_obj)
        file_output_dir = get_output_folder(output_dir, display_name, file_index=file_index)

        if cancel is not None and cancel.is_set():
            # P1-7: 被取消的文件也要留下可审计的摘要，而不是静默消失。
            if ctx is not None:
                ctx["status"] = "cancelled"
            _write_status_summary(
                file_index=file_index, display_name=display_name, status="cancelled",
                file_started_at=file_started_at, file_started_clock=file_started_clock,
                output_paths=[], errors=[], warnings=["任务在处理该文件前被取消"], info=source_info,
                file_output_dir=file_output_dir,
            )
            st.warning("⏹ 任务已取消")
            finish_terminal_progress()
            return all_output_paths_for_zip

        render_terminal_progress(
            mode_label="Markdown Postprocess",
            stage="Processing",
            message=f"Processing {display_name}",
            current=file_index,
            total=total_files,
            unit="files",
            rate_scope="markdown_files",
        )

        try:
            if input_kind == "markdown":
                file_result = process_markdown_file(
                    file_obj,
                    upload_mode=upload_mode,
                    engine=engine,
                    output_dir=os.fspath(file_output_dir),
                    review_only=review_only,
                    enable_llm=enable_llm,
                    emit_reading_diagnostics=emit_reading_diagnostics,
                )
            elif input_kind == "mineru_json":
                file_result = process_mineru_json_file(
                    file_obj,
                    upload_mode=upload_mode,
                    output_dir=os.fspath(file_output_dir),
                    include_provenance_comments=middle_rerender_include_provenance,
                    include_printed_page_comments=middle_rerender_include_printed_page_comments,
                    include_page_header_comments=middle_rerender_include_page_header_comments,
                    include_page_footer_comments=middle_rerender_include_page_footer_comments,
                    include_margin_comments=middle_rerender_include_margin_comments,
                    include_page_separators=middle_rerender_include_page_separators,
                    marginal_output_mode=middle_rerender_marginal_output_mode,
                    classical_marginalia_mode=middle_rerender_classical_marginalia_mode,
                    classical_text_marginalia_mode=middle_rerender_classical_text_marginalia_mode,
                    generic_line_output_mode=middle_rerender_generic_line_output_mode,
                    equation_output_mode=middle_rerender_equation_output_mode,
                    engine=engine,
                    apply_markdown_postprocess=middle_rerender_apply_postprocess,
                    review_only=review_only,
                    enable_llm=enable_llm,
                    emit_reading_diagnostics=emit_reading_diagnostics,
                )
            else:
                file_result = process_middle_json_file(
                    file_obj,
                    upload_mode=upload_mode,
                    output_dir=os.fspath(file_output_dir),
                    include_provenance_comments=middle_rerender_include_provenance,
                    include_printed_page_comments=middle_rerender_include_printed_page_comments,
                    include_page_header_comments=middle_rerender_include_page_header_comments,
                    include_page_footer_comments=middle_rerender_include_page_footer_comments,
                    include_margin_comments=middle_rerender_include_margin_comments,
                    include_page_separators=middle_rerender_include_page_separators,
                    marginal_output_mode=middle_rerender_marginal_output_mode,
                    classical_marginalia_mode=middle_rerender_classical_marginalia_mode,
                    classical_text_marginalia_mode=middle_rerender_classical_text_marginalia_mode,
                    generic_line_output_mode=middle_rerender_generic_line_output_mode,
                    equation_output_mode=middle_rerender_equation_output_mode,
                    engine=engine,
                    apply_markdown_postprocess=middle_rerender_apply_postprocess,
                    review_only=review_only,
                    enable_llm=enable_llm,
                    emit_reading_diagnostics=emit_reading_diagnostics,
                )
        except Exception as exc:
            # P1-7: 失败路径必须留下摘要；随后继续向上抛出以保持原有错误呈现。
            _write_status_summary(
                file_index=file_index, display_name=display_name, status="failed",
                file_started_at=file_started_at, file_started_clock=file_started_clock,
                output_paths=[], errors=[f"{type(exc).__name__}: {exc}"], warnings=[], info=source_info,
                file_output_dir=file_output_dir,
            )
            raise

        all_output_paths_for_zip.extend(file_result["output_paths"])

        file_name = file_result["file_name"]
        summary_path = write_document_summary(
            output_dir=file_output_dir, source_name=file_name, processing_id=processing_id,
            file_index=file_index + 1, mode="markdown_postprocess", strategy="rerender_and_repair",
            models=work_ctx.get("models") or {}, config=run_config,
            started_at=file_started_at, finished_at=utc_now_iso(),
            elapsed_seconds=time.perf_counter() - file_started_clock,
            status="succeeded",
            page_count=file_result.get("page_count")
            or (file_result.get("middle_validation") or {}).get("summary", {}).get("page_count"),
            output_paths=file_result["output_paths"], warnings=file_result.get("warnings", []), errors=[],
            **source_info,
        )
        register_document_summary(work_ctx, summary_path)
        record_processed_outputs(work_ctx, Path(file_output_dir).name, file_result["output_paths"])
        output_path = file_result["output_path"]
        report_path = file_result["report_path"]
        llm_meta = file_result["llm_meta"]
        llm_status = llm_meta.get("status")
        skipped_reason = llm_meta.get("skipped_reason")

        if input_kind in {"middle_json", "mineru_json"}:
            validation = file_result.get("middle_validation") or {}
            validation_summary = validation.get("summary") or {}
            if input_kind == "mineru_json":
                st.success(f"✅ 已导入 MinerU 官方 JSON 并生成 Contexture Middle：{file_name}")
            else:
                st.success(f"✅ 已重渲染 Contexture Middle JSON：{file_name}")
            st.caption(
                f"Contexture Middle 校验：{'通过' if validation.get('ok') else '有问题'}；页数：{validation_summary.get('page_count', 'unknown')}"
            )
        else:
            st.success(f"✅ 已处理 Markdown：{file_name}")
        st.caption(f"输出：{os.path.basename(output_path)}")
        if report_path and report_path != output_path and emit_reading_diagnostics:
            st.caption(f"诊断：{os.path.basename(file_result.get('reading_diagnostics_path') or report_path)}")
        for warning in file_result.get("warnings", []):
            st.warning(warning)
        if effective_llm:
            st.caption(
                f"LLM 状态：{llm_status or 'unknown'}；候选动作：{llm_meta.get('accepted_decision_count', 0)}；实际写回：{llm_meta.get('applied_action_count', 0)}"
            )
            if skipped_reason:
                st.caption(f"跳过原因：{skipped_reason}")

        render_terminal_progress(
            mode_label="Markdown Postprocess",
            stage="Completed",
            message=f"Completed {file_name}",
            current=file_index + 1,
            total=total_files,
            unit="files",
            rate_scope="markdown_files",
        )

    finish_terminal_progress()
    return all_output_paths_for_zip
