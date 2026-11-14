"""Lossless on-disk span encoding; business consumers use canonical Middle."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import zlib
from pathlib import Path

from aih_contexture.middle.schema import SCHEMA_VERSION

STORAGE_SCHEMA = 'contexture-middle-storage/1'
CODEC = 'zlib-json-spans/1'


def _blocks(blocks):
    for block in blocks or []:
        if isinstance(block, dict):
            yield block
            yield from _blocks(block.get('children'))


def decode_middle_storage(data):
    """Decode without changing source data; canonical input is a zero-cost pass."""
    if not isinstance(data, dict):
        return data
    if not str(data.get('schema_version') or '').startswith('contexture-middle-'):
        return data
    encoding = data.get('storage_encoding')
    if encoding is None:
        if data.get('schema_version') == STORAGE_SCHEMA:
            raise ValueError('Middle storage encoding metadata is missing')
        return data
    if (data.get('schema_version') != STORAGE_SCHEMA or not isinstance(encoding, dict)
            or encoding.get('codec') != CODEC or encoding.get('middle_schema_version') != SCHEMA_VERSION):
        raise ValueError('Unsupported Middle storage encoding')
    result = copy.deepcopy(data)
    result['schema_version'] = encoding['middle_schema_version']
    result.pop('storage_encoding')
    for page in result.get('pages') or []:
        if not isinstance(page, dict):
            continue
        for block in _blocks(page.get('blocks')):
            stored = block.pop('span_storage', None)
            if stored is None:
                continue
            if 'spans' in block or not isinstance(stored, dict):
                raise ValueError('Conflicting Middle span representations')
            length, count = stored.get('raw_bytes'), stored.get('count')
            if (stored.get('codec') != CODEC or type(length) is not int or length <= 0
                    or type(count) is not int or count < 0):
                raise ValueError('Invalid Middle span storage metadata')
            try:
                compressed = base64.b64decode(stored['data'], validate=True)
                decoder = zlib.decompressobj()
                raw = decoder.decompress(compressed, length + 1)
                if (len(raw) != length or not decoder.eof or decoder.unused_data
                        or decoder.unconsumed_tail
                        or hashlib.sha256(raw).hexdigest() != stored.get('sha256')):
                    raise ValueError('Middle span storage integrity check failed')
                spans = json.loads(raw)
            except (KeyError, TypeError, zlib.error, UnicodeError) as exc:
                raise ValueError('Invalid Middle span storage payload') from exc
            if not isinstance(spans, list) or len(spans) != count or not all(isinstance(s, dict) for s in spans):
                raise ValueError('Invalid decoded Middle spans')
            block['spans'] = spans
    return result


def encode_middle_storage(data):
    """Return a serialization view, compressing only spans when it saves bytes.

    Values outside changed structural containers are shared and must not be
    mutated through this view. No source value or geometry is omitted.
    """
    if not isinstance(data, dict) or data.get('schema_version') != SCHEMA_VERSION:
        return data
    packed = 0

    def block_view(block):
        nonlocal packed
        result = dict(block)
        spans = block.get('spans')
        if isinstance(spans, list) and len(spans) >= 4:
            raw = json.dumps(spans, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            if len(raw) >= 1024:
                stored = {'codec': CODEC, 'count': len(spans), 'raw_bytes': len(raw),
                          'sha256': hashlib.sha256(raw).hexdigest(),
                          'data': base64.b64encode(zlib.compress(raw, 3)).decode('ascii')}
                if len(json.dumps(stored, separators=(',', ':'))) + 32 < len(raw):
                    result.pop('spans')
                    result['span_storage'] = stored
                    packed += 1
        if isinstance(block.get('children'), list):
            result['children'] = [block_view(b) if isinstance(b, dict) else b for b in block['children']]
        return result

    result = dict(data)
    result['pages'] = []
    for page in data.get('pages') or []:
        if isinstance(page, dict):
            view = dict(page)
            view['blocks'] = [block_view(b) if isinstance(b, dict) else b for b in page.get('blocks') or []]
            result['pages'].append(view)
        else:
            result['pages'].append(page)
    if not packed:
        return data
    result['schema_version'] = STORAGE_SCHEMA
    result['storage_encoding'] = {'codec': CODEC, 'middle_schema_version': data.get('schema_version')}
    return result


def load_middle_json(path):
    from aih_contexture.utils.gc_pause import paused_gc
    with paused_gc():
        return decode_middle_storage(json.loads(Path(path).read_text(encoding='utf-8-sig')))


def middle_json_text(data, *, compress=True):
    payload = encode_middle_storage(data) if compress else decode_middle_storage(data)
    return json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
