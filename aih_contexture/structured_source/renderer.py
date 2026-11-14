from __future__ import annotations

import json
import re
from html import escape
from typing import Any


def _markdown_text(text: str) -> str:
    text = text.strip()
    if re.fullmatch(r"\{\d+\}", text):
        return "\\" + text[:-1] + "\\}"
    if re.match(r"^\d+\.\s", text):
        text = re.sub(r"^(\d+)\.", r"\1\\.", text)
    return text


def render_scholarly_markdown(document: dict[str, Any]) -> str:
    metadata = document.get("metadata") or {}
    titles = metadata.get("titles") or []
    title = next((item.get("value") for item in titles if item.get("value")), document["source"]["name"])
    lines = [f"# {_markdown_text(str(title))}", ""]
    structures = {item["id"]: item for item in document.get("structures", [])}
    anchors = document.get("anchors", [])
    anchor_by_id = {item["id"]: item for item in anchors}
    digital_pages = sorted(
        (item for item in anchors if item.get("kind") == "digital_page" and item.get("range")),
        key=lambda item: (anchor_by_id.get(item["range"]["start_anchor_id"], {}).get("block_order", 0), item.get("order", 0)),
    )
    page_starts: dict[int, list[tuple[int, dict[str, Any], dict[str, Any]]]] = {}
    referenced_printed_ids: set[str] = set()
    for page_index, page in enumerate(digital_pages):
        boundary = anchor_by_id[page["range"]["start_anchor_id"]]
        page_starts.setdefault(int(boundary.get("block_order", 0)), []).append((page_index, page, boundary))
        printed_id = page.get("attrs", {}).get("printed_page_anchor_id")
        if printed_id:
            referenced_printed_ids.add(printed_id)
    printed_points: dict[int, list[dict[str, Any]]] = {}
    for anchor in anchors:
        if anchor.get("kind") == "printed_page" and anchor.get("id") not in referenced_printed_ids:
            printed_points.setdefault(int(anchor.get("block_order", 0)), []).append(anchor)

    def append_anchors(block_order: int) -> None:
        for page_index, page, boundary in page_starts.get(block_order, []):
            lines.extend([f"{{{page_index}}}", "", "---", ""])
            printed_page = page.get("attrs", {}).get("printed_page")
            if printed_page:
                lines.extend([f"<!-- Page: {str(printed_page).replace('--', '- -')} -->", ""])
            facs = page.get("attrs", {}).get("facs")
            if facs:
                lines.extend([f"<!-- Facsimile: {str(facs).replace('--', '- -')} -->", ""])
            lines.extend([f'<!-- SourceAnchor: id="{boundary["id"]}" kind="page_boundary" -->', ""])
        for anchor in printed_points.get(block_order, []):
            lines.extend([
                f'<!-- SourceAnchor: id="{anchor["id"]}" kind="printed_page" -->',
                f"<!-- Page: {str(anchor.get('label') or '').replace('--', '- -')} -->",
                "",
            ])

    for block in document.get("blocks", []):
        append_anchors(int(block.get("order", 0)))
        text = _markdown_text(str(block.get("text") or ""))
        if not text:
            continue
        block_type = block.get("type")
        if block_type == "SectionHeader":
            depth = int(block.get("attrs", {}).get("source_depth") or 1)
            lines.append("#" * min(6, max(2, depth + 1)) + " " + text)
            if depth > 5:
                parent = structures.get(block.get("parent_id"), {})
                payload = {"id": parent.get("id"), "depth": depth, "path": parent.get("source_locator")}
                lines.append(f"<!-- SourceStructure: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))} -->")
        elif block_type == "ListItem":
            lines.append(f"- {text}")
        elif block_type == "Footnote":
            label = block.get("attrs", {}).get("note_label") or block.get("attrs", {}).get("n")
            prefix = f"{label} " if label and not text.startswith(str(label)) else ""
            lines.append(f"<aside class=\"footnote\">{prefix}{text}</aside>")
        elif block_type == "MarginalNote":
            lines.append(f"<!-- MarginalNote: {text.replace('--', '- -')} -->")
        elif block_type == "Quote":
            lines.extend(f"> {part}" for part in text.splitlines())
        else:
            lines.append(text)
        lines.append("")
    append_anchors(len(document.get("blocks", [])))
    if digital_pages:
        lines.extend([f"{{{len(digital_pages)}}}", "", "---", ""])
    return "\n".join(lines).rstrip() + "\n"


def render_scholarly_html(document: dict[str, Any]) -> str:
    """Render the structured source as a standalone, dependency-free HTML view."""
    metadata = document.get("metadata") or {}
    titles = metadata.get("titles") or []
    title = next((item.get("value") for item in titles if item.get("value")), document["source"]["name"])
    parts = ["<!doctype html>", '<html lang="en"><head><meta charset="utf-8">',
             f"<title>{escape(str(title))}</title>",
             "<style>body{font-family:serif;line-height:1.6;max-width:58rem;margin:2rem auto;padding:0 1rem}"
             "h1,h2,h3,h4,h5,h6{line-height:1.2}aside.footnote{font-size:.9em;margin:1rem 0;padding:.5rem 1rem;"
             "border-left:3px solid #999;background:#f7f7f7}blockquote{margin-left:1rem;color:#444}"
             ".page-boundary{border:0;border-top:1px solid #aaa;margin:2rem 0}</style></head><body>"]
    parts.append(f"<h1>{escape(str(title))}</h1>")
    anchors = document.get("anchors", [])
    anchor_by_id = {item["id"]: item for item in anchors}
    page_starts: dict[int, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for page in anchors:
        if page.get("kind") != "digital_page" or not page.get("range"):
            continue
        boundary = anchor_by_id[page["range"]["start_anchor_id"]]
        page_starts.setdefault(int(boundary.get("block_order", 0)), []).append((page, boundary))

    def append_page_boundaries(block_order: int) -> None:
        for page, boundary in page_starts.get(block_order, []):
            page_range = page["range"]
            attrs = page.get("attrs") or {}
            html_attrs = {
                "class": "page-boundary",
                "data-digital-page": page.get("label"),
                "data-range-start": page_range.get("start_anchor_id"),
                "data-range-end": page_range.get("end_anchor_id"),
                "data-range-semantics": page_range.get("semantics"),
                "data-source-anchor": boundary.get("id"),
                "data-printed-page": attrs.get("printed_page"),
                "data-facsimile": attrs.get("facs"),
            }
            rendered_attrs = " ".join(
                f'{name}="{escape(str(value), quote=True)}"'
                for name, value in html_attrs.items() if value is not None
            )
            parts.append(f"<hr {rendered_attrs}>")

    for block in document.get("blocks", []):
        append_page_boundaries(int(block.get("order", 0)))
        text = str(block.get("text") or "").strip()
        if not text:
            continue
        safe = escape(text).replace("\n", "<br>\n")
        block_type = block.get("type")
        if block_type == "SectionHeader":
            depth = int(block.get("attrs", {}).get("source_depth") or 1)
            parts.append(f"<h{min(6, max(2, depth + 1))}>{safe}</h{min(6, max(2, depth + 1))}>")
        elif block_type == "Footnote":
            label = block.get("attrs", {}).get("note_label") or block.get("attrs", {}).get("n")
            prefix = f"{label} " if label and not text.startswith(str(label)) else ""
            parts.append(f'<aside class="footnote">{escape(prefix + text)}</aside>')
        elif block_type == "Quote":
            parts.append(f"<blockquote>{safe}</blockquote>")
        elif block_type == "ListItem":
            parts.append(f"<li>{safe}</li>")
        else:
            parts.append(f"<p>{safe}</p>")
    append_page_boundaries(len(document.get("blocks", [])))
    parts.append("</body></html>\n")
    return "\n".join(parts)
