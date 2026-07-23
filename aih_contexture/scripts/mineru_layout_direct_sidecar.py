from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

import click
from PIL import Image


@click.command(help="Run MinerU PP-DocLayoutV2 directly without the MinerU pipeline.")
@click.option("--job-json", type=click.Path(exists=True, dir_okay=False), default=None)
@click.option("--result-json", type=click.Path(dir_okay=False), default=None)
@click.option("--persistent", is_flag=True, help="Run a JSON-lines persistent sidecar on stdin/stdout.")
def mineru_layout_direct_sidecar_cli(job_json: str | None, result_json: str | None, persistent: bool) -> None:
    if persistent:
        run_persistent_sidecar()
        return
    if not job_json or not result_json:
        raise click.ClickException("--job-json and --result-json are required unless --persistent is used.")
    job = json.loads(Path(job_json).read_text(encoding="utf-8"))
    config = dict(job.get("config") or {})
    image_paths = [Path(path) for path in job.get("image_paths") or []]
    page_sizes = _page_sizes(job.get("page_sizes"))

    payload = run_layout_only(image_paths, page_sizes=page_sizes, config=config)

    result_path = Path(result_json)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class MineruDirectLayoutSession:
    def __init__(self, config: dict[str, Any]):
        from mineru.model.layout.pp_doclayoutv2 import PPDocLayoutV2LayoutModel
        from mineru.utils.config_reader import get_device
        from mineru.utils.enum_class import ModelPath
        from mineru.utils.models_download_utils import auto_download_and_get_model_root_path

        self.config = dict(config or {})
        model_path = str(self.config.get("mineru_layout_model_dir") or "")
        if not model_path:
            model_path = str(Path(auto_download_and_get_model_root_path(ModelPath.pp_doclayout_v2)) / ModelPath.pp_doclayout_v2)
        device = str(self.config.get("mineru_layout_device") or get_device())
        self.batch_size = int(self.config.get("mineru_layout_batch_size") or 1)
        self.use_paddlex_filter_boxes = self.config.get("mineru_layout_use_paddlex_filter_boxes")
        self.model = PPDocLayoutV2LayoutModel(model_path, device)

    def run(
        self,
        image_paths: list[Path],
        *,
        page_sizes: list[tuple[int, int]] | None,
    ) -> list[dict[str, Any]]:
        images = []
        for image_path in image_paths:
            with Image.open(image_path) as image:
                images.append(image.convert("RGB").copy())

        raw_results = self.model.batch_predict(
            images,
            batch_size=max(1, self.batch_size),
            use_paddlex_filter_boxes=self.use_paddlex_filter_boxes,
        )
        return _payload_from_raw_results(raw_results, page_sizes=page_sizes)

    def close(self) -> None:
        close = getattr(self.model, "close", None)
        if callable(close):
            close()


def run_persistent_sidecar() -> None:
    session: MineruDirectLayoutSession | None = None
    session_key: str | None = None
    for line in sys.stdin:
        request: dict[str, Any]
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            _write_response(None, ok=False, error=f"Invalid JSON request: {exc}")
            continue
        request_id = request.get("request_id")
        task = str(request.get("task") or "")
        try:
            if task == "shutdown":
                _write_response(request_id, ok=True, result={"ok": True})
                break
            if task == "health":
                _write_response(request_id, ok=True, result={"ok": True, "loaded": session is not None})
                continue
            if task != "layout":
                raise ValueError(f"Unsupported task: {task!r}")

            config = dict(request.get("config") or {})
            key = _session_key(config)
            if session is None or key != session_key:
                if session is not None:
                    session.close()
                session = MineruDirectLayoutSession(config)
                session_key = key

            image_paths = [Path(path) for path in request.get("image_paths") or []]
            page_sizes = _page_sizes(request.get("page_sizes"))
            result = session.run(image_paths, page_sizes=page_sizes)
            _write_response(request_id, ok=True, result=result)
        except Exception as exc:  # noqa: BLE001 - sidecar must report errors over JSONL.
            _write_response(request_id, ok=False, error=f"{exc!r}\n{traceback.format_exc()}")
    if session is not None:
        session.close()


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

    return _payload_from_raw_results(raw_results, page_sizes=page_sizes)


def _payload_from_raw_results(
    raw_results: Any,
    *,
    page_sizes: list[tuple[int, int]] | None,
) -> list[dict[str, Any]]:
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


def _session_key(config: dict[str, Any]) -> str:
    keys = (
        "mineru_layout_model_dir",
        "mineru_layout_device",
        "mineru_layout_batch_size",
        "mineru_layout_use_paddlex_filter_boxes",
    )
    return json.dumps({key: config.get(key) for key in keys}, sort_keys=True, ensure_ascii=False)


def _write_response(request_id: Any, *, ok: bool, result: Any = None, error: str | None = None) -> None:
    payload = {"request_id": request_id, "ok": ok}
    if ok:
        payload["result"] = result
    else:
        payload["error"] = error or "unknown sidecar error"
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


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
