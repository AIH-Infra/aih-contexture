from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime
from typing import Any, Iterable, Mapping

from aih_contexture.converters.ocr_direct_async import OcrDirectAsyncConverter
from aih_contexture.scripts.ui.batch_inputs import (
    check_file_accessible,
    input_file_objects,
)
from aih_contexture.scripts.ui.task_outputs import (
    finalize_zip_outputs,
    get_output_basename,
    record_processed_outputs,
)
from aih_contexture.scripts.ui.vlm_batch_runner import run_materialized_pdf_batches
from aih_contexture.scripts.ui.vlm_config import build_vlm_specialized_config
from aih_contexture.scripts.ui.vlm_output_saver import save_vlm_specialized_outputs
from aih_contexture.scripts.ui.vlm_progress import (
    finish_vlm_progress,
    make_vlm_progress_callback,
    update_vlm_batch_progress,
)


def run_vlm_specialized_batch(
    *,
    st: Any,
    uploaded_files: list[Any],
    upload_mode: str,
    output_dir: str | os.PathLike[str],
    config_values: Mapping[str, Any],
    output_formats: Iterable[str],
    vlm_use_page_range: bool,
    vlm_start_page: int | None,
    vlm_end_page: int | None,
    vlm_concurrency_mode: str,
    ocr_total_concurrent: int,
    ocr_max_concurrent_files: int,
    ocr_batch_rest: float,
    emit_middle_json: bool,
    emit_middle_report: bool,
    emit_middle_debug: bool,
    emit_middle_scholarly: bool,
    emit_middle_scholarly_report: bool,
    emit_layout_overlay: bool,
    emit_span_overlay: bool,
    emit_middle_full_json: bool = False,
    cancel: Any | None = None,
    ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    work_ctx: dict[str, Any] = ctx if ctx is not None else {}
    output_formats = list(output_formats)

    ocr_direct_config = build_vlm_specialized_config(
        config_values,
        output_formats=output_formats,
    )

    all_output_paths_for_zip: list[str] = []
    start_time = time.time()
    global_semaphore = asyncio.Semaphore(max(1, int(ocr_total_concurrent or 1)))
    batch_size = max(1, int(ocr_max_concurrent_files or 1))

    file_objects = input_file_objects(upload_mode, uploaded_files, work_ctx)
    mode_label = "单本书页内并行" if vlm_concurrency_mode in {"page_parallel", "serial_file"} else "多本书整本并行"
    st.info(
        f"📚 使用 OCR Direct 模式（{mode_label}："
        f"{ocr_max_concurrent_files}文件 × {ocr_total_concurrent}并发槽）"
    )
    if ocr_direct_config.get("ocr_backend") == "mineru_vl":
        st.caption(
            "MinerU-VL 并发："
            f"页面并发={ocr_direct_config.get('ocr_concurrency')}，"
            f"API 请求并发={ocr_direct_config.get('mineru_vl_request_concurrency')}，"
            f"块调度上限={ocr_direct_config.get('mineru_vl_block_concurrency')}"
        )
    elif ocr_direct_config.get("ocr_backend") == "paddleocr_vl":
        st.caption(
            "PaddleOCR-VL 并发："
            f"页面并发={ocr_direct_config.get('ocr_concurrency')}，"
            f"API 请求并发={ocr_direct_config.get('paddleocr_vl_request_concurrency')}"
        )
    st.write(f"📋 待处理文件：{len(file_objects)} 个")

    resume_from_batch = 0
    if work_ctx.get("ocr_paused") and work_ctx.get("ocr_pause_info"):
        resume_from_batch = work_ctx.get("ocr_resume_batch_start", 0)
        if work_ctx["ocr_pause_info"].get("all_output_paths_for_zip"):
            all_output_paths_for_zip = work_ctx["ocr_pause_info"]["all_output_paths_for_zip"]
        st.info(f"🔄 从批次 {resume_from_batch // max(1, ocr_max_concurrent_files) + 1} 恢复处理...")
        work_ctx["ocr_paused"] = False
        work_ctx["ocr_pause_info"] = None

    from aih_contexture.services.ocr_chandra import ModelCrashError

    async def process_single_file(file_path: str, file_name: str, file_idx: int):
        try:
            if not check_file_accessible(file_path):
                return (file_idx, file_name, None, None, "文件被锁定（可能被PDF阅读器打开）", False)

            progress_callback = make_vlm_progress_callback(
                work_ctx,
                mode="vlm_specialized",
                file_name=file_name,
                file_index=file_idx,
                total_files=len(file_objects),
            )
            file_converter = OcrDirectAsyncConverter(
                ocr_direct_config,
                progress_callback=progress_callback,
            )
            markdown = await file_converter(file_path, global_semaphore)
            return (file_idx, file_name, markdown, file_converter, None, False)
        except ModelCrashError as e:
            return (file_idx, file_name, None, None, str(e), True)
        except Exception as e:
            return (file_idx, file_name, None, None, str(e), False)

    async def process_batch_and_save(batch_file_list, batch_num, batch_start):
        tasks = [
            process_single_file(fp, fn, batch_start + idx)
            for idx, (fp, fn) in enumerate(batch_file_list)
        ]
        batch_results = await asyncio.gather(*tasks)

        model_crashed = False
        crash_error = None
        saved_count = 0
        for file_idx, file_name, markdown, file_converter, error, is_crash in batch_results:
            if is_crash:
                model_crashed = True
                crash_error = error
                st.error(f"🚨 {file_name} 模型崩溃：{error}")
                continue
            if error:
                st.error(f"❌ {file_name} 转换失败：{error}")
                continue

            saved_count += 1
            fname_base = get_output_basename(
                file_name,
                vlm_start_page if vlm_use_page_range else None,
                vlm_end_page if vlm_use_page_range else None,
            )
            output_files = save_vlm_specialized_outputs(
                converter=file_converter,
                markdown_text=markdown,
                output_dir=os.fspath(output_dir),
                fname_base=fname_base,
                file_name=file_name,
                output_formats=output_formats,
                emit_middle_json=emit_middle_json,
                emit_middle_report=emit_middle_report,
                emit_middle_debug=emit_middle_debug,
                emit_middle_scholarly=emit_middle_scholarly,
                emit_middle_scholarly_report=emit_middle_scholarly_report,
                emit_layout_overlay=emit_layout_overlay,
                emit_span_overlay=emit_span_overlay,
                emit_middle_full_json=emit_middle_full_json,
            )

            all_output_paths_for_zip.extend(output_files)
            record_processed_outputs(
                work_ctx,
                f"{fname_base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                output_files,
            )
            st.write(f"  💾 {file_name} 已保存")

        return saved_count, model_crashed, crash_error

    def on_ocr_batch_start(batch_num, total_batches, batch_len, batch_start):
        update_vlm_batch_progress(
            work_ctx,
            mode="vlm_specialized",
            stage="处理中",
            batch_num=batch_num,
            total_batches=total_batches,
            total_files=len(file_objects),
            message=f"批次 {batch_num}/{total_batches}，{batch_len} 个文件",
        )
        st.write(f"📦 处理批次 {batch_num}/{total_batches}（{batch_len} 个文件）")

    def on_ocr_batch_done(batch_num, result):
        saved_count, _, _ = result
        update_vlm_batch_progress(
            work_ctx,
            mode="vlm_specialized",
            stage="保存结果",
            batch_num=batch_num,
            total_files=len(file_objects),
            message=f"批次 {batch_num} 已保存 {saved_count} 个文件",
        )
        st.write(f"✅ 批次 {batch_num} 完成，已保存 {saved_count} 个文件")

    def on_ocr_batch_rest(rest_seconds):
        update_vlm_batch_progress(
            work_ctx,
            mode="vlm_specialized",
            stage="批次休息",
            total_files=len(file_objects),
            message=f"等待 {rest_seconds} 秒后继续下一批",
        )
        st.write(f"💤 休息 {rest_seconds} 秒...")

    def ocr_batch_should_stop(result):
        _, model_crashed, _ = result
        return bool(model_crashed)

    batch_run_result = asyncio.run(
        run_materialized_pdf_batches(
            file_objects=file_objects,
            batch_size=batch_size,
            upload_mode=upload_mode,
            process_batch=process_batch_and_save,
            cancel=cancel,
            ctx=work_ctx,
            resume_from=resume_from_batch,
            batch_rest=ocr_batch_rest,
            on_batch_start=on_ocr_batch_start,
            on_batch_done=on_ocr_batch_done,
            on_rest=on_ocr_batch_rest,
            should_stop=ocr_batch_should_stop,
        )
    )
    if batch_run_result.get("cancelled"):
        work_ctx["status"] = "cancelled"
        finish_vlm_progress(
            work_ctx,
            mode="vlm_specialized",
            stage="已取消",
            message="任务已取消",
        )
        st.warning("⏹ 任务已取消")
        return {"crashed": False, "cancelled": True}

    if batch_run_result.get("stopped"):
        _, _, crash_error = batch_run_result["result"]
        batch_result = {
            "crashed": True,
            "batch_start": batch_run_result["batch_start"],
            "batch_num": batch_run_result["batch_num"],
            "error": crash_error,
        }
    else:
        batch_result = {"crashed": False}

    if batch_result.get("crashed", False):
        work_ctx["ocr_paused"] = True
        work_ctx["ocr_pause_info"] = {
            "batch_start": batch_result["batch_start"],
            "batch_num": batch_result["batch_num"],
            "error": batch_result["error"],
            "file_objects": file_objects,
            "all_output_paths_for_zip": all_output_paths_for_zip,
            "start_time": start_time,
        }
        work_ctx["ocr_resume_batch_start"] = batch_result["batch_start"]
        work_ctx["status"] = "error"

        st.error(f"⚠️ 模型崩溃检测！批次 {batch_result['batch_num']} 处理失败")
        st.warning(batch_result["error"])
        st.info("📋 已处理的文件已保存到磁盘，不会丢失")
        finish_vlm_progress(
            work_ctx,
            mode="vlm_specialized",
            stage="暂停/失败",
            message=f"批次 {batch_result['batch_num']} 失败，已保留已完成结果",
        )
        return {"crashed": True, "paused": True}

    if all_output_paths_for_zip:
        elapsed_time = time.time() - start_time
        finish_vlm_progress(
            work_ctx,
            mode="vlm_specialized",
            stage="完成",
            message=f"全部完成，总耗时 {elapsed_time:.1f} 秒",
        )
        st.success(f"🎉 所有文件处理完成！总耗时：{elapsed_time:.1f} 秒")
        finalize_zip_outputs(work_ctx, all_output_paths_for_zip, output_dir, "ocr_direct_results.zip")
        work_ctx["status"] = "done"
    else:
        finish_vlm_progress(
            work_ctx,
            mode="vlm_specialized",
            stage="失败",
            message="未生成可保存的结果",
        )
        work_ctx["status"] = "failed"

    return {"crashed": False, "paused": False}
