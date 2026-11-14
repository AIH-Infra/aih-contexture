"""Reading decisions from coordinates carried by the recognizer's own Middle.

No PDF reads, book-specific substitutions, or human edit files are used here.
Source block text remains immutable; the caller stores a checked edit plan.
"""
from __future__ import annotations

import math
import re
import statistics
from collections.abc import Mapping
from typing import Any


def _font_size(value: Any, default: float = 0.) -> float:
    try:
        value = float(value)
        return value if math.isfinite(value) and value > 0 else default
    except (TypeError, ValueError):
        return default


def _is_mapping(value: Any) -> bool:
    # Exact dicts skip the slower ABC check; called for every word span.
    return type(value) is dict or isinstance(value, Mapping)


def compact_native_spans(block: Mapping[str, Any]) -> list[dict[str, Any]]:
    text = str(block.get('text') or '')
    output = []
    cursor = 0
    for span in block.get('spans') or []:
        if not _is_mapping(span):
            continue
        raw = str(span.get('text') or '')
        if not raw.strip():
            continue
        attrs = span.get('attrs') if _is_mapping(span.get('attrs')) else {}
        row = {'text': raw}
        box = span.get('bbox')
        if isinstance(box, (tuple, list)) and len(box) == 4:
            try:
                box = [round(float(v), 4) for v in box]
                if all(math.isfinite(v) for v in box) and box[2] > box[0] and box[3] > box[1]:
                    row['bbox'] = box
            except (ValueError, TypeError):
                pass
        kept = {k: attrs[k] for k in ('font_size', 'formats', 'has_superscript', 'has_subscript') if attrs.get(k) not in (None, [], False)}
        if 'font_size' in kept:
            if _font_size(kept['font_size']):
                kept['font_size'] = _font_size(kept['font_size'])
            else:
                kept.pop('font_size')
        claimed = attrs.get('char_range')
        if isinstance(claimed, (list, tuple)) and len(claimed) == 2:
            try:
                start, end = map(int, claimed)
                if 0 <= start < end <= len(text) and text[start:end] == raw:
                    kept['char_range'] = [start, end]
                    cursor = end
            except (ValueError, TypeError):
                pass
        else:
            start = text.find(raw, cursor)
            if start >= 0:
                kept['char_range'] = [start, start + len(raw)]
                cursor = start + len(raw)
        if kept:
            row['attrs'] = kept
        provenance = [{k: p[k] for k in ('backend','stage') if p.get(k)}
            for p in span.get('provenance',[]) if _is_mapping(p)]
        if provenance:
            row['provenance'] = provenance[:2]
        output.append(row)
    return output


def native_words(block: Mapping[str, Any], page: Mapping[str, Any]) -> list[dict[str, Any]]:
    output = []
    width, height = page.get('width'), page.get('height')
    if not isinstance(width, (int, float)) or not isinstance(height, (int, float)):
        return output
    for span in compact_native_spans(block):
        raw = span['text']
        box = span.get('bbox')
        attrs = span.get('attrs') or {}
        offsets = attrs.get('char_range')
        # A multi-word span cannot supply per-word coordinates by interpolation.
        if not box or not offsets or not raw.strip() or re.search(r'\s', raw.strip()):
            continue
        if not (0 <= box[0] < box[2] <= width + .1 and 0 <= box[1] < box[3] <= height + .1):
            continue
        if raw != raw.strip():
            continue
        output.append({'raw': raw, 'bbox': box, 'char_range': offsets,
            'block_id': str(block.get('id') or ''), 'font_size': attrs.get('font_size'),
            'x': (box[0]+box[2])/2, 'y': (box[1]+box[3])/2})
    return output


def native_edit_supported(block: Mapping[str, Any], edit: Mapping[str, Any]) -> bool:
    for span in compact_native_spans(block):
        if not span.get('bbox') or re.search(r'\s', span['text']) or span['text'] != span['text'].strip():
            continue
        if (span.get('attrs') or {}).get('char_range') == edit.get('char_range') and span['text'] == edit.get('original'):
            return span.get('bbox') == edit.get('bbox')
    return False


def analyze_native_margins(page: Mapping[str, Any], analysis: dict[str, Any]) -> None:
    blocks = [b for b in page.get('blocks', []) if isinstance(b, Mapping)]
    width = float(page.get('width') or 0)
    body = [b for b in blocks if b.get('type') == 'Text'
        and (b.get('attrs') or {}).get('semantic_role') != 'footnote_definition'
        and isinstance(b.get('bbox'), list) and len(b['bbox']) == 4
        and b['bbox'][2]-b['bbox'][0] > width*.45]
    words = [w for b in body for w in native_words(b, page)]
    if not words:
        return
    # Estimate the lane from repeated line leaders, excluding tiny marginal
    # codes. Word positions are native, not guessed from paragraph rectangles.
    sizes = [_font_size(w['font_size']) for w in words if _font_size(w.get('font_size')) and not w['raw'].isdigit()]
    if not sizes:
        return
    size = statistics.median(sizes)
    by_line = {}
    for word in words:
        if not word['raw'].isdigit() and float(word.get('font_size') or size) >= size*.8:
            by_line.setdefault(round(word['y']/max(3.,size)), []).append(word)
    if len(by_line) < 4:
        return
    left = statistics.median(min(w['bbox'][0] for w in line) for line in by_line.values())
    right = statistics.median(max(w['bbox'][2] for w in line) for line in by_line.values())
    occupied = {(e.get('block_id'), tuple(e.get('char_range') or [])) for e in analysis['edits']}
    def remove(word, action):
        key = word['block_id'], tuple(word['char_range'])
        if key not in occupied:
            analysis['edits'].append({'block_id': word['block_id'], 'char_range': word['char_range'],
                'original': word['raw'], 'bbox': word['bbox'], 'action': action,
                'reason': 'native_word_outside_body_lane', 'confidence': 'high',
                'evidence': ['geometry:native_span', 'geometry:outside_repeated_body_lane', 'exact_source_char_range']})
            occupied.add(key)
    anchors = [i for i in analysis['locators'] if i.get('scheme') == 'bekker' and (i.get('components') or {}).get('page')]
    for word in words:
        old_page = re.fullmatch(r'\[(\d{2,4})\]', word['raw'])
        outside = word['bbox'][2] < left-.5 or word['bbox'][0] > right+.5
        if old_page and outside and float(word.get('font_size') or size) < size*.8:
            remove(word, 'separate_native_margin')
            analysis['locators'].append({'raw':word['raw'],'normalized':word['raw'],
                'block_id':word['block_id'],'char_range':word['char_range'],'bbox':word['bbox'],
                'role':'locator','scheme':'bracketed_old_page','components':{'page':int(old_page[1])},
                'confidence':'high','evidence':['geometry:native_span','geometry:outside_repeated_body_lane','shape:bracketed_page']})
    # Other classical volumes use paragraph numbers rather than Bekker lines.
    # Require a repeated, aligned, consecutive marginal sequence; one isolated
    # digit or an unanchored 5/10/15 ladder is insufficient evidence.
    if not anchors:
        groups = []
        for word in sorted(words, key=lambda w:w['y']):
            if not word['raw'].isdigit() or not 0 < int(word['raw']) < 1000:
                continue
            side = 'left' if word['bbox'][2] < left-.5 else 'right' if word['bbox'][0] > right+.5 else None
            if side is None or float(word.get('font_size') or size) > size*1.1:
                continue
            edge = word['bbox'][2] if side == 'left' else word['bbox'][0]
            group = next((g for g in groups if g['side']==side and abs(g['edge']-edge) <= max(3.,size*.5)), None)
            if group is None:
                group = {'side':side,'edge':edge,'words':[]}; groups.append(group)
            group['words'].append(word)
        for group in groups:
            sequence = group['words']
            if len(sequence) < 2 or not all(int(b['raw']) == int(a['raw'])+1 and b['y']-a['y'] > size*2 for a,b in zip(sequence,sequence[1:])):
                continue
            for word in sequence:
                remove(word, 'separate_native_margin')
                analysis['locators'].append({'raw':word['raw'],'normalized':word['raw'],
                    'block_id':word['block_id'],'char_range':word['char_range'],'bbox':word['bbox'],
                    'role':'locator','scheme':'paragraph','components':{'number':int(word['raw'])},
                    'confidence':'high','evidence':['geometry:native_span','geometry:outside_repeated_body_lane','sequence:aligned_consecutive_paragraph_numbers']})
    for word in words:
        if not word['raw'].isdigit() or not anchors:
            continue
        small = float(word.get('font_size') or size) < size*.8
        outside = word['bbox'][2] < left - .5 or word['bbox'][0] > right + .5
        earlier = [a for a in anchors if isinstance(a.get('bbox'), list) and a['bbox'][1] <= word['y']]
        if not (small and outside and earlier):
            continue
        value = int(word['raw'])
        if value > 99:
            continue
        remove(word, 'separate_native_margin')
        item = {'raw': word['raw'], 'normalized': word['raw'], 'block_id': word['block_id'],
            'char_range': word['char_range'], 'bbox': word['bbox'], 'confidence': 'high',
            'evidence': ['geometry:native_span', 'geometry:outside_repeated_body_lane']}
        if 5 <= value <= 35 and value % 5 == 0:
            analysis['locators'].append({**item, 'role':'locator', 'scheme':'bekker',
                'components': {'page':None, 'column':None, 'line':value}})
        else:
            analysis['undetermined'].append({**item, 'role':'undetermined'})
            analysis['review'].append({'kind':'native_margin_number_needs_review', **item})
    # A model's narrow aside region supplies an anchor for recovering fragments
    # assigned to an overlapping paragraph by the line-to-block merger.
    for note in [b for b in blocks if b.get('type') == 'MarginalNote']:
        box = note.get('bbox')
        if not isinstance(box, list) or len(box) != 4 or box[2]-box[0] > width*.22:
            continue
        if not (box[0] >= right-2 or box[2] <= left+2):
            continue
        own = native_words(note, page)
        if not own or not any(any(c.isalpha() for c in w['raw']) for w in own):
            continue
        font = statistics.median(float(w.get('font_size') or size) for w in own)
        recovered = [w for w in words if box[0]-.5 <= w['x'] <= box[2]+.5
            and box[1]-font <= w['y'] <= box[3]+font
            and float(w.get('font_size') or size) <= font*1.3]
        if not recovered:
            continue
        joined = sorted(own+recovered, key=lambda w:(round(w['y']/max(2.,font)), w['x']))
        item = next((i for i in analysis['text_marginalia'] if i.get('block_id') == note['id']), None)
        if item is None:
            continue
        item['raw'] = item['normalized'] = ' '.join(w['raw'] for w in joined)
        item['native_source_fragments'] = [{k:w[k] for k in ('block_id','char_range','raw','bbox')} for w in joined]
        item['evidence'] = list(item.get('evidence') or []) + ['geometry:native_aside_fragments']
        for word in recovered:
            remove(word, 'separate_native_margin')

    # A missed footnote may share the model's paragraph box. Require separate
    # small-font lines below all normal-size prose, not merely a bottom-page
    # Roman/numeric prefix. Inline note references fail these spatial checks.
    all_words = [w for b in blocks if b.get('type')=='Text'
        and (b.get('attrs') or {}).get('semantic_role') != 'footnote_definition'
        for w in native_words(b,page) if left-1 <= w['x'] <= right+1]
    rows = []
    for word in sorted(all_words,key=lambda w:(w['y'],w['x'])):
        row = next((r for r in rows if abs(statistics.median(w['y'] for w in r)-word['y']) < size*.65), None)
        if row is None:
            row=[]; rows.append(row)
        row.append(word)
    def row_font(row):
        return statistics.median(_font_size(w.get('font_size'),size) for w in row)
    normal_rows = [r for r in rows if row_font(r) >= size*.9 and any(any(c.isalpha() for c in w['raw']) for w in r)]
    if not normal_rows:
        return
    last_body_y = max(statistics.median(w['y'] for w in r) for r in normal_rows)
    accepted_by_block = {}
    for row in rows:
        y = statistics.median(w['y'] for w in row)
        if y <= max(float(page.get('height') or 0)*.65, last_body_y+size*.5) or row_font(row) >= size*.87:
            continue
        if len(row) < 3 or sum(any(c.isalpha() for c in w['raw']) for w in row) < 2:
            continue
        # Move whole native lines. Filtering individual words by size would
        # leave tall glyphs and citations behind in the body.
        for word in sorted(row,key=lambda w:w['x']):
            accepted_by_block.setdefault(word['block_id'],[]).append(word)
    for accepted in accepted_by_block.values():
        if not accepted:
            continue
        from aih_contexture.middle.semantics.page_furniture import is_publication_imprint
        if is_publication_imprint(' '.join(w['raw'] for w in accepted),
                                  ' '.join(str(b.get('text') or '') for b in blocks)):
            continue
        analysis.setdefault('native_footnotes',[]).append({
            'raw':' '.join(w['raw'] for w in accepted),
            'bbox':[min(w['bbox'][0] for w in accepted),min(w['bbox'][1] for w in accepted),
                    max(w['bbox'][2] for w in accepted),max(w['bbox'][3] for w in accepted)],
            'fragments':[{k:w[k] for k in ('block_id','char_range','raw','bbox')} for w in accepted],
            'evidence':['geometry:native_span','geometry:small_font_lines_below_body'],
        })
        for word in accepted:
            remove(word, 'separate_native_margin')
