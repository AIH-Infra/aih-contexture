"""Keep document completion separate from work inside each active batch."""
from __future__ import annotations

import time


STAGE_NAMES = {
    "starting": "准备", "model_loading": "加载模型", "preprocess": "预处理",
    "batch": "准备批次", "document": "构建页面", "layout": "版面分析",
    "line_detection": "构建文字行", "ocr": "文字识别", "extracting": "提取文字",
    "postprocess": "内容处理", "processing": "内容处理", "render": "生成结果",
    "saving": "保存结果", "completed": "完成", "failed": "失败", "cancelled": "已停止",
}


def update_pipeline_progress(ctx, event):
    ctx["pipeline_progress"] = dict(event)
    file_index = event.get("file_index")
    files = dict(ctx.get("pipeline_file_states", {}))
    state = files.get(file_index) if file_index is not None else ctx.get("pipeline_progress_state")
    if state is None or event.get("kind") == "file_started":
        state = {"completed_batches": {}, "active_batches": {}, "total": 0}
    else:
        state = {**state, "completed_batches": dict(state["completed_batches"]),
                 "active_batches": dict(state["active_batches"])}
    state["file_name"] = event.get("file_name", state.get("file_name", ""))
    state["total"] = int(event.get("document_total_pages") or state["total"])
    if event.get("absolute_progress") and event.get("unit") == "pages":
        state["total"] = int(event.get("total") or state["total"])
    state["total_batches"] = int(event.get("total_batches") or state.get("total_batches", 0))
    index = int(event.get("batch_index") or 0)
    kind, stage = event.get("kind"), event.get("stage")
    if kind in {"batch_processed", "batch_completed"}:
        state["completed_batches"][index] = int(event.get("batch_page_count") or event.get("total") or 0)
        state["active_batches"].pop(index, None)
    elif kind in {"file_completed", "file_failed", "file_cancelled"}:
        if kind == "file_completed":
            state["completed"] = state["total"]
        state["active_batches"] = {}
    elif index not in state["completed_batches"]:
        if index:
            state["active_batches"].pop(0, None)
        previous = state["active_batches"].get(index, {})
        # The coordinator's batch events describe output order. Actual worker
        # stages describe the work in flight and take priority in the UI.
        if stage != "batch" or not previous:
            state["active_batches"][index] = {
                **event,
                "stage_started_at": previous["stage_started_at"]
                if previous.get("stage") == stage else time.monotonic(),
            }
    state["event"] = dict(event)
    ctx["pipeline_progress_state"] = state
    if file_index is not None:
        files[file_index] = state
        ctx["pipeline_file_states"] = files


def render_pipeline_progress(st, ctx):
    files = ctx.get("pipeline_file_states")
    if files:
        active = [state for _, state in sorted(files.items())
                  if state["event"].get("kind") not in {"file_completed", "file_failed", "file_cancelled"}]
        for state in active or [ctx["pipeline_progress_state"]]:
            _render_file_progress(st, ctx, state)
        return
    state = ctx.get("pipeline_progress_state")
    if not state:
        return
    _render_file_progress(st, ctx, state)


def _render_file_progress(st, ctx, state):
    st.write(state["file_name"])
    total = state["total"]
    completed = min(total, state.get("completed", sum(state["completed_batches"].values())))
    if total > 0:
        st.progress(completed / total, text=f"本文件已处理 {completed} / {total} 页")
    event = state["event"]
    if event.get("stage") in {"saving", "completed", "failed", "cancelled"}:
        st.caption(STAGE_NAMES[event["stage"]])
        return
    for index, active in sorted(state["active_batches"].items()):
        if index == 0 and len(state["active_batches"]) > 1:
            continue
        parts = []
        if index and state["total_batches"] > 1:
            parts.append(f"批次 {index}/{state['total_batches']}")
        parts.append(STAGE_NAMES.get(active.get("stage"), active.get("stage", "处理中")))
        current, count = int(active.get("current") or 0), int(active.get("total") or 0)
        if count > 0 and current > 0 and active.get("stage") != "batch":
            unit = "页" if active.get("unit") == "pages" else "项"
            parts.append(f"{current}/{count} {unit}")
        if ctx["status"] == "running":
            elapsed = max(0, int(time.monotonic() - active["stage_started_at"]))
            parts.append(f"已用 {elapsed} 秒")
        st.caption(" · ".join(parts))

