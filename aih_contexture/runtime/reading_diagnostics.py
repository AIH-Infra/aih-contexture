"""Optional reading diagnostics, separate from every publication artifact."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path


def reading_diagnostics_enabled(config=None):
    config = config or {}
    # This is an execution/output preference, never inherited from a document.
    value = config.get('emit_reading_diagnostics', config.get('emit_diagnostics', False))
    return value is True or isinstance(value, str) and value.lower() in {'true', '1', 'yes'}


def publication_document(document):
    """Remove only this feature's derived reports, preserving source semantics."""
    return _publication_document_owned(copy.deepcopy(document))


def _publication_document_owned(result):
    """Internal cleaner for a just-created transaction's private document."""
    metadata = result.get('metadata')
    if isinstance(metadata, dict):
        from aih_contexture.middle.indra_evidence import strip_indra_review
        strip_indra_review(metadata)
        for key in ('reading_review', 'classical_marginalia_review', 'reading_diagnostics'):
            metadata.pop(key, None)
        for key in ('semantic_resolution', 'classical_marginalia_resolution'):
            if isinstance(metadata.get(key), dict):
                metadata[key].pop('warnings', None)
    for page in result.get('pages') or []:
        attrs = page.get('attrs') or {}
        attrs.pop('reading_folio_review', None)
        analysis = attrs.get('classical_marginalia')
        if isinstance(analysis, dict):
            for key in ('warnings', 'review', 'render_diagnostics'):
                analysis.pop(key, None)
        def clean_blocks(blocks):
            for block in blocks or []:
                block_attrs = block.get('attrs') or {}
                furniture = block_attrs.pop('page_furniture_review', None)
                if isinstance(furniture, dict):
                    block_attrs['semantic_furniture_source'] = {
                        key: copy.deepcopy(furniture[key]) for key in
                        ('original_type', 'original_attributes', 'upstream_confidence') if key in furniture}
                block_attrs.pop('semantic_warnings', None)
                clean_blocks(block.get('children'))
        clean_blocks(page.get('blocks'))
    return result


def build_reading_diagnostics(document, validation, warnings, tables):
    from aih_contexture.middle.reading_review import reading_review_status
    from aih_contexture.middle.classical_review import classical_review_status
    from aih_contexture.middle.indra_evidence import indra_review_from_document
    return {'schema': 'contexture-reading-diagnostics/1',
            'source_name': document.get('source_name'),
            'reading_review': reading_review_status(document, tables),
            'classical_review': classical_review_status(document),
            'validation': copy.deepcopy(validation), 'warnings': list(warnings),
            'indra_review': indra_review_from_document(document),
            'tables': copy.deepcopy(tables),
            'page_furniture': [{'page_index':p.get('index'), 'block_id':b.get('id'),
                                'review':copy.deepcopy(b['attrs']['page_furniture_review'])}
                               for p in document.get('pages') or [] for b in p.get('blocks') or []
                               if (b.get('attrs') or {}).get('page_furniture_review')],
            'classical_analysis': [{'index':p.get('index'),
                                    'analysis':copy.deepcopy((p.get('attrs') or {}).get('classical_marginalia'))}
                                   for p in document.get('pages') or []
                                   if (p.get('attrs') or {}).get('classical_marginalia')]}


def bind_reading_diagnostics(diagnostic_path, markdown_path):
    from aih_contexture.runtime.artifacts import atomic_write_text
    path, reading = Path(diagnostic_path), Path(markdown_path)
    payload = json.loads(path.read_text(encoding='utf-8-sig'))
    payload['reading_artifact'] = {'name': reading.name,
        'sha256': hashlib.sha256(reading.read_text(encoding='utf-8-sig').encode('utf-8')).hexdigest()}
    # Keep each saved variant's binding instead of rebinding its sibling's file.
    target = reading.with_suffix('.diagnostics.json')
    atomic_write_text(str(target), json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return str(target)


def write_reading_diagnostics(diagnostics, output_dir, basename, *, markdown=None, markdown_name=None):
    """Write one explicitly requested sidecar bound to the exact saved reading."""
    from aih_contexture.runtime.artifacts import atomic_write_text
    payload = copy.deepcopy(diagnostics)
    if markdown is not None:
        payload['reading_artifact'] = {'name': markdown_name or basename + '.md',
                                      'sha256': hashlib.sha256(markdown.encode('utf-8')).hexdigest()}
    stem = Path(markdown_name).stem if markdown is not None and markdown_name else basename
    path = Path(output_dir) / (stem + '.diagnostics.json')
    atomic_write_text(str(path), json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return str(path)
