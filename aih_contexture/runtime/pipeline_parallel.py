"""Run Pipeline page batches in worker processes and yield them in batch order.

Each worker loads its own models once and takes the next batch from a shared
queue, so faster batches never wait for a fixed split. The parent only writes
outputs, in the original order, which keeps every artifact identical to the
sequential path. Worker progress travels through a queue to the parent.
"""
from __future__ import annotations

import multiprocessing
import os
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ProcessPoolExecutor
from typing import Any

_WORKER: dict[str, Any] = {}


def _init_worker() -> None:
    from multiprocessing.util import Finalize

    from aih_contexture.backends.sidecar_pool import SidecarRuntimePool
    from aih_contexture.models import create_model_dict

    sidecar_pool = SidecarRuntimePool()
    _WORKER["artifacts"] = create_model_dict()
    _WORKER["sidecar_pool"] = sidecar_pool
    # Pool workers leave via os._exit; Finalize still runs, atexit would not.
    Finalize(sidecar_pool, sidecar_pool.close_all, exitpriority=10)


def _init_progress_worker(events, initializer) -> None:
    from aih_contexture.runtime.progress_events import set_progress_sink

    os.environ["CONTEXTURE_PROGRESS_EVENTS"] = "1"
    set_progress_sink(events.put)
    if initializer is not None:
        initializer()


def _run_progress_batch(task, index, job, kwargs, context):
    from aih_contexture.runtime.progress_events import emit_progress_event, set_progress_context

    set_progress_context(**context)
    count = context.get("batch_page_count", 0)
    emit_progress_event("batch_started", "batch", current=0, total=count, unit="pages")
    result = task(index, job, kwargs)
    emit_progress_event("batch_processed", "batch", current=count, total=count, unit="pages")
    return result


def _relay_progress(events) -> None:
    from aih_contexture.runtime.progress_events import emit_progress_event

    while True:
        event = events.get()
        if event is None:
            return
        kind, stage = event.pop("kind"), event.pop("stage")
        emit_progress_event(kind, stage, **event)


def _run_batch(index: int, batch_job: dict[str, Any], kwargs: dict[str, Any]):
    from aih_contexture.runtime.artifacts import build_pipeline_batch_output

    return build_pipeline_batch_output(
        index, batch_job, artifacts=_WORKER["artifacts"], sidecar_pool=_WORKER["sidecar_pool"], **kwargs,
    )


def iter_parallel_batch_outputs(
    batch_jobs: list[dict[str, Any]],
    workers: int,
    *,
    task: Callable[[int, dict[str, Any], dict[str, Any]], Any] = _run_batch,
    initializer: Callable[[], None] | None = _init_worker,
    progress_contexts: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> Iterator[Any]:
    context = multiprocessing.get_context("spawn")
    events = context.Queue()
    relay = threading.Thread(target=_relay_progress, args=(events,), daemon=True)
    relay.start()
    executor = ProcessPoolExecutor(
        max_workers=max(1, int(workers)),
        mp_context=context,
        initializer=_init_progress_worker,
        initargs=(events, initializer),
    )
    futures: list[Future] = []
    try:
        futures = [
            executor.submit(
                _run_progress_batch, task, index, job, kwargs,
                progress_contexts[index] if progress_contexts is not None else {
                    "batch_index": index + 1, "total_batches": len(batch_jobs),
                    "batch_label": job.get("label", ""),
                },
            )
            for index, job in enumerate(batch_jobs)
        ]
        for future in futures:
            yield future.result()
    finally:
        for future in futures:
            future.cancel()
        executor.shutdown(wait=True, cancel_futures=True)
        events.put(None)
        relay.join()
        events.close()
        events.join_thread()
