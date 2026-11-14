"""Page-local line ladders from exact native word evidence; no book names or PDF reads."""
from __future__ import annotations

import re
import statistics
from typing import Any

from aih_contexture.middle.native_geometry import native_edit_supported, native_words
from aih_contexture.utils.markdown_regions import markdown_lines
from aih_contexture.utils.storage_numbers import COORDINATE_QUANTUM


def _block_line_ladders(page, analysis, body):
    """Whole margin blocks only: never split prose without exact word boxes."""
    from aih_contexture.middle.classical_capabilities import classical_bbox_is_trustworthy
    width, height = float(page.get('width') or 0), float(page.get('height') or 0)
    body = [b for b in body if classical_bbox_is_trustworthy(b.get('bbox'), page, b)]
    if not width or not height or len(body) < 2 or sum(len(str(b.get('text') or '')) for b in body) < 700:
        return
    left = statistics.median(b['bbox'][0] for b in body)
    right = statistics.median(b['bbox'][2] for b in body)
    lo, hi = min(b['bbox'][1] for b in body), max(b['bbox'][3] for b in body)
    groups = []
    for b in page.get('blocks') or []:
        raw = str(b.get('text') or '').strip()
        box = b.get('bbox') or []
        if (b.get('type') != 'MarginalNote' or not re.fullmatch(r'\d{1,3}', raw)
                or not 0 < int(raw) < 1000 or int(raw) % 5
                or not classical_bbox_is_trustworthy(box, page, b)):
            continue
        x0,y0,x1,y1 = box
        side = 'left' if x1 < left-width*.004 else 'right' if x0 > right+width*.004 else None
        if (not side or not lo-height*.015 <= (y0+y1)/2 <= hi+height*.015
                or y1-y0 > height*.025 or x1-x0 > width*.06):
            continue
        item={'block_id':b['id'],'raw':raw,'char_range':[0,len(raw)],'bbox':box,
              'x':(x0+x1)/2,'y':(y0+y1)/2,'side':side}
        group=next((g for g in groups if g[0]['side']==side
                    and min(abs(statistics.median(w['bbox'][i] for w in g)-box[i]) for i in (0,2))<=width*.012),None)
        if group is None:
            group=[];groups.append(group)
        group.append(item)
    confirmed=[]
    for group in groups:
        group.sort(key=lambda w:w['y'])
        values=[int(w['raw']) for w in group]
        if len(group)<5 or values[0]>15 or not all(b>a and (b-a)%5==0 for a,b in zip(values,values[1:])):
            continue
        units=[(b['y']-a['y'])/(int(b['raw'])-int(a['raw'])) for a,b in zip(group,group[1:])]
        pitch=statistics.median(units)
        digit_height=statistics.median(w['bbox'][3]-w['bbox'][1] for w in group)
        # Each coordinate has half-quantum error. A height/difference has at
        # most one quantum; dividing a centre difference by the smallest line
        # step bounds pitch error. Ambiguous thresholds retain the source.
        step=min(b-a for a,b in zip(values,values[1:]))
        pitch_error=COORDINATE_QUANTUM/step
        if (not 1.3*digit_height + 1.3*COORDINATE_QUANTUM + pitch_error <= pitch
                <= 3.8*digit_height - 3.8*COORDINATE_QUANTUM - pitch_error
                or group[-1]['y']-group[0]['y'] < height*.25
                or not all(.72*pitch<=u<=1.4*pitch for u in units)):
            continue
        confirmed.extend(group)
    if not confirmed:
        return
    identities={_identity(w) for w in confirmed}
    for key in ('locators','text_marginalia','undetermined'):
        analysis[key][:]=[w for w in analysis.get(key,[]) if _identity(w) not in identities]
    analysis['review'][:]=[r for r in analysis.get('review',[]) if not (r.get('kind')=='undetermined_candidate' and _identity(r) in identities)]
    for word in confirmed:
        analysis['locators'].append({**{key:word[key] for key in ('block_id','raw','char_range','bbox')},
            'normalized':word['raw'],'role':'locator','scheme':'generic_line',
            'components':{'line':int(word['raw'])},'confidence':'high',
            'evidence':['sequence:step5','geometry:outside_body_lane','pitch_match:block_ladder',
                        'source:standalone_margin_block']})
    ordered=sorted(confirmed,key=lambda w:(w['y'],w['x']))
    values=list(dict.fromkeys(w['raw'] for w in ordered))
    analysis['ranges'].append({'scheme':'generic_line','stream_id':'page','display':'Lines: '+', '.join(values),
        'items':values,'source_items':[{k:w[k] for k in ('block_id','raw','char_range','bbox')} for w in ordered],
        'single_point':False,'reading_y':ordered[0]['y']})
    analysis['review'].append({'kind':'generic_line_sequence_confirmed','values':values,'count':len(confirmed)})


def _protected(block):
    return any(flag for _,flag in markdown_lines(str(block.get('text') or '')))


def _rows(words, size):
    rows = []
    for word in sorted(words, key=lambda w: (w['y'], w['x'])):
        if word['raw'].isdigit() or (word.get('font_size') or size) < size * .8:
            continue
        if not rows or abs(word['y'] - statistics.median(w['y'] for w in rows[-1])) > size * .6:
            rows.append([])
        rows[-1].append(word)
    return rows


def _identity(word):
    return word.get('block_id'), tuple(word.get('char_range') or [])


def analyze_generic_lines(page: dict[str, Any], analysis: dict[str, Any]) -> None:
    if any(item.get('scheme') == 'bekker' for item in analysis.get('locators', [])):
        return
    width = page.get('width') or 0
    blocks = [b for b in page.get('blocks', []) if isinstance(b, dict)]
    body = [b for b in blocks if b.get('type') == 'Text' and len(b.get('bbox') or []) == 4
            and b['bbox'][2] - b['bbox'][0] > width * .4
            and not _protected(b)
            and (b.get('attrs') or {}).get('semantic_role') != 'footnote_definition']
    body_words = [w for b in body for w in native_words(b, page)]
    sizes = [w['font_size'] for w in body_words if w.get('font_size') and not w['raw'].isdigit()]
    if not width or not sizes:
        if not body_words:
            _block_line_ladders(page, analysis, body)
        return
    size = statistics.median(sizes)
    rows = _rows(body_words, size)
    if len(rows) < 8:
        return
    centres = [statistics.median(w['y'] for w in row) for row in rows]
    gaps = [b-a for a, b in zip(centres, centres[1:]) if size*.8 < b-a < size*2.4]
    if not gaps:
        return
    pitch = statistics.median(gaps)
    left = statistics.median(min(w['bbox'][0] for w in row) for row in rows)
    right = statistics.median(max(w['bbox'][2] for w in row) for row in rows)
    lo, hi = min(centres), max(centres)
    by_id = {str(b.get('id') or ''): b for b in blocks}
    # A recognizer may absorb a genuine margin number into a heading or list.
    allowed = {'Text', 'MarginalNote', 'LineNumber', 'SectionHeader', 'ListItem', 'ListGroup'}
    words = [w for b in blocks if (b.get('type') in allowed or
             b.get('type') == 'ComplexRegion' and
             ((b.get('attrs') or {}).get('raw_label') or (b.get('attrs') or {}).get('raw_block_type')) in {'ListGroup','list_group'})
             and not _protected(b) and (b.get('attrs') or {}).get('semantic_role') != 'footnote_definition'
             for w in native_words(b, page)]
    candidates = []
    for word in words:
        raw = word['raw']
        if not re.fullmatch(r'\d{1,3}', raw) or not 0 < int(raw) < 1000 or int(raw) % 5:
            continue
        # Leading apparatus may label ruled/lacuna lines above the first prose
        # word. A complete aligned ladder must still pass the pitch checks.
        top = min(lo-pitch*.5, float(page.get('height') or 0)*.12)
        if (word.get('font_size') or size) > size * .85 or not top <= word['y'] <= hi+pitch*.5:
            continue
        side = 'left' if word['bbox'][2] < left-.5 else 'right' if word['bbox'][0] > right+.5 else None
        if side:
            candidates.append({**word, 'side': side})
    groups = []
    for word in sorted(candidates, key=lambda w: (w['side'], w['y'])):
        # Both edges can be stable depending on the publisher's digit alignment.
        # Use the nearest edge, rather than splitting 5 and 10 into separate ladders.
        group = next((g for g in groups if g[0]['side'] == word['side']
                      and min(abs(statistics.median(w['bbox'][i] for w in g)-word['bbox'][i])
                              for i in (0, 2)) <= max(3., size*.65)), None)
        if group is None:
            group = []; groups.append(group)
        group.append(word)
    confirmed = []
    for group in groups:
        values = [int(w['raw']) for w in group]
        if len(group) < 3 or not all(b > a and (b-a) % 5 == 0 for a, b in zip(values, values[1:])):
            continue
        normal_links = 0
        valid = True
        for a, b in zip(group, group[1:]):
            expected = (int(b['raw'])-int(a['raw'])) * pitch
            actual = b['y']-a['y']
            if .75*expected <= actual <= 1.25*expected:
                normal_links += 1
                continue
            # A title/illustration creates real space but is not counted as prose lines.
            obstacles = [block['bbox'] for block in blocks
                         if (block.get('type') in {'SectionHeader', 'Picture', 'Figure', 'Table'}
                             or block.get('type') == 'Text' and len(str(block.get('text') or '')) < 80
                             and len(block.get('bbox') or []) == 4
                             and block['bbox'][2]-block['bbox'][0] < (right-left)*.65)
                         and len(block.get('bbox') or []) == 4
                         and a['y'] < block['bbox'][1] < block['bbox'][3] < b['y']
                         and block['bbox'][0] < right and block['bbox'][2] > left]
            occupied = sum(box[3]-box[1] for box in obstacles)
            if not obstacles or not .75*expected <= actual-occupied <= 1.5*expected:
                valid = False
                break
        if not valid or normal_links < 2:
            continue
        if not all(native_edit_supported(by_id[w['block_id']],
                       {'char_range': w['char_range'], 'original': w['raw'], 'bbox': w['bbox']}) for w in group):
            continue
        confirmed.extend(group)
    if not confirmed:
        return
    identities = {_identity(w) for w in confirmed}
    for key in ('text_marginalia', 'undetermined'):
        analysis[key][:] = [item for item in analysis.get(key, []) if _identity(item) not in identities]
    analysis['locators'][:] = [item for item in analysis.get('locators', []) if _identity(item) not in identities]
    analysis['review'][:] = [r for r in analysis.get('review', [])
                             if not (r.get('kind') == 'undetermined_candidate' and _identity(r) in identities)]
    for word in confirmed:
        evidence = ['sequence:step5', 'pitch_match:body_line_pitch', 'geometry:outside_body_lane']
        analysis['locators'].append({
            'raw': word['raw'], 'normalized': str(int(word['raw'])), 'role': 'locator',
            'scheme': 'generic_line', 'components': {'line': int(word['raw'])},
            'block_id': word['block_id'], 'char_range': word['char_range'], 'bbox': word['bbox'],
            'confidence': 'high', 'evidence': evidence,
        })
        # bbox is required by the projection's exact-native-source gate. Omitting
        # it previously emitted a Lines comment but left the token in the body.
        if by_id[word['block_id']].get('type') != 'MarginalNote':
            analysis['edits'].append({
                'block_id': word['block_id'], 'char_range': word['char_range'], 'original': word['raw'],
                'bbox': word['bbox'], 'action': 'separate_native_margin',
                'reason': 'generic_line_sequence_outside_body_lane', 'confidence': 'high',
                'evidence': evidence, 'locator': word['raw'],
            })
    ordered = sorted(confirmed, key=lambda w: (w['y'], w['x']))
    # One physical page has one observed list even if OCR split its digit column.
    values = list(dict.fromkeys(str(int(w['raw'])) for w in ordered))
    analysis['ranges'].append({
        'scheme': 'generic_line', 'stream_id': 'page', 'display': 'Lines: '+', '.join(values),
        'items': values, 'source_items': [{key:w[key] for key in ('block_id','char_range','raw','bbox')} for w in ordered],
        'single_point': False, 'reading_y': ordered[0]['y'],
    })
    analysis['review'].append({'kind':'generic_line_sequence_confirmed', 'values':values, 'count':len(confirmed)})
    # An upstream margin classifier can steal an actual body numeral. Recover
    # a native line prefix only when both exact source word boxes still exist.
    for word in words:
        source = by_id[word['block_id']]
        if source.get('type') != 'MarginalNote' or not word['raw'].isdigit() or _identity(word) in identities:
            continue
        if (word.get('font_size') or 0) < size*.75 or not left-size*.6 <= word['bbox'][0] <= right:
            continue
        targets = [w for w in body_words if w['char_range'][0] == 0 and not w['raw'].isdigit()
                   and abs(w['y']-word['y']) <= size*.4
                   and 0 <= w['bbox'][0]-word['bbox'][2] <= size*1.5]
        if len(targets) != 1:
            continue
        target = targets[0]
        analysis.setdefault('native_body_prefixes', []).append({'source':word,'target':target})
        for key in ('locators','undetermined','text_marginalia','restores'):
            analysis[key][:] = [item for item in analysis.get(key, []) if _identity(item) != _identity(word)]
        occupied_body = _identity(word)
        identities.add(occupied_body)
    # Their location is established, but their edition system is not. Retain
    # the same source identity in the unresolved reading channel as well as
    # the locator evidence; neither line nor prose-drop policy owns these.
    prose = [w for w in body_words if not w['raw'].isdigit()]
    outer_left = min(w['bbox'][0] for w in prose)
    outer_right = max(w['bbox'][2] for w in prose)
    occupied = {_identity(item) for item in analysis.get('locators', [])
                if item.get('scheme') in {'generic_line','bekker','bracketed_old_page'}}
    for word in words:
        if _identity(word) in occupied or _identity(word) in identities or not re.fullmatch(r'\d{1,4}', word['raw']):
            continue
        if (word.get('font_size') or size) > size*1.15 or not lo-pitch*.5 <= word['y'] <= hi+pitch*.5:
            continue
        if word['bbox'][2]-word['bbox'][0] > len(word['raw'])*size*.9:
            continue
        if any(b.get('type') == 'Footnote' and re.match(r'^\s*(?:<sup>\s*)?'+re.escape(word['raw'])+r'(?:\s*</sup>|[.)\s])', str(b.get('text') or ''))
               for b in blocks):
            continue
        if not (word['bbox'][2] < outer_left-size*.5 or word['bbox'][0] > outer_right+size*.5):
            continue
        block = by_id[word['block_id']]
        if not native_edit_supported(block, {'original':word['raw'], 'char_range':word['char_range'], 'bbox':word['bbox']}):
            continue
        for key in ('text_marginalia','undetermined'):
            analysis[key][:] = [item for item in analysis.get(key, []) if _identity(item) != _identity(word)]
        analysis['locators'][:] = [item for item in analysis.get('locators', []) if _identity(item) != _identity(word)]
        evidence = ['geometry:outside_full_body_envelope','shape:small_numeric','sequence:generic_line_context']
        locator = {**{key:word[key] for key in ('block_id','char_range','raw','bbox')},
            'normalized':word['raw'], 'role':'locator','scheme':'numeric_margin',
            'confidence':'high','evidence':evidence,'edition_system':'unconfirmed'}
        analysis['locators'].append(locator)
        analysis['undetermined'].append({**locator, 'role':'undetermined',
            'notes':['numeric_margin_system_unconfirmed']})
        analysis['review'].append({'kind':'unconfirmed_numeric_margin',
            'block_id':word['block_id'], 'char_range':word['char_range'],
            'reason':'numeric_margin_system_unconfirmed'})
        if block.get('type') != 'MarginalNote':
            analysis['edits'].append({
                'block_id':word['block_id'],'char_range':word['char_range'],'original':word['raw'],
                'bbox':word['bbox'],'action':'separate_native_margin','confidence':'high',
                'reason':'numeric_margin_locator','evidence':evidence,
            })
