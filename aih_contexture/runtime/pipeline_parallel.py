"""Run Pipeline page batches in worker processes and yield them in batch order.

Each worker loads its own models once and takes the next batch from a shared
queue, so faster batches never wait for a fixed split. The parent only writes
outputs, in the original order, which keeps every artifact identical to the
sequential path. Workers stay silent on the progress channel; the parent
reports each batch as it is consumed.
"""
from __future__ import annotations

import multiprocessing
import os
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ProcessPoolExecutor
from typing import Any

_WORKER: dict[str, Any] = {}


def _init_worker() -> None:
    os.environ["CONTEXTURE_PROGRESS_EVENTS"] = "0"
    from multiprocessing.util import Finalize

    from aih_contexture.backends.sidecar_pool import SidecarRuntimePool
    from aih_contexture.models import create_model_dict

    sidecar_pool = SidecarRuntimePool()
    _WORKER["artifacts"] = create_model_dict()
    _WORKER["sidecar_pool"] = sidecar_pool
    # Pool workers leave via os._exit; Finalize still runs, atexit would not.
    Finalize(sidecar_pool, sidecar_pool.close_all, exitpriority=10)


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
    **kwargs: Any,
) -> Iterator[Any]:
    executor = ProcessPoolExecutor(
        max_workers=max(1, int(workers)),
        mp_context=multiprocessing.get_context("spawn"),
        initializer=initializer,
    )
    futures: list[Future] = []
    try:
        futures = [executor.submit(task, index, job, kwargs) for index, job in enumerate(batch_jobs)]
        for future in futures:
            yield future.result()
    finally:
        for future in futures:
            future.cancel()
        executor.shutdown(wait=True, cancel_futures=True)
