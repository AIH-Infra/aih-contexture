from __future__ import annotations

import re


_MARGIN_BLOCK_RE = re.compile(
    r"<!--\s*Margin(?::[A-Za-z_-]+)?(?:\s+[^>]*)?\s*-->\s*(.*?)\s*<!--\s*/Margin\s*-->",
    re.IGNORECASE | re.DOTALL,
)
_STANDALONE_MARGIN_MARKER_RE = re.compile(
    r"(?im)^\s*<!--\s*/?Margin(?::[A-Za-z_-]+)?(?:\s+[^>]*)?\s*-->\s*$"
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
