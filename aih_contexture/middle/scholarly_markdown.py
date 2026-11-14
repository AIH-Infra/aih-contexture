from __future__ import annotations

from aih_contexture.middle.storage import decode_middle_storage

import json
import re
from typing import Any
from urllib.parse import quote
from statistics import median

from aih_contexture.config.marginal_output import normalize_marginal_output_mode
from aih_contexture.middle.classical_capabilities import classical_marginalia_capabilities, classical_margin_side, classical_bbox_is_trustworthy
from aih_contexture.middle.table_rendering import project_table
from aih_contexture.middle.reading_structure import table_reading_source, is_table_group_source
from aih_contexture.middle.table_rendering import has_table_structure_tokens
from aih_contexture.middle.prose_geometry import native_prose_geometry, native_wrapped_blocks
from aih_contexture.middle.page_folios import observed_folio_plan, prepare_page_folio_render_view
from aih_contexture.utils.markdown_regions import transform_prose_regions, markdown_lines
from aih_contexture.utils.reading_literals import escape_literal_angles, escape_unpaired_prose_math
from aih_contexture.middle.semantics import resolve_middle_for_rendering
from aih_contexture.middle.semantics.classical_marginalia import (
    normalize_classical_marginalia_mode,
    normalize_classical_text_marginalia_mode,
    page_locator_comments,
    resolve_classical_marginalia,
)
from aih_contexture.middle.classical_projection import (
    prepare_classical_render_view,
    semantic_body_projection,
    semantic_body_text,
)
from aih_contexture.utils.footnote_markers import (
    match_leading_footnote_marker,
    split_strong_footnote_entries,
)


HIDDEN_BLOCK_TYPES = {"PageHeader", "PageFooter", "PageNumber"}
_RESOLVED_RENDER_TOKEN = object()
FOOTNOTE_MARKER_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:"
    r"(?:\\\(\s*)?(?:\^\s*)?\{?([0-9]{1,4}|[ivxlcdm]{1,12})\}?(?:\s*\\\))?[.)]?\s+"
    r")",
    re.IGNORECASE,
)
HTML_SUPERSCRIPT_LEADING_MARKER_RE = re.compile(
    r"^\s*<sup>\s*([0-9]{1,4}|[ivxlcdm]{1,12}|[①-⑳])\s*</sup>\s*",
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
EDITORIAL_TAG_RE = re.compile(
    r"<(?!\s*/?(?:sup|sub|i|b|em|strong|span|br|u|s|del|mark)\b|!--)([^>]+)>",
    re.IGNORECASE,
)


def protect_editorial_angle_brackets(text: str) -> str:
    return escape_literal_angles(text) if text and '<' in text else text


def _reading_prose(text: str, *, literal_prefixes: bool = False) -> str:
    text = escape_unpaired_prose_math(text)
    def transform(value):
        value = _normalize_footnote_references(value)
        value = _normalize_soft_line_breaks(value)
        value = protect_editorial_angle_brackets(value)
        if literal_prefixes:
            value = re.sub(r'(?m)^([ \t]{0,3})([-+*])(?=[ \t]+\S)', r'\1\\\2', value)
            value = re.sub(r'(?m)^([ \t]{0,3})(\d{1,9})([.)])(?=[ \t]+\S)', r'\1\2\\\3', value)
        return SCHOLARLY_NUMBERED_PARAGRAPH_RE.sub(r'\1\\.\2', value)
    return transform_prose_regions(text, transform)


def _render_unstructured_group(text: str) -> list[str]:
    def literal(value):
        value = protect_editorial_angle_brackets(value)
        value = re.sub(r'(?m)^([ \t]{0,3})([-+*])(?=[ \t]+\S)', r'\1\\\2', value)
        return re.sub(r'(?m)^([ \t]{0,3})(\d{1,9})([.)])(?=[ \t]+\S)', r'\1\2\\\3', value)
    rows = transform_prose_regions(text, literal).splitlines()
    return [*[row + ('  ' if row and i < len(rows)-1 else '')
              for i, row in enumerate(rows)], '']



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
    classical_marginalia_mode: str = "off",
    classical_text_marginalia_mode: str = "separate",
    generic_line_output_mode: str = "drop",
    classical_pdf_words_by_page: dict[int, list[dict[str, Any]]] | None = None,
    classical_evidence: dict[str, Any] | None = None,
    page_manifest_out: dict[str, Any] | None = None,
    _resolved_token: object | None = None,
) -> str:
    """Render Contexture Middle JSON into the normalized scholarly Markdown layer."""
    data = decode_middle_storage(data)
    effective_classical_mode = normalize_classical_marginalia_mode(classical_marginalia_mode)
    effective_classical_text_mode = normalize_classical_text_marginalia_mode(classical_text_marginalia_mode)
    if generic_line_output_mode not in {'drop', 'page_comments'}:
        raise ValueError(f'Invalid generic line output mode: {generic_line_output_mode!r}')
    # Bind footer decisions before classical projection shifts source offsets.
    folio_plan = observed_folio_plan(data)
    if effective_classical_mode == "page_locators":
        # Resolve against original source text before the footnote resolver has
        # an opportunity to normalize or otherwise project block contents.
        analysed = resolve_classical_marginalia(
            data,
            config={
                "classical_marginalia_mode": effective_classical_mode,
                "classical_text_marginalia_mode": effective_classical_text_mode,
            },
            pdf_words_by_page=classical_pdf_words_by_page,
            evidence=classical_evidence,
        )
        data = prepare_classical_render_view(analysed)
    if _resolved_token is not _RESOLVED_RENDER_TOKEN or effective_classical_mode != 'off':
        data = resolve_middle_for_rendering(
            data,
            {
                "footnote_enabled": footnote_enabled,
                "superscript_policy": superscript_policy,
            },
        )
    data = prepare_page_folio_render_view(data, folio_plan)
    pages = data.get("pages", []) if isinstance(data, dict) else []
    if not isinstance(pages, list):
        return ""

    parts: list[str] = []
    starts: list[dict[str, Any]] = []
    length = 0
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
            classical_marginalia_mode=effective_classical_mode,
            classical_text_marginalia_mode=effective_classical_text_mode,
            generic_line_output_mode=generic_line_output_mode,
        )
        lines = list(rendered_page)
        if page_footnotes:
            lines.extend([""])
            lines.extend(page_footnotes)
        from aih_contexture.middle.reading_pages import reading_text
        chunk = reading_text(_clean_markdown('\n'.join(lines)))
        if parts:
            parts.append('\n\n\n')
            length += 3
        starts.append({'index': page_index, 'anchor': str(page.get('anchor_start', page_index)), 'start': length})
        parts.append(chunk)
        length += len(chunk)

    tail = '\n\n\n' + f'{{{final_anchor}}}'
    if include_page_separators and page_separator:
        tail += '\n\n' + page_separator

    markdown = ''.join(parts) + tail + '\n'
    if not parts:
        markdown = markdown.lstrip()
    if page_manifest_out is not None:
        from aih_contexture.middle.reading_pages import page_manifest
        page_manifest_out.clear()
        page_manifest_out.update(page_manifest(markdown, starts))
    return markdown


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
    classical_marginalia_mode: str,
    classical_text_marginalia_mode: str,
    generic_line_output_mode: str = 'drop',
) -> tuple[list[str], list[str]]:
    page_index = int(page.get("index", 0))
    anchor_start = int(page.get("anchor_start", page_index))
    anchor_end = int(page.get("anchor_end", page_index + 1))
    blocks = sorted(
        (block for block in page.get("blocks", []) if isinstance(block, dict)),
        key=_block_render_order,
    )
    printed_page = _text(page.get("printed_page")) or _printed_page_from_blocks(blocks) or _header_page_number(page, blocks)

    lines = ["", f"{{{anchor_start}}}", ""]
    if include_page_separators and page_separator:
        lines.extend([page_separator, ""])
    if printed_page and include_printed_page_comments:
        lines.extend([f"<!-- Page: {_comment_text(printed_page)} -->", ""])
    if classical_marginalia_mode == "page_locators":
        locator_comments = page_locator_comments(page, generic_line_output_mode=generic_line_output_mode)
        if locator_comments:
            lines.extend(locator_comments)
            lines.append("")

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
    previous_body = None
    generic_context = any(item.get('scheme') == 'generic_line' for item in
        ((page.get('attrs') or {}).get('classical_marginalia') or {}).get('ranges', []))
    prose_geometry = native_prose_geometry(page) if classical_marginalia_mode == 'page_locators' else None
    for block in blocks:
        block_type = str(block.get("type") or "")
        if block_type in HIDDEN_BLOCK_TYPES:
            continue
        if classical_marginalia_mode == "page_locators" and block_type == "MarginalNote":
            # The analyser has already split this block into locator, restored
            # body, marginal prose, and unresolved pieces. Never let the legacy
            # renderer reclassify a locator as a footnote or bare body line.
            continue

        if include_provenance_comments:
            lines.extend([_block_comment(block, anchor_start=anchor_start, anchor_end=anchor_end), ""])

        if block_type == "Footnote" or _is_footnote_like_block(block, page):
            previous_body = None
            if ((block.get('attrs') or {}).get('footnote_status') == 'unconfirmed'
                    or classical_marginalia_mode == "page_locators" and _classical_note_marker_unconfirmed(block, blocks)):
                # A missing marker must not become an invented '1'; a plain
                # author initial such as 'A.' must remain part of the note.
                body = _reading_prose(_block_text(block))
                key = re.sub(r"\s+", " ", body).strip()
                if key not in seen_footnotes:
                    seen_footnotes.add(key)
                    footnotes.extend(["**Footnote** " + body, ""])
                continue
            for marker, body in _extract_footnote_entries(_block_text(block),
                    allow_ambiguous_alpha=(block.get('attrs') or {}).get('semantic_role') == 'footnote_definition'):
                if not marker:
                    key = re.sub(r"\s+", " ", body).strip()
                    if key not in seen_footnotes:
                        seen_footnotes.add(key)
                        footnotes.extend(["**Footnote** " + body, ""])
                    continue
                footnote_id = marker
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

        rendered_block = _render_block(
                block,
                page=page,
                anchor_start=anchor_start,
                anchor_end=anchor_end,
                include_margin_comments=include_margin_comments,
                marginal_output_mode=marginal_output_mode,
                include_blockquote_markers=include_blockquote_markers,
                equation_output_mode=equation_output_mode,
                include_provenance_comments=include_provenance_comments,
            )
        if ((generic_context or prose_geometry is not None) and not include_provenance_comments and previous_body is not None
                and block_type == 'Text' and rendered_block and _wrapped_body_blocks(previous_body, block, page, geometry=prose_geometry)):
            while lines and not lines[-1]:
                lines.pop()
            if lines:
                lines[-1] = _reading_prose(lines[-1] + '\n' + rendered_block[0])
                lines.append('')
            else:
                lines.extend(rendered_block)
        else:
            lines.extend(rendered_block)
        previous_body = block if block_type == 'Text' else None

    if classical_marginalia_mode == "page_locators":
        lines.extend(_render_classical_text_marginalia(
            page, blocks, include_confirmed=classical_text_marginalia_mode == "separate",
        ))

    return lines, footnotes


def _wrapped_body_blocks(previous: dict, current: dict, page: dict, *, geometry=None) -> bool:
    if _is_blockquote_block(previous) or _is_blockquote_block(current):
        return False
    left, right = _block_text(previous).rstrip(), _block_text(current).lstrip()
    if not left or not right:
        return False
    terminals = '.?!;:。！？；：'
    if left[-1] in terminals or left.rstrip(' \t\"\'”’»›)]}·').endswith(tuple(terminals)):
        return False
    if any(protected for _, protected in markdown_lines(left + '\n' + right)):
        return False
    boxes = [block.get('bbox') for block in (previous, current)]
    if not all(classical_bbox_is_trustworthy(box, page, block)
               for box, block in zip(boxes, (previous, current))):
        return False
    native = native_wrapped_blocks(previous, current, page,
                                   geometry if geometry is not None else native_prose_geometry(page))
    if native is not None:
        return native
    if not right[0].islower():
        return False
    sizes = []
    prose_boxes = []
    for block in (previous, current):
        fonts = [_positive_float((span.get('attrs') or {}).get('font_size'))
                 for span in block.get('spans', []) if isinstance(span, dict)]
        fonts = [value for value in fonts if value]
        if not fonts:
            return False
        size = median(fonts)
        sizes.append(size)
        evidence = [span for span in block.get('spans', [])
                    if isinstance(span, dict) and str(span.get('text') or '').strip()
                    and not str(span.get('text') or '').strip().isdigit()
                    and (_positive_float((span.get('attrs') or {}).get('font_size')) or 0) >= size * .85
                    and classical_bbox_is_trustworthy(span.get('bbox'), page, block)]
        if not evidence:
            return False
        boxes_for_words = [span['bbox'] for span in evidence]
        top = min(box[1] for box in boxes_for_words)
        first_line = [box for box in boxes_for_words if box[1] < top + size * .6]
        prose_boxes.append([min(box[0] for box in boxes_for_words), top,
                            min(box[0] for box in first_line), max(box[3] for box in boxes_for_words)])
    if not .85 < sizes[0] / sizes[1] < 1.18:
        return False
    scale = median(sizes)
    before, after = prose_boxes
    return (before[3] - scale * .4 <= after[1] <= before[3] + scale * 2.5
            and abs(before[0] - after[2]) <= scale * .75)


def _render_classical_text_marginalia(
    page: dict[str, Any], blocks: list[dict[str, Any]], *, include_confirmed: bool = True,
) -> list[str]:
    attrs = page.get("attrs") if isinstance(page.get("attrs"), dict) else {}
    analysis = attrs.get("classical_marginalia")
    if not isinstance(analysis, dict):
        return []
    by_id = {str(block.get("id") or ""): block for block in blocks}
    result: list[str] = []
    # Dropping confirmed marginal prose must not discard uncertain content,
    # especially on pages where no reliable layout geometry exists.
    items = [dict(item, _classical_display_role="text_marginal") for item in analysis.get("text_marginalia", []) or [] if isinstance(item, dict)] if include_confirmed else []
    items.extend(dict(item, _classical_display_role="undetermined") for item in analysis.get("undetermined", []) or [] if isinstance(item, dict))
    handwritten_ids = {
        str(item.get("block_id") or "")
        for item in analysis.get("handwritten", []) or []
        if isinstance(item, dict) and item.get("block_id")
    }
    seen_ids = {str(item.get("block_id") or "") for item in items if isinstance(item, dict)}
    for block_id in handwritten_ids - seen_ids:
        block = by_id.get(block_id)
        if block:
            items.append({"block_id": block_id, "raw": _block_text(block), "bbox": block.get("bbox"), "role": "handwritten_review"})
    block_order = {str(b.get("id") or ""): idx for idx, b in enumerate(blocks) if isinstance(b, dict)}
    items.sort(key=lambda item: (
        float(item.get("bbox", [0, 0, 0, 0])[1]) if isinstance(item, dict) and isinstance(item.get("bbox"), (list, tuple)) and len(item["bbox"]) == 4 else float("inf"),
        block_order.get(str(item.get("block_id") or ""), 1e9) if isinstance(item, dict) else 1e9,
        str(item.get("block_id") or "") if isinstance(item, dict) else "",
    ))
    numeric_side = ''
    numeric_values: list[str] = []

    def flush_numeric() -> None:
        if numeric_values:
            label = f'{numeric_side.title()} margin' if numeric_side else 'Margin'
            result.extend([f'> **{label}**', '>', '> '+', '.join(numeric_values), ''])
            numeric_values.clear()
    for item in items:
        if not isinstance(item, dict):
            continue
        block_id = str(item.get("block_id") or "")
        block = by_id.get(block_id)
        raw = str(item.get("raw") or "").strip()
        if not raw:
            continue
        raw = protect_editorial_angle_brackets(raw)
        side = classical_margin_side(page, block, item)
        if side in {"unknown", None, ""}:
            side = ""
        role = str(item.get("_classical_display_role") or item.get("role") or "text_marginal")
        if re.fullmatch(r'\d{1,4}', raw):
            if numeric_values and side != numeric_side:
                flush_numeric()
            numeric_side = side
            numeric_values.append(raw)
            continue
        flush_numeric()
        label = f"{side.title()} marginal note" if side else "Margin"
        result.extend([
            f"> **{label}**",
            ">",
            *[f"> {line}" if line else ">" for line in raw.splitlines()],
            "",
        ])
    flush_numeric()
    return result


def _block_top(block: dict[str, Any]) -> float:
    bbox = block.get("bbox")
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        try:
            return float(bbox[1])
        except (TypeError, ValueError):
            pass
    return float("inf")


def _block_render_order(block: dict[str, Any]) -> tuple[float, int, float, str]:
    try:
        order = float(block.get("order", 0))
    except (TypeError, ValueError):
        order = 0.0
    attrs = block.get("attrs") if isinstance(block.get("attrs"), dict) else {}
    is_restore = bool(attrs.get("classical_restore_source_id"))
    # Preserve the legacy order/id tie-break for ordinary blocks. The extra
    # y-key is only for synthetic restore fragments.
    return order, 1 if is_restore else 0, _block_top(block) if is_restore else 0.0, str(block.get("id", ""))


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
    include_provenance_comments: bool = False,
) -> list[str]:
    block_type = str(block.get("type") or "")
    text = _block_text(block)
    if block_type == 'Table':
        text = table_reading_source(block)
    if block_type not in {'Code', 'Table', 'Equation'}:
        text = escape_unpaired_prose_math(text)
    if block_type not in {'Code', 'Table', 'Equation'}:
        # Only document-owned anchors delimit physical pages. A brace literal
        # supplied by a source block must remain visible body text in Markdown.
        text = transform_prose_regions(text, lambda part: re.sub(
            r'(?m)^\{(\d+)\}[ \t]*$', r'\\{\1}', part))
    if not text and block_type not in {"Figure", "Picture", "ImageDescription"}:
        return []
    is_blockquote = _is_blockquote_block(block)
    if block_type not in {"Equation", "Table", "Text", "Code", "Form"} and not is_blockquote:
        text = _normalize_footnote_references(text)
    if block_type not in {"Equation", "Table", "Text", "Code", "Form", "ComplexRegion"} and not is_blockquote:
        text = _normalize_soft_line_breaks(text)

    if block_type == "SectionHeader":
        level = _heading_level(block)
        return [f"{'#' * level} {protect_editorial_angle_brackets(text)}", ""]
    if block_type == "Table":
        return _render_table(text)
    if block_type == 'Code':
        if re.match(r'^ {0,3}(?:`{3,}|~{3,})', text):
            return [text, '']
        runs = [len(match.group(0)) for match in re.finditer(r'`+', text)]
        fence = '`' * max(3, max(runs, default=0) + 1)
        return [fence, text, fence, '']
    if block_type == "Equation":
        if _should_render_equation_as_plain_text(text, equation_output_mode):
            return [protect_editorial_angle_brackets(text), ""]
        return ["$$", text, "$$", ""]
    if block_type == "Caption":
        return [f"*{protect_editorial_angle_brackets(text)}*", ""]
    if block_type == "Reference":
        return [protect_editorial_angle_brackets(text), ""]
    if is_blockquote:
        text = _reading_prose(text)
        if not include_blockquote_markers:
            return [text, ""]
        return _render_markdown_blockquote(text)
    if block_type == "ListItem":
        text = protect_editorial_angle_brackets(text)
        marker = re.match(r'^(\d+)([.)][.,)]*)(?=\s)', text)
        if marker:
            attrs = block.get('attrs') or {}
            literal = (len(marker[1]) > 1 and marker[1].startswith('0')) or attrs.get('semantic_role') == 'numbered_paragraph'
            if literal and marker[2] in {'.', ')'}:
                text = text[:marker.end(1)] + '\\' + text[marker.end(1):]
            return [text, '']
        return [f"- {protect_editorial_angle_brackets(text)}", ""]
    if block_type == "MarginalNote":
        if not include_margin_comments:
            return [protect_editorial_angle_brackets(text), ""]
        return _render_margin_block(
            block,
            protect_editorial_angle_brackets(text),
            page_width=_positive_float(page.get("width")),
            anchor_start=anchor_start,
            anchor_end=anchor_end,
            marginal_output_mode=marginal_output_mode,
            include_provenance_comments=include_provenance_comments,
        )
    if block_type == "InlineAnnotation":
        if not include_provenance_comments:
            return [protect_editorial_angle_brackets(text), '']
        return _render_comment_block("InlineAnnotation", block, text, anchor_start=anchor_start, anchor_end=anchor_end)
    if block_type == "ImageDescription":
        if not include_provenance_comments:
            return [protect_editorial_angle_brackets(text), '']
        return _render_comment_block("ImageDescription", block, text, anchor_start=anchor_start, anchor_end=anchor_end)
    if block_type in {"Figure", "Picture"}:
        attrs = block.get('attrs') or {}
        path = attrs.get('image_path') or attrs.get('img_path') or attrs.get('asset_path')
        if path:
            target = quote(str(path).replace('\\', '/'), safe='/:._-~')
            return [f"![{_image_alt(text or 'Image')}]({target})", '']
        if re.fullmatch(r'!\[[^\]]*\]\([^\n]+\)', text.strip()):
            return [text.strip(), '']
        caption = text or "Image"
        return [f"![{_image_alt(caption)}]()", ""]
    if block_type == "ComplexRegion":
        if is_table_group_source(block):
            structured = table_reading_source(block)
            if (re.search(r'<table\b', structured, re.I) or has_table_structure_tokens(structured)
                    or re.search(r'(?m)^\s*\|?.+\|.+\n\s*\|?\s*:?-{3,}', structured)):
                return _render_table(structured)
            return _render_unstructured_group(text)
        text = text.replace('\n', '  \n')
        if not include_provenance_comments:
            return [protect_editorial_angle_brackets(text), '']
        return _render_comment_block("ComplexRegion", block, text, anchor_start=anchor_start, anchor_end=anchor_end)
    if block_type == "Text":
        if (block.get('attrs') or {}).get('classical_body_prefix'):
            text = str(block['attrs']['classical_body_prefix'])+' '+text
        attrs = block.get('attrs') or {}
        literal = (attrs.get('source') in {'layout', 'pipeline_render_json'}
                   and not attrs.get('official_markdown_fallback'))
        return [_reading_prose(text, literal_prefixes=literal), ""]
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
    return [project_table(text)[0], ""]


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
    text = _reading_prose(body if body is not None else _block_text(block))
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
    include_provenance_comments: bool = False,
) -> list[str]:
    if marginal_output_mode == "drop":
        return []
    if marginal_output_mode == "plain":
        return [text, ""]
    if marginal_output_mode == "line_markers" and _is_plain_margin_marker(text):
        return [f"<!-- Line: {_comment_text(text)} -->", ""]
    side = _margin_side(block, page_width=page_width)
    if not include_provenance_comments:
        label = f'{side.title()} margin' if side in {'left', 'right'} else 'Margin'
        return [f'> **{label}**', '>', *[f'> {line}' if line else '>' for line in text.splitlines()], '']
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
    value = block.get('text')
    if isinstance(value, str) and value.strip():
        value = value.replace('\r\n', '\n').replace('\r', '\n')
        if block.get('type') in {'Code', 'Form', 'Table'}:
            return value.strip('\n')
        return transform_prose_regions(value, lambda part: re.sub(r'[ \t]+', ' ', part)).strip()
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


def _header_page_number(page: dict, blocks: list[dict]) -> str:
    """An isolated numeric folio in a native top-edge header, not a body regex."""
    from aih_contexture.middle.native_geometry import native_words
    width, height = page.get('width'), page.get('height')
    if not width or not height:
        return ''
    candidates = []
    for block in blocks:
        box = block.get('bbox') or []
        if block.get('type') != 'PageHeader' or len(box) != 4 or box[3] > height*.18:
            continue
        words = native_words(block, page)
        numbers = [w for w in words if re.fullmatch(r'\d{1,4}', w['raw'])]
        prose = [w for w in words if any(c.isalpha() for c in w['raw'])]
        if len(numbers) != 1:
            continue
        word = numbers[0]
        if not (word['x'] < width*.22 or word['x'] > width*.78):
            continue
        if prose:
            gap = min(max(p['bbox'][0]-word['bbox'][2], word['bbox'][0]-p['bbox'][2], 0) for p in prose)
            if gap < width*.05:
                continue
        elif _block_text(block).strip() != word['raw']:
            continue
        candidates.append(word['raw'])
    return candidates[0] if len(set(candidates)) == 1 else ''


def _is_valid_roman_page(value: str) -> bool:
    text = value.strip().upper()
    if not text:
        return False
    return re.fullmatch(r"M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})", text) is not None


def _is_footnote_like_block(block: dict[str, Any], page: dict[str, Any]) -> bool:
    block_type = str(block.get("type") or "")
    if block_type not in {"Text", "ListItem"}:
        return False
    # The semantics resolver is the authority. A chapter number in the lower
    # half of a page is not evidence of a footnote.
    attrs = block.get('attrs') or {}
    if attrs.get('semantic_role') != 'footnote_definition' or not attrs.get('footnote_evidence'):
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


def _extract_footnote_entries(text: str, *, allow_ambiguous_alpha: bool = False) -> list[tuple[str | None, str]]:
    normalized = _normalize_footnote_references(_text(text))
    normalized = _normalize_soft_line_breaks(normalized)
    if not normalized:
        return [(None, "")]
    entries = _split_html_sup_footnote_entries(normalized)
    if entries:
        return entries
    entries = split_strong_footnote_entries(normalized)
    if entries:
        return entries
    marker, body = _extract_footnote_marker_and_body(normalized, allow_ambiguous_alpha=allow_ambiguous_alpha)
    return [(marker, body)]


def _classical_note_marker_unconfirmed(block: dict[str, Any], blocks: list[dict[str, Any]]) -> bool:
    text = _block_text(block)
    match = match_leading_footnote_marker(text,
        allow_ambiguous_alpha=(block.get('attrs') or {}).get('semantic_role') == 'footnote_definition')
    if match is None:
        return True
    # Lowercase letters, explicit superscripts, numbers and symbols remain
    # supported. A plain uppercase initial needs an independent matching cue.
    if not re.match(r"^\s*[A-Z]{1,3}\.\s", text):
        return False
    reference = re.compile(r"<sup>\s*" + re.escape(match.original) + r"\s*</sup>")
    if any(reference.search(_block_text(b)) for b in blocks if b.get('type') in {'Text','ListItem'}):
        return False
    from aih_contexture.middle.native_geometry import compact_native_spans
    spans = compact_native_spans(block)
    return not (spans and (spans[0].get('attrs') or {}).get('has_superscript'))


def _split_html_sup_footnote_entries(text: str) -> list[tuple[str, str]]:
    matches = list(
        re.finditer(
            r"(?m)^\s*<sup>\s*([0-9]{1,4}|[ivxlcdm]{1,12}|[①-⑳])\s*</sup>\s*",
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


def _extract_footnote_marker_and_body(text: str, *, allow_ambiguous_alpha: bool = False) -> tuple[str | None, str]:
    normalized = _text(text)
    marker = match_leading_footnote_marker(normalized, allow_ambiguous_alpha=allow_ambiguous_alpha)
    if marker is None:
        return None, normalized
    return marker.original, normalized[marker.body_start:].strip()


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
        joined = ''
        for line in (line for line in lines if line):
            attached_hyphen = len(joined) >= 2 and joined[-1] in '-¬' and joined[-2].isalpha() and line[:1].islower()
            joined += ('' if not joined or attached_hyphen else ' ') + line
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
    text = transform_prose_regions(text, lambda value: re.sub(r"\n{4,}", "\n\n\n", value))
    return text.strip()
