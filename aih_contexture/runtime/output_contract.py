from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

_SAFE_RE = re.compile(r"[<>:\"/\\|?*\x00-\x1f]+")
_SPACE_RE = re.compile(r"\s+")
# Windows 保留设备名：即使带扩展名（CON.md）在旧版 Windows 上也无法创建。
_WIN_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def safe_name(value: str | os.PathLike[str], fallback: str = "document") -> str:
    # Input names can come from a Windows client while running on macOS/Linux.
    # Interpret both path separators before sanitizing the document basename.
    name = Path(os.fspath(value).replace("\\", "/")).name
    text = Path(name).stem if Path(name).suffix else name
    text = _SAFE_RE.sub("_", str(text).strip())
    text = _SPACE_RE.sub(" ", text).strip(" .")
    if text.upper() in _WIN_RESERVED:
        text += "_"
    return text or fallback


def timestamp_token(value: datetime | None = None) -> str:
    return (value or datetime.now()).strftime("%Y%m%d_%H%M%S")


def document_output_folder(
    output_root: str | os.PathLike[str],
    source_name: str | os.PathLike[str],
    *,
    started_at: datetime | None = None,
) -> str:
    root = Path(output_root)
    stem = safe_name(source_name)
    root.mkdir(parents=True, exist_ok=True)
    base = root / f"{stem}_{timestamp_token(started_at)}"
    candidate = base
    index = 2
    while True:
        try:
            # Reserve the directory even before the first artifact is written.
            # An existence check followed by exist_ok=True allows concurrent
            # jobs (and sequential reservations of empty folders) to collide.
            candidate.mkdir(exist_ok=False)
        except FileExistsError:
            candidate = root / f"{base.name}_{index}"
            index += 1
        else:
            return os.fspath(candidate)


def document_output_basename(source_name: str | os.PathLike[str], start_page=None, end_page=None) -> str:
    stem = safe_name(source_name)
    if start_page is not None and end_page is not None:
        return f"{stem}_p{start_page}-{end_page}"
    return stem


def model_slug(value: object, fallback: str = "unknown") -> str:
    """Return a stable filesystem-safe model label.

    Multiple models can be reported by the Pipeline route.  Preserve their
    configured order in the archive label rather than serialising a Python
    list representation.  The result is capped so that API model names
    (which can be arbitrarily long) cannot push archive names past
    filesystem limits — archives get a 64-char slug budget.
    """
    if isinstance(value, (list, tuple, set)):
        # 每个成员独立限长：整体截断会把排在后面的后端整个截掉，
        # 造成"命名不反映实际后端"的另一种形态。
        parts = [_cap_slug(model_slug(item, ""), 24) for item in value if item not in (None, "")]
        text = "_".join(part for part in parts if part)
        return _cap_slug(text) or fallback
    text = str(value or fallback).strip().lower()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "_", text)
    return _cap_slug(text.strip("_")) or fallback


def _cap_slug(text: str, limit: int = 64) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip("_") or text[:1]


def effective_backend_label(actual_backends: object, *, fallback: str = "none") -> list[str]:
    """Normalise *actually executed* backends into archive-name labels (P1-9).

    The archive name must describe what really ran, never fall back to UI
    configuration that was not executed.  A disabled OCR stage reports
    ``none``; when every reported backend is ``none`` (or nothing was reported
    at all) the label collapses to a single ``fallback`` label.

    Kept as a pure function so the contract is unit-testable — the previous
    inline expression inside the Streamlit body could not be reached by tests.
    """
    if actual_backends is None:
        return [fallback]
    if isinstance(actual_backends, str):
        items: list[object] = [actual_backends]
    elif isinstance(actual_backends, (list, tuple, set)):
        items = list(actual_backends)
    else:
        items = [actual_backends]

    labels: list[str] = []
    for item in items:
        if item in (None, ""):
            continue
        text = str(item).strip()
        if not text or text.lower() == "none":
            continue
        if text not in labels:
            labels.append(text)
    return labels or [fallback]


def _coerce_datetime(value: object) -> datetime | None:
    """Accept datetime or ISO-8601 strings so batch start times survive str round-trips."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def zip_name(
    *,
    mode: str,
    processing_id: str,
    started_at: object = None,
    ocr_model: object = None,
    layout_model: object = None,
    vlm_model: object = None,
) -> str:
    started = _coerce_datetime(started_at)
    if mode == "pipeline":
        label = f"{model_slug(ocr_model, 'none')}_{model_slug(layout_model, 'none')}"
    elif mode in {"vlm_generalized", "vlm_specialized"}:
        label = model_slug(vlm_model, mode)
    elif mode == "structured_source":
        label = "structured_source"
    elif mode == "markdown_postprocess":
        label = "markdown_postprocess"
    else:
        label = model_slug(mode)
    return f"{label}_{timestamp_token(started).split('_')[0]}_{model_slug(processing_id, '0000')}.zip"
