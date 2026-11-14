"""Sidecar worker: runs inside the Indra environment, speaks the JSON-lines protocol of backends/sidecar_pool.py.

Standalone on purpose (stdlib + indra_ocr only): it is started with the Indra venv's own Python, which does not
have aih_contexture. Requests, one JSON object per line on stdin:

    {"request_id": ..., "task": "info"}
    {"request_id": ..., "task": "convert", "pdf": path, "mode": "auto", "dpi": 200, "math": false,
     "cores": 4, "model_dir": path-or-null}
    {"request_id": ..., "task": "shutdown"}

Replies: {"request_id": ..., "ok": true, "result": ...} or {"request_id": ..., "ok": false, "error": text}.
``cores`` follows Indra's planning: four or more pages use single-thread worker processes, fewer pages use
one process with multiple threads. Progress events are emitted per completed page. PDF handles are closed
before returning results. Strict layout retains model workers across batches and reads original page indices.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

_converter = None
_executor = None
_executor_key = None
_serial_key = None

_MODEL_CONTENT_SUFFIXES = {".onnx", ".npz", ".json", ".safetensors"}
_LAYOUT_MODEL_NAMES = {"det.onnx", "meta.json", "order.onnx"}


def _model_asset_stamp(kwargs: dict) -> tuple:
    folder = Path(kwargs.get("path") or "")
    if not folder.is_dir():
        return (str(folder), ())
    files = sorted(
        (
            path for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() in _MODEL_CONTENT_SUFFIXES
        ),
        key=lambda path: path.name.lower(),
    )
    if kwargs.get("layout_only"):
        files = [path for path in files if path.name.lower() in _LAYOUT_MODEL_NAMES]
    elif not kwargs.get("math"):
        files = [path for path in files if not path.name.lower().startswith("math")]
    return (
        str(folder.resolve()),
        tuple(
            (
                path.name.lower(), int(path.stat().st_dev), int(path.stat().st_ino),
                int(path.stat().st_size), int(path.stat().st_mtime_ns), int(path.stat().st_ctime_ns),
            )
            for path in files
        ),
    )


class LayoutOnlyConverter:
    """Detection and layout with PDF text features, without recognition sessions."""

    def __init__(self, kwargs: dict, threads: int):
        from pathlib import Path
        import onnxruntime as ort
        from indra_ocr.pipeline import OrtOCR

        folder = Path(kwargs["path"])
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        options.enable_cpu_mem_arena = False
        # Reuse Indra's detection/ordering methods without its OCR initializer.
        self.ocr = OrtOCR.__new__(OrtOCR)
        self.ocr.det = ort.InferenceSession(
            str(folder / "det.onnx"), options, providers=["CPUExecutionProvider"]
        )
        self.ocr.order = None
        if (folder / "order.onnx").is_file():
            self.ocr.order = ort.InferenceSession(
                str(folder / "order.onnx"), options, providers=["CPUExecutionProvider"]
            )
        self.ocr.long_side = meta["det_long_side"]
        self.ocr.adaptive = True
        self.ocr.table_heads = False
        self.dpi = kwargs["dpi"]

    def pdf_page(self, path, document, index):
        from indra_ocr.document import _render, assign_runs, MAX_PAGE_PIXELS
        from indra_ocr.textlayer import extract_runs
        from indra_ocr.pipeline import Page, Line
        from indra_ocr.layout_post import page_blocks

        started = time.perf_counter()
        page = document[index]
        width, height = page.get_size()
        scale = min(self.dpi / 72.0, (MAX_PAGE_PIXELS / max(width * height, 1)) ** 0.5)
        gray = _render(page, scale)
        timings = {"render_ms": 1000 * (time.perf_counter() - started)}
        started = time.perf_counter()
        # This route explicitly reuses existing PDF OCR. The upstream trust
        # checker rejects invisible OCR layers before reading their characters.
        # Extract those characters directly, without invoking recognition.
        runs, _ = extract_runs(page)
        timings["text_ms"] = 1000 * (time.perf_counter() - started)
        started = time.perf_counter()
        boxes, pictures = self.ocr.detect_all(gray)
        timings["det_ms"] = 1000 * (time.perf_counter() - started)
        tokens, _ = assign_runs(runs, boxes[:, :4], scale)
        texts = ["".join(token[0] for token in line).strip() for line in tokens]
        started = time.perf_counter()
        order, layout, _ = self.ocr.reading_order(boxes, texts, (gray.shape[1], gray.shape[0]))
        if layout is not None:
            blocks = page_blocks(boxes[:, :4], texts, order, layout[0], layout[1])
        else:
            blocks = [{"label": "Text", "bbox": boxes[i, :4].tolist(), "text": texts[i]} for i in order]
        for box in pictures:
            centre_y = (box[1] + box[3]) / 2
            position = next((i for i, block in enumerate(blocks)
                             if (block["bbox"][1] + block["bbox"][3]) / 2 > centre_y), len(blocks))
            blocks.insert(position, {"label": "Picture", "bbox": box.tolist(), "text": ""})
        timings["order_ms"] = 1000 * (time.perf_counter() - started)
        timings["rec_ms"] = 0.0
        timings["total_ms"] = sum(timings.values())
        note = "internal OCR disabled"
        if not any(run.text.strip() for run in runs):
            note += "; missing text layer"
        result = Page(
            lines=[Line(boxes[i, :4].tolist(), texts[i], None) for i in order],
            blocks=blocks, timings=timings, source="layout_only", note=note,
        )
        result.render_dpi = scale * 72.0
        return result


def _init_converter(kwargs: dict, threads: int) -> None:
    import cv2
    import indra_ocr

    global _converter
    cv2.setNumThreads(threads)
    layout_only = kwargs.pop("layout_only", False)
    if layout_only:
        _converter = LayoutOnlyConverter(kwargs, threads)
    else:
        _converter = indra_ocr.load(threads=threads, **kwargs)


def _shutdown_executor() -> None:
    global _executor, _executor_key
    executor = _executor
    _executor = None
    _executor_key = None
    if executor is not None:
        executor.shutdown(wait=True, cancel_futures=True)


def _read_page(unit: tuple[str, int]) -> tuple[int, object]:
    import pypdfium2 as pdfium

    path, index = unit
    # Each task releases its file handle before returning to the parent.
    document = pdfium.PdfDocument(path)
    try:
        if isinstance(_converter, LayoutOnlyConverter):
            page = _converter.pdf_page(path, document, index)
        else:
            page = _converter._safe(lambda: _converter.pdf_page(path, document, index))
            page.render_dpi = _converter.page_scale(document[index]) * 72.0
    finally:
        document.close()
    return index, page


def _progress(request: dict, current: int, total: int) -> None:
    event = {
        "kind": "progress", "stage": request.get("progress_stage", "ocr"),
        "current": current, "total": total, "unit": "pages",
        "message": f"Indra completed {current}/{total} pages",
    }
    sys.stdout.write("@@CONTEXTURE_EVENT@@ " + json.dumps(event) + "\n")
    sys.stdout.flush()


def convert(request: dict) -> dict:
    global _converter, _executor, _executor_key, _serial_key

    import indra_ocr

    started = time.perf_counter()
    kwargs = {"dpi": float(request.get("dpi") or 200), "mode": request.get("mode") or "auto", "math": bool(request.get("math"))}
    if request.get("model_dir"):
        kwargs["path"] = request["model_dir"]
    import pypdfium2 as pdfium
    from concurrent.futures import ProcessPoolExecutor, as_completed
    from multiprocessing import get_context

    cores = max(1, int(request.get("cores") or indra_ocr.usable_cores()))
    layout_only = bool(request.get("layout_only"))
    # Installed detector/layout files are sufficient for strict layout.
    if not layout_only or not kwargs.get("path"):
        kwargs["path"] = str(indra_ocr.model_dir(kwargs.get("path"), math=kwargs["math"]))
    if layout_only:
        kwargs["layout_only"] = True
        kwargs["math"] = False
    document = pdfium.PdfDocument(request["pdf"])
    try:
        total = len(document)
    finally:
        document.close()
    indices = request.get("page_indices", list(range(total)))
    if any(not 0 <= index < total for index in indices):
        raise ValueError("Indra page index out of range")
    units = [(request["pdf"], index) for index in indices]
    total = len(units)
    result = []
    _progress(request, 0, total)
    if not units:
        return {
            "pages": [],
            "wall_seconds": time.perf_counter() - started,
            "version": getattr(indra_ocr, "__version__", None),
        }

    model_identity = request.get("model_identity") or ""
    model_asset_stamp = _model_asset_stamp(kwargs)
    if cores == 1 or total < 4:
        key = (json.dumps(kwargs, sort_keys=True), cores, model_identity, model_asset_stamp)
        if _executor is not None:
            _shutdown_executor()
        if key != _serial_key:
            _init_converter(dict(kwargs), cores)
            _serial_key = key
        for unit in units:
            result.append(_read_page(unit))
            _progress(request, len(result), total)
    else:
        thread_env = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
        saved = {key: os.environ.get(key) for key in thread_env}
        os.environ.update({key: "1" for key in thread_env})
        try:
            key = (
                json.dumps(kwargs, sort_keys=True), min(cores, total),
                model_identity, model_asset_stamp,
            )
            _converter = None
            _serial_key = None
            if key != _executor_key:
                _shutdown_executor()
                _executor = ProcessPoolExecutor(
                    min(cores, total), mp_context=get_context("spawn"),
                    initializer=_init_converter, initargs=(dict(kwargs), 1),
                )
                _executor_key = key
            pool = _executor
            try:
                futures = [pool.submit(_read_page, unit) for unit in units]
                for future in as_completed(futures):
                    result.append(future.result())
                    _progress(request, len(result), total)
            except BaseException:
                _shutdown_executor()
                raise
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
    pages = []
    positions = {index: position for position, index in enumerate(indices)}
    for index, page in sorted(result):
        pages.append({
            "page_num": positions[index],
            "dpi": getattr(page, "render_dpi", kwargs["dpi"]),
            "seconds": page.timings.get("total_ms", 0) / 1000,
            "timings": page.timings,
            "source": page.source,
            "note": page.note,
            "rotation": page.rotation,
            "skew": page.skew,
            "vertical": page.vertical,
            "blocks": [{"type": b["label"], "bbox": [float(v) for v in b["bbox"]], "content": b.get("text", "")} for b in page.blocks],
            "lines": [{"bbox": [float(v) for v in line.box], "text": line.text,
                       "conf": float(line.conf) if line.conf is not None else None} for line in page.lines],
        })
    return {"pages": pages, "wall_seconds": time.perf_counter() - started, "version": getattr(indra_ocr, "__version__", None)}


def info(_: dict) -> dict:
    import indra_ocr

    return {"version": getattr(indra_ocr, "__version__", None), "usable_cores": indra_ocr.usable_cores()}


TASKS = {"convert": convert, "info": info}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        request = json.loads(line)
        reply = {"request_id": request.get("request_id")}
        if request.get("task") == "shutdown":
            if _executor is not None:
                _executor.shutdown(wait=True, cancel_futures=True)
            return
        try:
            reply.update(ok=True, result=TASKS[request["task"]](request))
        except Exception as exc:  # noqa: BLE001 - reported to the caller, which decides
            reply.update(ok=False, error=f"{type(exc).__name__}: {exc}")
        sys.stdout.write(json.dumps(reply, ensure_ascii=False) + chr(10))
        sys.stdout.flush()


if __name__ == "__main__":  # the guard matters: Windows spawns worker processes that re-import this module
    main()
