"""Conservative table projection. Original Middle text is never modified."""
from __future__ import annotations

import hashlib
import html
import re
from typing import Any

from bs4 import BeautifulSoup, NavigableString, Tag

_TOKEN = re.compile(r"<(fcel|ecel|lcel|ucel|xcel|nl)\s*/?>", re.I)
_INLINE = {"sup", "sub", "em", "i", "strong", "b", "br", "code"}


def _decode_structure_tokens(text: str) -> str:
    # Decode structural tags only. Unescaping the whole cell would turn a
    # literal &lt;T&gt; or comparison into an HTML element and lose its letters.
    return re.sub(r"&lt;(fcel|ecel|lcel|ucel|xcel|nl)\s*/?&gt;",
                  lambda m: '<' + m.group(1).lower() + '>', text, flags=re.I)


def _parse_inline(text: str):
    def protect(match):
        return match.group(0) if match.group(1).lower() in _INLINE else html.escape(match.group(0), quote=False)
    protected = re.sub(r"</?([A-Za-z][\w:-]*)\b[^>]*>", protect, text)
    return BeautifulSoup(protected, "html.parser")


def has_table_structure_tokens(text: str) -> bool:
    return bool(_TOKEN.search(html.unescape(text)))


def _inline_html(node: Any) -> str:
    if isinstance(node, NavigableString):
        return html.escape(str(node), quote=False)
    if not isinstance(node, Tag):
        return ""
    children = "".join(_inline_html(child) for child in node.children)
    if node.name in _INLINE:
        return "<br>" if node.name == "br" else f"<{node.name}>{children}</{node.name}>"
    return children


def _otsl_to_html(text: str) -> str | None:
    """Accept only complete rectangular OTSL with verifiable span ownership.

    LCEL continues left, UCEL above, XCEL both. A malformed or mixed HTML
    sequence is not repaired by guessing. See official Docling serialization.
    """
    text = _decode_structure_tokens(text).strip()
    if text.lower().startswith("<otsl>") and text.lower().endswith("</otsl>"):
        text = text[6:-7].strip()
    parts = _TOKEN.split(text)
    if parts[0].strip() or len(parts) > 40_000:
        return None
    rows: list[list[tuple[str, str]]] = []
    row: list[tuple[str, str]] = []
    for index in range(1, len(parts), 2):
        token, value = parts[index].lower(), parts[index + 1].strip()
        if token == "nl":
            if not row or value:
                return None
            rows.append(row);row = []
        else:
            if token != "fcel" and value:
                return None
            row.append((token, value))
    if row or not rows or not rows[0] or len(rows[0]) > 256:
        return None
    columns = len(rows[0])
    if any(len(row) != columns for row in rows):
        return None
    grid: list[list[tuple[int, int] | None]] = [[None] * columns for _ in rows]
    origins: dict[tuple[int, int], str] = {}
    for r, row in enumerate(rows):
        for c, (token, value) in enumerate(row):
            left = grid[r][c - 1] if c else None
            above = grid[r - 1][c] if r else None
            if token in {"fcel", "ecel"}:
                grid[r][c] = (r, c);origins[(r, c)] = value
            elif token == "lcel" and left is not None and left[0] == r:
                grid[r][c] = left
            elif token == "ucel" and above is not None and above[1] == c:
                grid[r][c] = above
            elif token == "xcel" and left is not None and left == above:
                grid[r][c] = left
            else:
                return None
    bounds = {origin: list(origin) for origin in origins}
    for r, row in enumerate(grid):
        for c, owner in enumerate(row):
            bounds[owner][0] = max(bounds[owner][0], r)
            bounds[owner][1] = max(bounds[owner][1], c)
    spans = {}
    for origin in origins:
        bottom, right = bounds[origin]
        if any(grid[r][c] != origin for r in range(origin[0], bottom + 1) for c in range(origin[1], right + 1)):
            return None
        spans[origin] = (bottom - origin[0] + 1, right - origin[1] + 1)
    output = ["<table>"]
    for r in range(len(rows)):
        output.append("<tr>")
        for c in range(columns):
            if (r, c) not in origins:
                continue
            rowspan, colspan = spans[(r, c)]
            attrs = (f' rowspan="{rowspan}"' if rowspan > 1 else "") + (f' colspan="{colspan}"' if colspan > 1 else "")
            value = _parse_inline(origins[(r, c)])
            output.append(f"<td{attrs}>{_inline_html(value)}</td>")
        output.append("</tr>")
    output.append("</table>")
    return "\n".join(output)


def project_table(text: str) -> tuple[str, str | None]:
    """Return reading text and an optional review reason; normal HTML is exact."""
    if not has_table_structure_tokens(text):
        return text, None
    converted = _otsl_to_html(text)
    if converted is not None:
        return converted, None
    # Mixed HTML has already lost part of its structural grammar. Retain its
    # existing cell order, text and inline typography, but do not invent spans.
    soup = BeautifulSoup(text, "html.parser")
    if not soup.find("table"):
        separated = _TOKEN.sub(lambda m: '\n\n' if m.group(1).lower() == 'nl' else ' | ', _decode_structure_tokens(text))
        cleaned = '\n\n'.join(_inline_html(_parse_inline(part)) for part in separated.split('\n\n') if part.strip())
        return cleaned, "unresolved_table_structure"
    for tag in list(soup.find_all(["fcel", "ecel", "lcel", "ucel", "xcel", "nl"])):
        tag.unwrap()
    for string in list(soup.find_all(string=True)):
        clean = _TOKEN.sub("", html.unescape(str(string)))
        if clean != str(string):
            string.replace_with(clean)
    if soup.find("table"):
        # Keep cell topology and inline markup exactly as the old HTML states
        # it. The warning explicitly says that topology is unverified.
        cleaned = str(soup)
    else:
        cleaned = "".join(_inline_html(child) for child in soup.children)
    return cleaned, "unresolved_table_structure"


def table_review_records(data: dict[str, Any]) -> list[dict[str, Any]]:
    from aih_contexture.middle.reading_structure import table_reading_source, is_table_group_source
    records = []
    for page in data.get("pages") or []:
        for block in page.get("blocks") or []:
            group = block.get('type') == 'ComplexRegion' and is_table_group_source(block)
            if block.get("type") != "Table" and not group:
                continue
            text = table_reading_source(block)
            if not text:
                text = " ".join(str(span.get("text") or "") for span in block.get("spans") or [])
            if has_table_structure_tokens(text):
                _, reason = project_table(text)
                records.append({"page_index": page.get("index"), "block_id": block.get("id"),
                                "status": "needs_review" if reason else "converted_otsl",
                                "reason": reason, "source_text": text,
                                "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()})
            elif not re.search(r'<table\b', text, re.I) and not re.search(r'(?m)^\s*\|?.+\|.+\n\s*\|?\s*:?-{3,}', text):
                records.append({'page_index': page.get('index'), 'block_id': block.get('id'),
                                'status': 'needs_review', 'reason': 'table_group_structure_unconfirmed' if group else 'source_table_structure_missing',
                                'source_text': text,
                                'source_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()})
    return records
