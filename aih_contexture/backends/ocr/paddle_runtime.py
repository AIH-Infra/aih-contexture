from __future__ import annotations

import json
import os
import importlib.util
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from aih_contexture.backends.external_config import default_paddle_python, external_project_root_from_python


class PaddleOcrRuntime:
    """Run PaddleOCR OCR on page images and return raw JSON payloads."""

    def __init__(self, config: dict[str, Any] | None = None, *, predictor: Any = None):
        self.config = config or {}
        self.predictor = predictor

    @property
    def ocr_version(self) -> str:
        return str(self.config.get("paddle_ocr_version") or "PP-OCRv5")

    @property
    def lang(self) -> str:
        return str(self.config.get("paddle_ocr_lang") or "ch")

    def is_available(self) -> bool:
        return importlib.util.find_spec("paddleocr") is not None

    def run(self, image_paths: list[str | Path], *, page_sizes: list[tuple[int, int]] | None = None) -> list[dict[str, Any]]:
        if not image_paths:
            return []
        if self.predictor is None and self._should_use_sidecar():
            return self._run_sidecar(image_paths, page_sizes=page_sizes)
        predictor = self.predictor or self._create_predictor()
        close_predictor = self.predictor is None
        try:
            raw_results = self._predict(predictor, image_paths)
            return [
                self._payload_from_result(result, index=index, page_size=_page_size(page_sizes, index))
                for index, result in enumerate(raw_results)
            ]
        finally:
            if close_predictor and hasattr(predictor, "close"):
                predictor.close()

    def _should_use_sidecar(self) -> bool:
        if str(self.config.get("paddle_runtime_mode") or "").lower() == "in_process":
            return False
        return self._sidecar_python() is not None

    def _sidecar_python(self) -> str | None:
        value = (
            self.config.get("paddle_ocr_python")
            or self.config.get("paddle_python")
            or default_paddle_python()
        )
        return str(value) if value else None

    def _run_sidecar(
        self,
        image_paths: list[str | Path],
        *,
        page_sizes: list[tuple[int, int]] | None,
    ) -> list[dict[str, Any]]:
        python = self._sidecar_python()
        if not python:
            raise RuntimeError("Paddle OCR sidecar python is not configured.")
        with tempfile.TemporaryDirectory(prefix="contexture-paddle-ocr-sidecar-") as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "job.json"
            result_path = temp_path / "result.json"
            job_path.write_text(
                json.dumps(
                    {
                        "task": "ocr",
                        "image_paths": [str(path) for path in image_paths],
                        "page_sizes": page_sizes,
                        "config": self.config,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [python, "-m", "aih_contexture.scripts.paddle_sidecar", "--job-json", str(job_path), "--result-json", str(result_path)],
                cwd=Path(__file__).resolve().parents[3],
                env=self._env(python),
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    "Paddle OCR sidecar failed with exit code "
                    f"{completed.returncode}.\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
                )
            return json.loads(result_path.read_text(encoding="utf-8"))

    def _create_predictor(self):
        if not self.is_available():
            raise RuntimeError(
                "PaddleOCR is not available. Install paddleocr dependencies before "
                "running the Paddle OCR runtime, or configure paddle_ocr_python / "
                "CONTEXTURE_PADDLE_PYTHON to a PaddleOCR environment."
            )
        from paddleocr import PaddleOCR

        init_kwargs: dict[str, Any] = {
            "ocr_version": self.ocr_version,
            "lang": self.lang,
        }
        optional_keys = {
            "paddle_ocr_device": "device",
            "paddle_ocr_engine": "engine",
            "paddle_ocr_enable_mkldnn": "enable_mkldnn",
            "paddle_ocr_cpu_threads": "cpu_threads",
            "paddle_ocr_use_doc_orientation_classify": "use_doc_orientation_classify",
            "paddle_ocr_use_doc_unwarping": "use_doc_unwarping",
            "paddle_ocr_use_textline_orientation": "use_textline_orientation",
            "paddle_ocr_text_det_limit_side_len": "text_det_limit_side_len",
            "paddle_ocr_text_det_limit_type": "text_det_limit_type",
            "paddle_ocr_text_det_thresh": "text_det_thresh",
            "paddle_ocr_text_det_box_thresh": "text_det_box_thresh",
            "paddle_ocr_text_det_unclip_ratio": "text_det_unclip_ratio",
            "paddle_ocr_text_rec_score_thresh": "text_rec_score_thresh",
            "paddle_ocr_text_detection_model_name": "text_detection_model_name",
            "paddle_ocr_text_detection_model_dir": "text_detection_model_dir",
            "paddle_ocr_text_recognition_model_name": "text_recognition_model_name",
            "paddle_ocr_text_recognition_model_dir": "text_recognition_model_dir",
        }
        for config_key, init_key in optional_keys.items():
            value = self.config.get(config_key)
            if value is not None and value != "":
                if init_key in {"enable_mkldnn", "use_doc_orientation_classify", "use_doc_unwarping", "use_textline_orientation"}:
                    value = _coerce_bool(value)
                elif init_key == "device":
                    value = _normalize_paddle_device(value)
                init_kwargs[init_key] = value
        init_kwargs.setdefault("enable_mkldnn", False)
        init_kwargs.setdefault("use_doc_orientation_classify", False)
        init_kwargs.setdefault("use_doc_unwarping", False)
        init_kwargs.setdefault("use_textline_orientation", False)
        return PaddleOCR(**init_kwargs)

    def _env(self, python: str | None) -> dict[str, str]:
        env = os.environ.copy()
        repo_root = str(Path(__file__).resolve().parents[3])
        python_paths = [repo_root]
        external_root = external_project_root_from_python(python)
        if external_root:
            python_paths.append(str(external_root))
        existing = env.get("PYTHONPATH")
        if existing:
            python_paths.append(existing)
        env["PYTHONPATH"] = os.pathsep.join(python_paths)
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        return env

    def _predict(self, predictor: Any, image_paths: list[str | Path]) -> list[Any]:
        input_paths = [str(path) for path in image_paths]
        if hasattr(predictor, "predict"):
            try:
                results = predictor.predict(input_paths)
                return list(results)
            except TypeError:
                results = []
                for path in input_paths:
                    results.extend(list(predictor.predict(path)))
                return results
        if hasattr(predictor, "ocr"):
            results = []
            for path in input_paths:
                results.extend(_legacy_ocr_to_results(predictor.ocr(path), input_path=path))
            return results
        raise TypeError("Paddle OCR predictor must expose predict() or ocr().")

    def _payload_from_result(
        self,
        result: Any,
        *,
        index: int,
        page_size: tuple[int, int] | None,
    ) -> dict[str, Any]:
        payload = _result_json(result)
        if "res" not in payload:
            payload = {"res": payload}
        res = payload.setdefault("res", {})
        if not isinstance(res, dict):
            raise ValueError(f"Unexpected Paddle OCR result shape at page {index}: {payload!r}")
        if res.get("page_index") is None:
            res["page_index"] = index
        if page_size and "page_size" not in res:
            res["page_size"] = [float(page_size[0]), float(page_size[1])]
        res.setdefault("ocr_version", self.ocr_version)
        res.setdefault("lang", self.lang)
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
    raise TypeError(f"Cannot extract JSON from Paddle OCR result: {type(result)!r}")


def _legacy_ocr_to_results(value: Any, *, input_path: str) -> list[dict[str, Any]]:
    page_items = value[0] if isinstance(value, list) and value else value
    rec_texts: list[str] = []
    rec_scores: list[float] = []
    rec_boxes: list[Any] = []
    if isinstance(page_items, list):
        for item in page_items:
            if not isinstance(item, list | tuple) or len(item) < 2:
                continue
            rec_boxes.append(item[0])
            text_score = item[1]
            if isinstance(text_score, list | tuple) and text_score:
                rec_texts.append(str(text_score[0]))
                if len(text_score) > 1 and isinstance(text_score[1], (int, float)):
                    rec_scores.append(float(text_score[1]))
                else:
                    rec_scores.append(0.0)
    return [{"input_path": input_path, "rec_texts": rec_texts, "rec_scores": rec_scores, "rec_boxes": rec_boxes}]


def _page_size(page_sizes: list[tuple[int, int]] | None, index: int) -> tuple[int, int] | None:
    if page_sizes is None or index >= len(page_sizes):
        return None
    return page_sizes[index]


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _normalize_paddle_device(value: Any) -> Any:
    device = str(value or "").strip().lower()
    match = re.fullmatch(r"gpu:(\d+)", device)
    if not match:
        return value

    requested_id = int(match.group(1))
    gpu_count = _paddle_gpu_count()
    if gpu_count is None or requested_id < gpu_count:
        return value
    if gpu_count > 0:
        return "gpu:0"
    return "cpu"


def _paddle_gpu_count() -> int | None:
    try:
        import paddle

        cuda = getattr(getattr(paddle, "device", None), "cuda", None)
        device_count = getattr(cuda, "device_count", None)
        if callable(device_count):
            return int(device_count())
    except Exception:
        return None
    return None
