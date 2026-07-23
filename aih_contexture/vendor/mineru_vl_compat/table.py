from __future__ import annotations

from html import escape
import re
from typing import Any


_FCEL_RE = re.compile(r"<fcel>", re.IGNORECASE)
_NL_RE = re.compile(r"<nl>", re.IGNORECASE)


def normalize_mineru_table_content(content: str) -> tuple[str, dict[str, Any]]:
    """Convert MinerU-VL table protocol text into a renderable table body.

    MinerU-VL table recognition can return compact protocol text such as
    ``<fcel>A<fcel>B<nl>``. Official MinerU post-processing turns table content
    into HTML before markdown rendering; Contexture should do the same instead
    of leaking protocol markers into scholarly Markdown.
    """
    raw = str(content or "").strip()
    if not raw:
        return "", {"format": "empty", "row_count": 0}
    if "<table" in raw.lower():
        return raw, {"format": "html", "row_count": raw.lower().count("<tr")}
    if "<fcel>" not in raw.lower() and "<nl>" not in raw.lower():
        return raw, {"format": "plain", "row_count": len([line for line in raw.splitlines() if line.strip()])}

    rows = []
    for row_text in _NL_RE.split(raw):
        cells = [cell.strip() for cell in _FCEL_RE.split(row_text) if cell.strip()]
        if cells:
            rows.append(cells)

    if not rows:
        cleaned = _NL_RE.sub("\n", _FCEL_RE.sub(" ", raw)).strip()
        return cleaned, {"format": "protocol_text", "row_count": 0}

    max_cols = max(len(row) for row in rows)
    if max_cols <= 1:
        text = "\n".join(row[0] for row in rows)
        return text, {"format": "protocol_lines", "row_count": len(rows)}

    html_rows = []
    for row in rows:
        padded = row + [""] * (max_cols - len(row))
        cells_html = "".join(f"<td>{escape(cell)}</td>" for cell in padded)
        html_rows.append(f"<tr>{cells_html}</tr>")
    html = "<table>\n" + "\n".join(html_rows) + "\n</table>"
    return html, {"format": "protocol_html", "row_count": len(rows), "column_count": max_cols}
