from __future__ import annotations

import re

from bs4 import BeautifulSoup


_MARGIN_BLOCK_RE = re.compile(
    r"<!--\s*Margin(?::[A-Za-z_-]+)?(?:\s+[^>]*)?\s*-->\s*(.*?)\s*<!--\s*/Margin\s*-->",
    re.IGNORECASE | re.DOTALL,
)
_STANDALONE_MARGIN_MARKER_RE = re.compile(
    r"(?im)^\s*<!--\s*/?Margin(?::[A-Za-z_-]+)?(?:\s+[^>]*)?\s*-->\s*$"
)
_HTML_BLOCKQUOTE_RE = re.compile(
    r"<blockquote\b[^>]*>.*?</blockquote>",
    re.IGNORECASE | re.DOTALL,
)


def strip_margin_comment_markers(markdown: str) -> str:
    """Remove Contexture Margin comment wrappers while preserving marginalia text."""
    if not markdown:
        return markdown

    def replace_margin_block(match: re.Match[str]) -> str:
        body = match.group(1)
        body = re.sub(r"(?m)^\s*>\s?", "", body)
        return body.strip()

    markdown = _MARGIN_BLOCK_RE.sub(replace_margin_block, markdown)
    return _STANDALONE_MARGIN_MARKER_RE.sub("", markdown)


def strip_blockquote_markers(markdown: str) -> str:
    """Remove recognized blockquote wrappers while preserving quoted text."""
    if not markdown:
        return markdown

    markdown = _HTML_BLOCKQUOTE_RE.sub(
        lambda match: _html_blockquote_to_text(match.group(0)),
        markdown,
    )
    return _strip_markdown_blockquote_lines(markdown)


def _html_blockquote_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    quote = soup.find("blockquote")
    if quote is None:
        return html
    return quote.get_text("\n").strip()


def _strip_markdown_blockquote_lines(markdown: str) -> str:
    lines = markdown.splitlines()
    output: list[str] = []
    quote_buffer: list[str] = []
    protected_comment_block: str | None = None

    def flush_quote() -> None:
        nonlocal quote_buffer
        if not quote_buffer:
            return
        output.extend(quote_buffer)
        quote_buffer = []

    for line in lines:
        marker = _comment_block_marker(line)
        if marker:
            flush_quote()
            protected_comment_block = marker
            output.append(line)
            continue

        if protected_comment_block:
            output.append(line)
            if _is_comment_block_end(line, protected_comment_block):
                protected_comment_block = None
            continue

        match = re.match(r"^([ \t]{0,3})>\s?(.*)$", line)
        if match and not _looks_like_html_comment_line(match.group(2)):
            quote_buffer.append(match.group(1) + match.group(2))
            continue

        flush_quote()
        output.append(line)

    flush_quote()
    return "\n".join(output)


def _looks_like_html_comment_line(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("<!--") or stripped.endswith("-->")


def _comment_block_marker(line: str) -> str | None:
    match = re.match(r"^\s*<!--\s*(Margin|InlineAnnotation|ImageDescription|ComplexRegion)\b", line, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).lower()


def _is_comment_block_end(line: str, marker: str) -> bool:
    return re.match(rf"^\s*<!--\s*/{re.escape(marker)}\s*-->\s*$", line, flags=re.IGNORECASE) is not None
