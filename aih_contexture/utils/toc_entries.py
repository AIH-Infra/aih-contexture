from __future__ import annotations

import re


ROMAN_PAGE_RE = r"[ivxlcdmIVXLCDM]{1,8}"
ARABIC_PAGE_RE = r"\d{1,4}"
PAGE_AT_END_RE = re.compile(
    rf"^(?P<title>\S.*?)(?:[\s\u00a0]*[·.•⋯…\-\u2013\u2014]*)\s+"
    rf"(?P<page>{ARABIC_PAGE_RE}|{ROMAN_PAGE_RE})\s*$"
)
PURE_PAGE_NUMBER_RE = re.compile(rf"^\s*(?:{ARABIC_PAGE_RE}|{ROMAN_PAGE_RE})\s*$")
ENTRY_START_RE = re.compile(r"^\s*\d{1,4}[.-]\s+")
HEADING_START_RE = re.compile(
    r"^(?:BOOK|CHAPTER|PART|SECTION|CONTENTS?|目录)\b",
    re.IGNORECASE,
)
CREDIT_RE = re.compile(
    r"^[A-Z][A-Za-z.'\-\u2019]+(?:\s+[A-Z][A-Za-z.'\-\u2019]+){0,5}$"
)


def plain_toc_text(html: str) -> str:
    text = re.sub(r"<[^>]+>", "", html or "")
    return " ".join(text.strip().split())


def line_page_suffix(text: str) -> tuple[str, str] | None:
    value = plain_toc_text(text)
    if not value or PURE_PAGE_NUMBER_RE.match(value):
        return None
    match = PAGE_AT_END_RE.match(value)
    if not match:
        return None
    title = match.group("title").strip()
    page = match.group("page")
    letters = re.sub(r"[^A-Za-z\u00c0-\u024f\u4e00-\u9fff]", "", title)
    if len(letters) < 2:
        return None
    if title[-1:] in ":-":
        return None
    # "Chapter I" is a heading, "Notes vii" is a front-matter entry.
    if page.isalpha() and HEADING_START_RE.match(title):
        return None
    return title, page


def looks_like_toc_heading(text: str) -> bool:
    normalized = plain_toc_text(text)
    if not normalized or line_page_suffix(normalized):
        return False
    if HEADING_START_RE.match(normalized):
        return True
    if re.match(r"^[A-Z]\.\s+\S", normalized):
        return True
    letters = re.sub(r"[^A-Za-z]+", "", normalized)
    return len(letters) >= 6 and letters.upper() == letters and " " in normalized


def looks_like_toc_credit(text: str) -> bool:
    normalized = plain_toc_text(text)
    if not normalized or line_page_suffix(normalized) or looks_like_toc_heading(normalized):
        return False
    if any(ch.isdigit() for ch in normalized):
        return False
    if len(normalized) > 60:
        return False
    return CREDIT_RE.match(normalized) is not None


def looks_like_title_wrap(previous: str, current: str) -> bool:
    prev = plain_toc_text(previous)
    cur = plain_toc_text(current)
    if not prev or not cur or line_page_suffix(prev):
        return False
    if looks_like_toc_heading(cur) or looks_like_toc_credit(cur):
        return False
    if ENTRY_START_RE.match(cur):
        return False
    first = cur[:1]
    return first.islower() or prev.endswith((":", ",", ";", "and", "of", "the"))


def is_toc_line_cluster(lines: list[str]) -> bool:
    scored = [line for line in lines if plain_toc_text(line)]
    if len(scored) < 2:
        return False
    hits = sum(1 for line in scored if line_page_suffix(line) is not None)
    return hits >= 2 and hits >= len(scored) / 2


def group_toc_text_lines(lines: list[str]) -> list[dict[str, object]]:
    """Group plain TOC lines into headings, entries, and credits.

    Each item is {"kind": "heading"|"entry", "lines": [str, ...], "complete": bool}.
    """
    entries: list[dict[str, object]] = []
    current: dict[str, object] | None = None

    def flush() -> None:
        nonlocal current
        if current is not None:
            entries.append(current)
            current = None

    for raw in lines:
        text = plain_toc_text(raw)
        if not text:
            continue

        if looks_like_toc_heading(text):
            flush()
            entries.append({"kind": "heading", "lines": [raw], "complete": True})
            continue

        if line_page_suffix(text):
            if current is None or current.get("complete"):
                flush()
                current = {"kind": "entry", "lines": [raw], "complete": True}
            else:
                current["lines"].append(raw)
                current["complete"] = True
            continue

        if current is None:
            current = {"kind": "entry", "lines": [raw], "complete": False}
            continue

        prev = str(current["lines"][-1])
        if not current.get("complete") and looks_like_title_wrap(prev, text):
            current["lines"].append(raw)
            continue
        if current.get("complete") and looks_like_toc_credit(text):
            current["lines"].append(raw)
            continue

        flush()
        current = {"kind": "entry", "lines": [raw], "complete": False}

    flush()
    return entries


from typing import Callable, TypeVar


T = TypeVar("T")


def group_toc_items(items: list[T], text_of: Callable[[T], str]) -> list[dict[str, object]]:
    """Group TOC items using the same rules as group_toc_text_lines."""
    entries: list[dict[str, object]] = []
    current: dict[str, object] | None = None

    def flush() -> None:
        nonlocal current
        if current is not None:
            entries.append(current)
            current = None

    for item in items:
        text = plain_toc_text(text_of(item))
        if not text:
            continue

        if looks_like_toc_heading(text):
            flush()
            entries.append({"kind": "heading", "lines": [item], "complete": True})
            continue

        if line_page_suffix(text):
            if current is None or current.get("complete"):
                flush()
                current = {"kind": "entry", "lines": [item], "complete": True}
            else:
                current["lines"].append(item)
                current["complete"] = True
            continue

        if current is None:
            current = {"kind": "entry", "lines": [item], "complete": False}
            continue

        prev = text_of(current["lines"][-1])
        if not current.get("complete") and looks_like_title_wrap(prev, text):
            current["lines"].append(item)
            continue
        if current.get("complete") and looks_like_toc_credit(text):
            current["lines"].append(item)
            continue

        flush()
        current = {"kind": "entry", "lines": [item], "complete": False}

    flush()
    return entries
