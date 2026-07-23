from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


class PaddleStructureV3Runtime:
    """Run PaddleOCR PP-StructureV3 and return raw document JSON payloads."""

    def __init__(self, config: dict[str, Any] | None = None, *, pipeline: Any = None):
        self.config = config or {}
        self.pipeline = pipeline

    @property
    def lang(self) -> str:
        return str(self.config.get("paddle_structure_lang") or "ch")

    @property
    def ocr_version(self) -> str:
        return str(self.config.get("paddle_structure_ocr_version") or "PP-OCRv5")

    def is_available(self) -> bool:
        return importlib.util.find_spec("paddleocr") is not None

    def run(self, input_path: str | Path) -> list[dict[str, Any]]:
        pipeline = self.pipeline or self._create_pipeline()
        close_pipeline = self.pipeline is None
        try:
            raw_results = self._predict(pipeline, input_path)
            return [self._payload_from_result(result, index=index) for index, result in enumerate(raw_results)]
        finally:
            if close_pipeline and hasattr(pipeline, "close"):
                pipeline.close()

    def _create_pipeline(self):
        if not self.is_available():
            raise RuntimeError(
                "PaddleOCR is not available. Install PaddleOCR doc-parser dependencies "
                "before running PP-StructureV3."
            )
        from paddleocr import PPStructureV3

        init_kwargs: dict[str, Any] = {
            "lang": self.lang,
            "ocr_version": self.ocr_version,
        }
        optional_keys = {
            "paddle_structure_device": "device",
            "paddle_structure_engine": "engine",
            "paddle_structure_paddlex_config": "paddlex_config",
            "paddle_structure_layout_detection_model_name": "layout_detection_model_name",
            "paddle_structure_layout_detection_model_dir": "layout_detection_model_dir",
            "paddle_structure_text_detection_model_name": "text_detection_model_name",
            "paddle_structure_text_detection_model_dir": "text_detection_model_dir",
            "paddle_structure_text_recognition_model_name": "text_recognition_model_name",
            "paddle_structure_text_recognition_model_dir": "text_recognition_model_dir",
            "paddle_structure_use_doc_orientation_classify": "use_doc_orientation_classify",
            "paddle_structure_use_doc_unwarping": "use_doc_unwarping",
            "paddle_structure_use_textline_orientation": "use_textline_orientation",
            "paddle_structure_use_table_recognition": "use_table_recognition",
            "paddle_structure_use_formula_recognition": "use_formula_recognition",
            "paddle_structure_use_chart_recognition": "use_chart_recognition",
            "paddle_structure_use_region_detection": "use_region_detection",
            "paddle_structure_use_seal_recognition": "use_seal_recognition",
            "paddle_structure_format_block_content": "format_block_content",
            "paddle_structure_layout_threshold": "layout_threshold",
            "paddle_structure_layout_nms": "layout_nms",
            "paddle_structure_layout_unclip_ratio": "layout_unclip_ratio",
            "paddle_structure_layout_merge_bboxes_mode": "layout_merge_bboxes_mode",
            "paddle_structure_text_rec_score_thresh": "text_rec_score_thresh",
        }
        for config_key, init_key in optional_keys.items():
            value = self.config.get(config_key)
            if value is not None and value != "":
                if init_key.startswith("use_") or init_key in {"format_block_content", "layout_nms"}:
                    value = _coerce_bool(value)
                init_kwargs[init_key] = value
        init_kwargs.setdefault("use_doc_orientation_classify", False)
        init_kwargs.setdefault("use_doc_unwarping", False)
        init_kwargs.setdefault("use_textline_orientation", False)
        try:
            return PPStructureV3(**init_kwargs)
        except RuntimeError as exc:
            message = str(exc)
            if "dependency error" in message.lower() or "requires additional dependencies" in message.lower():
                raise RuntimeError(
                    "PP-StructureV3 requires PaddleX OCR extras. Install the matching "
                    "PaddleX extras in the active environment, for example: "
                    'pip install "paddlex[ocr]"'
                ) from exc
            raise

    def _predict(self, pipeline: Any, input_path: str | Path) -> list[Any]:
        if hasattr(pipeline, "predict"):
            try:
                return list(pipeline.predict(input=str(input_path)))
            except TypeError:
                return list(pipeline.predict(str(input_path)))
        if hasattr(pipeline, "predict_iter"):
            try:
                return list(pipeline.predict_iter(input=str(input_path)))
            except TypeError:
                return list(pipeline.predict_iter(str(input_path)))
        raise TypeError("PP-StructureV3 pipeline must expose predict() or predict_iter().")

    def _payload_from_result(self, result: Any, *, index: int) -> dict[str, Any]:
        payload = _result_json(result)
        if "res" not in payload:
            payload = {"res": payload}
        res = payload.setdefault("res", {})
        if not isinstance(res, dict):
            raise ValueError(f"Unexpected PP-StructureV3 result shape at page {index}: {payload!r}")
        if res.get("page_index") is None:
            res["page_index"] = index
        res.setdefault("pipeline", "PP-StructureV3")
        res.setdefault("lang", self.lang)
        res.setdefault("ocr_version", self.ocr_version)
        return payload


def _result_json(result: Any) -> dict[str, Any]:
    value = getattr(result, "json", None)
    if callable(value):
        value = value()
    if isinstance(value, dict):
        return value
    if isinstance(result, dict):
        return result
    if hasattr(result, "to_dict"):
        value = result.to_dict()
        if isinstance(value, dict):
            return value
    raise TypeError(f"Cannot extract JSON from PP-StructureV3 result: {type(result)!r}")


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)
