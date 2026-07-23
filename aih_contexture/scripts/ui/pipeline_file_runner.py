from __future__ import annotations

import os
import time
import traceback
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from aih_contexture.scripts.ui.batch_inputs import materialize_pdf_batch, pdf_page_count, safe_cleanup_temp_files
from aih_contexture.scripts.ui.pipeline_batch_plan import plan_pipeline_page_ranges
from aih_contexture.scripts.ui.pipeline_job_plan import build_pipeline_batch_jobs, build_pipeline_file_job_spec
from aih_contexture.scripts.ui.pipeline_subprocess import run_pipeline_file_subprocess
from aih_contexture.scripts.ui.task_outputs import (
    get_output_basename,
    output_paths_from_records,
    record_worker_file_outputs,
    worker_elapsed_seconds,
    worker_error_details,
)


MessageCallback = Callable[[str], None]


def _noop_message(_: str) -> None:
    return None


def run_pipeline_file(
    file_obj: object,
    *,
    file_idx: int,
    total_files: int,
    upload_mode: str,
    ctx: dict[str, Any],
    cancel: Any,
    values: Mapping[str, Any],
    output_dir: str,
    output_formats: Sequence[str],
    repo_root: str,
    config_builder: Callable[[dict[str, Any]], dict[str, Any]],
    write: MessageCallback = _noop_message,
    info: MessageCallback = _noop_message,
    warning: MessageCallback = _noop_message,
    error: MessageCallback = _noop_message,
) -> dict[str, Any]:
    if cancel.is_set():
        warning("⏹ 任务已取消")
        ctx["status"] = "cancelled"
        return {"status": "cancelled", "output_paths": []}

    ctx["progress"] = file_idx / total_files if total_files else 0.0
    temp_files: list[str] = []
    file_name = "<unknown>"

    try:
        materialized_files, temp_files = materialize_pdf_batch([file_obj], upload_mode)
        file_path, file_name = materialized_files[0]
        write(f"### 处理文件 {file_idx + 1}/{total_files}: {file_name}")

        total_pages = pdf_page_count(file_path)
        write(f"📊 检测到 {total_pages} 页")

        effective_pages_per_batch = _effective_pages_per_batch(values)
        page_ranges = plan_pipeline_page_ranges(
            total_pages=total_pages,
            process_mode=values.get("process_mode", "自动"),
            batch_threshold=int(values.get("batch_threshold", 50)),
            pages_per_batch=effective_pages_per_batch,
            use_page_range=bool(values.get("use_page_range", False)),
            start_page_1based=values.get("start_page_1based"),
            end_page_1based=values.get("end_page_1based"),
        )

        use_page_range = bool(values.get("use_page_range", False))
        fname_base = get_output_basename(
            file_name if upload_mode == "上传文件" else file_path,
            values.get("start_page_1based") if use_page_range else None,
            values.get("end_page_1based") if use_page_range else None,
        )

        os.makedirs(output_dir, exist_ok=True)

        if cancel.is_set():
            warning("⏹ 任务已取消")
            ctx["status"] = "cancelled"
            return {"status": "cancelled", "file_name": file_name, "output_paths": []}

        batch_jobs = build_pipeline_batch_jobs(page_ranges, values, config_builder)
        if ctx.get("status") == "cancelled":
            return {"status": "cancelled", "file_name": file_name, "output_paths": []}
        write(_format_backend_plan(batch_jobs))

        processing_start_time = time.time()
        job_spec = build_pipeline_file_job_spec(
            file_path=file_path,
            file_name=file_name,
            output_dir=output_dir,
            output_formats=output_formats,
            fname_base=fname_base,
            batch_jobs=batch_jobs,
        )

        write(f"🚀 启动单文件子进程: {file_name}")
        result = run_pipeline_file_subprocess(job_spec, repo_root=repo_root)

        if result.get("success"):
            fallback_result_key = f"{file_name}_{time.strftime('%Y%m%d_%H%M%S')}"
            _, file_outputs = record_worker_file_outputs(ctx, result, fallback_result_key)
            output_paths = output_paths_from_records(file_outputs)
            total_elapsed = worker_elapsed_seconds(result, processing_start_time)
            backend_summary = result.get("backend_summary") or {}
            if backend_summary:
                info(_format_backend_summary(backend_summary))
            info(f"⏱️ 处理耗时: {total_elapsed:.2f}秒")
            write(f"✅ 《{file_name}》处理完成")
            return {
                "status": "success",
                "file_name": file_name,
                "output_paths": output_paths,
                "result": result,
            }

        err, details = worker_error_details(result)
        error(f"处理《{file_name}》失败: {err}")
        if details:
            error(details)
        partial_outputs = []
        if result.get("file_outputs"):
            fallback_result_key = f"{file_name}_{time.strftime('%Y%m%d_%H%M%S')}_partial"
            _, partial_outputs = record_worker_file_outputs(ctx, result, fallback_result_key)
            if partial_outputs:
                warning(f"⚠️ 已保留子进程崩溃前写出的 {len(partial_outputs)} 个部分结果。")
        return {
            "status": "failed",
            "file_name": file_name,
            "output_paths": output_paths_from_records(partial_outputs),
            "error": err,
            "details": details,
            "result": result,
        }

    except Exception as exc:
        error(f"处理《{file_name}》失败: {str(exc)}")
        details = traceback.format_exc()
        error(details)
        return {
            "status": "failed",
            "file_name": file_name,
            "output_paths": [],
            "error": str(exc),
            "details": details,
        }

    finally:
        safe_cleanup_temp_files(temp_files, max_retries=1, delay=0)


def _format_backend_plan(batch_jobs: Sequence[dict[str, Any]]) -> str:
    summary = _backend_summary_from_batch_jobs(batch_jobs)
    return "🧭 本次实际后端计划: " + _format_backend_summary_payload(summary)


def _effective_pages_per_batch(values: Mapping[str, Any]) -> int:
    pages_per_batch = max(1, int(values.get("pages_per_batch", 25)))
    layout_backend = str(values.get("layout_backend") or "").strip().lower().replace("-", "_")
    if layout_backend != "surya2_layout":
        return pages_per_batch
    layout_concurrency = int(
        values.get("surya2_layout_batch_size")
        or values.get("surya2_layout_concurrency")
        or values.get("surya2_request_concurrency")
        or 1
    )
    return max(pages_per_batch, max(1, layout_concurrency))


def _format_backend_summary(summary: Mapping[str, Any]) -> str:
    return "🧭 子进程实际后端: " + _format_backend_summary_payload(summary)


def _format_backend_summary_payload(summary: Mapping[str, Any]) -> str:
    preprocess = _join_values(summary.get("ocr_preprocess_backends"))
    layout = _join_values(summary.get("layout_backends")) or "unknown"
    layout_model = _join_values(summary.get("layout_models")) or "default"
    ocr = _join_values(summary.get("ocr_backends")) or "unknown"
    disable_ocr = _join_values(summary.get("disable_ocr"))
    prefix = f"ocr_preprocess={preprocess}; " if preprocess else ""
    if disable_ocr:
        return f"{prefix}layout={layout}; layout_model={layout_model}; ocr={ocr}; disable_ocr={disable_ocr}"
    return f"{prefix}layout={layout}; layout_model={layout_model}; ocr={ocr}"


def _backend_summary_from_batch_jobs(batch_jobs: Sequence[dict[str, Any]]) -> dict[str, list[Any]]:
    preprocess_backends: list[Any] = []
    layout_backends: list[Any] = []
    layout_models: list[Any] = []
    ocr_backends: list[Any] = []
    disable_ocr_values: list[Any] = []
    for batch_job in batch_jobs:
        config = batch_job.get("config_dict", {}) or {}
        preprocess = _normalize_ocr_preprocess_backend(config.get("ocr_preprocess_backend"))
        if preprocess != "none":
            _append_unique(preprocess_backends, preprocess)
        _append_unique(layout_backends, config.get("layout_backend"))
        _append_unique(layout_models, _layout_model_from_config(config))
        effective_disable_ocr = bool(config.get("disable_ocr", False)) or preprocess != "none"
        requested_ocr = config.get("ocr_backend")
        if effective_disable_ocr and requested_ocr == "chrome_screenai" and preprocess != "none":
            _append_unique(ocr_backends, "chrome_screenai")
        else:
            _append_unique(ocr_backends, "none" if effective_disable_ocr else requested_ocr)
        _append_unique(disable_ocr_values, effective_disable_ocr)
    return {
        "ocr_preprocess_backends": preprocess_backends,
        "layout_backends": layout_backends,
        "layout_models": layout_models,
        "ocr_backends": ocr_backends,
        "disable_ocr": disable_ocr_values,
    }


def _layout_model_from_config(config: Mapping[str, Any]) -> str | None:
    if config.get("external_layout_model"):
        return str(config["external_layout_model"])
    if config.get("paddle_layout_model_name"):
        return str(config["paddle_layout_model_name"])
    layout_backend = str(config.get("layout_backend") or "").strip().lower()
    if layout_backend == "mineru_vl_layout":
        return str(config.get("mineru_vl_model") or "MinerU-VL")
    if layout_backend == "surya2_layout":
        return str(config.get("surya2_model") or "Surya 2")
    if layout_backend == "paddle_pp_doclayout_v3":
        return "PP-DocLayoutV3"
    if layout_backend == "paddle_pp_doclayout_plus_l":
        return "PP-DocLayout_plus-L"
    return None


def _append_unique(items: list[Any], value: Any) -> None:
    if value is None or value == "":
        return
    if value not in items:
        items.append(value)


def _normalize_ocr_preprocess_backend(value: Any) -> str:
    normalized = str(value or "none").strip().lower().replace("-", "_")
    if normalized == "chrome_screenai":
        return "chrome_screenai_searchable_pdf"
    if normalized in {"", "none"}:
        return "none"
    return normalized


def _join_values(values: Any) -> str:
    if not values:
        return ""
    if not isinstance(values, (list, tuple)):
        values = [values]
    return ",".join(str(value) for value in values)
