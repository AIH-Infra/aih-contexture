from __future__ import annotations

import json
from typing import Any


def render_middle_debug_markdown(
    data: dict[str, Any],
    *,
    max_text_chars: int = 240,
    include_geometry: bool = True,
) -> str:
    pages = data.get("pages", []) if isinstance(data, dict) else []
    lines = [
        "# Contexture Middle Debug Preview",
        "",
        "<!-- ContextureDebug: renderer=middle_debug_markdown purpose=inspection -->",
        "",
        f"- schema_version: `{data.get('schema_version', '')}`",
        f"- source_name: `{data.get('source_name', '')}`",
        f"- page_count: `{data.get('page_count', len(pages) if isinstance(pages, list) else 0)}`",
        f"- backends: `{_compact_json(data.get('backends', {}))}`",
    ]

    metadata = data.get("metadata")
    if metadata:
        lines.append(f"- metadata: `{_compact_json(metadata)}`")

    if not isinstance(pages, list):
        lines.extend(["", "> Invalid Middle JSON: `pages` is not a list."])
        return "\n".join(lines).rstrip() + "\n"

    sorted_pages = sorted((page for page in pages if isinstance(page, dict)), key=lambda page: int(page.get("index", 0)))
    final_anchor = 0
    for page in sorted_pages:
        page_index = int(page.get("index", 0))
        final_anchor = max(final_anchor, page_index + 1)
        lines.extend(_render_page(page, max_text_chars=max_text_chars, include_geometry=include_geometry))

    lines.extend(["", f"{{{final_anchor}}}", ""])
    return "\n".join(lines).rstrip() + "\n"


def _render_page(page: dict[str, Any], *, max_text_chars: int, include_geometry: bool) -> list[str]:
    page_index = int(page.get("index", 0))
    anchor_start = page.get("anchor_start", page_index)
    anchor_end = page.get("anchor_end", page_index + 1)
    width = page.get("width")
    height = page.get("height")
    printed_page = page.get("printed_page")

    lines = [
        "",
        f"{{{anchor_start}}}",
        "",
        f"## Page {page_index}",
        "",
        f"<!-- PageDebug: index={page_index} anchors={{{anchor_start}}}-{{{anchor_end}}} size={_format_size(width, height)} printed={_quote_attr(printed_page)} -->",
        "",
    ]

    blocks = page.get("blocks", [])
    if not isinstance(blocks, list) or not blocks:
        lines.append("_No blocks._")
        return lines

    for block in sorted((block for block in blocks if isinstance(block, dict)), key=lambda item: (int(item.get("order", 0)), str(item.get("id", "")))):
        lines.extend(_render_block(block, max_text_chars=max_text_chars, include_geometry=include_geometry))

    return lines


def _render_block(block: dict[str, Any], *, max_text_chars: int, include_geometry: bool) -> list[str]:
    block_type = block.get("type", "Unknown")
    block_id = block.get("id", "")
    order = block.get("order", "")
    anchor_start = block.get("anchor_start", block.get("page_index", ""))
    anchor_end = block.get("anchor_end", "")
    confidence = block.get("confidence")
    provenance = _first_provenance(block.get("provenance"))
    raw_label = provenance.get("raw_label") or (block.get("attrs") or {}).get("raw_label")
    backend = provenance.get("backend")
    model = provenance.get("model")

    fields = [
        f"id={_quote_attr(block_id)}",
        f"type={_quote_attr(block_type)}",
        f"order={order}",
        f"anchors={{{anchor_start}}}-{{{anchor_end}}}",
    ]
    if raw_label is not None:
        fields.append(f"raw_label={_quote_attr(raw_label)}")
    if backend:
        fields.append(f"backend={_quote_attr(backend)}")
    if model:
        fields.append(f"model={_quote_attr(model)}")
    if confidence is not None:
        fields.append(f"confidence={confidence}")
    if include_geometry and block.get("bbox") is not None:
        fields.append(f"bbox={_format_number_list(block.get('bbox'))}")

    lines = [
        f"### {block_type} `{block_id}`",
        "",
        f"<!-- BlockDebug: {' '.join(fields)} -->",
    ]

    text = _truncate_text(str(block.get("text") or ""), max_text_chars)
    if text:
        lines.extend(["", _quote_text(text)])
    else:
        lines.extend(["", "_No text._"])

    attrs = block.get("attrs")
    if attrs:
        safe_attrs = {
            key: value
            for key, value in attrs.items()
            if key not in {"raw"} and value not in (None, "", [], {})
        }
        if safe_attrs:
            lines.extend(["", f"`attrs`: `{_compact_json(safe_attrs)}`"])

    lines.append("")
    return lines


def _first_provenance(value: Any) -> dict[str, Any]:
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    return {}


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _format_size(width: Any, height: Any) -> str:
    if width is None or height is None:
        return "unknown"
    return f"{width}x{height}"


def _format_number_list(value: Any) -> str:
    if not isinstance(value, list):
        return "[]"
    formatted = []
    for item in value:
        if isinstance(item, float):
            formatted.append(f"{item:g}")
        else:
            formatted.append(str(item))
    return "[" + ",".join(formatted) + "]"


def _quote_attr(value: Any) -> str:
    text = str(value) if value is not None else ""
    return json.dumps(text, ensure_ascii=False)


def _truncate_text(text: str, max_chars: int) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if max_chars <= 0 or len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1].rstrip() + "…"


def _quote_text(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.split("\n"))
