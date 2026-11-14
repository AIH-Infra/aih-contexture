from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from aih_contexture.formatters import PageAnchorFormatter, PageAnchorPlugin, join_markdown_pages
from aih_contexture.providers.pdf import PdfProvider


_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_SPACE_RE = re.compile(r"[ \t\u00a0\u2000-\u200b\u3000]+")
_PRINTED_PAGE_RE = re.compile(r"^(?:\d{1,4}|[ivxlcdm]{1,10})$", re.IGNORECASE)
_ROMAN_PAGE_RE = re.compile(
    r"^M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})$",
    re.IGNORECASE,
)
_EDGE_PAGE_PREFIX_RE = re.compile(r"^(?P<page>\d{1,4}|[ivxlcdm]{1,10})(?=\s|[.·•—–-])", re.IGNORECASE)
_EDGE_PAGE_SUFFIX_RE = re.compile(r"(?<=[\s.·•—–-])(?P<page>\d{1,4}|[ivxlcdm]{1,10})$", re.IGNORECASE)
_LATIN_HYPHEN_RE = re.compile(r"([A-Za-z]{2,})-\n([a-z][A-Za-z]{1,})")


@dataclass(slots=True)
class TextLayerPageDiagnostic:
    page_index: int
    accepted: bool
    visible_characters: int
    replacement_characters: int
    control_characters: int
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_index": self.page_index,
            "accepted": self.accepted,
            "visible_characters": self.visible_characters,
            "replacement_characters": self.replacement_characters,
            "control_characters": self.control_characters,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class _PrintedPageCandidate:
    line_index: int
    label: str
    value: int
    zone: str
    start: int
    end: int


class TextLayerMarkdownConverter:
    """Render an embedded PDF text layer to conservative, page-anchored Markdown."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = dict(config or {})
        self.last_diagnostics: list[dict[str, Any]] = []
        self.last_printed_pages: list[str | None] = []
        self.last_printed_page_summary: dict[str, Any] = {}
        self.last_recommendation: dict[str, Any] = {}
        self.page_count = 0
        self.document_page_count = 0

    def __call__(self, filepath: str) -> str:
        # Click/API callers commonly carry optional settings as ``None``.
        # Passing those through overrides PdfProvider class defaults (including
        # its text-quality thresholds), so discard only unset values here.
        provider_config = {
            key: value for key, value in self.config.items() if value is not None
        }
        provider_config.update({
            "force_ocr": False,
            "keep_chars": False,
            "build_highres_images": False,
        })
        provider_config.pop("page_range", None)
        provider = PdfProvider(
            filepath,
            provider_config,
        )
        document_pages = list(provider.page_range)
        requested_pages = self.config.get("page_range")
        requested_page_set = None if requested_pages is None else {int(page) for page in requested_pages}
        if requested_page_set is not None and any(
            page < 0 or page >= provider.page_count for page in requested_page_set
        ):
            raise ValueError("text-layer page range is outside the source PDF")
        selected_pages = (
            document_pages
            if requested_page_set is None
            else [page for page in document_pages if page in requested_page_set]
        )
        self.page_count = len(selected_pages)
        self.document_page_count = len(document_pages)
        pages: list[str] = []
        diagnostics: list[TextLayerPageDiagnostic] = []
        normalized_lines: dict[int, list[str]] = {}
        candidates_by_page: dict[int, list[_PrintedPageCandidate]] = {}

        for page_index in document_pages:
            raw_lines = [
                "".join(span.text for span in line.spans)
                for line in provider.page_lines.get(page_index, [])
            ]
            replacement_characters = sum(line.count("\ufffd") for line in raw_lines)
            control_characters = sum(
                sum(ord(char) < 32 and char not in "\n\t\r" for char in line)
                for line in raw_lines
            )
            cleaned_lines = _normalized_lines(raw_lines)
            page_text = _render_lines(
                cleaned_lines,
                repair_hyphenation=bool(self.config.get("text_layer_hyphenation_repair", True)),
            )
            diagnostic = _diagnose_page(
                page_index,
                page_text,
                replacement_characters=replacement_characters,
                control_characters=control_characters,
            )
            diagnostics.append(diagnostic)
            normalized_lines[page_index] = cleaned_lines
            candidates_by_page[page_index] = _printed_page_candidates(cleaned_lines)

        # PdfProvider retains the full span/geometry graph for every page.
        # The fast path has already reduced it to normalized plain-text lines,
        # so release that graph before the page-number sequence and Markdown
        # rendering passes.
        del provider

        trusted_printed_pages = _infer_printed_page_sequences(
            document_pages,
            candidates_by_page,
            minimum_run=int(self.config.get("text_layer_min_printed_page_run", 3)),
            allowed_steps=tuple(self.config.get("text_layer_printed_page_steps", (1, 2))),
        )
        self.last_printed_page_summary = {
            "strategy": "consecutive_edge_sequence",
            "minimum_run": int(self.config.get("text_layer_min_printed_page_run", 3)),
            "allowed_steps": list(self.config.get("text_layer_printed_page_steps", (1, 2))),
            "trusted_source_pages": len(trusted_printed_pages),
            "source_page_count": self.document_page_count,
        }
        printed_pages: list[str | None] = []
        for page_index in selected_pages:
            printed_candidate = trusted_printed_pages.get(page_index)
            lines = normalized_lines[page_index]
            if printed_candidate is not None:
                lines = [
                    _remove_printed_page_label(line, printed_candidate)
                    if line_index == printed_candidate.line_index
                    else line
                    for line_index, line in enumerate(lines)
                ]
                lines = [line for line in lines if line]
            pages.append(
                _render_lines(
                    lines,
                    repair_hyphenation=bool(self.config.get("text_layer_hyphenation_repair", True)),
                )
            )
            printed_pages.append(printed_candidate.label if printed_candidate else None)

        quality_pages = [
            item
            for item in diagnostics
            if item.visible_characters >= 24 or item.replacement_characters or item.control_characters
        ]
        accepted = sum(item.accepted for item in quality_pages)
        minimum_ratio = float(self.config.get("text_layer_min_accepted_ratio", 0.9))
        sparse_pages = sum(item.reason == "sparse_page" for item in diagnostics)
        invalid_pages = sum(item.reason == "invalid_characters" for item in diagnostics)
        valid_ratio = accepted / len(quality_pages) if quality_pages else 0.0
        sparse_ratio = sparse_pages / self.document_page_count if self.document_page_count else 1.0
        recommend_screenai = (
            not quality_pages
            or valid_ratio < minimum_ratio
            or sparse_ratio > float(self.config.get("text_layer_max_sparse_ratio", 0.25))
        )

        plugin = PageAnchorPlugin(
            formatter=PageAnchorFormatter("{{{}}}"),
            enabled=True,
            position="before",
            page_separator="---",
        )
        anchored_pages = [
            plugin.wrap_page_content(page_index, text, printed_page)
            for page_index, text, printed_page in zip(selected_pages, pages, printed_pages)
        ]
        self.last_diagnostics = [item.to_dict() for item in diagnostics]
        self.last_printed_pages = printed_pages
        self.last_recommendation = {
            "recommend_screenai": recommend_screenai,
            "reason": (
                "no_substantive_text"
                if not quality_pages
                else "low_valid_text_ratio"
                if valid_ratio < minimum_ratio
                else "too_many_sparse_pages"
                if sparse_ratio > float(self.config.get("text_layer_max_sparse_ratio", 0.25))
                else None
            ),
            "substantive_pages": len(quality_pages),
            "valid_substantive_pages": accepted,
            "sparse_pages": sparse_pages,
            "invalid_pages": invalid_pages,
            "valid_substantive_ratio": valid_ratio,
            "sparse_page_ratio": sparse_ratio,
            "assessment_scope": "source_document",
            "assessment_page_count": self.document_page_count,
            "output_page_count": self.page_count,
        }
        # Empty source pages carry an anchor but no text.  Joining two such
        # pages otherwise leaves four newline characters around the separator.
        # Keep the page boundary while restoring the documented two-newline
        # maximum for Markdown whitespace.
        rendered = join_markdown_pages(anchored_pages, page_anchors_enabled=True)
        return re.sub(r"\n{3,}", "\n\n", rendered).strip() + "\n"


def _normalized_lines(lines: list[str]) -> list[str]:
    cleaned = [_normalize_line(line) for line in lines]
    return [line for line in cleaned if line]


def _render_lines(lines: list[str], *, repair_hyphenation: bool) -> str:
    text = "\n".join(lines)
    if repair_hyphenation:
        text = _LATIN_HYPHEN_RE.sub(r"\1\2", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _normalize_line(value: str) -> str:
    value = unicodedata.normalize("NFC", value or "")
    value = value.replace("\ufffd", "").replace("\u200b", "")
    value = _CONTROL_RE.sub(" ", value)
    return _SPACE_RE.sub(" ", value).strip()


def _printed_page_candidates(lines: list[str]) -> list[_PrintedPageCandidate]:
    candidates: list[_PrintedPageCandidate] = []
    edge_size = min(3, len(lines))
    for line_index, line in enumerate(lines):
        zone = "head" if line_index < edge_size else "foot" if line_index >= len(lines) - edge_size else None
        if zone is None:
            continue
        match = _PRINTED_PAGE_RE.fullmatch(line) or _EDGE_PAGE_PREFIX_RE.search(line) or _EDGE_PAGE_SUFFIX_RE.search(line)
        if match is None:
            continue
        label = match.group("page") if "page" in match.groupdict() else match.group(0)
        value = _printed_page_value(label)
        if value is not None:
            candidates.append(_PrintedPageCandidate(line_index, label, value, zone, match.start(), match.end()))
    return candidates


def _remove_printed_page_label(line: str, candidate: _PrintedPageCandidate) -> str:
    return _normalize_line(line[: candidate.start] + line[candidate.end :])


def _printed_page_value(value: str) -> int | None:
    if value.isdecimal():
        return int(value)
    if not _ROMAN_PAGE_RE.fullmatch(value):
        return None
    symbols = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    numbers = [symbols[character] for character in value.upper()]
    return sum(-number if index + 1 < len(numbers) and number < numbers[index + 1] else number for index, number in enumerate(numbers))


def _infer_printed_page_sequences(
    document_pages: list[int],
    candidates_by_page: dict[int, list[_PrintedPageCandidate]],
    *,
    minimum_run: int,
    allowed_steps: tuple[int, ...],
) -> dict[int, _PrintedPageCandidate]:
    """Trust only a same-edge, physically consecutive, fixed-step page sequence."""
    trusted: dict[int, _PrintedPageCandidate] = {}
    minimum_run = max(2, minimum_run)
    allowed_steps = tuple(step for step in allowed_steps if step > 0) or (1,)
    for start_position, start_page in enumerate(document_pages):
        for start_candidate in candidates_by_page[start_page]:
            if start_position + 1 >= len(document_pages):
                continue
            next_page = document_pages[start_position + 1]
            if next_page != start_page + 1:
                continue
            for second_candidate in candidates_by_page[next_page]:
                step = second_candidate.value - start_candidate.value
                if second_candidate.zone != start_candidate.zone or step not in allowed_steps:
                    continue
                run = [(start_page, start_candidate), (next_page, second_candidate)]
                expected_value = second_candidate.value + step
                for page_index in document_pages[start_position + 2 :]:
                    previous_page = run[-1][0]
                    if page_index != previous_page + 1:
                        break
                    next_candidate = next(
                        (
                            candidate
                            for candidate in candidates_by_page[page_index]
                            if candidate.zone == start_candidate.zone and candidate.value == expected_value
                        ),
                        None,
                    )
                    if next_candidate is None:
                        break
                    run.append((page_index, next_candidate))
                    expected_value += step
                if len(run) >= minimum_run:
                    trusted.update(run)
    return trusted


def _diagnose_page(
    page_index: int,
    text: str,
    *,
    replacement_characters: int = 0,
    control_characters: int = 0,
) -> TextLayerPageDiagnostic:
    visible = sum(not char.isspace() for char in text)
    reason = None
    if visible < 24:
        reason = "sparse_page"
    elif replacement_characters or control_characters:
        reason = "invalid_characters"
    return TextLayerPageDiagnostic(
        page_index=page_index,
        accepted=reason in {None, "sparse_page"},
        visible_characters=visible,
        replacement_characters=replacement_characters,
        control_characters=control_characters,
        reason=reason,
    )
