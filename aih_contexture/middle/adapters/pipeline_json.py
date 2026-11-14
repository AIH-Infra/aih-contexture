"""Import the project's recorded Pipeline render tree without model calls.

This protocol contains rendered blocks, not the live Document/span graph.
Missing word geometry is deliberately not reconstructed from HTML.
"""
from __future__ import annotations

import html
from pathlib import Path
import re
from typing import Any

from bs4 import BeautifulSoup
from markdownify import markdownify

from aih_contexture.middle.heading_levels import normalize_middle_heading_levels
from aih_contexture.middle.labels import normalize_block_type
from aih_contexture.middle.schema import MiddleBlock, MiddleDocument, MiddlePage

_PAGE_ID = re.compile(r'^/page/(\d+)(?:/|$)')
_HTML_TAGS = {
    'p', 'div', 'span', 'br', 'em', 'i', 'strong', 'b', 'sup', 'sub', 'a',
    'code', 'pre', 'blockquote', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4',
    'h5', 'h6', 'table', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th', 'img',
    'math', 'del', 's', 'u', 'hr', 'content-ref',
}


def is_pipeline_render_json(payload: Any) -> bool:
    if not isinstance(payload, dict) or payload.get('schema_version'):
        return False
    pages = payload.get('children')
    return (isinstance(pages, list) and bool(pages)
            and payload.get('block_type', 'Document') == 'Document'
            and all(isinstance(p, dict) and p.get('block_type') == 'Page'
                    and _PAGE_ID.match(str(p.get('id') or '')) for p in pages))


def _walk(nodes):
    for node in nodes or []:
        yield node
        yield from _walk(node.get('children'))


def _expanded_html(node: dict, lookup: dict, issues: list[str], seen=frozenset()) -> str:
    identity = node.get('id')
    if identity in seen:
        raise ValueError(f'Cyclic Pipeline content reference: {identity}')
    seen = seen | {identity}
    value = str(node.get('html') or '')
    if not value:
        return ''.join(_expanded_html(child, lookup, issues, seen) for child in node.get('children') or [])
    soup = BeautifulSoup(value, 'html.parser')
    for ref in list(soup.find_all('content-ref')):
        target = lookup.get(ref.get('src'))
        if target is None:
            issues.append(f"Unresolved content reference: {ref.get('src')}")
            ref.replace_with(soup.new_string(f"[Unresolved source block: {ref.get('src')}]") )
        else:
            ref.replace_with(BeautifulSoup(_expanded_html(target, lookup, issues, seen), 'html.parser'))
    return str(soup)


def _reading_text(value: str, kind: str) -> str:
    # Escape unknown editorial angle phrases only in a typed source block;
    # table HTML is kept separately and is never passed through this function.
    value = re.sub(r'<\s*/?\s*([\w-]+)\b[^>]*>',
                   lambda m: m.group(0) if m.group(1).lower() in _HTML_TAGS else html.escape(m.group(0)), value)
    soup = BeautifulSoup(value, 'html.parser')
    if kind in {'SectionHeader', 'ListItem'}:
        for tag in soup.find_all(['li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            tag.unwrap()
    return markdownify(str(soup), heading_style='ATX', escape_misc=False).strip()


def pipeline_json_to_middle_document(
    payload: dict[str, Any], *, source_name: str | None = None,
    source_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Read a strict Pipeline tree, retaining actual physical page identities."""
    if not is_pipeline_render_json(payload):
        raise ValueError('Not a Contexture Pipeline render-tree JSON document')
    nodes = list(_walk(payload['children']))
    lookup = {}
    for node in nodes:
        identity = node.get('id')
        if not identity or identity in lookup:
            raise ValueError(f'Missing or duplicate Pipeline block id: {identity}')
        lookup[identity] = node
    pages = []
    seen_pages = set()
    for raw_page in payload['children']:
        index = int(_PAGE_ID.match(raw_page['id']).group(1))
        if index in seen_pages:
            raise ValueError(f'Duplicate Pipeline physical page: {index}')
        seen_pages.add(index)
        box = raw_page.get('bbox') or []
        width = box[2] - box[0] if len(box) == 4 else None
        height = box[3] - box[1] if len(box) == 4 else None
        blocks = []
        issues: list[str] = []

        def emit(raw):
            kind = normalize_block_type(raw.get('block_type') or '')
            if kind == 'ComplexRegion' and raw.get('children'):
                for child in raw['children']:
                    emit(child)
                return
            value = _expanded_html(raw, lookup, issues)
            attrs = {'source': 'pipeline_render_json', 'raw_block_type': raw.get('block_type')}
            if kind == 'MarginalNote':
                from aih_contexture.middle.semantics.recorded_annotations import annotation_payload
                value, annotation_attrs = annotation_payload(value)
                attrs.update(annotation_attrs)
            if kind == 'Table' or (raw.get('block_type') == 'TableGroup' and re.search(r'<table\b', value, re.I)):
                attrs['table_html'] = value
                attrs['table_structure_source'] = 'pipeline_render_tree'
                text = BeautifulSoup(value, 'html.parser').get_text(' ', strip=True)
            else:
                text = _reading_text(value, kind)
            if kind == 'SectionHeader':
                match = re.search(r'<h([1-6])\b', value, re.I)
                if match:
                    attrs.update(heading_level=int(match.group(1)), heading_level_source='native_html')
            resources = []
            for node in _walk([raw]):
                for resource_id in (node.get('images') or {}):
                    entry = {'id': resource_id}
                    if source_dir is not None and re.fullmatch(r'/page/\d+/\w+/\d+', resource_id):
                        # Use complete identities and actual files. Never guess
                        # that all pictures on a page share Figure_0.
                        stem = resource_id.replace('/', '_')
                        for suffix in ('.jpeg', '.jpg', '.png', '.webp'):
                            path = Path(source_dir) / (stem + suffix)
                            if path.is_file():
                                entry['path'] = path.name
                                break
                    resources.append(entry)
            if resources:
                attrs['image_resources'] = resources
                attrs['resource_id'] = resources[0]['id']
                if kind in {'Figure', 'Picture'} and resources[0].get('path'):
                    attrs['image_path'] = resources[0]['path']
            blocks.append(MiddleBlock(
                id=raw['id'], type=kind, page_index=index, order=len(blocks),
                text=text, bbox=raw.get('bbox'), polygon=raw.get('polygon'), attrs=attrs,
            ))

        for raw in raw_page.get('children') or []:
            emit(raw)
        printed = [b.text.strip().strip('{}') for b in blocks if b.type == 'PageNumber' and re.fullmatch(r'\s*\{?(?:\d{1,5}|[ivxlcdmIVXLCDM]+)\}?\s*', b.text)]
        page_attrs = {'coordinate_space': 'page', 'input_frame_index': index}
        if issues:
            page_attrs['diagnostic'] = list(dict.fromkeys(issues))
        pages.append(MiddlePage(index=index, width=width, height=height,
                                printed_page=printed[0] if len(set(printed)) == 1 else None,
                                blocks=blocks, attrs=page_attrs))
    document = MiddleDocument(pages=pages, source_name=source_name,
                              backends={'layout': 'recorded_pipeline'},
                              metadata={'pipeline_json_import': {
                                  'protocol': 'contexture-pipeline-render-tree',
                                  'word_geometry_available': False,
                              }})
    return normalize_middle_heading_levels(document).to_dict()
