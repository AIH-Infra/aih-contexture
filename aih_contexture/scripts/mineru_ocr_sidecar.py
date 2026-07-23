from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
import numpy as np
from PIL import Image


@click.command(help="Run MinerU PytorchPaddleOCR without the MinerU full pipeline.")
@click.option("--job-json", type=click.Path(exists=True, dir_okay=False), required=True)
@click.option("--result-json", type=click.Path(dir_okay=False), required=True)
def mineru_ocr_sidecar_cli(job_json: str, result_json: str) -> None:
    job = json.loads(Path(job_json).read_text(encoding="utf-8"))
    config = dict(job.get("config") or {})
    image_paths = [Path(path) for path in job.get("image_paths") or []]
    page_sizes = _page_sizes(job.get("page_sizes"))

    payload = run_ocr(image_paths, page_sizes=page_sizes, config=config)

    result_path = Path(result_json)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def run_ocr(
    image_paths: list[Path],
    *,
    page_sizes: list[tuple[int, int]] | None,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    from mineru.model.ocr.pytorch_paddle import PytorchPaddleOCR

    lang = str(config.get("mineru_ocr_lang") or config.get("paddle_ocr_lang") or "ch")
    det_db_box_thresh = float(config.get("mineru_ocr_det_db_box_thresh") or 0.3)
    det_db_unclip_ratio = float(config.get("mineru_ocr_det_db_unclip_ratio") or 1.8)
    enable_merge_det_boxes = bool(config.get("mineru_ocr_enable_merge_det_boxes", True))

    model = PytorchPaddleOCR(
        det_db_box_thresh=det_db_box_thresh,
        lang=lang,
        det_db_unclip_ratio=det_db_unclip_ratio,
        enable_merge_det_boxes=enable_merge_det_boxes,
    )

    payload = []
    for index, image_path in enumerate(image_paths):
        with Image.open(image_path) as image:
            rgb_image = image.convert("RGB")
            rgb_array = np.ascontiguousarray(np.asarray(rgb_image))
            result = model.ocr(rgb_array)
        page_size = _page_size(page_sizes, index) or rgb_image.size
        payload.append(
            {
                "res": {
                    "page_index": index,
                    "page_size": [float(page_size[0]), float(page_size[1])],
                    "model_name": "MinerU PytorchPaddleOCR",
                    "items": _normalize_ocr_result(result),
                }
            }
        )
    return payload


def _normalize_ocr_result(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, tuple):
        result = list(result)
    if isinstance(result, list) and len(result) == 1 and isinstance(result[0], list):
        result = result[0]

    items: list[dict[str, Any]] = []
    for raw in result or []:
        geometry = None
        text = ""
        confidence = None
        if isinstance(raw, dict):
            geometry = raw.get("box") or raw.get("bbox") or raw.get("poly") or raw.get("points")
            text = str(raw.get("text") or raw.get("rec_text") or "").strip()
            confidence = raw.get("score") or raw.get("confidence")
        elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
            geometry = raw[0]
            rec = raw[1]
            if isinstance(rec, (list, tuple)):
                text = str(rec[0] if rec else "").strip()
                if len(rec) > 1:
                    confidence = rec[1]
            else:
                text = str(rec or "").strip()
                if len(raw) > 2:
                    confidence = raw[2]
        if not text or geometry is None:
            continue
        items.append(
            {
                "text": text,
                "geometry": geometry,
                "confidence": float(confidence) if isinstance(confidence, (int, float)) else None,
            }
        )
    return items


def _page_sizes(value: Any) -> list[tuple[int, int]] | None:
    if value is None:
        return None
    sizes: list[tuple[int, int]] = []
    for item in value:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            sizes.append((int(item[0]), int(item[1])))
    return sizes


def _page_size(page_sizes: list[tuple[int, int]] | None, index: int) -> tuple[int, int] | None:
    if page_sizes is None or index >= len(page_sizes):
        return None
    return page_sizes[index]


if __name__ == "__main__":
    mineru_ocr_sidecar_cli()
