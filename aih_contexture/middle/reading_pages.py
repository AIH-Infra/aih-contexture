"""Versioned page slices for an exact, normalized reading artifact."""
from __future__ import annotations

import hashlib
import re

PAGE_MANIFEST_KEY = 'reading_page_manifest'


def reading_text(text: str) -> str:
    return text.removeprefix('\ufeff').replace('\r\n', '\n').replace('\r', '\n')


def page_manifest(markdown: str, starts: list[dict]) -> dict:
    text = reading_text(markdown)
    entries = [{**entry, 'end': starts[i+1]['start'] if i+1 < len(starts) else len(text)}
               for i, entry in enumerate(starts)]
    return {'version': 1, 'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
            'offset_unit': 'unicode_codepoints', 'newline': 'LF', 'pages': entries}


def manifest_pages(markdown: str, manifest) -> list[tuple[int, str, str]] | None:
    text = reading_text(markdown)
    if (not isinstance(manifest, dict) or manifest.get('version') != 1
            or manifest.get('offset_unit') != 'unicode_codepoints'
            or manifest.get('newline') != 'LF'
            or manifest.get('sha256') != hashlib.sha256(text.encode('utf-8')).hexdigest()):
        return None
    entries = manifest.get('pages')
    if not isinstance(entries, list) or not entries:
        return None
    output, previous, indices = [], 0, set()
    for entry in entries:
        if not isinstance(entry, dict):
            return None
        start, end, index = entry.get('start'), entry.get('end'), entry.get('index')
        if (type(start) is not int or type(end) is not int or type(index) is not int
                or start != previous or not start < end <= len(text) or index in indices):
            return None
        anchor = str(entry.get('anchor', index))
        if not anchor.isascii() or not anchor.isdigit() or not text[start:].startswith('{'+anchor+'}\n'):
            return None
        output.append((index, anchor, text[start:end]))
        previous = end
        indices.add(index)
    return output if previous == len(text) else None


def reading_page_slices(markdown: str, manifest) -> list[tuple[int, str, str]] | None:
    """Display saved slices, excluding only a protected-aware terminal marker.

    The raw artifact and its manifest still cover the complete saved text.
    This mirrors the legacy preview contract without making a terminal marker
    into an extra physical page or exposing it as the last page's prose.
    """
    pages = manifest_pages(markdown, manifest)
    if not pages:
        return pages
    from aih_contexture.utils.markdown_regions import markdown_lines
    index, label, body = pages[-1]
    terminal = str(max(item[0] for item in pages) + 1)
    offset = 0
    for line, protected in markdown_lines(body):
        if not protected and line.strip() == '{'+terminal+'}':
            tail = body[offset+len(line):]
            if not re.sub(r'(?m)^\s*---\s*$', '', tail).strip():
                pages[-1] = (index, label, body[:offset])
                break
        offset += len(line)
    return pages


def rebind_page_manifest(markdown: str, source_manifest) -> dict | None:
    """Rebind final postprocessed text only when every boundary is unambiguous.

    This is a compatibility fallback, not the authoritative renderer path.
    Structure protection remains in effect; ambiguous edits lose the derived
    index rather than attaching stale offsets to changed text.
    """
    from aih_contexture.utils.markdown_regions import markdown_lines
    if manifest_pages(markdown, source_manifest) is not None:
        return source_manifest
    if not isinstance(source_manifest, dict) or source_manifest.get('version') != 1:
        return None
    expected = source_manifest.get('pages')
    if not isinstance(expected, list) or not expected:
        return None
    text = reading_text(markdown)
    anchors, offset = [], 0
    for line, protected in markdown_lines(text):
        match = re.fullmatch(r'\{(\d+)\}[ \t]*(?:\n)?', line) if not protected else None
        if match:
            anchors.append((match[1], offset))
        offset += len(line)
    labels = [str(entry.get('anchor', entry.get('index'))) for entry in expected if isinstance(entry, dict)]
    if len(labels) != len(expected) or len(anchors) not in {len(labels), len(labels)+1}:
        return None
    if [label for label, _ in anchors[:len(labels)]] != labels or anchors[0][1] != 0:
        return None
    if len(anchors) > len(labels):
        last_label, last_offset = anchors[-1]
        if last_label != str(max(entry['index'] for entry in expected)+1):
            return None
        tail = text[last_offset:].split('\n', 1)[-1]
        if re.sub(r'(?m)^\s*---\s*$', '', tail).strip():
            return None
    result = page_manifest(text, [{'index': entry['index'], 'anchor': labels[i], 'start': anchors[i][1]}
                                 for i, entry in enumerate(expected)])
    return result if manifest_pages(text, result) is not None else None
