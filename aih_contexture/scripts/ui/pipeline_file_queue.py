"""Schedule short files across warm workers, and long files across page batches."""
from __future__ import annotations

import io
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from aih_contexture.runtime.pipeline_parallelism import plan_from_values
from aih_contexture.runtime.run_summary import ensure_processing_id
from aih_contexture.scripts.ui.batch_inputs import pdf_page_count
from aih_contexture.scripts.ui.pipeline_batch_plan import target_page_ranges
from aih_contexture.scripts.ui.pipeline_file_process import PipelineFileProcess
from aih_contexture.scripts.ui import pipeline_file_runner
from aih_contexture.scripts.ui.pipeline_progress import update_pipeline_progress


def short_file_workers(values, page_counts, *, probe=None):
    # Resource estimates describe the largest whole file, not the sum of the
    # queue. A tiny individual file must not cap concurrency for the whole queue.
    plan = plan_from_values({**values, "pages_per_batch": max(page_counts)}, probe=probe)
    workers = min(plan.workers, len(page_counts))
    if plan.mode == "auto":
        workers = min(workers, max(1, sum(page_counts) // 25))
    size = int(values.get("pages_per_batch") or 100)
    return replace(plan, workers=workers, pages_per_batch=size, batch_threshold=size)


def run_pipeline_file_queue(files, *, ctx, cancel, values, on_result, **kwargs):
    """Call on_result once for each started file; stop scheduling on cancellation.

    Callbacks that touch the shared UI context run only on this coordinator
    thread. Worker threads hold private contexts and only enqueue messages.
    """
    files = list(files)
    ensure_processing_id(ctx, kwargs["output_dir"])
    size = int(values.get("pages_per_batch") or 100)
    prepared = []
    for index, file_obj in enumerate(files):
        if cancel.is_set():
            break
        source = file_obj[0]
        try:
            count = pdf_page_count(io.BytesIO(source) if isinstance(source, bytes) else source)
        except Exception:
            # The normal file runner records the original input error and its
            # diagnostic. It is not eligible for the warm-worker path.
            count = None
        ranges = target_page_ranges(
            total_pages=count or 0, use_page_range=bool(values.get("use_page_range")),
            start_page_1based=values.get("start_page_1based"), end_page_1based=values.get("end_page_1based"),
        )
        selected = sum(max(0, end - start) for start, end in ranges)
        short = count is not None and 0 < selected <= size
        prepared.append((index, file_obj, count, selected, short))

    messages = queue.Queue()
    completed = 0
    message_callbacks = {name: kwargs.pop(name, lambda _: None) for name in ("write", "info", "warning", "error")}

    def process(item, client=None, plan=None):
        index, file_obj, count, _, _ = item
        file_ctx = {"status": "running", "processing_id": ctx["processing_id"]}
        def progress(event):
            messages.put(("progress", {**event, "file_index": index,
                                      "file_name": event.get("file_name") or file_obj[1]}))
        result = pipeline_file_runner.run_pipeline_file(
            file_obj, file_idx=index, total_files=len(files), ctx=file_ctx,
            cancel=cancel, values=values, progress_callback=progress, total_pages=count,
            subprocess_runner=client.run if client else None, execution_plan=plan,
            **{name: (lambda text, name=name: messages.put((name, text))) for name in message_callbacks}, **kwargs,
        )
        result["file_index"] = index
        result["_file_context"] = file_ctx
        messages.put(("result", result))

    def dispatch(kind, payload):
        nonlocal completed
        if kind == "progress":
            update_pipeline_progress(ctx, payload)
        elif kind == "result":
            index = payload["file_index"]
            file_ctx = payload.pop("_file_context")
            records = ctx.setdefault("processed_files", {})
            for key, outputs in file_ctx.get("processed_files", {}).items():
                records[key if key not in records else f"{key}_{index}"] = outputs
            summaries = ctx.setdefault("document_summary_paths", [])
            for path in file_ctx.get("document_summary_paths", []):
                if path not in summaries:
                    summaries.append(path)
            terminal = {"success": "completed", "failed": "failed", "cancelled": "cancelled"}[payload["status"]]
            update_pipeline_progress(ctx, {
                **ctx.get("pipeline_file_states", {}).get(index, {}).get("event", {}),
                "kind": f"file_{terminal}", "stage": terminal,
                "file_index": index, "file_name": payload.get("file_name", ""),
            })
            if payload["status"] != "cancelled":
                completed += 1
            ctx["progress"] = completed / len(files)
            on_result(payload)
        else:
            message_callbacks[kind](payload)

    def drain():
        while not messages.empty():
            dispatch(*messages.get_nowait())

    cursor = 0
    while cursor < len(prepared) and not cancel.is_set():
        end = cursor + 1
        if prepared[cursor][-1]:
            while end < len(prepared) and prepared[end][-1]:
                end += 1
        group = prepared[cursor:end]
        if len(group) < 2:
            # Run even a long/invalid input in a thread so its progress can be
            # relayed while it is running, using the same coordinator path.
            plan = None
            worker_count = 1
        else:
            plan = short_file_workers(values, [item[3] for item in group])
            worker_count = plan.workers
            message_callbacks["info"](f"短文件队列：{worker_count} 个常驻进程，每个进程一次处理一份文件。")
            for note in plan.notes:
                message_callbacks["warning"](note)
            plan = replace(plan, workers=1, notes=[])

        pending = iter(group)
        pending_lock = threading.Lock()
        def work():
            client = PipelineFileProcess(kwargs["repo_root"]) if plan is not None else None
            try:
                while not cancel.is_set():
                    with pending_lock:
                        item = next(pending, None)
                    if item is None:
                        break
                    process(item, client, plan)
            finally:
                if client is not None:
                    client.close()

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(work) for _ in range(worker_count)]
            while not all(future.done() for future in futures):
                try:
                    dispatch(*messages.get(timeout=0.1))
                except queue.Empty:
                    pass
            drain()
            for future in futures:
                future.result()
        cursor = end
    if cancel.is_set():
        ctx["status"] = "cancelled"
