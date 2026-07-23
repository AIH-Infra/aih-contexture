from __future__ import annotations

from typing import Any

from aih_contexture.vendor.mineru_vl_compat.table import normalize_mineru_table_content


def normalize_mineru_block(block: dict[str, Any]) -> dict[str, Any]:
    """Normalize a MinerU-VL raw/compatible block before Middle conversion."""
    normalized = dict(block)
    label = str(normalized.get("label") or normalized.get("type") or "").strip().lower()
    text = str(normalized.get("text") or normalized.get("content") or normalized.get("html") or "")

    if label == "table" or str(normalized.get("type") or "").strip().lower() == "table":
        table_content, table_meta = normalize_mineru_table_content(text)
        normalized["text"] = table_content
        normalized["html"] = table_content if "<table" in table_content.lower() else None
        normalized["mineru_table_format"] = table_meta
        if text != table_content:
            normalized["raw_mineru_content"] = text

    return normalized
