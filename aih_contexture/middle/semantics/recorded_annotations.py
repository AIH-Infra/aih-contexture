"""Normalize recorded annotation containers without rewriting their source HTML."""
from __future__ import annotations

import re
from collections import Counter
from bs4 import BeautifulSoup
from markdownify import markdownify


def annotation_payload(value: str) -> tuple[str, dict]:
    """Unwrap only the project's typed aside protocol, never arbitrary prose."""
    soup = BeautifulSoup(value, 'html.parser')
    tags = soup.find_all('aside', class_='marginal-annotation')
    roots = [node for node in soup.contents if str(node).strip()]
    if len(tags) != 1 or len(roots) != 1 or roots[0] is not tags[0]:
        return value, {}
    tag = tags[0]
    position = str(tag.get('data-position') or '').replace('\\_', '_').lower()
    subtype = str(tag.get('data-subtype') or '').replace('\\_', '_').lower()
    attrs = {'source_annotation_html': value, 'source_annotation_position': position,
             'source_annotation_subtype': subtype}
    if position in {'left_margin', 'right_margin'}:
        attrs['side'] = position.split('_')[0]
    return tag.decode_contents(), attrs


def _signature(text):
    text = re.sub(r'\s+', ' ', text).strip()
    # Only edge folios are variable. Interior dates/chapter numbers remain.
    text = re.sub(r'^(?:\d{1,5}|[IVXLCDMivxlcdm]{1,8})\s+', '', text)
    text = re.sub(r'\s+(?:\d{1,5}|[IVXLCDMivxlcdm]{1,8})$', '', text)
    return text.casefold()


def normalize_recorded_annotations(document):
    """Recover repeated running furniture using geometry plus recurrence.

    Operates on the semantic resolver's private copy. A single handwritten or
    textual top note is not a running header merely because of its position.
    """
    pages = document.get('pages') or []
    candidates = []
    for page in pages:
        height = float(page.get('height') or 0)
        for block in page.get('blocks') or []:
            attrs = block.setdefault('attrs', {})
            if attrs.get('annotation_source_type') and block.get('type') == attrs.get('annotation_rendered_type'):
                evidence = attrs.get('annotation_furniture_source')
                if isinstance(evidence, dict) and evidence == {
                        'text': block.get('text'), 'bbox': block.get('bbox')}:
                    continue
                block['type'] = attrs.pop('annotation_source_type')
                attrs.pop('annotation_rendered_type', None)
                attrs.pop('annotation_furniture_source', None)
            if block.get('type') != 'MarginalNote':
                continue
            text = str(block.get('text') or '')
            if '<aside' in text and 'marginal-annotation' in text:
                content, extra = annotation_payload(text)
                if extra:
                    block['text'] = markdownify(content).strip()
                    attrs.update(extra)
                    text = block['text']
            box = block.get('bbox') or []
            if (not height or len(box) != 4 or not text.strip() or len(text) > 160
                    or attrs.get('is_handwritten') or attrs.get('style') == 'handwriting'):
                continue
            try:
                top = 0 <= float(box[1]) < float(box[3]) <= height * .15
                bottom = height * .9 <= float(box[1]) < float(box[3]) <= height
            except (ValueError, TypeError):
                continue
            signature = _signature(text)
            if (not (top or bottom) or len(signature) < 4
                    or not re.search(r'[A-Za-z\u00c0-\u024f]', signature)):
                continue
            candidates.append((page, block, 'PageHeader' if top else 'PageFooter', signature))
    # Count independent physical pages, not duplicate boxes on one page.
    counts = Counter((kind, signature) for kind, signature, _ in
                     {(kind, signature, p.get('index')) for p, _, kind, signature in candidates})
    for page, block, kind, signature in candidates:
        if counts[kind, signature] < 3:
            continue
        attrs = block['attrs']
        attrs.setdefault('annotation_source_type', 'MarginalNote')
        attrs['annotation_rendered_type'] = kind
        attrs['annotation_furniture_source'] = {'text': block.get('text'), 'bbox': list(block.get('bbox') or [])}
        block['type'] = kind
    for page in pages:
        if page.get('printed_page'):
            continue
        values = set()
        for block in page.get('blocks') or []:
            if block.get('type') not in {'PageHeader', 'PageNumber'}:
                continue
            text = str(block.get('text') or '').strip()
            match = re.search(r'^(\d{1,5})(?:\s|$)|(?:\s|^)(\d{1,5})$', text)
            if match:
                values.add(match[1] or match[2])
        if len(values) == 1:
            page['printed_page'] = values.pop()
