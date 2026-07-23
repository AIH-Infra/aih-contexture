from __future__ import annotations

import json
import re
from typing import Any

from aih_contexture.config.marginal_output import normalize_marginal_output_mode
from aih_contexture.middle.semantics import resolve_middle_for_rendering


HIDDEN_BLOCK_TYPES = {"PageHeader", "PageFooter", "PageNumber"}
FOOTNOTE_MARKER_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\\\(\s*)?(?:\^\s*)?\{?([0-9]{1,4}|[ivxlcdm]{1,12})\}?(?:\s*\\\))?[.)]?\s+",
    re.IGNORECASE,
)
HTML_SUPERSCRIPT_LEADING_MARKER_RE = re.compile(
    r"^\s*<sup>\s*([0-9]{1,4}|[ivxlcdm]{1,12})\s*</sup>\s*",
    re.IGNORECASE,
)
LATEX_SUPERSCRIPT_FOOTNOTE_RE = re.compile(
    r"\\\(\s*\^\s*\{?([0-9]{1,4}|[ivxlcdm]{1,12})\}?\s*\\\)",
    re.IGNORECASE,
)
DOLLAR_SUPERSCRIPT_FOOTNOTE_RE = re.compile(
    r"\$\s*\^\s*\{?([0-9]{1,4}|[ivxlcdm]{1,12})\}?\s*\$",
    re.IGNORECASE,
)
BARE_SUPERSCRIPT_FOOTNOTE_RE = re.compile(
    r"(?<![\w$\\])\^\s*\{?([0-9]{1,4}|[ivxlcdm]{1,12})\}?(?![\w])",
    re.IGNORECASE,
)
PLAIN_SUPERSCRIPT_FOOTNOTE_RE = re.compile(
    r"\(\s*\^\s*\{?([0-9]{1,4}|[ivxlcdm]{1,12})\}?\s*\)",
    re.IGNORECASE,
)
UNICODE_SUPERSCRIPT_DIGITS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
UNICODE_SUPERSCRIPT_RE = re.compile(r"([⁰¹²³⁴⁵⁶⁷⁸⁹]+)")
HTML_SUPERSCRIPT_WITH_PAREN_RE = re.compile(r"<sup>\s*([0-9]{1,4}|[ivxlcdm]{1,12})\s*\)</sup>", re.IGNORECASE)
PRINTED_PAGE_MARKER_RE = re.compile(r"^\s*\{?([0-9]{1,4}|[ivxlcdm]{1,12})\}?\s*$", re.IGNORECASE)
PLAIN_MARGIN_MARKER_RE = re.compile(r"^[0-9]{1,4}$")
SCHOLARLY_NUMBERED_PARAGRAPH_RE = re.compile(r"^(\d{3,4})\.(\s+)", re.MULTILINE)
APPARATUS_INDEX_FORMULA_RE = re.compile(
    r"^[\s\|\:/,.;~\-\u2013\u2014\u2016\u2225\\_\^\{\}\(\)\[\]"
    r"0-9A-Za-z\u00b9\u00b2\u00b3\u2070-\u2079\u2080-\u2089"
    r"\u1d43-\u1d4d\u1d50-\u1d5c\u1d62-\u1d6a"
    r"\u02b0-\u02b8\u02e1-\u02e4"
    r"\u00a0\u202f\u2009\u200a\u200b]+$"
)
APPARATUS_INDEX_STRONG_MATH_RE = re.compile(
    r"(?:=|[+\u2212*/<>]|\\(?:frac|sqrt|sum|int|prod|lim|begin|end|alpha|beta|gamma|delta|theta|lambda|mu|pi|sigma|omega)\b)"
)


def render_middle_scholarly_markdown(
    data: dict[str, Any],
    *,
    include_provenance_comments: bool = False,
    include_printed_page_comments: bool = True,
    include_page_header_comments: bool = True,
    include_page_footer_comments: bool = True,
    include_margin_comments: bool = True,
    include_blockquote_markers: bool = True,
    include_page_separators: bool = True,
    marginal_output_mode: str | None = None,
    equation_output_mode: str = "humanities_safe",
    footnote_enabled: bool = True,
    superscript_policy: str = "footnote_safe",
    page_separator: str = "---",
) -> str:
    """Render Contexture Middle JSON into the normalized scholarly Markdown layer."""
    data = resolve_middle_for_rendering(
        data,
        {
            "footnote_enabled": footnote_enabled,
            "superscript_policy": superscript_policy,
        },
    )
    pages = data.get("pages", []) if isinstance(data, dict) else []
    if not isinstance(pages, list):
        return ""

    lines: list[str] = []
    effective_marginal_output_mode = _effective_marginal_output_mode(
        marginal_output_mode,
        include_margin_comments=include_margin_comments,
    )
    sorted_pages = sorted((page for page in pages if isinstance(page, dict)), key=lambda page: int(page.get("index", 0)))
    final_anchor = 0

    for page in sorted_pages:
        page_index = int(page.get("index", 0))
        final_anchor = max(final_anchor, page_index + 1)
        rendered_page, page_footnotes = _render_page(
            page,
            include_provenance_comments=include_provenance_comments,
            include_printed_page_comments=include_printed_page_comments,
            include_page_header_comments=include_page_header_comments,
            include_page_footer_comments=include_page_footer_comments,
            include_margin_comments=include_margin_comments,
            marginal_output_mode=effective_marginal_output_mode,
            include_blockquote_markers=include_blockquote_markers,
            include_page_separators=include_page_separators,
            equation_output_mode=equation_output_mode,
            page_separator=page_separator,
        )
        lines.extend(rendered_page)
        if page_footnotes:
            lines.extend([""])
            lines.extend(page_footnotes)

    lines.extend(["", f"{{{final_anchor}}}"])
    if include_page_separators and page_separator:
        lines.extend(["", page_separator])

    return _clean_markdown("\n".join(lines)) + "\n"


def _render_page(
    page: dict[str, Any],
    *,
    include_provenance_comments: bool,
    include_printed_page_comments: bool,
    include_page_header_comments: bool,
    include_page_footer_comments: bool,
    include_margin_comments: bool,
    marginal_output_mode: str,
    include_blockquote_markers: bool,
    include_page_separators: bool,
    equation_output_mode: str,
    page_separator: str,
) -> tuple[list[str], list[str]]:
    page_index = int(page.get("index", 0))
    anchor_start = int(page.get("anchor_start", page_index))
    anchor_end = int(page.get("anchor_end", page_index + 1))
    blocks = sorted(
        (block for block in page.get("blocks", []) if isinstance(block, dict)),
        key=lambda block: (int(block.get("order", 0)), str(block.get("id", ""))),
    )
    printed_page = _text(page.get("printed_page")) or _printed_page_from_blocks(blocks)

    lines = ["", f"{{{anchor_start}}}", ""]
    if include_page_separators and page_separator:
        lines.extend([page_separator, ""])
    if printed_page and include_printed_page_comments:
        lines.extend([f"<!-- Page: {_comment_text(printed_page)} -->", ""])

    if include_page_header_comments:
        for block in blocks:
            if block.get("type") == "PageHeader":
                text = _block_text(block)
                if text:
                    lines.extend([f"<!-- PageHeader: {_comment_text(text)} -->", ""])
    if include_page_footer_comments:
        for block in blocks:
            if block.get("type") == "PageFooter":
                text = _block_text(block)
                if text:
                    lines.extend([f"<!-- PageFooter: {_comment_text(text)} -->", ""])

    footnotes: list[str] = []
    footnote_number = 1
    seen_footnotes: set[str] = set()
    for block in blocks:
        block_type = str(block.get("type") or "")
        if block_type in HIDDEN_BLOCK_TYPES:
            continue
        if include_provenance_comments:
            lines.extend([_block_comment(block, anchor_start=anchor_start, anchor_end=anchor_end), ""])

        if block_type == "Footnote" or _is_footnote_like_block(block, page):
            for marker, body in _extract_footnote_entries(_block_text(block)):
                footnote_id = marker or str(footnote_number)
                footnote_number += 1
                dedupe_key = marker or re.sub(r"\s+", " ", body).strip().lower()
                if dedupe_key in seen_footnotes:
                    continue
                seen_footnotes.add(dedupe_key)
                footnotes.extend(
                    _render_footnote(
                        block,
                        footnote_id=footnote_id,
                        body=body,
                        anchor_start=anchor_start,
                        anchor_end=anchor_end,
                    )
                )
            continue

        lines.extend(
            _render_block(
                block,
                page=page,
                anchor_start=anchor_start,
                anchor_end=anchor_end,
                include_margin_comments=include_margin_comments,
                marginal_output_mode=marginal_output_mode,
                include_blockquote_markers=include_blockquote_markers,
                equation_output_mode=equation_output_mode,
            )
        )

    return lines, footnotes


def _render_block(
    block: dict[str, Any],
    *,
    page: dict[str, Any],
    anchor_start: int,
    anchor_end: int,
    include_margin_comments: bool,
    marginal_output_mode: str,
    include_blockquote_markers: bool,
    equation_output_mode: str,
) -> list[str]:
    block_type = str(block.get("type") or "")
    text = _block_text(block)
    if not text and block_type not in {"Figure", "Picture", "ImageDescription"}:
        return []
    if block_type not in {"Equation", "Table"}:
        text = _normalize_footnote_references(text)
    is_blockquote = _is_blockquote_block(block)
    if block_type not in {"Equation", "Table", "Code", "Form"} and not is_blockquote:
        text = _normalize_soft_line_breaks(text)

    if block_type == "SectionHeader":
        level = _heading_level(block)
        return [f"{'#' * level} {text}", ""]
    if block_type == "Table":
        return _render_table(text)
    if block_type == "Equation":
        if _should_render_equation_as_plain_text(text, equation_output_mode):
            return [text, ""]
        return ["$$", text, "$$", ""]
    if block_type == "Caption":
        return [f"*{text}*", ""]
    if block_type == "Reference":
        return [text, ""]
    if is_blockquote:
        if not include_blockquote_markers:
            return [text, ""]
        return _render_markdown_blockquote(text)
    if block_type == "ListItem":
        return [f"- {text}", ""]
    if block_type == "MarginalNote":
        if not include_margin_comments:
            return [text, ""]
        return _render_margin_block(
            block,
            text,
            page_width=_positive_float(page.get("width")),
            anchor_start=anchor_start,
            anchor_end=anchor_end,
            marginal_output_mode=marginal_output_mode,
        )
    if block_type == "InlineAnnotation":
        return _render_comment_block("InlineAnnotation", block, text, anchor_start=anchor_start, anchor_end=anchor_end)
    if block_type == "ImageDescription":
        return _render_comment_block("ImageDescription", block, text, anchor_start=anchor_start, anchor_end=anchor_end)
    if block_type in {"Figure", "Picture"}:
        caption = text or "Image"
        return [f"![{_image_alt(caption)}]()", ""]
    if block_type == "ComplexRegion":
        return _render_comment_block("ComplexRegion", block, text, anchor_start=anchor_start, anchor_end=anchor_end)
    return [text, ""]


def _is_blockquote_block(block: dict[str, Any]) -> bool:
    attrs = block.get("attrs") if isinstance(block.get("attrs"), dict) else {}
    raw = attrs.get("raw") if isinstance(attrs.get("raw"), dict) else {}
    candidates = [
        attrs.get("style"),
        attrs.get("raw_label"),
        raw.get("type"),
        raw.get("label"),
        raw.get("category"),
    ]
    for value in candidates:
        normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in {"blockquote", "block_quote", "quote", "citation"}:
            return True
    return False


def _render_markdown_blockquote(text: str) -> list[str]:
    lines = [f"> {line}" if line else ">" for line in text.splitlines()]
    return lines + [""]


def _render_table(text: str) -> list[str]:
    if "<table" in text.lower():
        return [text, ""]
    return [text, ""]


def _heading_level(block: dict[str, Any]) -> int:
    attrs = block.get("attrs") if isinstance(block.get("attrs"), dict) else {}
    for key in ("heading_level", "raw_heading_level", "text_level"):
        value = attrs.get(key)
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            return max(1, min(6, number))
    return 2


def _render_footnote(
    block: dict[str, Any],
    *,
    footnote_id: str,
    body: str | None = None,
    anchor_start: int,
    anchor_end: int,
) -> list[str]:
    text = _normalize_soft_line_breaks(
        _normalize_footnote_references(body if body is not None else _block_text(block))
    )
    return [f"<sup>{_html_sup_text(footnote_id)}</sup> {text}", ""]


def _render_comment_block(
    tag: str,
    block: dict[str, Any],
    text: str,
    *,
    anchor_start: int,
    anchor_end: int,
    quote: bool = False,
) -> list[str]:
    block_id = json.dumps(str(block.get("id") or ""), ensure_ascii=False)
    lines = [f"<!-- {tag}: id={block_id} anchors={{{anchor_start}}}-{{{anchor_end}}} -->"]
    if quote:
        lines.extend(f"> {line}" if line else ">" for line in text.splitlines())
    elif text:
        lines.append(text)
    lines.extend([f"<!-- /{tag} -->", ""])
    return lines


def _render_margin_block(
    block: dict[str, Any],
    text: str,
    *,
    page_width: float | None,
    anchor_start: int,
    anchor_end: int,
    marginal_output_mode: str,
) -> list[str]:
    if marginal_output_mode == "drop":
        return []
    if marginal_output_mode == "plain":
        return [text, ""]
    if marginal_output_mode == "line_markers" and _is_plain_margin_marker(text):
        return [f"<!-- Line: {_comment_text(text)} -->", ""]
    side = _margin_side(block, page_width=page_width)
    if side not in {"left", "right"}:
        return [text, ""]
    block_id = json.dumps(str(block.get("id") or ""), ensure_ascii=False)
    lines = [f"<!-- Margin:{side} id={block_id} a={anchor_start}-{anchor_end} -->"]
    lines.extend(f"> {line}" if line else ">" for line in text.splitlines())
    lines.extend(["<!-- /Margin -->", ""])
    return lines


def _effective_marginal_output_mode(value: str | None, *, include_margin_comments: bool) -> str:
    if not include_margin_comments and value is None:
        return "plain"
    return normalize_marginal_output_mode(value, enable_marginal_detection=include_margin_comments)


def _is_plain_margin_marker(text: str) -> bool:
    return PLAIN_MARGIN_MARKER_RE.fullmatch(str(text or "").strip()) is not None


def _is_apparatus_index_formula(text: str) -> bool:
    stripped = str(text or "").strip()
    if not stripped or len(stripped) > 48:
        return False
    if APPARATUS_INDEX_STRONG_MATH_RE.search(stripped):
        return False
    if not any(ch.isdigit() for ch in stripped) and not re.search(r"[A-Z][0-9\u00b9\u00b2\u00b3\u2070-\u2079]|\|", stripped):
        return False
    return APPARATUS_INDEX_FORMULA_RE.fullmatch(stripped) is not None


def _should_render_equation_as_plain_text(text: str, mode: str | None) -> bool:
    normalized = str(mode or "humanities_safe").strip().lower().replace("-", "_")
    if normalized in {"math", "latex", "preserve", "keep"}:
        return False
    if normalized in {"plain", "text", "disable", "disabled", "off", "all_plain"}:
        return True
    return _is_apparatus_index_formula(text)


def _margin_side(block: dict[str, Any], *, page_width: float | None) -> str | None:
    attrs = block.get("attrs") if isinstance(block.get("attrs"), dict) else {}
    candidates = [
        attrs.get("side"),
        attrs.get("placement"),
        attrs.get("raw_label"),
    ]
    raw = attrs.get("raw")
    if isinstance(raw, dict):
        candidates.extend([raw.get("label"), raw.get("type"), raw.get("placement")])
    for value in candidates:
        normalized = str(value or "").strip().lower().replace("-", "_")
        if normalized in {"left", "margin_left", "marginal_left", "marginal_note_left", "left_margin"}:
            return "left"
        if normalized in {"right", "margin_right", "marginal_right", "marginal_note_right", "right_margin"}:
            return "right"
    bbox = block.get("bbox")
    if isinstance(page_width, (int, float)) and page_width > 0 and isinstance(bbox, list) and len(bbox) == 4:
        center_x = (float(bbox[0]) + float(bbox[2])) / 2
        if center_x <= float(page_width) * 0.25:
            return "left"
        if center_x >= float(page_width) * 0.75:
            return "right"
    return None


def _block_text(block: dict[str, Any]) -> str:
    direct = _text(block.get("text"))
    if direct:
        return direct
    spans = block.get("spans")
    if isinstance(spans, list):
        pieces = [_text(span.get("text")) for span in spans if isinstance(span, dict)]
        return " ".join(piece for piece in pieces if piece)
    return ""


def _printed_page_from_blocks(blocks: list[dict[str, Any]]) -> str:
    for block in blocks:
        if block.get("type") != "PageNumber":
            continue
        marker = _printed_page_marker(_block_text(block))
        if marker:
            return marker
    return ""


def _printed_page_marker(text: str) -> str | None:
    match = PRINTED_PAGE_MARKER_RE.match(text)
    if not match:
        return None
    marker = match.group(1)
    if marker.isdigit() or _is_valid_roman_page(marker):
        return marker
    return None


def _is_valid_roman_page(value: str) -> bool:
    text = value.strip().upper()
    if not text:
        return False
    return re.fullmatch(r"M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})", text) is not None


def _is_footnote_like_block(block: dict[str, Any], page: dict[str, Any]) -> bool:
    block_type = str(block.get("type") or "")
    if block_type not in {"Text", "ListItem"}:
        return False
    text = _block_text(block)
    if not FOOTNOTE_MARKER_RE.match(text):
        return False
    if SCHOLARLY_NUMBERED_PARAGRAPH_RE.match(text):
        return False
    height = page.get("height")
    bbox = block.get("bbox")
    if isinstance(height, (int, float)) and isinstance(bbox, list) and len(bbox) == 4:
        return float(bbox[1]) >= float(height) * 0.55
    return True


def _extract_footnote_entries(text: str) -> list[tuple[str | None, str]]:
    normalized = _normalize_footnote_references(_text(text))
    normalized = _normalize_soft_line_breaks(normalized)
    if not normalized:
        return [(None, "")]
    entries = _split_html_sup_footnote_entries(normalized)
    if entries:
        return entries
    marker, body = _extract_footnote_marker_and_body(normalized)
    return [(marker, body)]


def _split_html_sup_footnote_entries(text: str) -> list[tuple[str, str]]:
    matches = list(
        re.finditer(
            r"(?m)^\s*<sup>\s*([0-9]{1,4}|[ivxlcdm]{1,12})\s*</sup>\s*",
            text,
            re.IGNORECASE,
        )
    )
    if not matches:
        return []
    entries: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            entries.append((match.group(1), body))
    return entries


def _extract_footnote_marker_and_body(text: str) -> tuple[str | None, str]:
    normalized = _text(text)
    html_match = HTML_SUPERSCRIPT_LEADING_MARKER_RE.match(normalized)
    if html_match:
        return html_match.group(1), normalized[html_match.end():].strip()
    match = FOOTNOTE_MARKER_RE.match(normalized)
    if not match:
        return None, normalized
    marker = match.group(1)
    return marker, normalized[match.end():].strip()


def _normalize_footnote_references(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return f"<sup>{_html_sup_text(match.group(1))}</sup>"

    text = LATEX_SUPERSCRIPT_FOOTNOTE_RE.sub(repl, text)
    text = DOLLAR_SUPERSCRIPT_FOOTNOTE_RE.sub(repl, text)
    text = BARE_SUPERSCRIPT_FOOTNOTE_RE.sub(repl, text)
    text = PLAIN_SUPERSCRIPT_FOOTNOTE_RE.sub(repl, text)
    text = HTML_SUPERSCRIPT_WITH_PAREN_RE.sub(repl, text)

    def unicode_repl(match: re.Match[str]) -> str:
        marker = match.group(1).translate(UNICODE_SUPERSCRIPT_DIGITS)
        return f"<sup>{_html_sup_text(marker)}</sup>"

    text = UNICODE_SUPERSCRIPT_RE.sub(unicode_repl, text)
    return re.sub(
        r"([^\n])\s*\n+\s*(<sup>(?:[0-9]{1,4}|[ivxlcdm]{1,12})</sup>)\s*(?=\n|$)",
        r"\1\2",
        text,
        flags=re.IGNORECASE,
    )


def _normalize_soft_line_breaks(text: str) -> str:
    """Join OCR/VLM hard line breaks inside prose while preserving paragraph breaks."""
    if not text:
        return ""
    text = str(text).replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = re.split(r"\n\s*\n", text.strip())
    normalized: list[str] = []
    for paragraph in paragraphs:
        lines = [line.strip() for line in paragraph.splitlines()]
        if not lines:
            continue
        if _looks_structural_lines(lines):
            normalized.append("\n".join(lines))
            continue
        joined = " ".join(line for line in lines if line)
        joined = re.sub(r"\s+([,.;:!?，。；：！？、)\]\}])", r"\1", joined)
        joined = re.sub(r"([(\[\{])\s+", r"\1", joined)
        joined = re.sub(r"\s{2,}", " ", joined).strip()
        if joined:
            normalized.append(joined)
    return "\n\n".join(normalized)


def _looks_structural_lines(lines: list[str]) -> bool:
    nonempty = [line for line in lines if line]
    if not nonempty:
        return False
    if any(line.startswith("```") for line in nonempty):
        return True
    if any(line.startswith("|") and line.endswith("|") for line in nonempty):
        return True
    if any(re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", line) for line in nonempty):
        return True
    if any(line.startswith(("#", ">", "$$", "<table", "</table")) for line in nonempty):
        return True
    return False


def _html_sup_text(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _block_comment(block: dict[str, Any], *, anchor_start: int, anchor_end: int) -> str:
    provenance = _first_provenance(block.get("provenance"))
    fields = {
        "id": block.get("id"),
        "type": block.get("type"),
        "anchors": f"{{{anchor_start}}}-{{{anchor_end}}}",
        "layout": provenance.get("backend"),
        "confidence": block.get("confidence"),
    }
    parts = [f"{key}={json.dumps(str(value), ensure_ascii=False)}" for key, value in fields.items() if value not in (None, "")]
    return f"<!-- Block: {' '.join(parts)} -->"


def _first_provenance(value: Any) -> dict[str, Any]:
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    return {}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"[ \t]+", " ", str(value).replace("\r\n", "\n").replace("\r", "\n")).strip()


def _comment_text(text: str) -> str:
    return text.replace("--", "- -").strip()


def _image_alt(text: str) -> str:
    return text.replace("[", "(").replace("]", ")").strip()


def _positive_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _clean_markdown(text: str) -> str:
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    text = SCHOLARLY_NUMBERED_PARAGRAPH_RE.sub(r"\1\\.\2", text)
    return text.strip()
