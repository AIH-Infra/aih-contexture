from __future__ import annotations

from typing import Any


MARGINAL_OUTPUT_MODES = ("line_markers", "margin_comments", "plain", "drop")


def normalize_marginal_output_mode(value: Any, *, enable_marginal_detection: bool) -> str:
    mode = str(value or "").strip().lower().replace("-", "_")
    if not enable_marginal_detection and mode in {"line_markers", "margin_comments"}:
        return "drop"
    if mode in MARGINAL_OUTPUT_MODES:
        return mode
    return "line_markers" if enable_marginal_detection else "drop"
