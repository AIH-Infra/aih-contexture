"""Sidecar worker: runs inside the Indra environment, speaks the JSON-lines protocol of backends/sidecar_pool.py.

Standalone on purpose (stdlib + indra_ocr only): it is started with the Indra venv's own Python, which does not
have aih_contexture. Requests, one JSON object per line on stdin:

    {"request_id": ..., "task": "info"}
    {"request_id": ..., "task": "convert", "pdf": path, "mode": "auto", "dpi": 200, "math": false,
     "cores": 4, "model_dir": path-or-null}
    {"request_id": ..., "task": "shutdown"}

Replies: {"request_id": ..., "ok": true, "result": ...} or {"request_id": ..., "ok": false, "error": text}.
``cores`` is Indra's own knob: with four or more pages the pages are spread over one single-thread process per
core, with fewer a single process uses all the cores on each page (indra_ocr.parallel.convert_many).
"""
from __future__ import annotations

import json
import sys
import time


def convert(request: dict) -> dict:
    import indra_ocr

    started = time.perf_counter()
    kwargs = {"dpi": float(request.get("dpi") or 200), "mode": request.get("mode") or "auto", "math": bool(request.get("math"))}
    if request.get("model_dir"):
        kwargs["path"] = request["model_dir"]
    cores = request.get("cores")
    outcomes = list(indra_ocr.convert_many([request["pdf"]], cores=int(cores) if cores else None, **kwargs))
    _, result = outcomes[0]
    if isinstance(result, Exception):
        raise RuntimeError(str(result))
    pages = []
    for index, page in result:
        pages.append({
            "page_num": index,
            "dpi": kwargs["dpi"],
            "seconds": page.timings.get("total_ms", 0) / 1000,
            "source": page.source,
            "note": page.note,
            "rotation": page.rotation,
            "skew": page.skew,
            "vertical": page.vertical,
            "blocks": [{"type": b["label"], "bbox": [float(v) for v in b["bbox"]], "content": b.get("text", "")} for b in page.blocks],
            "lines": [{"bbox": [float(v) for v in line.box], "text": line.text, "conf": float(line.conf)} for line in page.lines],
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
            return
        try:
            reply.update(ok=True, result=TASKS[request["task"]](request))
        except Exception as exc:  # noqa: BLE001 - reported to the caller, which decides
            reply.update(ok=False, error=f"{type(exc).__name__}: {exc}")
        sys.stdout.write(json.dumps(reply, ensure_ascii=False) + chr(10))
        sys.stdout.flush()


if __name__ == "__main__":  # the guard matters: Windows spawns worker processes that re-import this module
    main()
