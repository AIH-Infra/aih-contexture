from __future__ import annotations

from collections import Counter

from bs4 import BeautifulSoup, NavigableString, Tag

from aih_contexture.schema import BlockTypes
from aih_contexture.utils.footnote_markers import (
    extract_strong_footnote_marker_sequence,
    marker_from_value,
    match_leading_footnote_marker,
)


def _visible_text_before(root: BeautifulSoup, target: Tag) -> str:
    pieces: list[str] = []
    for node in root.descendants:
        if node is target:
            break
        if isinstance(node, NavigableString):
            pieces.append(str(node))
    return "".join(pieces)


def _first_visible_text(root: BeautifulSoup) -> NavigableString | None:
    for node in root.descendants:
        if isinstance(node, NavigableString) and str(node).strip():
            return node
    return None


def _wrap_leading_marker(root: BeautifulSoup):
    first_text = _first_visible_text(root)
    if first_text is None:
        return None, None

    parent = first_text.parent
    if isinstance(parent, Tag) and parent.name == "sup":
        marker = marker_from_value(parent.get_text("", strip=True))
        return (parent, marker) if marker is not None else (None, None)

    marker = match_leading_footnote_marker(str(first_text))
    if marker is None:
        return None, None

    value = str(first_text)
    before = value[: marker.start]
    body = value[marker.body_start :]
    if before:
        first_text.insert_before(NavigableString(before))
    sup = root.new_tag("sup")
    sup.string = marker.original
    first_text.insert_before(sup)
    if body:
        first_text.insert_before(NavigableString(" " + body.lstrip()))
    first_text.extract()
    return sup, marker


def _has_pdftext_spans(document, block_id) -> bool:
    block = document.get_block(block_id) if document is not None else None
    if block is None:
        return False
    spans = block.contained_blocks(document, (BlockTypes.Span,))
    return any(getattr(span, "text_extraction_method", None) == "pdftext" for span in spans)


def normalize_footnote_html(
    html_text: str,
    *,
    document,
    block_id,
    superscript_policy: str = "footnote_safe",
) -> str:
    if not html_text:
        return html_text

    policy = str(superscript_policy or "footnote_safe").strip().lower()
    root = BeautifulSoup(html_text, "html.parser")
    leading_tag, leading_marker = _wrap_leading_marker(root)

    if policy == "suppress_all":
        for tag in list(root.find_all("sup")):
            tag.unwrap()
        return str(root)
    if policy == "preserve_all" or not _has_pdftext_spans(document, block_id):
        return str(root)

    block = document.get_block(block_id) if document is not None else None
    raw_text = block.raw_text(document) if block is not None else root.get_text(" ")
    sequence = extract_strong_footnote_marker_sequence(raw_text)
    allowed_internal = Counter(
        (marker.style, marker.normalized) for marker in sequence[1:]
    )

    for tag in list(root.find_all("sup")):
        if tag is leading_tag:
            continue
        if tag.find_parent(("math", "sub")) is not None:
            continue
        marker = marker_from_value(tag.get_text("", strip=True))
        if marker is not None and allowed_internal[(marker.style, marker.normalized)] > 0:
            allowed_internal[(marker.style, marker.normalized)] -= 1
            continue
        tag.unwrap()

    if leading_marker is None:
        _wrap_leading_marker(root)

    return str(root)
