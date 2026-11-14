from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

# GLM-OCR's region-recognition protocol is one short prompt per task
# (GLM-OCR glmocr/config.yaml, "Text/Table/Formula Recognition:").
GLM_OCR_PROMPTS = {
    "text": "Text Recognition:",
    "table": "Table Recognition:",
    "formula": "Formula Recognition:",
}

_FENCE_RE = re.compile(r"^\s*```[A-Za-z]*\s*\n(.*?)\n\s*```\s*$", re.DOTALL)
_CHUNK_REPEAT_RE = re.compile(r"(.{4,40}?)\1{7,}", re.DOTALL)
_ALLOWED_TABLE_TAGS = {
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "br", "sup", "sub", "b", "i", "em", "strong",
}
_SPAN_ATTRS = ("rowspan", "colspan")


def glm_ocr_prompt(label: str | None) -> str:
    return GLM_OCR_PROMPTS.get(str(label or "text").strip().lower(), GLM_OCR_PROMPTS["text"])


def clean_glm_text(text: str) -> str:
    """Strip transport noise (leading blank lines, a wrapping code fence)."""
    value = str(text or "").replace("\r\n", "\n").strip("\n").strip()
    fence = _FENCE_RE.match(value)
    if fence:
        value = fence.group(1).strip()
    return value


def looks_degenerate(text: str, *, min_line_repeats: int = 6) -> bool:
    """True when the output looks like a decoding loop rather than a transcription.

    Only structural repetition is flagged: the same line `min_line_repeats` times
    in a row, or one 4-40 character chunk repeated 8+ times back to back.
    Real text almost never does either; false positives only cost a re-check.
    """
    value = str(text or "")
    if not value:
        return False
    run = 1
    previous = None
    for line in value.splitlines():
        stripped = line.strip()
        if stripped and stripped == previous:
            run += 1
            if run >= min_line_repeats:
                return True
        else:
            run = 1
        previous = stripped
    return bool(_CHUNK_REPEAT_RE.search(value[:20000]))


def sanitize_table_html(raw: str) -> str:
    """Return the first <table> of `raw` reduced to an allowlist of structural tags.

    Model output is untrusted: scripts, styles, links and every attribute except
    integer rowspan/colspan are dropped. An empty string means "no usable table".
    """
    value = clean_glm_text(raw)
    if "<table" not in value.lower():
        return ""
    soup = BeautifulSoup(value, "html.parser")
    table = soup.find("table")
    if table is None:
        return ""
    for tag in list(table.find_all(True)):
        if tag.name in {"script", "style"}:
            tag.decompose()
        elif tag.name not in _ALLOWED_TABLE_TAGS:
            tag.unwrap()
    for tag in [table, *table.find_all(True)]:
        keep: dict[str, Any] = {}
        for attr in _SPAN_ATTRS:
            raw_value = tag.attrs.get(attr)
            if raw_value is not None and str(raw_value).strip().isdigit() and int(str(raw_value).strip()) > 1:
                keep[attr] = str(int(str(raw_value).strip()))
        tag.attrs = keep
    if not table.find("tr"):
        return ""
    return str(table)


def table_html_rows(table_html: str) -> list[str]:
    """One plain-text line per table row, cells separated by a single space."""
    if not table_html:
        return []
    soup = BeautifulSoup(table_html, "html.parser")
    rows: list[str] = []
    for tr in soup.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"])]
        line = " ".join(cell for cell in cells if cell)
        if line:
            rows.append(line)
    return rows
