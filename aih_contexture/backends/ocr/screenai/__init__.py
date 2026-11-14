"""Vendored from locro (https://github.com/sergiocorreia/clv-locro, commit ba53ee2).

Copyright (c) 2026 Sergio Correia. License: MIT (see NOTICE).
A ctypes wrapper that loads Chrome's proprietary ``chrome_screen_ai.dll``
in-process and calls its exported C API directly -- no Chrome process and
no network access at runtime.  The DLL and model files are NOT distributed
with this package: resolve them via
``aih_contexture.backends.external_config.default_screenai_model_dir``.
Local modifications: upstream modules are copied verbatim, except cli.py
(the standalone typer CLI), which was not vendored. This __init__ adds one
seam on top: ``ScreenAI`` is subclassed so a bare ``ScreenAI()`` resolves
its component directory through
``aih_contexture.backends.external_config.ensure_screenai_model_dir``
(env override -> managed cache -> locro install -> Chrome) instead of
upstream's Chrome-first discovery; pass ``model_dir=`` explicitly to
bypass the policy.
"""

from pathlib import Path

from ._download import download_component
from .models import BoundingBox, OcrBlock, OcrLine, OcrPage, OcrResult, OcrWord
from .ocr import ScreenAI as _UpstreamScreenAI


class ScreenAI(_UpstreamScreenAI):
    """Upstream wrapper with Contexture's managed-cache default resolution."""

    def __init__(self, model_dir: Path | None = None, *, light_mode: bool = False):
        if model_dir is None:
            from aih_contexture.backends.external_config import ensure_screenai_model_dir

            model_dir = Path(ensure_screenai_model_dir())
        super().__init__(model_dir=model_dir, light_mode=light_mode)


__all__ = [
    "BoundingBox",
    "OcrBlock",
    "OcrLine",
    "OcrPage",
    "OcrResult",
    "OcrWord",
    "ScreenAI",
    "download_component",
]
