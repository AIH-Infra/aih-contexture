from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
from PIL import Image


@click.command(help="Run MinerU PP-DocLayoutV2 directly without the MinerU pipeline.")
@click.option("--job-json", type=click.Path(exists=True, dir_okay=False), required=True)
@click.option("--result-json", type=click.Path(dir_okay=False), required=True)
def mineru_layout_direct_sidecar_cli(job_json: str, result_json: str) -> None:
    job = json.loads(Path(job_json).read_text(encoding="utf-8"))
    config = dict(job.get("config") or {})
    image_paths = [Path(path) for path in job.get("image_paths") or []]
    page_sizes = _page_sizes(job.get("page_sizes"))

    payload = run_layout_only(image_paths, page_sizes=page_sizes, config=config)

    result_path = Path(result_json)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def run_layout_only(
    image_paths: list[Path],
    *,
    page_sizes: list[tuple[int, int]] | None,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    from mineru.model.layout.pp_doclayoutv2 import PPDocLayoutV2LayoutModel
    from mineru.utils.config_reader import get_device
    from mineru.utils.enum_class import ModelPath
    from mineru.utils.models_download_utils import auto_download_and_get_model_root_path

    model_path = str(config.get("mineru_layout_model_dir") or "")
    if not model_path:
        model_path = str(Path(auto_download_and_get_model_root_path(ModelPath.pp_doclayout_v2)) / ModelPath.pp_doclayout_v2)
    device = str(config.get("mineru_layout_device") or get_device())
    batch_size = int(config.get("mineru_layout_batch_size") or 1)
    use_paddlex_filter_boxes = config.get("mineru_layout_use_paddlex_filter_boxes")

    model = PPDocLayoutV2LayoutModel(model_path, device)
    images = []
    try:
        for image_path in image_paths:
            with Image.open(image_path) as image:
                images.append(image.convert("RGB").copy())

        raw_results = model.batch_predict(
            images,
            batch_size=max(1, batch_size),
            use_paddlex_filter_boxes=use_paddlex_filter_boxes,
        )
    finally:
        close = getattr(model, "close", None)
        if callable(close):
            close()

    payload = []
    for index, boxes in enumerate(raw_results):
        page_size = _page_size(page_sizes, index)
        payload.append(
            {
                "res": {
                    "page_index": index,
                    "page_size": [float(page_size[0]), float(page_size[1])] if page_size else None,
                    "model_name": "PP-DocLayoutV2",
                    "boxes": [_box_payload(box, order=order) for order, box in enumerate(boxes or [])],
                }
            }
        )
    return payload


def _box_payload(box: dict[str, Any], *, order: int) -> dict[str, Any]:
    bbox = box.get("bbox") or box.get("coordinate")
    payload = {
        "label": box.get("label") or box.get("type") or "text",
        "score": box.get("score", box.get("confidence")),
        "coordinate": bbox,
        "bbox": bbox,
        "index": box.get("index", order),
        "order": box.get("order", box.get("index", order)),
    }
    if box.get("polygon") is not None:
        payload["polygon"] = box["polygon"]
    return payload


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
    mineru_layout_direct_sidecar_cli()
