from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from aih_contexture.postprocess import MarkdownPostprocessEngine
from aih_contexture.evaluation.scholarly_markdown import evaluate_scholarly_markdown_text
from aih_contexture.runtime.artifacts import compact_middle_json_for_storage
from aih_contexture.middle.adapters.mineru_official import (
    default_source_name_from_json_path,
    mineru_official_json_to_middle_document,
)
from aih_contexture.middle.debug_markdown import render_middle_debug_markdown
from aih_contexture.middle.scholarly_markdown import render_middle_scholarly_markdown
from aih_contexture.middle.validation import validate_middle_json
from aih_contexture.settings import settings


def read_markdown_input(file_obj: Any, upload_mode: str) -> tuple[str, str]:
    if upload_mode == "上传文件":
        return file_obj.name, file_obj.getvalue().decode("utf-8")

    file_name = os.path.basename(os.fspath(file_obj))
    with open(file_obj, "r", encoding="utf-8", newline="") as f:
        return file_name, f.read()


def validate_markdown_llm_result(result: Any, *, enable_llm: bool) -> dict[str, Any]:
    llm_meta = result.metadata.get("llm", {}) if isinstance(result.metadata, dict) else {}
    llm_status = llm_meta.get("status")
    skipped_reason = llm_meta.get("skipped_reason")

    if enable_llm and not llm_meta.get("invoked") and llm_status not in {"no_review_needed"}:
        raise RuntimeError(
            "LLM 修正模式未真正调用模型；需要检查 Base URL、模型名称和适配链路。"
            f" provider={llm_meta.get('provider')!r}, base_url={llm_meta.get('base_url')!r}, model={llm_meta.get('model')!r}, skipped_reason={skipped_reason!r}, status={llm_status!r}"
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
    return file_name, data


def read_json_payload_input(file_obj: Any, upload_mode: str) -> tuple[str, Any]:
    if upload_mode == "上传文件":
        file_name = file_obj.name
        raw_text = file_obj.getvalue().decode("utf-8")
    else:
        file_name = os.path.basename(os.fspath(file_obj))
        with open(file_obj, "r", encoding="utf-8") as f:
            raw_text = f.read()

    data = json.loads(raw_text)
    return file_name, data


def process_markdown_file(
    file_obj: Any,
    *,
    upload_mode: str,
    engine: Any,
    output_dir: str | os.PathLike[str],
    review_only: bool,
    enable_llm: bool,
) -> dict[str, Any]:
    file_name, markdown_text = read_markdown_input(file_obj, upload_mode)
    result = engine.process(markdown_text)
    llm_meta = validate_markdown_llm_result(result, enable_llm=enable_llm)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    fname_base = Path(file_name).stem
    report_path = output_path / f"{fname_base}.postprocess_report.json"
    report_path.write_text(json.dumps(result.summary(), ensure_ascii=False, indent=2), encoding="utf-8")

    suffix = ".page_repaired.review.md" if review_only else ".page_repaired.md"
    markdown_path = output_path / f"{fname_base}{suffix}"
    output_markdown = markdown_text if review_only else result.markdown
    markdown_path.write_text(output_markdown, encoding="utf-8", newline="")

    return {
        "file_name": file_name,
        "output_path": str(markdown_path),
        "report_path": str(report_path),
        "output_paths": [str(report_path), str(markdown_path)],
        "llm_meta": llm_meta,
    }


def process_middle_json_file(
    file_obj: Any,
    *,
    upload_mode: str,
    output_dir: str | os.PathLike[str],
    include_provenance_comments: bool = False,
    include_printed_page_comments: bool = True,
    include_page_header_comments: bool = True,
    include_page_footer_comments: bool = True,
    include_margin_comments: bool = True,
    include_page_separators: bool = True,
    marginal_output_mode: str | None = None,
    equation_output_mode: str = "humanities_safe",
    engine: Any | None = None,
    apply_markdown_postprocess: bool = False,
    review_only: bool = True,
    enable_llm: bool = False,
    emit_diagnostics: bool = False,
) -> dict[str, Any]:
    file_name, middle_json = read_json_input(file_obj, upload_mode)
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
        equation_output_mode=equation_output_mode,
        engine=engine,
        apply_markdown_postprocess=apply_markdown_postprocess,
        review_only=review_only,
        enable_llm=enable_llm,
        emit_diagnostics=emit_diagnostics,
    )


def process_mineru_json_file(
    file_obj: Any,
    *,
    upload_mode: str,
    output_dir: str | os.PathLike[str],
    include_provenance_comments: bool = False,
    include_printed_page_comments: bool = True,
    include_page_header_comments: bool = True,
    include_page_footer_comments: bool = True,
    include_margin_comments: bool = True,
    include_page_separators: bool = True,
    marginal_output_mode: str | None = None,
    equation_output_mode: str = "humanities_safe",
    engine: Any | None = None,
    apply_markdown_postprocess: bool = False,
    review_only: bool = True,
    enable_llm: bool = False,
    emit_diagnostics: bool = False,
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
        equation_output_mode=equation_output_mode,
        engine=engine,
        apply_markdown_postprocess=apply_markdown_postprocess,
        review_only=review_only,
        enable_llm=enable_llm,
        emit_diagnostics=emit_diagnostics,
    )
    result["mineru_import"] = middle_json.get("metadata", {})
    return result


def _process_middle_json_payload(
    *,
    file_name: str,
    middle_json: dict[str, Any],
    output_dir: str | os.PathLike[str],
    fname_base: str,
    include_provenance_comments: bool = False,
    include_printed_page_comments: bool = True,
    include_page_header_comments: bool = True,
    include_page_footer_comments: bool = True,
    include_margin_comments: bool = True,
    include_page_separators: bool = True,
    marginal_output_mode: str | None = None,
    equation_output_mode: str = "humanities_safe",
    engine: Any | None = None,
    apply_markdown_postprocess: bool = False,
    review_only: bool = True,
    enable_llm: bool = False,
    emit_diagnostics: bool = False,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    validation = validate_middle_json(middle_json)
    compact_middle_json = compact_middle_json_for_storage(middle_json)
    validation_payload = {
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

    middle_json_path = output_path / f"{fname_base}_middle.json"
    middle_json_path.write_text(
        json.dumps(compact_middle_json, ensure_ascii=False, separators=(",", ":")),
        encoding=settings.OUTPUT_ENCODING,
    )

    rendered_markdown = render_middle_scholarly_markdown(
        compact_middle_json,
        include_provenance_comments=include_provenance_comments,
        include_printed_page_comments=include_printed_page_comments,
        include_page_header_comments=include_page_header_comments,
        include_page_footer_comments=include_page_footer_comments,
        include_margin_comments=include_margin_comments,
        include_page_separators=include_page_separators,
        marginal_output_mode=marginal_output_mode,
        equation_output_mode=equation_output_mode,
    )

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
        postprocess_report_path = output_path / f"{fname_base}.postprocess_report.json"
        postprocess_report_path.write_text(
            json.dumps(postprocess_result.summary(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        markdown_text = rendered_markdown if review_only else postprocess_result.markdown

    suffix = ".page_repaired.review.md" if apply_markdown_postprocess and review_only else ".md"
    if apply_markdown_postprocess and not review_only:
        suffix = ".page_repaired.md"
    markdown_path = output_path / f"{fname_base}{suffix}"
    markdown_path.write_text(markdown_text, encoding="utf-8", newline="")

    output_paths = [
        str(middle_json_path),
        str(markdown_path),
    ]
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
    middle_rerender_include_provenance: bool = False,
    middle_rerender_include_printed_page_comments: bool = True,
    middle_rerender_include_page_header_comments: bool = True,
    middle_rerender_include_page_footer_comments: bool = True,
    middle_rerender_include_margin_comments: bool = True,
    middle_rerender_include_page_separators: bool = True,
    middle_rerender_marginal_output_mode: str | None = None,
    middle_rerender_equation_output_mode: str = "humanities_safe",
    middle_rerender_apply_postprocess: bool = False,
    cancel: Any | None = None,
    ctx: dict[str, Any] | None = None,
) -> list[str]:
    engine = build_markdown_postprocess_engine(
        enabled=True,
        review_only=review_only,
        enable_cleanup=enable_cleanup,
        enable_printed_page_repair=enable_printed_page_repair,
        enable_llm=enable_llm,
        llm_provider=llm_provider,
        llm_base_url=llm_base_url,
        llm_model=llm_model,
        llm_api_key=llm_api_key,
        llm_timeout=llm_timeout,
        llm_max_retries=llm_max_retries,
    )

    all_output_paths_for_zip: list[str] = []
    for file_obj in uploaded_files:
        if cancel is not None and cancel.is_set():
            if ctx is not None:
                ctx["status"] = "cancelled"
            st.warning("⏹ 任务已取消")
            return all_output_paths_for_zip

        if input_kind == "markdown":
            file_result = process_markdown_file(
                file_obj,
                upload_mode=upload_mode,
                engine=engine,
                output_dir=output_dir,
                review_only=review_only,
                enable_llm=enable_llm,
            )
        elif input_kind == "mineru_json":
            file_result = process_mineru_json_file(
                file_obj,
                upload_mode=upload_mode,
                output_dir=output_dir,
                include_provenance_comments=middle_rerender_include_provenance,
                include_printed_page_comments=middle_rerender_include_printed_page_comments,
                include_page_header_comments=middle_rerender_include_page_header_comments,
                include_page_footer_comments=middle_rerender_include_page_footer_comments,
                include_margin_comments=middle_rerender_include_margin_comments,
                include_page_separators=middle_rerender_include_page_separators,
                marginal_output_mode=middle_rerender_marginal_output_mode,
                equation_output_mode=middle_rerender_equation_output_mode,
                engine=engine,
                apply_markdown_postprocess=middle_rerender_apply_postprocess,
                review_only=review_only,
                enable_llm=enable_llm,
            )
        else:
            file_result = process_middle_json_file(
                file_obj,
                upload_mode=upload_mode,
                output_dir=output_dir,
                include_provenance_comments=middle_rerender_include_provenance,
                include_printed_page_comments=middle_rerender_include_printed_page_comments,
                include_page_header_comments=middle_rerender_include_page_header_comments,
                include_page_footer_comments=middle_rerender_include_page_footer_comments,
                include_margin_comments=middle_rerender_include_margin_comments,
                include_page_separators=middle_rerender_include_page_separators,
                marginal_output_mode=middle_rerender_marginal_output_mode,
                equation_output_mode=middle_rerender_equation_output_mode,
                engine=engine,
                apply_markdown_postprocess=middle_rerender_apply_postprocess,
                review_only=review_only,
                enable_llm=enable_llm,
            )

        all_output_paths_for_zip.extend(file_result["output_paths"])

        file_name = file_result["file_name"]
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
        st.caption(f"报告：{os.path.basename(report_path)}")
        if enable_llm:
            st.caption(
                f"LLM 状态：{llm_status or 'unknown'}；候选动作：{llm_meta.get('accepted_decision_count', 0)}；实际写回：{llm_meta.get('applied_action_count', 0)}"
            )
            if skipped_reason:
                st.caption(f"跳过原因：{skipped_reason}")

    return all_output_paths_for_zip
