"""Contexture-owned orchestration for the vendored Torch OCR components."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .geometry import sorted_boxes, merge_det_boxes, get_rotate_crop_image_for_text_rec
from .infer import pytorchocr_utility as utility
from .infer.predict_det import TextDetector
from .infer.predict_rec import TextRecognizer


class PaddleTorchOCR:
    """Detect and recognize an RGB page, returning Paddle-compatible OCR rows."""

    def __init__(
        self, *, model_dir: str, lang: str, device: str,
        model_spec: dict[str, str] | None = None,
        det_db_box_thresh: float, det_db_unclip_ratio: float,
        enable_merge_det_boxes: bool,
    ):
        if model_spec is None:
            from aih_contexture.backends.ocr.paddle_torch_resources import model_spec as select_models
            model_spec = select_models(lang)
        root = Path(model_dir)
        resources = Path(__file__).with_name("resources")
        args = utility.init_args().parse_args([])
        args.det_model_path = str(root / model_spec["det"])
        args.rec_model_path = str(root / model_spec["rec"])
        args.rec_char_dict_path = str(resources / "dict" / model_spec["dict"])
        for path in (args.det_model_path, args.rec_model_path, args.rec_char_dict_path):
            if not Path(path).is_file():
                raise FileNotFoundError(f"Paddle OCR Torch resource missing: {path}")
        args.device = device
        args.det_db_box_thresh = det_db_box_thresh
        args.det_db_unclip_ratio = det_db_unclip_ratio
        args.rec_batch_num = 6
        self.is_seal = lang in {"seal", "seal_lite"}
        self.enable_merge_det_boxes = enable_merge_det_boxes and not self.is_seal
        if self.is_seal:
            from .seal_crop import CropByPolys, SortPolyBoxes
            args.det_limit_side_len = 736
            args.det_limit_type = "min"
            args.det_db_thresh = 0.2
            args.det_db_box_thresh = 0.6
            args.det_db_unclip_ratio = 0.5
            args.det_box_type = "poly"
            args.use_dilation = False
            args.drop_score = 0
            self._seal_sort = SortPolyBoxes()
            self._seal_crop = CropByPolys(det_box_type="poly")
        self.drop_score = args.drop_score
        self.text_detector = TextDetector(args)
        self.text_recognizer = TextRecognizer(args)

    def ocr(self, rgb_image: np.ndarray) -> list:
        image = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)
        boxes, _ = self.text_detector(image)
        if boxes is None or len(boxes) == 0:
            return [[]]
        if self.is_seal:
            boxes = self._seal_sort(boxes)
            crops = self._seal_crop(image, boxes)
        else:
            boxes = sorted_boxes(boxes)
            if self.enable_merge_det_boxes:
                boxes = merge_det_boxes(boxes)
            crops = [get_rotate_crop_image_for_text_rec(image, np.array(box, copy=True)) for box in boxes]
        recognized, _ = self.text_recognizer(crops)
        return [[
            [np.asarray(box).tolist(), (text, float(score))]
            for box, (text, score) in zip(boxes, recognized)
            if score >= self.drop_score
        ]]
