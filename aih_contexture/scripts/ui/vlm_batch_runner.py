from __future__ import annotations

import asyncio
import gc
from typing import Awaitable, Callable, Iterable, TypeVar

from aih_contexture.scripts.ui.batch_inputs import materialize_pdf_batch, safe_cleanup_temp_files


T = TypeVar("T")

BatchProcessor = Callable[[list[tuple[str, str]], int, int], Awaitable[T]]
BatchStartCallback = Callable[[int, int, int, int], None]
BatchDoneCallback = Callable[[int, T], None]
RestCallback = Callable[[float], None]
StopPredicate = Callable[[T], bool]


def total_batch_count(total_items: int, batch_size: int) -> int:
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than 0")
    return (total_items + batch_size - 1) // batch_size


async def run_materialized_pdf_batches(
    *,
    file_objects: Iterable[tuple[object, str]],
    batch_size: int,
    upload_mode: str,
    process_batch: BatchProcessor[T],
    cancel=None,
    ctx: dict | None = None,
    resume_from: int = 0,
    batch_rest: float = 0,
    on_batch_start: BatchStartCallback | None = None,
    on_batch_done: BatchDoneCallback[T] | None = None,
    on_rest: RestCallback | None = None,
    should_stop: StopPredicate[T] | None = None,
) -> dict:
    files = list(file_objects)
    total_batches = total_batch_count(len(files), batch_size)
    last_result = None

    for batch_start in range(resume_from, len(files), batch_size):
        if cancel is not None and cancel.is_set():
            if ctx is not None:
                ctx["status"] = "cancelled"
            return {
                "cancelled": True,
                "stopped": False,
                "batch_start": batch_start,
                "batch_num": batch_start // batch_size + 1,
                "result": last_result,
            }

        batch_objects = files[batch_start:batch_start + batch_size]
        batch_num = batch_start // batch_size + 1
        if on_batch_start is not None:
            on_batch_start(batch_num, total_batches, len(batch_objects), batch_start)

        batch_file_list, batch_temp_files = materialize_pdf_batch(batch_objects, upload_mode)
        try:
            last_result = await process_batch(batch_file_list, batch_num, batch_start)
        finally:
            safe_cleanup_temp_files(batch_temp_files)
            gc.collect()

        if on_batch_done is not None:
            on_batch_done(batch_num, last_result)

        if should_stop is not None and should_stop(last_result):
            return {
                "cancelled": False,
                "stopped": True,
                "batch_start": batch_start,
                "batch_num": batch_num,
                "result": last_result,
            }

        if batch_num < total_batches and batch_rest > 0:
            if on_rest is not None:
                on_rest(batch_rest)
            await asyncio.sleep(batch_rest)

    return {
        "cancelled": False,
        "stopped": False,
        "batch_start": None,
        "batch_num": None,
        "result": last_result,
    }
