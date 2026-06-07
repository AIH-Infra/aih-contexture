from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from aih_contexture.backends.layout.paddle_runtime import PaddleLayoutDetectionRuntime
from aih_contexture.backends.ocr.paddle_runtime import PaddleOcrRuntime


@click.command(help="Run Paddle layout/OCR inside the current Python environment for Contexture sidecar calls.")
@click.option("--job-json", type=click.Path(exists=True, dir_okay=False), required=True)
@click.option("--result-json", type=click.Path(dir_okay=False), required=True)
def paddle_sidecar_cli(job_json: str, result_json: str) -> None:
    job = json.loads(Path(job_json).read_text(encoding="utf-8"))
    task = str(job.get("task") or "")
    image_paths = [Path(path) for path in job.get("image_paths") or []]
    page_sizes = _page_sizes(job.get("page_sizes"))
    config: dict[str, Any] = dict(job.get("config") or {})
    config["paddle_runtime_mode"] = "in_process"

    if task == "layout":
        payload = PaddleLayoutDetectionRuntime(config).run(image_paths, page_sizes=page_sizes)
    elif task == "ocr":
        payload = PaddleOcrRuntime(config).run(image_paths, page_sizes=page_sizes)
    else:
        raise click.ClickException(f"Unsupported Paddle sidecar task: {task!r}")

    result_path = Path(result_json)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _page_sizes(value: Any) -> list[tuple[int, int]] | None:
    if value is None:
        return None
    sizes: list[tuple[int, int]] = []
    for item in value:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            sizes.append((int(item[0]), int(item[1])))
    return sizes


if __name__ == "__main__":
    paddle_sidecar_cli()
