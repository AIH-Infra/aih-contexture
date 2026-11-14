"""Native PP-DocLayoutV3 CPU inference with the official ONNX model.

Paddle/PaddleX and Transformers are not imported. We retain the upstream
postprocessor, including model reading order and mask-derived polygons.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml

from aih_contexture.backends.external_config import default_runtime_root

MODEL_REPO = "PaddlePaddle/PP-DocLayoutV3_onnx"
MODEL_REVISION = "46bbdf188bb0a772c08aed74882ce7e51a8f1ea6"
MODEL_FILES = ("inference.onnx", "inference.yml")


def native_v3_selected(config: dict[str, Any]) -> bool:
    default = "PP-DocLayoutV3" if config.get("layout_backend") == "paddle_pp_doclayout_v3" else "PP-DocLayout_plus-L"
    if (config.get("paddle_layout_model_name") or default) != "PP-DocLayoutV3":
        return False
    engine = config.get("paddle_layout_engine")
    if engine == "onnxruntime":
        return True
    if engine or config.get("paddle_layout_python") or config.get("paddle_python") or os.environ.get("CONTEXTURE_PADDLE_PYTHON"):
        return False
    # Saved SDK configurations predate the engine selector. Preserve explicit
    # GPU/framework options rather than treating them as a request for CPU.
    if config.get("paddle_layout_device") not in (None, "", "cpu"):
        return False
    if config.get("paddle_layout_enable_mkldnn") or config.get("paddle_layout_enable_cinn"):
        return False
    model_dir = config.get("paddle_layout_model_dir")
    if model_dir and any((Path(model_dir).expanduser() / name).is_file() for name in ("inference.pdiparams", "inference.pdmodel", "inference.json")):
        return False
    return True


def resolve_model_dir(config: dict[str, Any], *, download: bool = False) -> Path:
    allow_download = config.get("paddle_layout_allow_download", False)
    if not isinstance(allow_download, bool):
        raise ValueError("paddle_layout_allow_download must be a boolean (true or false).")
    value = config.get("paddle_layout_model_dir") or os.environ.get("CONTEXTURE_DOCLAYOUT_V3_MODEL_DIR")
    root = Path(value).expanduser().resolve() if value else default_runtime_root() / "contexture/data/shared/models/Layout/PP-DocLayoutV3_onnx"
    missing = [name for name in MODEL_FILES if not (root / name).is_file()]
    if missing and download and allow_download:
        from filelock import FileLock
        from huggingface_hub import hf_hub_download

        root.mkdir(parents=True, exist_ok=True)
        with FileLock(root / ".download.lock"):
            for name in MODEL_FILES:
                if not (root / name).is_file():
                    hf_hub_download(MODEL_REPO, name, revision=MODEL_REVISION, local_dir=root)
        missing = [name for name in MODEL_FILES if not (root / name).is_file()]
    if missing:
        raise FileNotFoundError(
            f"PP-DocLayoutV3 ONNX weights/config missing in {root}: {', '.join(missing)}. "
            "Set paddle_layout_model_dir or explicitly enable paddle_layout_allow_download."
        )
    return root


class PPDocLayoutV3OnnxRuntime:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    def run(self, image_paths: list[str | Path], *, page_sizes=None) -> list[dict[str, Any]]:
        if not image_paths:
            return []
        device = self.config.get("paddle_layout_device")
        if device not in (None, "", "cpu"):
            raise ValueError("Native PP-DocLayoutV3 ONNX uses CPU. Set paddle_layout_device=cpu; choose an explicit Paddle engine for an existing Paddle GPU deployment.")
        size = self.config.get("paddle_layout_img_size")
        if size not in (None, 0, 800):
            raise ValueError("The official PP-DocLayoutV3 ONNX graph requires an 800 x 800 input.")
        batch_size = int(self.config.get("paddle_layout_batch_size") or 1)
        if not 1 <= batch_size <= 8:
            raise ValueError("Native PP-DocLayoutV3 CPU batch size must be between 1 and 8.")
        threads = int(self.config.get("paddle_layout_cpu_threads") or min(4, os.cpu_count() or 1))
        if threads < 1:
            raise ValueError("paddle_layout_cpu_threads must be positive.")
        threshold = self.config.get("paddle_layout_threshold")
        threshold = 0.5 if threshold is None else float(threshold)
        if not 0 <= threshold <= 1:
            raise ValueError("paddle_layout_threshold must be between 0 and 1.")
        root = resolve_model_dir(self.config, download=True)
        import onnxruntime as ort
        from .doclayout_postprocess import LayoutAnalysisProcess, convert_polygon_to_quad

        settings = yaml.safe_load((root / "inference.yml").read_text(encoding="utf-8"))
        if settings["Global"]["model_name"] != "PP-DocLayoutV3":
            raise ValueError("The supplied inference.yml is not a PP-DocLayoutV3 model.")
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        session = ort.InferenceSession(str(root / "inference.onnx"), sess_options=options, providers=["CPUExecutionProvider"])
        if {item.name for item in session.get_inputs()} != {"im_shape", "image", "scale_factor"}:
            raise ValueError("Unexpected PP-DocLayoutV3 ONNX input contract.")
        postprocess = LayoutAnalysisProcess(labels=settings["label_list"], scale_size=[800, 800])
        payload = []
        for start in range(0, len(image_paths), batch_size):
            paths = image_paths[start:start + batch_size]
            images, sizes = [], []
            for path in paths:
                bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
                if bgr is None:
                    raise ValueError(f"Cannot read PP-DocLayoutV3 image: {path}")
                height, width = bgr.shape[:2]
                sizes.append((width, height))
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                resized = cv2.resize(rgb, (800, 800), interpolation=cv2.INTER_CUBIC)
                images.append((resized.astype(np.float32) / 255.0).transpose(2, 0, 1))
            boxes, counts, masks = session.run(None, {
                "image": np.ascontiguousarray(np.stack(images)),
                "im_shape": np.full((len(paths), 2), 800, dtype=np.float32),
                "scale_factor": np.array([[800 / h, 800 / w] for w, h in sizes], dtype=np.float32),
            })
            if boxes.ndim != 2 or boxes.shape[1] != 7 or len(counts) != len(paths) or int(np.sum(counts)) != len(boxes) or len(masks) != len(boxes):
                raise ValueError("Unexpected PP-DocLayoutV3 ONNX output contract.")
            if not np.isfinite(boxes).all():
                raise RuntimeError("PP-DocLayoutV3 produced non-finite boxes or scores.")
            outputs, offset = [], 0
            for count in counts:
                end = offset + int(count)
                outputs.append({"boxes": boxes[offset:end], "masks": masks[offset:end]})
                offset = end
            processed = postprocess(
                outputs, [{"ori_img_size": size} for size in sizes], threshold=threshold,
                layout_nms=self.config.get("paddle_layout_nms", False),
                layout_unclip_ratio=self.config.get("paddle_layout_unclip_ratio"),
                layout_merge_bboxes_mode=self.config.get("paddle_layout_merge_bboxes_mode"),
                layout_shape_mode="auto", filter_overlap_boxes=True,
            )
            for local_index, (path, size, result) in enumerate(zip(paths, sizes, processed)):
                normalized = []
                for position, box in enumerate(result):
                    box = dict(box)
                    polygon = box.get("polygon_points")
                    if polygon is not None:
                        box["polygon_points"] = np.asarray(polygon).tolist()
                        # Pipeline geometry is quadrilateral; retain full native
                        # contours in raw metadata rather than discarding them.
                        quad = convert_polygon_to_quad(polygon)
                        if quad is not None:
                            box["polygon"] = quad.tolist()
                    box["native_order"] = box.get("order")
                    box["order"] = position
                    normalized.append(box)
                index = start + local_index
                payload.append({"res": {
                    "input_path": str(path), "page_index": index,
                    "page_size": list(page_sizes[index] if page_sizes else size),
                    "model_name": "PP-DocLayoutV3", "engine": "onnxruntime", "device": "cpu",
                    "model_revision": MODEL_REVISION, "boxes": normalized,
                }})
        return payload
