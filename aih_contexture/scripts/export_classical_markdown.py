"""Re-render existing Middle JSON with auditable classical marginalia handling.

No OCR is run. A source PDF, when supplied, contributes existing text-layer
coordinates only. The original Middle JSON and PDF are never overwritten.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from aih_contexture.middle.classical_projection import (
    prepare_classical_render_view,
    semantic_body_projection,
)
from aih_contexture.middle.scholarly_markdown import render_middle_scholarly_markdown
from aih_contexture.middle.semantics.classical_marginalia import (
    collect_pdf_margin_words,
    middle_source_fingerprint,
    page_locator_comments,
    resolve_classical_marginalia,
)
from aih_contexture.evaluation.scholarly_markdown import evaluate_scholarly_markdown_text
from aih_contexture.runtime.artifacts import (
    compact_middle_json_for_storage,
    write_classical_marginalia_sidecar,
)


def file_sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _output_paths(code: str, output_dir: Path) -> list[Path]:
    return [output_dir / name for name in (
        f'{code}.md', f'{code}_middle.json', f'{code}.body.txt',
        f'{code}.body_map.jsonl', f'{code}.review.jsonl',
        f'{code}_classical_marginalia.jsonl', f'{code}_classical_manifest.json',
        f'{code}.export.json', f'{code}.export_errors.json', 'manifest.json',
    )]


def _validate_sources(sources: Any, output_dir: Path) -> None:
    """Reject a conflicting inventory before writing any document."""
    if not isinstance(sources, list) or not sources:
        raise ValueError('Inventory must contain a nonempty JSON array')
    seen: set[str] = set()
    inputs: set[Path] = set()
    targets: set[Path] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError('Each inventory record must be an object')
        code = str(source.get('code') or '')
        if not re.fullmatch(r'[A-Za-z0-9_-]+', code):
            raise ValueError('Document code must be a safe filename component')
        if code.casefold() in seen:
            raise ValueError(f'Duplicate document code: {code}')
        seen.add(code.casefold())
        middle = source.get('middle_json') or source.get('source_middle_json')
        if not middle:
            raise ValueError(f'{code}: source Middle path is required')
        inputs.add(Path(middle).resolve())
        if source.get('layout_source_pdf'):
            inputs.add(Path(source['layout_source_pdf']).resolve())
        targets.update(p.resolve() for p in _output_paths(code, output_dir))
    if inputs & targets:
        raise ValueError('An output path would overwrite a source')


def _body_export(data: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Keep page/locator metadata in a companion map, outside the body text."""
    projected = semantic_body_projection(data)
    source_pages = {p['index']: p for p in data.get('pages', [])}
    pieces: list[str] = []
    mapping = []
    position = 0
    for page in projected.get('pages', []):
        parts = []
        for block in page.get('blocks', []):
            value = block.get('text')
            if not isinstance(value, str):
                value = ' '.join(str(span.get('text') or '') for span in block.get('spans', []) if isinstance(span, dict))
            text = value.strip()
            if text:
                parts.append(text)
        text = '\n\n'.join(parts)
        start = position
        pieces.append(text + '\n\n')
        position += len(text) + 2
        source = source_pages[page['index']]
        mapping.append({
            'page_index': page['index'], 'printed_page': page.get('printed_page'),
            'offset_unit': 'unicode_codepoint',
            'char_start': start, 'char_end': start + len(text),
            'locator_comments': page_locator_comments(source),
        })
    return ''.join(pieces), mapping


def export_document(
    source: dict[str, Any], output_dir: Path, evidence_path: Path | None = None,
    *, emit_reading_diagnostics: bool = False,
) -> dict[str, Any]:
    _validate_sources([source], output_dir)
    code = str(source['code'])
    if not re.fullmatch(r'[A-Za-z0-9_-]+', code):
        raise ValueError('Document code must be a safe filename component')
    middle_path = Path(source.get('middle_json') or source['source_middle_json'])
    expected_hash = source.get('middle_sha256') or source.get('source_sha256')
    middle_hash = file_sha256(middle_path)
    if expected_hash and middle_hash != expected_hash:
        raise ValueError(f'{code}: source Middle SHA-256 mismatch')
    from aih_contexture.middle.storage import load_middle_json
    document = load_middle_json(middle_path)
    from aih_contexture.middle.validation import require_middle_for_publication
    require_middle_for_publication(document)
    immutable_source = copy.deepcopy(document)
    evidence = json.loads(evidence_path.read_text(encoding='utf-8')) if evidence_path else None
    if evidence_path and evidence_path.resolve() in {p.resolve() for p in _output_paths(code, output_dir)}:
        raise ValueError('An output path would overwrite review evidence')
    if evidence is not None:
        if not isinstance(evidence, dict) or evidence.get('source_fingerprint') != middle_source_fingerprint(document):
            raise ValueError(f'{code}: review evidence source fingerprint mismatch')
        if evidence.get('source_middle_sha256') and evidence['source_middle_sha256'] != middle_hash:
            raise ValueError(f'{code}: review evidence Middle SHA-256 mismatch')
    words = None
    pdf_hash = None
    pdf_path = source.get('layout_source_pdf')
    if pdf_path:
        pdf_hash = file_sha256(Path(pdf_path))
        if source.get('layout_source_sha256') and pdf_hash != source['layout_source_sha256']:
            raise ValueError(f'{code}: source PDF SHA-256 mismatch')
        words = collect_pdf_margin_words(pdf_path)
    if evidence and evidence.get('source_pdf_sha256') and evidence['source_pdf_sha256'] != pdf_hash:
        raise ValueError(f'{code}: review evidence PDF SHA-256 mismatch')

    config = {'classical_marginalia_mode': 'page_locators', 'classical_text_marginalia_mode': 'separate'}
    analyzed = resolve_classical_marginalia(document, config=config, pdf_words_by_page=words, evidence=evidence)
    if analyzed.get('metadata', {}).get('classical_marginalia_resolution', {}).get('rejected_human_evidence'):
        raise ValueError(f'{code}: supplied review evidence was rejected')
    compact = compact_middle_json_for_storage(analyzed)
    serialized = json.dumps(compact, ensure_ascii=False, separators=(',', ':'))
    reloaded = json.loads(serialized)
    markdown = render_middle_scholarly_markdown(analyzed, **config)
    rerendered = render_middle_scholarly_markdown(reloaded, **config)
    if markdown != rerendered:
        raise ValueError(f'{code}: compact save/reload changes the reading output')
    if document != immutable_source or file_sha256(middle_path) != middle_hash:
        raise ValueError(f'{code}: input source was mutated')

    view = prepare_classical_render_view(analyzed)
    rejected = []
    pending = []
    for page in view.get('pages', []):
        analysis = page.get('attrs', {}).get('classical_marginalia', {})
        for diagnostic in analysis.get('render_diagnostics', []):
            rejected.append({'page_index': page['index'], **diagnostic})
        for item in analysis.get('undetermined', []):
            pending.append({'page_index': page['index'], 'kind': 'undetermined', **item})
        for item in analysis.get('review', []):
            pending.append({'page_index': page['index'], **item})
    evaluation = evaluate_scholarly_markdown_text(markdown, validate_classical_locators=True)
    if not evaluation['ok'] or rejected:
        output_dir.mkdir(parents=True, exist_ok=True)
        write_json(output_dir / f'{code}.export_errors.json', {'evaluation': evaluation, 'rejected_edits': rejected})
        raise ValueError(f'{code}: render validation failed; see export_errors.json')

    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / f'{code}.md'
    middle_out = output_dir / f'{code}_middle.json'
    body_path = output_dir / f'{code}.body.txt'
    body_map_path = output_dir / f'{code}.body_map.jsonl'
    review_path = output_dir / f'{code}.review.jsonl'
    output_paths = [md_path, middle_out, body_path, body_map_path]
    source_targets = {middle_path.resolve()}
    if pdf_path:
        source_targets.add(Path(pdf_path).resolve())
    if any(p.resolve() in source_targets for p in output_paths):
        raise ValueError('An output path would overwrite a source')
    md_path.write_text(markdown, encoding='utf-8')
    from aih_contexture.middle.table_rendering import table_review_records
    table_records = table_review_records(compact)
    if table_records and emit_reading_diagnostics:
        table_path = output_dir / f'{code}_table_review.jsonl'
        table_path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in table_records), encoding='utf-8')
        output_paths.append(table_path)
    middle_out.write_text(serialized + '\n', encoding='utf-8')
    body, body_map = _body_export(analyzed)
    body_path.write_text(body, encoding='utf-8')
    for path, records in [(body_map_path, body_map)]:
        path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in records), encoding='utf-8')
    sidecars = {}
    if emit_reading_diagnostics:
        from aih_contexture.runtime.reading_diagnostics import build_reading_diagnostics, write_reading_diagnostics
        sidecars['reading_diagnostics_path'] = write_reading_diagnostics(
            build_reading_diagnostics(analyzed, {}, [], table_records), output_dir, code,
            markdown=markdown, markdown_name=md_path.name)
    all_paths = output_paths + [Path(p) for p in sidecars.values()]
    resolution = analyzed['metadata']['classical_marginalia_resolution']
    report = {
        'code': code, 'title': source.get('title'), 'source_middle': str(middle_path),
        'source_middle_sha256': middle_hash, 'source_pdf': pdf_path, 'source_pdf_sha256': pdf_hash,
        'evidence_path': str(evidence_path) if evidence_path else None,
        'evidence_sha256': file_sha256(evidence_path) if evidence_path else None,
        'page_count': len(document.get('pages', [])),
        'resolution': resolution, 'evaluation': evaluation,
        'source_unchanged': True, 'compact_reload_identical': True,
        'rejected_edit_count': len(rejected), 'review_record_count': len(pending),
        'status': 'exported_with_review_records' if pending else 'exported',
        'outputs': [{'path': p.name, 'sha256': file_sha256(p), 'bytes': p.stat().st_size} for p in all_paths],
    }
    if emit_reading_diagnostics:
        write_json(output_dir / f'{code}.export.json', report)
    (output_dir / f'{code}.export_errors.json').unlink(missing_ok=True)
    print(json.dumps({k: report[k] for k in ('code', 'page_count', 'compact_reload_identical')}, ensure_ascii=False), flush=True)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--inventory', type=Path, help='JSON array with code, middle_json and optional source PDF/hash fields')
    selection.add_argument('--middle-json', type=Path, help='Single existing Middle JSON')
    parser.add_argument('--source-pdf', type=Path)
    parser.add_argument('--document-id', default='document')
    parser.add_argument('--evidence', type=Path, help='Source-bound review evidence for a single input')
    parser.add_argument('--evidence-dir', type=Path, help='Inventory evidence files named CODE.evidence.json')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--reading-diagnostics', action='store_true', default=False)
    args = parser.parse_args(argv)
    if args.inventory:
        sources = json.loads(args.inventory.read_text(encoding='utf-8'))
    else:
        sources = [{'code': args.document_id, 'middle_json': str(args.middle_json), 'layout_source_pdf': str(args.source_pdf) if args.source_pdf else None}]
    _validate_sources(sources, args.output_dir)
    reports = []
    for source in sources:
        candidate = args.evidence_dir / f'{source["code"]}.evidence.json' if args.evidence_dir else args.evidence
        if candidate is not None and not candidate.is_file():
            raise FileNotFoundError(candidate)
        reports.append(export_document(source, args.output_dir, candidate, emit_reading_diagnostics=args.reading_diagnostics))
    if args.reading_diagnostics:
        write_json(args.output_dir / 'manifest.json', {'schema': 'contexture-classical-export/0.1', 'documents': reports})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
