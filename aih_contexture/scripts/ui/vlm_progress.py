from __future__ import annotations

from collections.abc import Callable, MutableMapping
from typing import Any


MODE_LABELS = {
    "vlm_generalized": "VLM 泛化",
    "vlm_specialized": "VLM 特化",
}


def initial_vlm_progress(mode: str, total_files: int = 0) -> dict[str, Any]:
    return {
        "mode": mode,
        "mode_label": MODE_LABELS.get(mode, "VLM"),
        "stage": "准备中",
        "total_pages": 0,
        "done_pages": 0,
        "success_pages": 0,
        "failed_pages": 0,
        "current_file": "",
        "current_page": None,
        "file_index": 0,
        "total_files": int(total_files or 0),
        "batch_num": 0,
        "total_batches": 0,
        "message": "",
        "_files": {},
    }


def ensure_vlm_progress(
    ctx: MutableMapping[str, Any],
    *,
    mode: str,
    total_files: int = 0,
) -> dict[str, Any]:
    progress = ctx.get("vlm_progress")
    if not isinstance(progress, dict):
        progress = initial_vlm_progress(mode, total_files)
        ctx["vlm_progress"] = progress
    else:
        progress.setdefault("mode", mode)
        progress.setdefault("mode_label", MODE_LABELS.get(mode, "VLM"))
        progress["total_files"] = max(int(progress.get("total_files") or 0), int(total_files or 0))
        progress.setdefault("_files", {})
    return progress


def _set_ratio(ctx: MutableMapping[str, Any], progress: MutableMapping[str, Any]) -> None:
    total = int(progress.get("total_pages") or 0)
    done = int(progress.get("done_pages") or 0)
    ctx["progress"] = min(1.0, max(0.0, done / total)) if total > 0 else 0.0


def make_vlm_progress_callback(
    ctx: MutableMapping[str, Any],
    *,
    mode: str,
    file_name: str,
    file_index: int,
    total_files: int,
) -> Callable[[dict[str, Any]], None]:
    file_key = f"{file_index}:{file_name}"
    loaded_pages: int | None = None
    seen_pages: set[int] = set()

    def callback(event: dict[str, Any]) -> None:
        nonlocal loaded_pages
        progress = ensure_vlm_progress(ctx, mode=mode, total_files=total_files)
        files = progress.setdefault("_files", {})
        file_state = files.setdefault(
            file_key,
            {
                "name": file_name,
                "index": int(file_index),
                "total_pages": 0,
                "done_pages": 0,
            },
        )

        event_name = str(event.get("event") or "")
        progress["current_file"] = file_name
        progress["file_index"] = int(file_index)
        progress["total_files"] = int(total_files or 0)

        if event_name == "pages_discovered":
            total_pages = int(event.get("total_pages") or 0)
            if loaded_pages is None:
                loaded_pages = total_pages
                progress["total_pages"] = int(progress.get("total_pages") or 0) + total_pages
                file_state["total_pages"] = total_pages
            progress["stage"] = "预处理"
            progress["message"] = f"{file_name} · 共 {total_pages} 页，正在分批渲染"

        elif event_name == "render_batch":
            start_page = int(event.get("start_page") or 0)
            end_page = int(event.get("end_page") or 0)
            progress["stage"] = "预处理"
            progress["message"] = f"{file_name} · 正在渲染第 {start_page}-{end_page} 页"

        elif event_name == "repair_start":
            failed_pages = event.get("failed_pages") or []
            total_pages = len(failed_pages)
            seen_pages.clear()
            loaded_pages = total_pages
            progress["total_pages"] = total_pages
            progress["done_pages"] = 0
            progress["success_pages"] = 0
            progress["failed_pages"] = 0
            progress["current_page"] = None
            file_state["total_pages"] = total_pages
            file_state["done_pages"] = 0
            progress["stage"] = "修复中"
            progress["message"] = f"{file_name} · 正在补跑 {total_pages} 个失败页"

        elif event_name == "repair_batch":
            pages = event.get("pages") or []
            pages_text = ", ".join(str(page) for page in pages[:10])
            if len(pages) > 10:
                pages_text += "..."
            progress["stage"] = "渲染修复页"
            progress["message"] = f"{file_name} · 正在渲染失败页：{pages_text}"

        elif event_name == "pages_loaded":
            total_pages = int(event.get("total_pages") or 0)
            if loaded_pages is None:
                loaded_pages = total_pages
                progress["total_pages"] = int(progress.get("total_pages") or 0) + total_pages
                file_state["total_pages"] = total_pages
            progress["stage"] = "处理中"
            progress["message"] = f"已载入 {file_name}"

        elif event_name == "page_done":
            page_num = int(event.get("page_num") or 0)
            if page_num not in seen_pages:
                seen_pages.add(page_num)
                progress["done_pages"] = int(progress.get("done_pages") or 0) + 1
                file_state["done_pages"] = int(file_state.get("done_pages") or 0) + 1
                if bool(event.get("ok", True)):
                    progress["success_pages"] = int(progress.get("success_pages") or 0) + 1
                else:
                    progress["failed_pages"] = int(progress.get("failed_pages") or 0) + 1
            progress["stage"] = "修复中" if str(event.get("stage") or "") == "repairing" else "处理中"
            progress["current_page"] = page_num
            progress["message"] = f"{file_name} · 第 {page_num} 页"

        elif event_name == "repair_done":
            remaining = event.get("remaining_failed_pages") or []
            if remaining:
                progress["stage"] = "修复重试待继续"
                progress["message"] = f"{file_name} · 仍有 {len(remaining)} 页待修复"
            else:
                progress["stage"] = "整理输出"
                progress["message"] = f"{file_name} · 失败页已补跑完成，正在整理输出"

        elif event_name == "postprocess":
            progress["stage"] = "整理输出"
            progress["message"] = f"{file_name} 正在整理结果"

        elif event_name == "file_done":
            progress["stage"] = "保存结果"
            progress["message"] = f"{file_name} 已完成，正在保存"

        else:
            stage = event.get("stage")
            if stage:
                progress["stage"] = str(stage)

        _set_ratio(ctx, progress)

    return callback


def update_vlm_batch_progress(
    ctx: MutableMapping[str, Any],
    *,
    mode: str,
    stage: str,
    batch_num: int | None = None,
    total_batches: int | None = None,
    total_files: int = 0,
    message: str = "",
) -> None:
    progress = ensure_vlm_progress(ctx, mode=mode, total_files=total_files)
    progress["stage"] = stage
    if batch_num is not None:
        progress["batch_num"] = int(batch_num)
    if total_batches is not None:
        progress["total_batches"] = int(total_batches)
    if message:
        progress["message"] = message
    _set_ratio(ctx, progress)


def finish_vlm_progress(
    ctx: MutableMapping[str, Any],
    *,
    mode: str,
    stage: str,
    message: str = "",
) -> None:
    progress = ensure_vlm_progress(ctx, mode=mode)
    progress["stage"] = stage
    if message:
        progress["message"] = message
    if stage == "完成" and int(progress.get("total_pages") or 0) > 0:
        ctx["progress"] = 1.0
    else:
        _set_ratio(ctx, progress)


def render_vlm_progress(st: Any, ctx: MutableMapping[str, Any]) -> None:
    progress = ctx.get("vlm_progress")
    if not isinstance(progress, dict):
        return

    total = int(progress.get("total_pages") or 0)
    done = int(progress.get("done_pages") or 0)
    ratio = min(1.0, max(0.0, done / total)) if total else 0.0

    st.markdown(f"**{progress.get('mode_label', 'VLM')}处理进度**")
    st.progress(ratio)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("阶段", progress.get("stage") or "准备中")
    col2.metric("页面", f"{done}/{total}" if total else "准备中")
    col3.metric("成功", int(progress.get("success_pages") or 0))
    col4.metric("失败", int(progress.get("failed_pages") or 0))

    batch_num = int(progress.get("batch_num") or 0)
    total_batches = int(progress.get("total_batches") or 0)
    file_index = int(progress.get("file_index") or 0)
    total_files = int(progress.get("total_files") or 0)
    current_file = progress.get("current_file") or "等待文件"
    current_page = progress.get("current_page")

    pieces = []
    if total_batches:
        pieces.append(f"批次 {batch_num}/{total_batches}")
    if total_files:
        pieces.append(f"文件 {file_index + 1}/{total_files}")
    pieces.append(str(current_file))
    if current_page:
        pieces.append(f"第 {current_page} 页")

    message = progress.get("message")
    caption = " · ".join(pieces)
    if message:
        caption = f"{caption}｜{message}"
    st.caption(caption)
