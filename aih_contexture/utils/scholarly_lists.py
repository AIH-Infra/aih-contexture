from __future__ import annotations

import re

import regex
from aih_contexture.utils.markdown_regions import markdown_lines

from aih_contexture.utils.footnote_markers import (
    match_leading_footnote_marker,
    marker_sequence_value,
)


_HYPHEN_END_RE = regex.compile(r".*[\p{Ll}\d][-—¬]\s*$", regex.DOTALL)
_LEADING_EMPHASIS_RE = re.compile(
    r"^(?:(?:\*|_){1,3}|<(?:i|em|b|strong)\b[^>]*>)+",
    re.IGNORECASE,
)
_TRAILING_EMPHASIS_RE = re.compile(
    r"(?:(?:\*|_){1,3}|</(?:i|em|b|strong)>)+$",
    re.IGNORECASE,
)
_BULLET_ITEM_RE = re.compile(
    r"^\s*(?:[•●○◦■▪▫–—·]|\*|-)(?:\s+|$)"
)
_PAGE_ANCHOR_RE = re.compile(r"^\{\d+\}\s*$")
_PAGE_RULE_RE = re.compile(r"^-{3,}\s*$")
_PAGE_COMMENT_RE = re.compile(
    r"^<!--\s*Page(?:Header|Footer)?:.*?-->\s*$",
    re.IGNORECASE,
)
LINKED_NOTE_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?:(?P<bullet>[-*+])\s+)?"
    r"\[(?P<number>\d{1,4})(?P<marker>\.)?(?:[ \t]+(?P<fused>[A-Za-z]))?\]"
    r"\((?P<url>#[^)]+|[^)]+)\)(?P<trailing>\.)?"
    r"(?P<rest>.*)$",
    re.MULTILINE,
)
PLAIN_NOTE_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?:(?P<bullet>[-*+])\s+)?"
    r"(?P<number>\d{1,4})(?P<escape>\\?)(?P<marker>[.)])"
    r"(?P<space>\s+)(?P<body>\S.*)$",
    re.MULTILINE,
)
PLACEHOLDER_PAGE_LINK_RE = re.compile(r"^#page--\d+(?:-\d+)?$", re.IGNORECASE)


def strip_leading_emphasis(text: str) -> str:
    value = str(text or "").strip()
    while True:
        updated = _LEADING_EMPHASIS_RE.sub("", value, count=1)
        if updated == value:
            return value.lstrip()
        value = updated.lstrip()


def strip_trailing_emphasis(text: str) -> str:
    value = str(text or "").rstrip()
    while True:
        updated = _TRAILING_EMPHASIS_RE.sub("", value, count=1)
        if updated == value:
            return value.rstrip()
        value = updated.rstrip()


def leading_numeric_note_value(text: str) -> int | None:
    raw = str(text or "")
    linked = LINKED_NOTE_RE.match(raw)
    if linked:
        return int(linked.group("number"))
    marker = match_leading_footnote_marker(raw)
    if marker is None or marker.style not in {"numeric", "enclosed"}:
        return None
    return marker_sequence_value(marker)


def looks_like_bullet_item(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    if leading_numeric_note_value(value) is not None:
        return False
    return _BULLET_ITEM_RE.match(value) is not None


def looks_like_wrapped_continuation(previous: str, current: str) -> bool:
    prev = str(previous or "").rstrip()
    cur = strip_leading_emphasis(str(current or ""))
    if not prev or not cur:
        return False
    if leading_numeric_note_value(cur) is not None:
        return False
    if looks_like_bullet_item(cur):
        return False
    if _HYPHEN_END_RE.match(strip_trailing_emphasis(prev)):
        return True
    first = cur[0]
    if first.islower() or first in ",;:)]}":
        return True
    if first == "(" and not prev.endswith((".", "?", "!", "。", "？", "！")):
        return True
    return False


def join_wrapped_continuation(previous: str, current: str) -> str:
    prev = str(previous or "").rstrip()
    cur_plain = strip_leading_emphasis(str(current or ""))
    prev_core = strip_trailing_emphasis(prev)
    if _HYPHEN_END_RE.match(prev_core):
        return prev_core.rstrip()[:-1] + cur_plain
    if prev_core.endswith("-") and cur_plain[:1].islower():
        return prev_core[:-1] + cur_plain
    return f"{prev} {cur_plain}".replace("  ", " ")


def is_placeholder_page_link(url: str | None) -> bool:
    if not url:
        return False
    return PLACEHOLDER_PAGE_LINK_RE.fullmatch(str(url).strip()) is not None


def is_page_boundary_line(line: str) -> bool:
    stripped = str(line or "").strip()
    if not stripped:
        return True
    return bool(
        _PAGE_ANCHOR_RE.match(stripped)
        or _PAGE_RULE_RE.match(stripped)
        or _PAGE_COMMENT_RE.match(stripped)
    )



def repair_fused_note_links(markdown: str) -> str:
    """Turn ``- [5. L](#page--1-0)ev`` into a plain numbered note."""

    def replace(match: re.Match[str]) -> str:
        number = match.group("number")
        fused = match.group("fused") or ""
        rest = match.group("rest") or ""
        url = match.group("url") or ""
        if fused and is_placeholder_page_link(url):
            body = (fused + rest.lstrip()).lstrip()
            return f"{number}. {body}".rstrip()
        if is_placeholder_page_link(url):
            trailing = match.group("trailing") or match.group("marker") or "."
            body = (rest or "").lstrip()
            if body.startswith("."):
                trailing = "."
                body = body[1:].lstrip()
            return f"{number}{trailing} {body}".rstrip()
        return match.group(0)

    output: list[str] = []
    for line, protected in markdown_lines(markdown):
        if protected:
            output.append(line)
            continue
        output.append(LINKED_NOTE_RE.sub(replace, line))
    return "".join(output)


def flatten_nested_numbered_notes(markdown: str) -> str:
    """Keep consecutive numbered notes as siblings, never nested Markdown lists."""
    output: list[str] = []
    for line, protected in markdown_lines(markdown):
        if protected:
            output.append(line)
            continue
        ending = '\r\n' if line.endswith('\r\n') else '\n' if line.endswith('\n') else ''
        linked = LINKED_NOTE_RE.match(line)
        plain = PLAIN_NOTE_RE.match(line)
        if linked:
            url = linked.group("url") or ""
            should_flatten = bool(linked.group("indent")) or is_placeholder_page_link(url)
            if should_flatten:
                number = linked.group("number")
                rest = (linked.group("rest") or "").lstrip()
                trailing = linked.group("trailing") or linked.group("marker") or "."
                if rest.startswith("."):
                    trailing = "."
                    rest = rest[1:].lstrip()
                if linked.group("fused"):
                    rest = f"{linked.group('fused')}{rest}"
                output.append(f"{number}{trailing} {rest}".rstrip() + ending)
                continue
        if plain and plain.group("indent"):
            output.append(
                f"{plain.group('number')}{plain.group('marker')} {plain.group('body')}".rstrip() + ending
            )
            continue
        output.append(line)
    return "".join(output)


def unindent_page_start_continuations(markdown: str) -> str:
    """Keep a wrapped leftover on the new page, but do not nest it.

    Page markers stay where they are. The first line after a page boundary
    is only un-indented / de-bulleted when it is clearly the remainder of
    the previous note. The text itself is never moved back to the previous
    page.
    """
    guarded_lines = list(markdown_lines(markdown))
    lines = [line for line, _ in guarded_lines]
    output: list[str] = []
    index = 0
    while index < len(lines):
        output.append(lines[index])
        if guarded_lines[index][1] or not _PAGE_ANCHOR_RE.match(lines[index].strip()):
            index += 1
            continue

        cursor = index + 1
        while cursor < len(lines) and is_page_boundary_line(lines[cursor]) and not (
            lines[cursor].strip()
            and _PAGE_ANCHOR_RE.match(lines[cursor].strip())
            and cursor > index
        ):
            output.append(lines[cursor])
            cursor += 1
        while cursor < len(lines) and not lines[cursor].strip():
            output.append(lines[cursor])
            cursor += 1
        if cursor >= len(lines):
            index = cursor
            continue

        previous_idx = len(output) - 1
        while previous_idx >= 0 and is_page_boundary_line(output[previous_idx]):
            previous_idx -= 1
        previous = output[previous_idx] if previous_idx >= 0 else ""
        current = lines[cursor]
        if not guarded_lines[cursor][1] and looks_like_wrapped_continuation(previous, current):
            stripped = current.lstrip()
            if stripped.startswith(("- ", "* ", "+ ")):
                stripped = stripped[2:]
            output.append(stripped)
        else:
            output.append(current)
        index = cursor + 1

    return "".join(output)


def repair_scholarly_reference_markdown(markdown: str) -> str:
    markdown = repair_fused_note_links(markdown)
    markdown = flatten_nested_numbered_notes(markdown)
    markdown = unindent_page_start_continuations(markdown)
    return markdown
