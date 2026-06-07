from aih_contexture.scripts.ui.vlm_progress import (
    finish_vlm_progress,
    make_vlm_progress_callback,
    update_vlm_batch_progress,
)


def test_vlm_progress_callback_accumulates_pages_once_per_file():
    ctx = {}
    callback = make_vlm_progress_callback(
        ctx,
        mode="vlm_generalized",
        file_name="a.pdf",
        file_index=0,
        total_files=2,
    )

    callback({"event": "pages_loaded", "total_pages": 3})
    callback({"event": "pages_loaded", "total_pages": 3})
    callback({"event": "page_done", "page_num": 1, "ok": True})
    callback({"event": "page_done", "page_num": 1, "ok": True})
    callback({"event": "page_done", "page_num": 2, "ok": False})

    progress = ctx["vlm_progress"]
    assert progress["total_pages"] == 3
    assert progress["done_pages"] == 2
    assert progress["success_pages"] == 1
    assert progress["failed_pages"] == 1
    assert ctx["progress"] == 2 / 3


def test_vlm_progress_callbacks_accumulate_multiple_files():
    ctx = {}
    first = make_vlm_progress_callback(
        ctx,
        mode="vlm_specialized",
        file_name="a.pdf",
        file_index=0,
        total_files=2,
    )
    second = make_vlm_progress_callback(
        ctx,
        mode="vlm_specialized",
        file_name="b.pdf",
        file_index=1,
        total_files=2,
    )

    first({"event": "pages_loaded", "total_pages": 2})
    second({"event": "pages_loaded", "total_pages": 4})
    second({"event": "page_done", "page_num": 1, "ok": True})

    progress = ctx["vlm_progress"]
    assert progress["mode_label"] == "VLM 特化"
    assert progress["total_pages"] == 6
    assert progress["done_pages"] == 1
    assert progress["current_file"] == "b.pdf"
    assert progress["current_page"] == 1
    assert ctx["progress"] == 1 / 6


def test_vlm_batch_and_finish_progress_update_status():
    ctx = {}

    update_vlm_batch_progress(
        ctx,
        mode="vlm_generalized",
        stage="处理中",
        batch_num=2,
        total_batches=5,
        total_files=9,
        message="批次 2/5",
    )
    progress = ctx["vlm_progress"]
    assert progress["stage"] == "处理中"
    assert progress["batch_num"] == 2
    assert progress["total_batches"] == 5
    assert progress["total_files"] == 9
    assert progress["message"] == "批次 2/5"

    progress["total_pages"] = 4
    progress["done_pages"] = 4
    finish_vlm_progress(ctx, mode="vlm_generalized", stage="完成", message="完成")

    assert ctx["progress"] == 1.0
    assert ctx["vlm_progress"]["stage"] == "完成"


def test_vlm_progress_callback_tracks_repair_events():
    ctx = {}
    callback = make_vlm_progress_callback(
        ctx,
        mode="vlm_generalized",
        file_name="repair.pdf",
        file_index=0,
        total_files=1,
    )

    callback({"event": "repair_start", "failed_pages": [38, 178], "stage": "repairing"})
    callback({"event": "repair_batch", "pages": [38, 178], "stage": "repairing"})
    callback({"event": "page_done", "page_num": 38, "ok": True, "stage": "repairing"})

    progress = ctx["vlm_progress"]
    assert progress["total_pages"] == 2
    assert progress["done_pages"] == 1
    assert progress["success_pages"] == 1
    assert progress["stage"] == "修复中"
    assert progress["current_page"] == 38
    assert ctx["progress"] == 0.5
