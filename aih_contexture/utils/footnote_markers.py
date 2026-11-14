from __future__ import annotations

import html
import re
from dataclasses import dataclass


UNICODE_SUPERSCRIPT_DIGITS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")

_ENCLOSED_MARKER_GROUPS = (
    ("⓪", 0),
    ("①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳", 1),
    ("⑴⑵⑶⑷⑸⑹⑺⑻⑼⑽⑾⑿⒀⒁⒂⒃⒄⒅⒆⒇", 1),
    ("⒈⒉⒊⒋⒌⒍⒎⒏⒐⒑⒒⒓⒔⒕⒖⒗⒘⒙⒚⒛", 1),
    ("❶❷❸❹❺❻❼❽❾❿", 1),
    ("➀➁➂➃➄➅➆➇➈➉", 1),
    ("➊➋➌➍➎➏➐➑➒➓", 1),
)
ENCLOSED_MARKER_VALUES = {
    char: start + offset
    for chars, start in _ENCLOSED_MARKER_GROUPS
    for offset, char in enumerate(chars)
}
ENCLOSED_MARKER_CHARS = "".join(ENCLOSED_MARKER_VALUES)
ENCLOSED_MARKER_CLASS = re.escape(ENCLOSED_MARKER_CHARS)

_TAG_RE = re.compile(r"<[^>]+>")
_TRAILING_MARKER_PUNCTUATION_RE = re.compile(r"[)\].-]+$")
_HTML_SUP_LEADING_RE = re.compile(
    rf"^\s*<sup[^>]*>\s*(?P<marker>[0-9]{{1,4}}|[A-Za-z]{{1,3}}|[ivxlcdmIVXLCDM]{{1,12}}|[⁰¹²³⁴⁵⁶⁷⁸⁹]+|[{ENCLOSED_MARKER_CLASS}]|[*†‡§¶#]+)\s*</sup>"
    r"(?P<suffix>[.)]?)\s*",
    re.IGNORECASE,
)
_ENCLOSED_LEADING_RE = re.compile(
    rf"^\s*(?P<marker>[{ENCLOSED_MARKER_CLASS}])(?P<suffix>[.)]?)\s*"
)
_UNICODE_SUPERSCRIPT_LEADING_RE = re.compile(
    r"^\s*(?P<marker>[⁰¹²³⁴⁵⁶⁷⁸⁹]+)(?P<suffix>[.)]?)\s*"
)
_LATEX_SUPERSCRIPT_LEADING_RE = re.compile(
    r"^\s*\\\(\s*\^\s*\{?(?P<marker>[0-9]{1,4})\}?\s*\\\)(?P<suffix>[.)]?)\s*"
)
_CARET_SUPERSCRIPT_LEADING_RE = re.compile(
    r"^\s*\^(?P<marker>[0-9]{1,4})(?P<suffix>[.)]?)\^?\s*"
)
_PLAIN_LEADING_RE = re.compile(
    r"^\s*(?P<marker>[0-9]{1,4}|[ivxlcdmIVXLCDM]{1,12}|[*†‡§¶#]+)"
    r"(?P<suffix>[.)]?)(?P<space>\s+)",
    re.IGNORECASE,
)
_PLAIN_ALPHA_LEADING_RE = re.compile(
    r"^\s*(?P<marker>[A-Za-z]{1,3})(?P<suffix>[.)])(?P<space>\s+)",
    re.IGNORECASE,
)
_PAREN_NUMERIC_LEADING_RE = re.compile(
    r'^\s*\((?P<marker>[0-9]{1,4})\)(?P<suffix>[.]?)(?P<space>\s+)'
)
_AMBIGUOUS_ALPHA_PROSE_RE = re.compile(
    r'^\s*(?:d\.\s*[hi]\.|z\.\s*b\.|u\.\s*a\.|s\.\s*(?:\d|den\b|die\b|das\b|auch\b|oben\b|unten\b))', re.I
)
_STRONG_INTERNAL_MARKER_RE = re.compile(
    rf"(?P<boundary>^|[\n\r.!?。！？;；:：])(?P<space>[ \t]*)"
    rf"(?P<marker>[0-9]{{1,4}}|[⁰¹²³⁴⁵⁶⁷⁸⁹]+|[{ENCLOSED_MARKER_CLASS}])"
    r"(?P<suffix>[.)]?)(?P<after>\s+)",
    re.MULTILINE,
)


@dataclass(frozen=True)
class FootnoteMarkerMatch:
    original: str
    normalized: str
    style: str
    start: int
    end: int
    body_start: int


def _plain_marker(value: str) -> str:
    return html.unescape(_TAG_RE.sub("", str(value or ""))).strip()


def normalize_footnote_marker(value: str) -> str | None:
    marker = _TRAILING_MARKER_PUNCTUATION_RE.sub("", _plain_marker(value)).strip()
    if not marker:
        return None
    if len(marker) == 1 and marker in ENCLOSED_MARKER_VALUES:
        return str(ENCLOSED_MARKER_VALUES[marker])
    if all(char in "⁰¹²³⁴⁵⁶⁷⁸⁹" for char in marker):
        marker = marker.translate(UNICODE_SUPERSCRIPT_DIGITS)
    if marker.isascii() and marker.isdigit():
        return str(int(marker))
    if re.fullmatch(r"[ivxlcdmIVXLCDM]{1,12}", marker):
        return marker.lower()
    if re.fullmatch(r"[A-Za-z]{1,3}|[*†‡§¶#]+", marker):
        return marker.lower()
    return None


def marker_style(value: str) -> str | None:
    marker = _plain_marker(value)
    if len(marker) == 1 and marker in ENCLOSED_MARKER_VALUES:
        return "enclosed"
    if marker and all(char in "⁰¹²³⁴⁵⁶⁷⁸⁹" for char in marker):
        return "numeric"
    if marker.isascii() and marker.isdigit():
        return "numeric"
    if re.fullmatch(r"[ivxlcdmIVXLCDM]{1,12}", marker):
        return "roman"
    if re.fullmatch(r"[A-Za-z]{1,3}", marker):
        return "alpha"
    if re.fullmatch(r"[*†‡§¶#]+", marker):
        return "symbol"
    return None


def marker_from_value(value: str) -> FootnoteMarkerMatch | None:
    original = _plain_marker(value)
    normalized = normalize_footnote_marker(original)
    style = marker_style(original)
    if normalized is None or style is None:
        return None
    return FootnoteMarkerMatch(original, normalized, style, 0, len(str(value or "")), len(str(value or "")))


def match_leading_footnote_marker(text: str, *, allow_ambiguous_alpha: bool = False) -> FootnoteMarkerMatch | None:
    value = str(text or "")
    for pattern in (
        _HTML_SUP_LEADING_RE,
        _ENCLOSED_LEADING_RE,
        _UNICODE_SUPERSCRIPT_LEADING_RE,
        _LATEX_SUPERSCRIPT_LEADING_RE,
        _CARET_SUPERSCRIPT_LEADING_RE,
        _PAREN_NUMERIC_LEADING_RE,
        _PLAIN_ALPHA_LEADING_RE,
        _PLAIN_LEADING_RE,
    ):
        match = pattern.match(value)
        if not match:
            continue
        original = match.group("marker")
        # A plain multi-letter word followed by a period is not sufficient
        # evidence for a note call (Anm., Cf., ed., etc.). Explicit superscript
        # markers and roman numerals retain their existing representation.
        if pattern in {_PLAIN_ALPHA_LEADING_RE, _PLAIN_LEADING_RE} and not allow_ambiguous_alpha:
            if _AMBIGUOUS_ALPHA_PROSE_RE.match(value):
                continue
            if (len(original) > 1 and original.isalpha()
                    and not re.fullmatch(r'[ivxlcdmIVXLCDM]{1,12}', original)):
                continue
        normalized = normalize_footnote_marker(original)
        style = marker_style(original)
        if normalized is None or style is None:
            continue
        marker_start, marker_end = match.span("marker")
        return FootnoteMarkerMatch(
            original=original,
            normalized=normalized,
            style=style,
            start=marker_start,
            end=marker_end,
            body_start=match.end(),
        )
    return None


def marker_sequence_value(marker: FootnoteMarkerMatch | None) -> int | None:
    if marker is None or marker.style not in {"numeric", "enclosed"}:
        return None
    if not marker.normalized.isdigit():
        return None
    return int(marker.normalized)


def is_next_footnote_marker(
    previous: FootnoteMarkerMatch | None,
    candidate: FootnoteMarkerMatch | None,
) -> bool:
    if previous is None or candidate is None or previous.style != candidate.style:
        return False
    previous_value = marker_sequence_value(previous)
    candidate_value = marker_sequence_value(candidate)
    return (
        previous_value is not None
        and candidate_value is not None
        and candidate_value == previous_value + 1
    )


def extract_strong_footnote_marker_sequence(text: str) -> list[FootnoteMarkerMatch]:
    value = str(text or "")
    leading = match_leading_footnote_marker(value)
    if leading is None:
        return []
    markers = [leading]
    previous = leading
    for match in _STRONG_INTERNAL_MARKER_RE.finditer(value, leading.body_start):
        original = match.group("marker")
        normalized = normalize_footnote_marker(original)
        style = marker_style(original)
        if normalized is None or style is None:
            continue
        candidate = FootnoteMarkerMatch(
            original=original,
            normalized=normalized,
            style=style,
            start=match.start("marker"),
            end=match.end("marker"),
            body_start=match.end(),
        )
        if not is_next_footnote_marker(previous, candidate):
            continue
        markers.append(candidate)
        previous = candidate
    return markers


def split_strong_footnote_entries(text: str) -> list[tuple[str, str]]:
    value = str(text or "")
    markers = extract_strong_footnote_marker_sequence(value)
    if not markers:
        return []
    entries: list[tuple[str, str]] = []
    for index, marker in enumerate(markers):
        end = markers[index + 1].start if index + 1 < len(markers) else len(value)
        body = value[marker.body_start:end].strip()
        if body:
            entries.append((marker.original, body))
    return entries
