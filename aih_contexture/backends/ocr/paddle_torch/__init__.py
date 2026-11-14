"""Optional native Paddle OCR inference; no external MinerU installation.

The factory is lazy so importing Contexture never requires this component's
optional dependencies or loads its models.
"""
from __future__ import annotations


def create_ocr(
    *, model_dir: str, lang: str = "ch", device: str = "cpu",
    model_spec: dict[str, str] | None = None,
    det_db_box_thresh: float = 0.3, det_db_unclip_ratio: float = 1.8,
    enable_merge_det_boxes: bool = True,
):
    from .engine import PaddleTorchOCR

    return PaddleTorchOCR(
        model_dir=model_dir, lang=lang, device=device, model_spec=model_spec,
        det_db_box_thresh=det_db_box_thresh, det_db_unclip_ratio=det_db_unclip_ratio,
        enable_merge_det_boxes=enable_merge_det_boxes,
    )
