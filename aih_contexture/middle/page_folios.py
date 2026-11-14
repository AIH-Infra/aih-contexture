"""Observed footer tokens, without inventing labels from physical page indices.

Source Middle text and printed_page remain intact. Only the temporary reading
view hides a checked token and displays its observed value as a page comment.
"""
from __future__ import annotations

import copy
import re
from statistics import median

from aih_contexture.middle.native_geometry import native_words, native_edit_supported
from aih_contexture.utils.markdown_regions import markdown_lines

VERSION = 'page-folio/1'


def _known_label(page):
    labels = set()
    printed = page.get('printed_page')
    if printed is not None and str(printed).strip():
        value = str(printed).strip()
        if not re.fullmatch(r'[0-9]{1,5}', value):
            return None, True
        labels.add(value)
    for block in page.get('blocks') or []:
        if isinstance(block, dict) and block.get('type') == 'PageNumber':
            value = str(block.get('text') or '').strip()
            if re.fullmatch(r'[0-9]{1,5}', value):
                labels.add(value)
    return (next(iter(labels)) if len(labels) == 1 else None), len(labels) > 1


def _body_block(block):
    attrs = block.get('attrs') or {}
    roles = {str(attrs.get(key) or '').lower() for key in ('style', 'semantic_role', 'raw_label')}
    return (block.get('type') == 'Text' and not attrs.get('official_markdown_fallback')
            and not roles.intersection({'footnote_definition', 'footnote', 'poem', 'poetry', 'verse', 'code', 'blockquote'}))


def _footer_position(word, page):
    width, height = page.get('width'), page.get('height')
    if not isinstance(width, (int, float)) or not isinstance(height, (int, float)) or width <= 0 or height <= 0:
        return False
    box = word['bbox']
    return box[1] >= height*.85 and (box[2] <= width*.30 or box[0] >= width*.70)


def _plain_terminal_token(block, word):
    text = str(block.get('text') or '')
    start, end = word['char_range']
    if text[end:].strip() or text[text.rfind('\n', 0, start)+1:start].strip():
        return False
    cursor = 0
    for line, protected in markdown_lines(text):
        if cursor <= start < cursor+len(line):
            return not protected
        cursor += len(line)
    return False


def observed_folio_plan(data):
    """Rebuild exclusively from current source tokens; saved decisions are not trusted."""
    if not isinstance(data, dict):
        return {}
    pages = [p for p in data.get('pages') or [] if isinstance(p, dict)]
    contexts = []
    for page in pages:
        if (page.get('attrs') or {}).get('logical_page_mapping') == 'needs_review':
            continue
        index = page.get('index')
        if not isinstance(index, int):
            continue
        blocks = [b for b in page.get('blocks') or [] if isinstance(b, dict)]
        label, conflict = _known_label(page)
        possible = [(b, w) for b in blocks if _body_block(b)
                    and re.search(r'(?:^|\n)[ \t]*[0-9]{1,5}[ \t]*$', str(b.get('text') or ''))
                    for w in native_words(b, page)
                    if re.fullmatch(r'[0-9]{1,5}', w['raw']) and _footer_position(w, page)
                    and _plain_terminal_token(b, w)]
        words = [(b, w) for b in blocks if _body_block(b) for w in native_words(b, page)] if possible else []
        alpha = [w for _, w in words if any(c.isalpha() for c in w['raw']) and w.get('font_size')]
        size = median(w['font_size'] for w in alpha) if len(alpha) >= 5 else None
        candidates = []
        if size:
            bottom = max(w['y'] for w in alpha)
            for block, word in possible:
                if (not re.fullmatch(r'[0-9]{1,5}', word['raw']) or not _footer_position(word, page)
                        or not _plain_terminal_token(block, word)
                        or not word.get('font_size') or word['font_size'] > size*.75
                        or word['y'] < bottom+size*.5
                        or not native_edit_supported(block, {**word, 'original': word['raw']})):
                    continue
                candidates.append({key: copy.deepcopy(word[key]) for key in ('block_id', 'char_range', 'raw', 'bbox', 'font_size')})
        # Only recognizer-owned labels contribute sequence evidence. A token
        # inferred on another page never becomes a new anchor for this pass.
        lane = []
        if label and not conflict:
            lane.extend(w for _, w in words if w['raw'] == label and _footer_position(w, page)
                        and any(c['block_id'] == w['block_id'] and c['char_range'] == w['char_range'] for c in candidates))
            lane.extend(w for b in blocks if b.get('type') == 'PageNumber' for w in native_words(b, page)
                        if w['raw'] == label and _footer_position(w, page))
        contexts.append({'page': page, 'index': index, 'label': label, 'conflict': conflict,
                         'candidates': candidates, 'lane': lane})
    plans = {}
    for context in contexts:
        page, index = context['page'], context['index']
        accepted, pending = [], []
        for item in context['candidates']:
            evidence = ['geometry:native_span', 'exact_source_char_range', 'footer:small_separate_line_at_page_edge']
            confirmed = False
            if not context['conflict'] and context['label'] == item['raw']:
                confirmed = True
                evidence.append('equals_native_page_label')
            elif not context['conflict'] and context['label'] is None:
                nearby = [c for c in contexts if 0 < abs(c['index']-index) <= 4 and c['label'] and not c['conflict']]
                support = [c for c in nearby if int(c['label'])-int(item['raw']) == c['index']-index]
                same_lane = [c for c in support if (c['index']-index) % 2 == 0 and any(
                    abs(w['x']/c['page']['width']-(item['bbox'][0]+item['bbox'][2])/2/page['width']) <= .025
                    and abs(w['y']/c['page']['height']-(item['bbox'][1]+item['bbox'][3])/2/page['height']) <= .025
                    and w.get('font_size') and .65 <= w['font_size']/item['font_size'] <= 1.5
                    for w in c['lane'])]
                if len({c['index'] for c in support}) >= 2 and len(support) == len(nearby) and same_lane:
                    confirmed = True
                    evidence.extend(['observed_footer_sequence', 'two_independent_native_labels', 'matching_same_parity_footer_lane'])
            record = {**item, 'evidence': evidence}
            (accepted if confirmed else pending).append(record)
        if len(accepted) > 1:
            pending.extend(accepted)
            accepted = []
        if accepted or pending:
            plans[index] = {'version': VERSION, 'sources': accepted, 'pending': pending}
    return plans


def annotate_observed_folios(data):
    """Attach source-bound audit data to an already copied Middle document."""
    plans = observed_folio_plan(data)
    for page in data.get('pages') or []:
        if not isinstance(page, dict):
            continue
        attrs = page.get('attrs')
        if not isinstance(attrs, dict):
            attrs = {}; page['attrs'] = attrs
        attrs.pop('reading_folio', None)
        attrs.pop('reading_folio_review', None)
        plan = plans.get(page.get('index'), {})
        if plan.get('sources'):
            attrs['reading_folio'] = {'version': VERSION, 'sources': plan['sources']}
        if plan.get('pending'):
            attrs['reading_folio_review'] = {'version': VERSION, 'status': 'needs_review', 'sources': plan['pending']}
    return data


def prepare_page_folio_render_view(data, plans):
    if not any(plan.get('sources') for plan in plans.values()):
        return data
    view = copy.deepcopy(data)
    for page in view.get('pages') or []:
        sources = plans.get(page.get('index'), {}).get('sources') or []
        for item in sources:
            label, conflict = _known_label(page)
            if conflict or label not in (None, item['raw']):
                continue
            blocks = [b for b in page.get('blocks') or [] if b.get('id') == item['block_id'] and _body_block(b)]
            if len(blocks) != 1:
                continue
            block = blocks[0]
            # Classical projection can shift character offsets. Rebind only an
            # exact current token with the same authentic word box, never a
            # substring search or an interpolated rectangle.
            matches = [w for w in native_words(block, page) if w['raw'] == item['raw'] and w['bbox'] == item['bbox']]
            if len(matches) != 1 or not _plain_terminal_token(block, matches[0]):
                continue
            start, _ = matches[0]['char_range']
            block['text'] = str(block.get('text') or '')[:start].rstrip()
            block['spans'] = [span for span in block.get('spans') or []
                              if not (str(span.get('text') or '') == item['raw'] and span.get('bbox') == item['bbox'])]
            if not block['text']:
                block['type'] = 'PageNumber'
            page['printed_page'] = item['raw']
    return view
