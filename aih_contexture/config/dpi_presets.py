"""DPI presets for pipeline layout and OCR rendering."""

from __future__ import annotations


LAYOUT_QUALITY_PRESETS = {
    "fast": 96,
    "standard": 144,
    "high": 192,
}

OCR_QUALITY_PRESETS = {
    "low": 192,
    "medium": 300,
    "high": 400,
}

OCR_BACKEND_DEFAULT_QUALITY = {
    "surya": "low",
    "paddle_ocr_v5": "low",
    "paddleocr_vl_ocr": "medium",
    "tesseract": "medium",
    "calamari": "medium",
    "vlm": "medium",
    "vlm_ocr": "medium",
}

LAYOUT_BACKEND_DEFAULT_DPI = {
    "surya": 96,
    "mineru_pp_doclayout_v2": 200,
    "mineru_pp_doclayout_v2_direct": 200,
    "paddle_pp_doclayout_plus_l": 144,
    "paddle_pp_doclayout_v3": 144,
    "vlm": 96,
    "vlm_layout": 96,
    "external_layout_sidecar": 96,
}

_QUALITY_ALIASES = {
    "fast": "low",
    "standard": "medium",
}


def normalize_backend_name(value: str | None, default: str = "surya") -> str:
    return str(value or default).strip().lower().replace("-", "_")


def normalize_quality(value: str | None, default: str) -> str:
    normalized = str(value or default).strip().lower().replace("-", "_")
    return _QUALITY_ALIASES.get(normalized, normalized)


def positive_dpi(value: int | str | None) -> int | None:
    if value is None:
        return None
    dpi = int(value)
    if dpi <= 0:
        raise ValueError("DPI values must be positive integers.")
    return dpi


def get_layout_dpi(
    backend: str | None,
    *,
    surya_quality: str | None = "fast",
    override: int | str | None = None,
) -> int:
    explicit = positive_dpi(override)
    if explicit is not None:
        return explicit

    backend_name = normalize_backend_name(backend)
    if backend_name == "surya":
        quality = str(surya_quality or "fast").strip().lower().replace("-", "_")
        return LAYOUT_QUALITY_PRESETS.get(quality, LAYOUT_QUALITY_PRESETS["fast"])
    return LAYOUT_BACKEND_DEFAULT_DPI.get(backend_name, 96)


def get_ocr_quality_for_backend(
    backend: str | None,
    quality: str | None = "auto",
) -> str:
    backend_name = normalize_backend_name(backend)
    requested = str(quality or "auto").strip().lower().replace("-", "_")
    if requested == "auto":
        return OCR_BACKEND_DEFAULT_QUALITY.get(backend_name, "low")
    return normalize_quality(requested, "low")


def get_ocr_dpi(
    backend: str | None,
    *,
    quality: str | None = "auto",
    override: int | str | None = None,
) -> int:
    explicit = positive_dpi(override)
    if explicit is not None:
        return explicit

    resolved_quality = get_ocr_quality_for_backend(backend, quality)
    return OCR_QUALITY_PRESETS.get(resolved_quality, OCR_QUALITY_PRESETS["low"])
