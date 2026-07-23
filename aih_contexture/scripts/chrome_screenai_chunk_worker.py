from __future__ import annotations

import base64
import json
import shutil
import sys
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


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print(json.dumps({"ok": False, "error": "missing job token"}, ensure_ascii=False))
        return 2

    job: dict[str, Any] | None = None
    try:
        job = json.loads(base64.b64decode(argv[0]).decode("utf-8"))
        progress = _FileProgressWriter(Path(job["progress_json"]), page_total=int(job.get("page_count", 0) or 0))
        runtime = ChromeScreenAIRuntime(
            model_dir=job.get("model_dir"),
            light_mode=bool(job.get("light_mode", False)),
            preprocess_mode=str(job.get("preprocess_mode", "native")),
            workers=1,
            chunk_pages=max(1, int(job.get("page_count", 1) or 1)),
            batch_rest=0.0,
            rasterize_dpi=max(72, int(job.get("rasterize_dpi", 144) or 144)),
            emit_searchable_pdf=True,
            max_retries=max(1, int(job.get("max_retries", 1) or 1)),
            progress_callback=progress.on_event,
        )
        input_pdf = Path(job["input_pdf"])
        payload = runtime.process_document(input_pdf, list(range(int(job.get("page_count", 0) or 0))))
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
