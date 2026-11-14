from __future__ import annotations

import base64
import json
import shutil
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from aih_contexture.runtime.chrome_screenai_runtime import ChromeScreenAIRuntime


class _FileProgressWriter:
    def __init__(self, path: Path, *, page_total: int):
        self.path = path
        self.page_total = max(0, int(page_total))
        self.page_current = 0
        self.page_desc = "Chrome ScreenAI OCR"
        self._flush()

    def on_event(self, event: dict[str, Any]) -> None:
        event_name = str(event.get("event") or "")
        if event_name == "page_done":
            self.page_current += 1
        elif event_name == "searchable_pdf":
            self.page_desc = str(event.get("message") or self.page_desc)
        self._flush()

    def _flush(self) -> None:
        self.path.write_text(
            json.dumps(
                {
                    "page_current": self.page_current,
                    "page_total": self.page_total,
                    "page_desc": self.page_desc,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )


def _write_chunk_result(path: Path, result: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _run_chunk_lane(job: dict[str, Any]) -> int:
    """Reuse one isolated ScreenAI runtime across this lane's page chunks."""
    runtime = ChromeScreenAIRuntime(
        model_dir=job.get("model_dir"),
        light_mode=bool(job.get("light_mode", False)),
        preprocess_mode=str(job.get("preprocess_mode", "native")),
        remove_annotations=bool(job.get("remove_annotations", True)),
        workers=1,
        chunk_pages=1,
        batch_rest=0.0,
        rasterize_dpi=max(72, int(job.get("rasterize_dpi", 144) or 144)),
        emit_searchable_pdf=False,
        max_retries=max(1, int(job.get("max_retries", 1) or 1)),
        progress_callback=None,
    )
    input_pdf = Path(job["input_pdf"])
    result_dir = Path(job["result_dir"])
    chunks = job.get("chunks")
    if not isinstance(chunks, list):
        raise ValueError("ScreenAI chunk lane requires a chunks list")
    batch_rest = max(0.0, float(job.get("batch_rest", 0) or 0))

    try:
        for chunk_offset, chunk in enumerate(chunks):
            chunk_index = int(chunk["chunk_index"])
            page_indices = [int(index) for index in chunk["page_indices"]]
            chunk_result: dict[str, Any]
            try:
                pages = []
                for page_index in page_indices:
                    result = runtime._ocr_pdf_page_with_retry(input_pdf, page_index, page_index)
                    pages.append({
                        "page_index": result.page_index,
                        "markdown": result.markdown,
                        "clean_html": result.clean_html,
                        "printed_page": result.printed_page,
                        "chunk_page": result.chunk_page,
                    })
                chunk_result = {"chunk_index": chunk_index, "ok": True, "pages": pages}
            except Exception as exc:
                chunk_result = {"chunk_index": chunk_index, "ok": False, "error": str(exc)}

            _write_chunk_result(result_dir / f"chunk_{chunk_index}.json", chunk_result)
            if chunk_offset + 1 < len(chunks) and batch_rest > 0:
                time.sleep(batch_rest)
    finally:
        runtime._close_thread_pdf_docs()
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print(json.dumps({"ok": False, "error": "missing job token"}, ensure_ascii=False))
        return 2

    job: dict[str, Any] | None = None
    try:
        job_argument = argv[0]
        if job_argument.startswith("@"):
            job = json.loads(Path(job_argument[1:]).read_text(encoding="utf-8"))
        else:
            job = json.loads(base64.b64decode(job_argument).decode("utf-8"))
        if job.get("collect_chunks"):
            return _run_chunk_lane(job)

        collect_pages = bool(job.get("collect_pages"))
        progress = None
        if not collect_pages and job.get("progress_json"):
            progress = _FileProgressWriter(
                Path(job["progress_json"]),
                page_total=int(job.get("page_count", 0) or 0),
            )
        runtime = ChromeScreenAIRuntime(
            model_dir=job.get("model_dir"),
            light_mode=bool(job.get("light_mode", False)),
            preprocess_mode=str(job.get("preprocess_mode", "native")),
            remove_annotations=bool(job.get("remove_annotations", True)),
            workers=1,
            chunk_pages=max(1, int(job.get("page_count", 1) or 1)),
            batch_rest=0.0,
            rasterize_dpi=max(72, int(job.get("rasterize_dpi", 144) or 144)),
            emit_searchable_pdf=True,
            max_retries=max(1, int(job.get("max_retries", 1) or 1)),
            progress_callback=progress.on_event if progress is not None else None,
        )
        input_pdf = Path(job["input_pdf"])
        page_indices = job.get("page_indices")
        if not isinstance(page_indices, list):
            page_indices = list(range(int(job.get("page_count", 0) or 0)))
        page_indices = [int(index) for index in page_indices]
        if collect_pages:
            runtime.emit_searchable_pdf = False
        payload = runtime.process_document(input_pdf, page_indices)
        if collect_pages:
            Path(job["result_json"]).write_text(
                json.dumps({"ok": True, "pages": [
                    {
                        "page_index": index,
                        "markdown": markdown,
                        "clean_html": html,
                        "printed_page": printed,
                        "chunk_page": chunk,
                    }
                    for index, markdown, html, printed, chunk in zip(
                        page_indices,
                        payload.get("markdown_pages", []),
                        payload.get("clean_html_pages", []),
                        payload.get("printed_pages", []),
                        payload.get("chunk_pages", []),
                    )
                ]}, ensure_ascii=False),
                encoding="utf-8",
            )
            return 0
        searchable_pdf_path = payload.get("searchable_pdf_path")
        if not isinstance(searchable_pdf_path, str) or not searchable_pdf_path:
            raise RuntimeError("Chrome ScreenAI worker did not produce searchable_pdf_path")
        shutil.move(searchable_pdf_path, job["output_pdf"])
        Path(job["result_json"]).write_text(
            json.dumps({"ok": True, "searchable_pdf_path": job["output_pdf"]}, ensure_ascii=False),
            encoding="utf-8",
        )
        print(json.dumps({"ok": True}, ensure_ascii=False))
        return 0
    except Exception as exc:
        error_payload = {
            "ok": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
        if job is not None:
            try:
                Path(job["result_json"]).write_text(
                    json.dumps(error_payload, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception:
                pass
        print(json.dumps(error_payload, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
