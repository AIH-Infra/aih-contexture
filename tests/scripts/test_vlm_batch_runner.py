from pathlib import Path
import asyncio

import pytest

from aih_contexture.scripts.ui.vlm_batch_runner import (
    run_materialized_pdf_batches,
    total_batch_count,
)


class Cancel:
    def __init__(self, value=False):
        self.value = value

    def is_set(self):
        return self.value


def test_total_batch_count_rejects_invalid_batch_size():
    assert total_batch_count(5, 2) == 3
    with pytest.raises(ValueError):
        total_batch_count(1, 0)


def test_run_materialized_pdf_batches_materializes_uploads_and_cleans_temp_files():
    seen = []
    starts = []
    dones = []

    async def process_batch(batch_file_list, batch_num, batch_start):
        assert batch_file_list
        for path, name in batch_file_list:
            assert Path(path).exists()
            seen.append((Path(path).read_bytes(), name, batch_num, batch_start))
        return len(batch_file_list)

    result = asyncio.run(
        run_materialized_pdf_batches(
            file_objects=[(b"a", "a.pdf"), (b"b", "b.pdf"), (b"c", "c.pdf")],
            batch_size=2,
            upload_mode="上传文件",
            process_batch=process_batch,
            on_batch_start=lambda *args: starts.append(args),
            on_batch_done=lambda *args: dones.append(args),
        )
    )

    assert result["cancelled"] is False
    assert result["stopped"] is False
    assert seen == [
        (b"a", "a.pdf", 1, 0),
        (b"b", "b.pdf", 1, 0),
        (b"c", "c.pdf", 2, 2),
    ]
    assert starts == [(1, 2, 2, 0), (2, 2, 1, 2)]
    assert dones == [(1, 2), (2, 1)]
    for content, _, _, _ in seen:
        assert content in {b"a", b"b", b"c"}


def test_run_materialized_pdf_batches_returns_cancelled_before_processing():
    ctx = {}
    called = False

    async def process_batch(batch_file_list, batch_num, batch_start):
        nonlocal called
        called = True

    result = asyncio.run(
        run_materialized_pdf_batches(
            file_objects=[(b"a", "a.pdf")],
            batch_size=1,
            upload_mode="上传文件",
            process_batch=process_batch,
            cancel=Cancel(True),
            ctx=ctx,
        )
    )

    assert called is False
    assert result["cancelled"] is True
    assert ctx["status"] == "cancelled"


def test_run_materialized_pdf_batches_stops_when_predicate_matches():
    async def process_batch(batch_file_list, batch_num, batch_start):
        return {"stop": batch_num == 1}

    result = asyncio.run(
        run_materialized_pdf_batches(
            file_objects=[(b"a", "a.pdf"), (b"b", "b.pdf")],
            batch_size=1,
            upload_mode="上传文件",
            process_batch=process_batch,
            should_stop=lambda batch_result: batch_result["stop"],
        )
    )

    assert result["stopped"] is True
    assert result["batch_num"] == 1
    assert result["batch_start"] == 0
    assert result["result"] == {"stop": True}
