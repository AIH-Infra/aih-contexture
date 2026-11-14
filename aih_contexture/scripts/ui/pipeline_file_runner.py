from __future__ import annotations

import os
import time
import traceback
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from aih_contexture.runtime.run_summary import ensure_processing_id, utc_now_iso, write_document_summary
from aih_contexture.scripts.ui.batch_inputs import materialize_pdf_batch, pdf_page_count, safe_cleanup_temp_files
from aih_contexture.scripts.ui.pipeline_batch_plan import plan_pipeline_page_ranges
from aih_contexture.scripts.ui.pipeline_job_plan import build_pipeline_batch_jobs, build_pipeline_file_job_spec
from aih_contexture.scripts.ui.pipeline_subprocess import run_pipeline_file_subprocess
from aih_contexture.scripts.ui.task_outputs import (
    get_output_basename,
    get_output_folder,
    output_paths_from_records,
    record_worker_file_outputs,
    register_document_summary,
    worker_elapsed_seconds,
    worker_error_details,
)


MessageCallback = Callable[[str], None]


def _noop_message(_: str) -> None:
    return None


def _write_terminal_summary(
    *,
    status: str,
    file_output_dir: str,
    file_name: str,
    processing_id: str,
    ctx: dict[str, Any],
    file_idx: int,
    values: Mapping[str, Any],
    started_at: str,
    started_clock: float,
    output_paths: Sequence[str] = (),
    errors: Sequence[str] = (),
    warnings: Sequence[str] = (),
) -> str | None:
    """为取消/失败的 Pipeline 文件留下可审计摘要（P1-7）。

    输出目录一旦创建就必须留下 run_summary.json，否则会在 disk 上留下
    无法解释的空目录。摘要写入失败不得掩盖原始错误，因此全部吞掉异常。
    """
    try:
        summary_path = write_document_summary(
            output_dir=file_output_dir,
            source_name=file_name,
            processing_id=processing_id,
            file_index=file_idx + 1,
            mode="pipeline",
            strategy="pipeline",
            models=dict(ctx.get("models") or {}),
            config=dict(values or {}),
            started_at=started_at,
            finished_at=utc_now_iso(),
            elapsed_seconds=time.perf_counter() - started_clock,
            status=status,
            page_count=None,
            output_paths=list(output_paths),
            warnings=list(warnings),
            errors=list(errors),
        )
    except Exception:
        return None
    try:
        register_document_summary(ctx, summary_path)
    except Exception:
        pass
    return summary_path


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
    # 早期取消发生在输出目录创建之前，不会留下空目录，因此无需摘要。
    if cancel.is_set():
        warning("⏹ 任务已取消")
        ctx["status"] = "cancelled"
        return {"status": "cancelled", "output_paths": []}

    file_started_at = utc_now_iso()
    file_started_clock = time.perf_counter()

    ctx["progress"] = file_idx / total_files if total_files else 0.0
    temp_files: list[str] = []
    file_name = "<unknown>"
    # 可能在处理早期抛错，先置空以便 except 分支安全判断是否已建目录
    file_output_dir: str | None = None
    processing_id = ensure_processing_id(ctx, output_dir)

    try:
        materialized_files, temp_files = materialize_pdf_batch([file_obj], upload_mode)
        file_path, file_name = materialized_files[0]
        write(f"### 处理文件 {file_idx + 1}/{total_files}: {file_name}")

        total_pages = pdf_page_count(file_path)
        write(f"📊 检测到 {total_pages} 页")

        if _is_text_layer_fast_path(values):
            page_ranges = _text_layer_page_range(total_pages, values)
        else:
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
        file_output_dir = get_output_folder(output_dir, file_name, file_index=file_idx)
        fname_base = get_output_basename(
            file_name if upload_mode == "上传文件" else file_path,
            values.get("start_page_1based") if use_page_range else None,
            values.get("end_page_1based") if use_page_range else None,
        )

        os.makedirs(file_output_dir, exist_ok=True)

        if cancel.is_set():
            warning("⏹ 任务已取消")
            ctx["status"] = "cancelled"
            _write_terminal_summary(
                status="cancelled", file_output_dir=file_output_dir, file_name=file_name,
                processing_id=processing_id, ctx=ctx, file_idx=file_idx, values=values,
                started_at=file_started_at, started_clock=file_started_clock,
                warnings=["任务在处理该文件前被取消"],
            )
            return {"status": "cancelled", "file_name": file_name, "output_paths": []}

        batch_jobs = build_pipeline_batch_jobs(page_ranges, values, config_builder)
        if ctx.get("status") == "cancelled":
            _write_terminal_summary(
                status="cancelled", file_output_dir=file_output_dir, file_name=file_name,
                processing_id=processing_id, ctx=ctx, file_idx=file_idx, values=values,
                started_at=file_started_at, started_clock=file_started_clock,
                warnings=["任务在后端计划阶段被取消"],
            )
            return {"status": "cancelled", "file_name": file_name, "output_paths": []}
        write(_format_backend_plan(batch_jobs))

        processing_start_time = time.time()
        job_spec = build_pipeline_file_job_spec(
            file_path=file_path,
            file_name=file_name,
            output_dir=file_output_dir,
            output_formats=output_formats,
            fname_base=fname_base,
            batch_jobs=batch_jobs,
            processing_id=processing_id,
            file_index=file_idx + 1,
        )

        write(f"🚀 启动单文件子进程: {file_name}")
        stall_timeout_seconds = max(
            180,
            int(values.get("stall_timeout_minutes", 15) or 15) * 60,
        )
        result = run_pipeline_file_subprocess(
            job_spec,
            repo_root=repo_root,
            progress_timeout=stall_timeout_seconds,
        )

        if result.get("success"):
            fallback_result_key = f"{file_name}_{time.strftime('%Y%m%d_%H%M%S')}"
            _, file_outputs = record_worker_file_outputs(ctx, result, fallback_result_key)
            output_paths = output_paths_from_records(file_outputs)
            total_elapsed = worker_elapsed_seconds(result, processing_start_time)
            backend_summary = result.get("backend_summary") or {}
            summary_path = result.get("summary_path")
            if summary_path:
                ctx.setdefault("document_summary_paths", []).append(summary_path)
            ctx.setdefault("pipeline_backend_summaries", []).append(backend_summary)
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
        if result.get("stalled"):
            warning(
                f"当前文件连续 {int(result.get('stalled_for') or 0)} 秒无进展，"
                "已终止其子进程；等待 GPU 上下文释放后继续下一文件。"
            )
            time.sleep(5)
        if details:
            error(details)
        partial_outputs = []
        if result.get("file_outputs"):
            fallback_result_key = f"{file_name}_{time.strftime('%Y%m%d_%H%M%S')}_partial"
            _, partial_outputs = record_worker_file_outputs(ctx, result, fallback_result_key)
            if partial_outputs:
                warning(f"⚠️ 已保留子进程崩溃前写出的 {len(partial_outputs)} 个部分结果。")
        _write_terminal_summary(
            status="failed", file_output_dir=file_output_dir, file_name=file_name,
            processing_id=processing_id, ctx=ctx, file_idx=file_idx, values=values,
            started_at=file_started_at, started_clock=file_started_clock,
            output_paths=output_paths_from_records(partial_outputs),
            errors=[err],
        )
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
        if file_output_dir:
            _write_terminal_summary(
                status="failed", file_output_dir=file_output_dir, file_name=file_name,
                processing_id=processing_id, ctx=ctx, file_idx=file_idx, values=values,
                started_at=file_started_at, started_clock=file_started_clock,
                errors=[str(exc)],
            )
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


def _is_text_layer_fast_path(values: Mapping[str, Any]) -> bool:
    return str(values.get("layout_backend") or "").strip().lower().replace("-", "_") == "none"


def _text_layer_page_range(total_pages: int, values: Mapping[str, Any]) -> list[tuple[int, int]]:
    """Keep one job per file so its quality assessment covers the whole source PDF."""
    if total_pages < 1:
        return []
    if not values.get("use_page_range", False):
        return [(0, total_pages)]
    start = max(1, int(values.get("start_page_1based") or 1)) - 1
    end = min(total_pages, int(values.get("end_page_1based") or total_pages))
    return [(start, max(start + 1, end))]


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
