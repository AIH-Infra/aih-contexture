from __future__ import annotations

import json
import os
import importlib.util
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from aih_contexture.backends.external_config import default_paddle_python, external_project_root_from_python


class PaddleLayoutDetectionRuntime:
    """Run PaddleOCR LayoutDetection on page images and return raw JSON payloads."""

    def __init__(self, config: dict[str, Any] | None = None, *, predictor: Any = None):
        self.config = config or {}
        self.predictor = predictor

    @property
    def model_name(self) -> str:
        return str(self.config.get("paddle_layout_model_name") or "PP-DocLayout_plus-L")

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
            self.config.get("paddle_layout_python")
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
            raise RuntimeError("Paddle layout sidecar python is not configured.")
        with tempfile.TemporaryDirectory(prefix="contexture-paddle-layout-sidecar-") as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "job.json"
            result_path = temp_path / "result.json"
            job_path.write_text(
                json.dumps(
                    {
                        "task": "layout",
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
                    "Paddle layout sidecar failed with exit code "
                    f"{completed.returncode}.\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
                )
            return json.loads(result_path.read_text(encoding="utf-8"))

    def _create_predictor(self):
        if not self.is_available():
            backend = self.config.get("layout_backend") or self.config.get("external_layout_backend_name") or "paddle_pp_doclayout_plus_l"
            raise RuntimeError(
                "PaddleOCR is not available. Install paddleocr doc-parser dependencies before "
                f"selecting layout_backend={backend!r}, or configure paddle_layout_python / "
                "CONTEXTURE_PADDLE_PYTHON to a PaddleOCR environment."
            )
        from paddleocr import LayoutDetection

        init_kwargs: dict[str, Any] = {"model_name": self.model_name}
        optional_keys = {
            "paddle_layout_model_dir": "model_dir",
            "paddle_layout_device": "device",
            "paddle_layout_engine": "engine",
            "paddle_layout_threshold": "threshold",
            "paddle_layout_img_size": "img_size",
            "paddle_layout_enable_mkldnn": "enable_mkldnn",
            "paddle_layout_cpu_threads": "cpu_threads",
            "paddle_layout_enable_cinn": "enable_cinn",
            "paddle_layout_nms": "layout_nms",
            "paddle_layout_unclip_ratio": "layout_unclip_ratio",
            "paddle_layout_merge_bboxes_mode": "layout_merge_bboxes_mode",
        }
        for config_key, init_key in optional_keys.items():
            value = self.config.get(config_key)
            if value is not None and value != "":
                if init_key in {"enable_mkldnn", "enable_cinn", "layout_nms"}:
                    value = _coerce_bool(value)
                init_kwargs[init_key] = value
        init_kwargs.setdefault("enable_mkldnn", False)
        return LayoutDetection(**init_kwargs)

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
        batch_size = self.config.get("paddle_layout_batch_size")
        predict_kwargs: dict[str, Any] = {}
        if batch_size is not None and batch_size != "":
            predict_kwargs["batch_size"] = int(batch_size)
        if hasattr(predictor, "predict"):
            try:
                return list(predictor.predict(input_paths, **predict_kwargs))
            except TypeError:
                results = []
                for path in input_paths:
                    results.extend(list(predictor.predict(path)))
                return results
        if hasattr(predictor, "predict_iter"):
            return list(predictor.predict_iter(input_paths))
        raise TypeError("Paddle layout predictor must expose predict() or predict_iter().")

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
            raise ValueError(f"Unexpected Paddle layout result shape at page {index}: {payload!r}")
        if res.get("page_index") is None:
            res["page_index"] = index
        if page_size and "page_size" not in res:
            res["page_size"] = [float(page_size[0]), float(page_size[1])]
        res.setdefault("model_name", self.model_name)
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
    raise TypeError(f"Cannot extract JSON from Paddle layout result: {type(result)!r}")


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
