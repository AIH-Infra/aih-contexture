from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime
from typing import Any, Iterable, Mapping

from aih_contexture.converters.vlm_direct_async import VlmDirectAsyncConverter
from aih_contexture.prompts.manager import PromptTemplateManager
from aih_contexture.runtime.errors import ContextureCancelledError
from aih_contexture.runtime.execution import ContextureExecutionContext
from aih_contexture.runtime.job import ContextureJob, ContextureResult
from aih_contexture.runtime.runner import run_job
from aih_contexture.runtime.run_summary import ensure_processing_id, utc_now_iso, write_document_summary
from aih_contexture.scripts.ui.batch_inputs import (
    check_file_accessible,
    input_file_objects,
    validate_single_page_batch,
)
from aih_contexture.scripts.ui.task_outputs import (
    finalize_zip_outputs,
    get_output_basename,
    get_output_folder,
    record_processed_outputs,
    register_document_summary,
)
from aih_contexture.scripts.ui.vlm_batch_runner import run_materialized_pdf_batches
from aih_contexture.scripts.ui.vlm_config import build_vlm_generalized_config
from aih_contexture.scripts.ui.vlm_output_saver import save_vlm_generalized_outputs
from aih_contexture.scripts.ui.vlm_progress import (
    finish_vlm_progress,
    make_vlm_progress_callback,
    update_vlm_batch_progress,
)


def run_vlm_generalized_batch(
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
    vlm_direct_total_concurrent: int,
    vlm_direct_max_concurrent_files: int,
    vlm_batch_rest: float,
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
) -> list[str]:
    work_ctx: dict[str, Any] = ctx if ctx is not None else {}
    processing_id = ensure_processing_id(work_ctx, output_dir)
    output_formats = list(output_formats)

    vlm_direct_config, prompt_message = build_vlm_generalized_config(
        config_values,
        output_formats=output_formats,
        template_manager=PromptTemplateManager(),
    )
    if prompt_message:
        st.info(prompt_message)

    all_output_paths_for_zip: list[str] = []
    start_time = time.time()
    batch_started_at = utc_now_iso()
    work_ctx["batch_started_at"] = batch_started_at
    work_ctx["mode"] = "vlm_generalized"
    work_ctx["config"] = vlm_direct_config
    work_ctx["models"] = {"vlm": vlm_direct_config.get("vlm_direct_model") or vlm_direct_config.get("ocr_model") or vlm_direct_config.get("ocr_backend")}
    global_semaphore = asyncio.Semaphore(max(1, int(vlm_direct_total_concurrent or 1)))

    file_objects = input_file_objects(upload_mode, uploaded_files, work_ctx)
    if upload_mode == "上传文件":
        st.write(f"✅ 已预读取 {len(file_objects)} 个文件")

    if vlm_concurrency_mode == "batch_single_page":
        invalid_files, multi_page_files = validate_single_page_batch(file_objects, upload_mode)
        if invalid_files or multi_page_files:
            st.error("单页多文件批次模式要求每个输入文件都必须是 1 页 PDF。多页 PDF 需要使用『串行文件处理（多页 PDF）』模式。")
            for file_name, page_count in multi_page_files:
                st.error(f"- {file_name}: {page_count} 页")
            for file_name, error in invalid_files:
                st.error(f"- {file_name}: 无法读取页数（{error}）")
            if ctx is not None:
                ctx["status"] = "failed"
            return []

    st.info(
        f"🚀 使用 VLM Direct 模式（{'串行文件' if vlm_concurrency_mode == 'serial_file' else '单页批次'}："
        f"{vlm_direct_max_concurrent_files}文件 × {vlm_direct_total_concurrent}页并发）"
    )
    st.write(f"📋 待处理文件：{len(file_objects)} 个")

    async def process_single_file_async(file_path: str, file_name: str, file_idx: int):
        file_started_clock = time.perf_counter()
        file_started_at = utc_now_iso()
        try:
            if not check_file_accessible(file_path):
                return {"file_idx": file_idx, "file_path": file_path, "file_name": file_name, "error": "文件被锁定（可能被PDF阅读器打开）", "started_at": file_started_at, "elapsed_seconds": time.perf_counter() - file_started_clock}

            progress_callback = make_vlm_progress_callback(
                work_ctx,
                mode="vlm_generalized",
                file_name=file_name,
                file_index=file_idx,
                total_files=len(file_objects),
            )
            base_progress_callback = progress_callback

            def progress_callback(event):
                if cancel is not None and cancel.is_set():
                    raise ContextureCancelledError("VLM job was cancelled")
                base_progress_callback(event)

            checkpoint_name = get_output_basename(
                file_name,
                vlm_start_page if vlm_use_page_range else None,
                vlm_end_page if vlm_use_page_range else None,
            )
            runtime_config = {
                **vlm_direct_config,
                "vlm_direct_checkpoint_dir": os.path.join(os.fspath(output_dir), "_vlm_checkpoints"),
                "vlm_direct_checkpoint_name": f"{checkpoint_name}_{file_idx + 1}",
                "vlm_direct_legacy_checkpoint_name": checkpoint_name,
                "vlm_direct_streaming_batches": True,
                "vlm_direct_resume_checkpoint": True,
                "vlm_direct_batch_rest": max(0.0, float(vlm_batch_rest or 0.0))
                if vlm_concurrency_mode == "serial_file"
                else 0.0,
            }
            if vlm_concurrency_mode == "serial_file":
                job = ContextureJob(
                    input_path=file_path,
                    input_name=file_name,
                    mode="vlm_generalized",
                    output_formats=output_formats,
                    page_range=runtime_config.get("page_range"),
                    config=runtime_config,
                )
                execution_context = ContextureExecutionContext(
                    progress_callback=progress_callback,
                    cancellation_check=(cancel.is_set if cancel is not None else None),
                    checkpoint_dir=runtime_config["vlm_direct_checkpoint_dir"],
                    checkpoint_name=runtime_config["vlm_direct_checkpoint_name"],
                )
                result = await asyncio.to_thread(run_job, job, execution_context=execution_context)
                return {"file_idx": file_idx, "file_path": file_path, "file_name": file_name, "markdown": result.markdown, "result": result, "started_at": file_started_at, "elapsed_seconds": time.perf_counter() - file_started_clock}

            file_converter = VlmDirectAsyncConverter(runtime_config, progress_callback=progress_callback)
            markdown = await file_converter.convert_async(file_path, global_semaphore)
            return {"file_idx": file_idx, "file_path": file_path, "file_name": file_name, "markdown": markdown, "converter": file_converter, "started_at": file_started_at, "elapsed_seconds": time.perf_counter() - file_started_clock}
        except ContextureCancelledError:
            return {"file_idx": file_idx, "file_path": file_path, "file_name": file_name, "error": "__cancelled__", "started_at": file_started_at, "elapsed_seconds": time.perf_counter() - file_started_clock}
        except Exception as e:
            return {"file_idx": file_idx, "file_path": file_path, "file_name": file_name, "error": str(e), "started_at": file_started_at, "elapsed_seconds": time.perf_counter() - file_started_clock}

    batch_size = max(1, int(vlm_direct_max_concurrent_files or 1))

    def _derive_page_count(item: dict) -> int | None:
        """P1-4: runtime result 与直接 converter 两条路径都应推导出页数。"""
        result = item.get("result")
        if result is not None:
            if getattr(result, "page_count", None):
                return int(result.page_count)
            if result.page_outputs:
                return len(result.page_outputs)
        converter = item.get("converter")
        if converter is not None:
            for attr in ("last_json_pages", "last_clean_html_pages"):
                pages = getattr(converter, attr, None)
                if pages:
                    return len(pages)
        return None

    def _write_status_summary(
        item: dict, *, status: str, file_idx: int, file_name: str,
        errors: list[str] | None = None, warnings: list[str] | None = None,
    ) -> None:
        """P1-7: 失败/取消文件也必须留下 run_summary.json。"""
        file_output_dir = get_output_folder(output_dir, file_name, file_index=file_idx)
        summary_path = write_document_summary(
            output_dir=file_output_dir, source_name=file_name, processing_id=processing_id,
            file_index=file_idx + 1, mode="vlm_generalized", strategy="vlm_generalized",
            models=work_ctx["models"], config=vlm_direct_config,
            started_at=item.get("started_at") or utc_now_iso(), finished_at=utc_now_iso(),
            elapsed_seconds=float(item.get("elapsed_seconds") or 0.0), status=status,
            page_count=None, output_paths=[],
            warnings=warnings or [], errors=errors or [],
            source_path=item.get("file_path"),
        )
        register_document_summary(work_ctx, summary_path)

    async def process_vlm_batch_and_save(batch_file_list, batch_num, batch_start):
        tasks = [
            process_single_file_async(fp, fn, batch_start + idx)
            for idx, (fp, fn) in enumerate(batch_file_list)
        ]
        batch_results = await asyncio.gather(*tasks)

        batch_saved = 0
        for item in batch_results:
            file_idx = item["file_idx"]
            file_name = item["file_name"]
            markdown = item.get("markdown")
            file_converter = item.get("converter")
            result = item.get("result")
            error = item.get("error")
            if error == "__cancelled__":
                work_ctx["status"] = "cancelled"
                _write_status_summary(item, status="cancelled", file_idx=file_idx, file_name=file_name)
                continue
            if error:
                st.error(f"❌ {file_name} 转换失败：{error}")
                _write_status_summary(item, status="failed", file_idx=file_idx, file_name=file_name, errors=[f"{type(error).__name__}: {error}"])
                continue

            batch_saved += 1
            file_output_dir = get_output_folder(output_dir, file_name, file_index=file_idx)
            fname_base = get_output_basename(
                file_name,
                vlm_start_page if vlm_use_page_range else None,
                vlm_end_page if vlm_use_page_range else None,
            )
            file_warnings = list(result.warnings) if result is not None else []
            def _warn(message):
                if message not in file_warnings:
                    file_warnings.append(message)
                st.warning(message)

            output_files = save_vlm_generalized_outputs(
                converter=file_converter,
                result=result,
                markdown_text=markdown,
                output_dir=os.fspath(file_output_dir),
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
                warn=_warn,
            )

            work_ctx.setdefault("warnings", []).extend(
                message for message in file_warnings if message not in work_ctx.get("warnings", [])
            )

            all_output_paths_for_zip.extend(output_files)
            record_processed_outputs(work_ctx, file_name, output_files)
            summary_path = write_document_summary(
                output_dir=file_output_dir, source_name=file_name, processing_id=processing_id,
                file_index=file_idx + 1, mode="vlm_generalized", strategy="vlm_generalized",
                models=work_ctx["models"], config=vlm_direct_config,
                started_at=item["started_at"], finished_at=utc_now_iso(),
                elapsed_seconds=float(item["elapsed_seconds"]), status="succeeded",
                page_count=_derive_page_count(item),
                output_paths=output_files, warnings=file_warnings, errors=[],
                source_path=item.get("file_path"),
            )
            register_document_summary(work_ctx, summary_path)
            st.write(f"  💾 {file_name} 已保存")

        return {"saved": batch_saved, "cancelled": work_ctx.get("status") == "cancelled"}

    def on_vlm_batch_start(batch_num, total_batches, batch_len, batch_start):
        update_vlm_batch_progress(
            work_ctx,
            mode="vlm_generalized",
            stage="处理中",
            batch_num=batch_num,
            total_batches=total_batches,
            total_files=len(file_objects),
            message=f"批次 {batch_num}/{total_batches}，{batch_len} 个文件",
        )
        st.write(f"📦 处理批次 {batch_num}/{total_batches}（{batch_len} 个文件）")

    def on_vlm_batch_done(batch_num, batch_saved):
        saved_count = int(batch_saved.get("saved", 0)) if isinstance(batch_saved, dict) else int(batch_saved or 0)
        update_vlm_batch_progress(
            work_ctx,
            mode="vlm_generalized",
            stage="保存结果",
            batch_num=batch_num,
            total_files=len(file_objects),
            message=f"批次 {batch_num} 已保存 {saved_count} 个文件",
        )
        st.write(f"✅ 批次 {batch_num} 完成，已保存 {saved_count} 个文件")

    def on_vlm_batch_rest(rest_seconds):
        update_vlm_batch_progress(
            work_ctx,
            mode="vlm_generalized",
            stage="批次休息",
            total_files=len(file_objects),
            message=f"等待 {rest_seconds} 秒后继续下一批",
        )
        st.write(f"💤 休息 {rest_seconds} 秒...")

    batch_run_result = asyncio.run(
        run_materialized_pdf_batches(
            file_objects=file_objects,
            batch_size=batch_size,
            upload_mode=upload_mode,
            process_batch=process_vlm_batch_and_save,
            cancel=cancel,
            ctx=work_ctx,
            batch_rest=vlm_batch_rest if vlm_concurrency_mode == "batch_single_page" else 0.0,
            on_batch_start=on_vlm_batch_start,
            on_batch_done=on_vlm_batch_done,
            on_rest=on_vlm_batch_rest,
            should_stop=lambda result: bool(isinstance(result, dict) and result.get("cancelled")),
        )
    )
    if (
        batch_run_result.get("cancelled")
        or (
            batch_run_result.get("stopped")
            and isinstance(batch_run_result.get("result"), dict)
            and batch_run_result["result"].get("cancelled")
        )
        or work_ctx.get("status") == "cancelled"
        or (cancel is not None and cancel.is_set())
    ):
        work_ctx["status"] = "cancelled"
        finish_vlm_progress(
            work_ctx,
            mode="vlm_generalized",
            stage="已取消",
            message="任务已取消",
        )
        st.warning("⏹ 任务已取消")
        return []

    if all_output_paths_for_zip:
        elapsed_time = time.time() - start_time
        finish_vlm_progress(
            work_ctx,
            mode="vlm_generalized",
            stage="完成",
            message=f"全部完成，总耗时 {elapsed_time:.1f} 秒",
        )
        st.success(f"🎉 所有文件处理完成！总耗时：{elapsed_time:.1f} 秒")
        from aih_contexture.runtime.output_contract import zip_name
        finalize_zip_outputs(
            work_ctx, all_output_paths_for_zip, output_dir,
            zip_name(mode="vlm_generalized", vlm_model=work_ctx["models"]["vlm"], processing_id=processing_id),
            mode="vlm_generalized", models=work_ctx["models"], config=vlm_direct_config,
            started_at=batch_started_at, status="succeeded",
        )
        work_ctx["status"] = "done"
    else:
        finish_vlm_progress(
            work_ctx,
            mode="vlm_generalized",
            stage="失败",
            message="未生成可保存的结果",
        )
        work_ctx["status"] = "failed"

    return all_output_paths_for_zip
