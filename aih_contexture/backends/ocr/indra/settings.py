"""Settings and environment discovery for the Indra OCR backend.

Indra (https://github.com/datalab-to/indra) is a small ONNX CPU OCR with layout labels and reading order.
Contexture never bundles its weights (modified OpenRAIL-M): the model folder is the user's, and nothing is
downloaded unless ``indra_allow_download`` is set.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

PYTHON_ENV = "CONTEXTURE_INDRA_PYTHON"
MODEL_DIR_ENV = "INDRA_OCR_MODEL_DIR"
MODES = ("auto", "ocr", "text")
MODEL_FILES = ("det.onnx", "rec.onnx", "meta.json")
DEFAULT_DPI = 200
# Flagging thresholds for pages worth a second look. Starting points from a handful of pages (clean print reads
# 0.96-0.99 mean line confidence; a long-s old-print page read 0.885 mean / 0.573 worst), not calibrated values.
REVIEW_MEAN_CONFIDENCE = 0.92
REVIEW_MIN_CONFIDENCE = 0.60
WORKER_PATH = Path(__file__).with_name("worker.py")


@dataclass(frozen=True, slots=True)
class IndraSettings:
    python: str | None = None
    model_dir: str | None = None
    mode: str = "auto"
    dpi: int = DEFAULT_DPI
    math: bool = False
    cores: int | None = None  # None: planned automatically
    allow_download: bool = False
    cache_dir: str | None = None
    timeout: int = 3600
    review_mean: float = REVIEW_MEAN_CONFIDENCE
    review_min: float = REVIEW_MIN_CONFIDENCE

    @classmethod
    def from_config(cls, config: Mapping[str, Any] | None) -> "IndraSettings":
        config = config or {}
        # force_ocr is not consulted: the config parser sets it for every run that has OCR enabled, so it carries no intent.
        mode = str(config.get("indra_mode") or "auto").strip().lower()
        if mode not in MODES:
            raise ValueError(f"indra_mode must be one of {', '.join(MODES)}, not {mode!r}")
        dpi = int(config.get("indra_dpi") or DEFAULT_DPI)
        if dpi < 72:
            raise ValueError("indra_dpi must be at least 72")
        cores = config.get("indra_cores")
        return cls(
            python=_text(config.get("indra_python")) or os.environ.get(PYTHON_ENV) or None,
            model_dir=_text(config.get("indra_model_dir")) or os.environ.get(MODEL_DIR_ENV) or None,
            mode=mode,
            dpi=dpi,
            math=bool(config.get("indra_math", False)),
            cores=int(cores) if cores not in (None, "", 0) else None,
            allow_download=bool(config.get("indra_allow_download", False)),
            cache_dir=_text(config.get("indra_cache_dir")) or None,
            timeout=int(config.get("indra_timeout") or 3600),
            review_mean=float(config.get("indra_review_mean") or REVIEW_MEAN_CONFIDENCE),
            review_min=float(config.get("indra_review_min") or REVIEW_MIN_CONFIDENCE),
        )

    def interpreter(self) -> str:
        """The Python that runs the worker: the configured sidecar, else this one if it can import Indra."""
        if self.python:
            return self.python
        if importlib.util.find_spec("indra_ocr") is not None and importlib.util.find_spec("onnxruntime") is not None:
            return sys.executable
        raise IndraUnavailable(
            "Indra OCR is not installed in this environment. Install aih-contexture[indra] "
            "in Contexture's current environment, or explicitly set "
            f"--indra_python (or {PYTHON_ENV}) to an existing Indra environment."
        )


class IndraUnavailable(RuntimeError):
    """The Indra interpreter or model folder is missing; the message says how to fix it."""


def _text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def missing_model_files(model_dir: str | Path, *, math: bool = False) -> list[str]:
    folder = Path(model_dir)
    wanted = list(MODEL_FILES)
    if math:
        wanted += ["mathcls.onnx", "math_enc.onnx", "math_dec_init.onnx", "math_dec_step.onnx", "math_meta.json"]
    return [name for name in wanted if not (folder / name).exists()]


def check_ready(settings: IndraSettings) -> list[str]:
    """Problems that would stop a run, in plain words; empty when ready."""
    problems = []
    try:
        interpreter = settings.interpreter()
        if settings.python and not Path(interpreter).exists():
            problems.append(f"indra_python does not exist: {interpreter}")
    except IndraUnavailable as exc:
        problems.append(str(exc))
    if settings.model_dir:
        missing = missing_model_files(settings.model_dir, math=settings.math)
        if missing:
            problems.append(f"model folder {settings.model_dir} lacks {', '.join(missing)}")
    elif not settings.allow_download:
        problems.append(
            f"no Indra model folder: set --indra_model_dir (or {MODEL_DIR_ENV}) to a folder with "
            "det.onnx, rec.onnx, meta.json (order.onnx adds layout labels), or pass --indra_allow_download "
            "to fetch datalab-to/indra-ocr from Hugging Face (weights: modified OpenRAIL-M, not bundled)."
        )
    return problems
