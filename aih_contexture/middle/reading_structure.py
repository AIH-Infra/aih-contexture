"""Optional reading structure shared by live and recorded document adapters.

These fields are evidence from a source block, never inferred text repairs.
"""
from __future__ import annotations

import html
import copy
import re
from pathlib import Path, PurePosixPath
import shutil
from typing import Any


READING_BLOCK_ATTRS = {
    'html', 'table_html', 'table_cells', 'table_structure_source',
    'image_path', 'img_path', 'asset_path', 'resource_id', 'image_resources',
    'list_kind', 'list_marker', 'raw_list_marker', 'list_indent_level',
    'list_group', 'list_order', 'continuation_of', 'original_text',
    'inferred_type', 'raw_block_type_before_inference',
    'semantic_source_text', 'semantic_rendered_text',
    'semantic_source_type', 'semantic_rendered_type', 'semantic_furniture_source', 'footnote_status',
    'source_annotation_html', 'source_annotation_position', 'source_annotation_subtype',
    'annotation_source_type', 'annotation_rendered_type', 'annotation_furniture_source',
}


def is_table_group_source(block: dict[str, Any]) -> bool:
    attrs = block.get('attrs') or {}
    return any(re.sub(r'[\s_-]', '', str(attrs.get(key) or '')).lower() == 'tablegroup'
               for key in ('raw_block_type', 'raw_label', 'native_raw_label'))


def cells_to_html(cells: list[dict[str, Any]]) -> str:
    """Serialize actual source cells, preserving their row/column/span data."""
    rows: dict[int, list[dict[str, Any]]] = {}
    for cell in cells:
        rows.setdefault(int(cell['row']), []).append(cell)
    output = ['<table><tbody>']
    for row in sorted(rows):
        output.append('<tr>')
        for cell in sorted(rows[row], key=lambda item: int(item['col'])):
            tag = 'th' if cell.get('is_header') else 'td'
            attrs = ''.join(f' {name}="{int(cell[name])}"' for name in ('rowspan', 'colspan') if int(cell.get(name) or 1) > 1)
            # Native TableCell text_lines are already HTML in the pipeline.
            content = cell.get('html')
            if content is None:
                content = html.escape(str(cell.get('text') or '')).replace('\n', '<br>')
            output.append(f'<{tag}{attrs}>{content}</{tag}>')
        output.append('</tr>')
    output.append('</tbody></table>')
    return ''.join(output)


def table_reading_source(block: dict[str, Any]) -> str:
    """Prefer retained native structure to a lossy flattened text fallback."""
    attrs = block.get('attrs') or {}
    for name in ('table_html', 'html'):
        value = attrs.get(name)
        if isinstance(value, str) and (re.search(r'<table\b', value, re.I)
                                     or (name == 'table_html' and re.search(r'<(?:fcel|ecel|lcel|ucel|xcel|nl)\b', value, re.I))):
            return value
    cells = attrs.get('table_cells')
    if isinstance(cells, list) and cells:
        return cells_to_html(cells)
    return str(block.get('text') or '')


def source_block_reading_attrs(block: Any, document: Any, canonical_type: str) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    raw_type = getattr(block, 'block_type', None)
    raw_label = getattr(raw_type, 'name', None) or str(raw_type or '')
    native_html = getattr(block, 'html', None)
    if (canonical_type == 'ComplexRegion' and raw_label == 'TableGroup' and native_html
            and re.search(r'<table\b|<(?:fcel|ecel|lcel|ucel|xcel|nl)\b', str(native_html), re.I)):
        attrs.update(table_html=str(native_html), table_structure_source='native_html')
    if canonical_type == 'Table':
        if native_html:
            attrs['table_html'] = str(native_html)
            attrs['table_structure_source'] = 'native_html'
        try:
            from aih_contexture.schema import BlockTypes
            native_cells = block.contained_blocks(document, (BlockTypes.TableCell,))
        except (AttributeError, TypeError, KeyError):
            native_cells = []
        cells = []
        for cell in native_cells:
            lines = getattr(cell, 'text_lines', None)
            cells.append({
                'id': str(cell.id), 'row': cell.row_id, 'col': cell.col_id,
                'rowspan': cell.rowspan, 'colspan': cell.colspan,
                'is_header': cell.is_header,
                'html': '<br>'.join(lines) if lines is not None else '',
            })
        if cells:
            attrs['table_cells'] = cells
            if not native_html:
                attrs['table_html'] = cells_to_html(cells)
                attrs['table_structure_source'] = 'native_cells'
    if canonical_type == 'ListItem':
        attrs['list_indent_level'] = getattr(block, 'list_indent_level', 0)
        try:
            text = str(block.raw_text(document) or '')
        except (AttributeError, TypeError, KeyError):
            text = ''
        marker = re.match(r'^\s*(\d+[.)]+[.,)]*|[•●○◦▪▫])(?=\s)', text)
        if marker:
            attrs['raw_list_marker'] = marker.group(1)
    if canonical_type in {'Figure', 'Picture'}:
        attrs['resource_id'] = str(getattr(block, 'id', ''))
    return attrs


def bind_available_image_resources(data: dict[str, Any], available_names) -> dict[str, Any]:
    """Attach paths only when the renderer actually supplied that resource."""
    document = copy.deepcopy(data)
    by_stem = {}
    for name in available_names:
        value = str(name).replace('\\', '/')
        stem, _, suffix = value.rpartition('.')
        if suffix.lower() in {'jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'tif', 'tiff'}:
            by_stem.setdefault(stem, []).append(value)
    def walk(blocks):
        for block in blocks:
            if block.get('type') in {'Figure', 'Picture'}:
                attrs = block.setdefault('attrs', {})
                identity = str(attrs.get('resource_id') or block.get('id') or '')
                paths = by_stem.get(identity.replace('/', '_'), [])
                if len(paths) == 1:
                    attrs['image_path'] = paths[0]
            walk(block.get('children') or [])
    for page in document.get('pages') or []:
        walk(page.get('blocks') or [])
    return document


def copy_existing_reading_resources(data: dict[str, Any], source_dir, output_dir) -> list[str]:
    """Retain local relative resources when moving a reading export to a folder.

    Missing historical resources are allowed. Only existing files below the
    provided source directory are copied; JSON cannot name arbitrary targets.
    """
    source_root, target_root = Path(source_dir).resolve(), Path(output_dir).resolve()
    paths = set()
    def walk(blocks):
        for block in blocks or []:
            attrs = block.get('attrs') or {}
            paths.update(str(attrs[k]) for k in ('image_path','img_path','asset_path') if attrs.get(k))
            paths.update(str(r['path']) for r in attrs.get('image_resources', []) if isinstance(r,dict) and r.get('path'))
            walk(block.get('children'))
    for page in data.get('pages') or []:
        walk(page.get('blocks'))
    copied = []
    for value in sorted(paths):
        relative = PurePosixPath(value.replace('\\','/'))
        if relative.is_absolute() or '..' in relative.parts or ':' in value:
            continue
        source, target = (source_root / relative).resolve(), (target_root / relative).resolve()
        if not source.is_relative_to(source_root) or not target.is_relative_to(target_root) or not source.is_file():
            continue
        if source != target:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source,target)
        copied.append(str(target))
    return copied
