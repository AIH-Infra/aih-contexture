from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime
from typing import Any, Iterable, Mapping

from aih_contexture.converters.vlm_direct_async import VlmDirectAsyncConverter
from aih_contexture.prompts.manager import PromptTemplateManager
from aih_contexture.scripts.ui.batch_inputs import (
    check_file_accessible,
    input_file_objects,
    validate_single_page_batch,
)
from aih_contexture.scripts.ui.task_outputs import (
    finalize_zip_outputs,
    get_output_basename,
    record_processed_outputs,
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
        try:
            if not check_file_accessible(file_path):
                return (file_idx, file_name, None, None, "文件被锁定（可能被PDF阅读器打开）")

            progress_callback = make_vlm_progress_callback(
                work_ctx,
                mode="vlm_generalized",
                file_name=file_name,
                file_index=file_idx,
                total_files=len(file_objects),
            )
            file_converter = VlmDirectAsyncConverter(
                {
                    **vlm_direct_config,
                    "vlm_direct_checkpoint_dir": os.path.join(os.fspath(output_dir), "_vlm_checkpoints"),
                    "vlm_direct_checkpoint_name": get_output_basename(
                        file_name,
                        vlm_start_page if vlm_use_page_range else None,
                        vlm_end_page if vlm_use_page_range else None,
                    ),
                    "vlm_direct_streaming_batches": True,
                    "vlm_direct_resume_checkpoint": True,
                },
                progress_callback=progress_callback,
            )
            markdown = await file_converter.convert_async(file_path, global_semaphore)
            return (file_idx, file_name, markdown, file_converter, None)
        except Exception as e:
            return (file_idx, file_name, None, None, str(e))

    batch_size = max(1, int(vlm_direct_max_concurrent_files or 1))

    async def process_vlm_batch_and_save(batch_file_list, batch_num, batch_start):
        tasks = [
            process_single_file_async(fp, fn, batch_start + idx)
            for idx, (fp, fn) in enumerate(batch_file_list)
        ]
        batch_results = await asyncio.gather(*tasks)

        batch_saved = 0
        for file_idx, file_name, markdown, file_converter, error in batch_results:
            if error:
                st.error(f"❌ {file_name} 转换失败：{error}")
                continue

            batch_saved += 1
            fname_base = get_output_basename(
                file_name,
                vlm_start_page if vlm_use_page_range else None,
                vlm_end_page if vlm_use_page_range else None,
            )
            output_files = save_vlm_generalized_outputs(
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
                warn=st.warning,
            )

            all_output_paths_for_zip.extend(output_files)
            record_processed_outputs(
                work_ctx,
                f"{fname_base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                output_files,
            )
            st.write(f"  💾 {file_name} 已保存")

        return batch_saved

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
        update_vlm_batch_progress(
            work_ctx,
            mode="vlm_generalized",
            stage="保存结果",
            batch_num=batch_num,
            total_files=len(file_objects),
            message=f"批次 {batch_num} 已保存 {batch_saved} 个文件",
        )
        st.write(f"✅ 批次 {batch_num} 完成，已保存 {batch_saved} 个文件")

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
            batch_rest=vlm_batch_rest,
            on_batch_start=on_vlm_batch_start,
            on_batch_done=on_vlm_batch_done,
            on_rest=on_vlm_batch_rest,
        )
    )
    if batch_run_result.get("cancelled"):
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
        finalize_zip_outputs(work_ctx, all_output_paths_for_zip, output_dir, "vlm_direct_results.zip")
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
