"""Conservative same-page continuations from authentic word boxes.

Capitalization is not paragraph evidence. A continuation needs a repeated
body lane and line pitch, an unindented next line and compatible body type.
"""
from __future__ import annotations

import re
from statistics import median

from aih_contexture.middle.native_geometry import native_words


def _prose_block(block):
    attrs = block.get('attrs') or {}
    labels = {str(attrs.get(k) or '').lower() for k in ('style', 'semantic_role', 'raw_label')}
    return (block.get('type') == 'Text' and not labels.intersection({
        'poem', 'poetry', 'verse', 'blockquote', 'footnote_definition', 'code'})
        and not attrs.get('official_markdown_fallback'))


def native_prose_geometry(page):
    by_id = {}
    all_lines = []
    fonts = []
    for block in page.get('blocks', []):
        if not _prose_block(block):
            continue
        words = [w for w in native_words(block, page)
                 if any(c.isalpha() for c in w['raw']) and w.get('font_size')]
        if not words:
            continue
        size = median(w['font_size'] for w in words)
        # Keep small real first words. A font estimate must not move the
        # perceived line start to the second word of that line.
        words = [w for w in words if size*.5 <= w['font_size'] <= size*1.5]
        rows = []
        for word in sorted(words, key=lambda w: (w['y'], w['x'])):
            if not rows or abs(word['y']-median(w['y'] for w in rows[-1])) > size*.6:
                rows.append([])
            rows[-1].append(word)
        lines = [{'left': min(w['bbox'][0] for w in row),
                  'right': max(w['bbox'][2] for w in row),
                  'top': min(w['bbox'][1] for w in row),
                  'bottom': max(w['bbox'][3] for w in row),
                  'y': median(w['y'] for w in row),
                  'size': median(w['font_size'] for w in row)} for row in rows]
        by_id[block.get('id')] = {'lines': lines, 'size': size, 'words': len(words)}
        all_lines.extend(lines)
        fonts.extend(w['font_size'] for w in words)
    if len(fonts) < 8 or len(all_lines) < 3:
        return None
    return {'blocks': by_id, 'lines': all_lines, 'size': median(fonts)}


def native_wrapped_blocks(previous, current, page, geometry):
    """None means this page cannot support the stronger native evidence path."""
    if geometry is None:
        return None
    if not _prose_block(previous) or not _prose_block(current):
        return False
    for block in (previous, current):
        if block.get('page_index', page.get('index')) != page.get('index'):
            return False
    a = geometry['blocks'].get(previous.get('id'))
    b = geometry['blocks'].get(current.get('id'))
    if not a or not b:
        return False
    text = str(current.get('text') or '').lstrip()
    if (re.match(r'^(?:[-*+]\s|/?\s*\d+[.)]\s)', text)
            or len(text) < 80 and text.isupper()):
        return False
    before, after = a['lines'][-1], b['lines'][0]
    size = geometry['size']
    if not all(size*.6 <= entry['size'] <= size*1.35 for entry in (a, b)):
        return False
    # A locally repeated indent may belong to verse even when the recognizer
    # labels every line as Text. Establish the column's prose lane from long,
    # multiline blocks before trusting that local indent as a body margin.
    column_rows = [row for entry in geometry['blocks'].values()
                   if len(entry['lines']) >= 3 and entry['words'] >= 20
                   for row in entry['lines']
                   if row['right'] > min(before['left'], after['left'])
                   and row['left'] < max(before['right'], after['right'])]
    if not column_rows:
        return False
    full_width = max(row['right']-row['left'] for row in column_rows)
    prose_leaders = sorted(row['left'] for row in column_rows
                           if row['right']-row['left'] >= full_width*.65)
    if len(prose_leaders) < 3:
        return False
    prose_left = prose_leaders[int((len(prose_leaders)-1)*.2)]
    if abs(after['left']-prose_left) > size*.65:
        return False
    # A short single-line centered title is not a prose fragment. Multiline
    # prose can wrap around an illustration, so its last line need not start
    # at the main margin even though its next block resumes the prose lane.
    if (before['left'] < prose_left-size*.65
            or len(a['lines']) == 1 and before['left'] > prose_left+size*1.8
            and before['right']-before['left'] < full_width*.8):
        return False
    seed = min(before['left'], after['left'])
    lane_rows = [r for r in geometry['lines'] if abs(r['left']-seed) <= size*1.8
                 and r['right']-r['left'] >= size*5
                 and size*.65 <= r['size'] <= size*1.35]
    if len(lane_rows) < 3:
        return False
    leaders = sorted(r['left'] for r in lane_rows)
    lane_left = leaders[int((len(leaders)-1)*.2)]
    if abs(after['left']-lane_left) > size*.65:
        return False
    centers = []
    for y in sorted(r['y'] for r in lane_rows):
        if not centers or y-centers[-1] > size*.5:
            centers.append(y)
    gaps = [y-x for x,y in zip(centers, centers[1:]) if size*.9 <= y-x <= size*2.4]
    if len(gaps) < 2:
        return False
    pitch = median(gaps)
    if not pitch*.65 <= after['y']-before['y'] <= pitch*1.35:
        return False
    if before['right'] <= after['left'] or after['right'] <= before['left']:
        return False
    # Short poetic lines must not be joined merely for sharing an x origin.
    lane_width = median(r['right']-r['left'] for r in lane_rows)
    return (before['right']-before['left'] >= lane_width*.65
            or any(r['right']-r['left'] >= lane_width*.8 for r in b['lines'][1:]))
