"""Distribute PDF page batches through the LAN gateway and render each book once."""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import tarfile
import time
import urllib.request


def write_json(path: Path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def merge_parts(parts, *, page_count: int, source_name: str):
    """Restore source page numbers before applying document-wide reading rules."""
    from aih_contexture.middle.indra_evidence import collect_indra_evidence
    pages = []
    batches = []
    backend = None
    schema = None
    for start, count, middle, execution in sorted(parts, key=lambda part: part[0]):
        if execution.get('stage') != 'extract':
            raise ValueError('Batch was finalized before document merge')
        if [page['index'] for page in middle['pages']] != list(range(count)):
            raise ValueError('Batch has missing, duplicate or unordered pages')
        if backend is not None and middle['backends'] != backend:
            raise ValueError('Batch backend versions differ')
        if schema is not None and middle['schema_version'] != schema:
            raise ValueError('Batch schema versions differ')
        backend, schema = middle['backends'], middle['schema_version']
        for local in middle['pages']:
            page = copy.deepcopy(local)
            index = local['index'] + start
            page['index'] = index
            page['anchor_start'], page['anchor_end'] = index, index + 1
            for block in page['blocks']:
                block['page_index'] = index
                block['anchor_start'], block['anchor_end'] = index, index + 1
                prefix = f"/page/{local['index']}/"
                if not block['id'].startswith(prefix):
                    raise ValueError('Unexpected Indra block identifier')
                block['id'] = f"/page/{index}/" + block['id'][len(prefix):]
            pages.append(page)
        batches.append(dict(start=start, count=count, execution=execution))
    if [page['index'] for page in pages] != list(range(page_count)):
        raise ValueError('Document batches have gaps, overlaps or out-of-range pages')
    return dict(schema_version=schema, source_name=source_name, page_count=page_count,
                pages=pages, backends=backend, metadata={
                    'indra': collect_indra_evidence(pages),
                    'cluster': {'batches': batches},
                    'cluster_profile': {'ocr': 'chrome_screenai', 'layout': 'indra_layout',
                                        'internal_indra_ocr': False},
                })


def run(config_path: Path, inputs: list[Path], output: Path, gateway: str, batch_pages: int):
    import pymupdf
    from aih_contexture.runtime.job import ContextureResult
    from aih_contexture.runtime.runner import _apply_middle_contract
    if batch_pages < 1:
        raise ValueError('batch_pages must be positive')
    config = json.loads(config_path.read_text(encoding='utf-8'))
    output.mkdir(parents=True, exist_ok=True)
    journal = output/'batch-state.json'
    identity = [dict(path=str(p.resolve()), sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in inputs]
    expected = dict(inputs=identity, batch_pages=batch_pages, gateway=gateway)
    state = json.loads(journal.read_text(encoding='utf-8')) if journal.exists() else expected | {
        'documents': [], 'created_at': time.time()}
    if any(state[key] != value for key, value in expected.items()):
        raise ValueError('Existing batch state belongs to different inputs or settings')

    def request(path, data=None):
        req = urllib.request.Request(gateway.rstrip('/')+path, data=data,
                                     headers={'Authorization': 'Bearer '+config['token']})
        with urllib.request.urlopen(req, timeout=180) as response:
            return response.read()

    if not state['documents']:
        for position, (source, identity_item) in enumerate(zip(inputs, identity)):
            directory = output/f"{position:03d}-{identity_item['sha256'][:12]}"
            directory.mkdir(exist_ok=True)
            chunks = []
            with pymupdf.open(source) as pdf:
                page_count = len(pdf)
                if not pdf.is_pdf or page_count == 0:
                    raise ValueError('Expected a nonempty PDF')
                for start in range(0, page_count, batch_pages):
                    count = min(batch_pages, page_count-start)
                    path = directory/f'{start:06d}.pdf'
                    with pymupdf.open() as chunk:
                        chunk.insert_pdf(pdf, from_page=start, to_page=start+count-1)
                        chunk.save(path)
                    chunks.append(dict(start=start, count=count, path=str(path.resolve()),
                                       sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
            state['documents'].append(dict(source_name=source.name, page_count=page_count,
                                           source_sha256=identity_item['sha256'],
                                           directory=str(directory.resolve()), chunks=chunks))
        write_json(journal, state)
    # Interleave books so one large document does not fill the queue first.
    documents = state['documents']
    for position in range(max(len(document['chunks']) for document in documents)):
        for document in documents:
            if position >= len(document['chunks']):
                continue
            chunk = document['chunks'][position]
            if 'job_id' not in chunk:
                payload = Path(chunk['path']).read_bytes()
                if hashlib.sha256(payload).hexdigest() != chunk['sha256']:
                    raise ValueError('Cached batch PDF changed')
                chunk['job_id'] = json.loads(request('/jobs?stage=extract', payload))['id']
                write_json(journal, state)
    pending = [chunk for document in documents for chunk in document['chunks']]
    while pending:
        for chunk in list(pending):
            destination = Path(chunk['path']).with_suffix('.result.json')
            if not destination.exists():
                job = json.loads(request('/jobs/'+chunk['job_id']))
                if job['status'] == 'failed':
                    raise RuntimeError(f"Batch {chunk['job_id']} failed: {job['error']}")
                if job['status'] != 'done':
                    continue
                with tarfile.open(fileobj=io.BytesIO(request('/jobs/'+chunk['job_id']+'/result')), mode='r:gz') as archive:
                    values = {}
                    for name in ('middle', 'execution'):
                        member = archive.getmember('output/'+name+'.json')
                        if not member.isfile() or member.size > 512*1024*1024:
                            raise ValueError('Invalid batch result member')
                        values[name] = json.load(archive.extractfile(member))
                if values['execution']['input_sha256'] != chunk['sha256']:
                    raise ValueError('Batch result belongs to another PDF')
                write_json(destination, values)
            pending.remove(chunk)
        if pending:
            time.sleep(3)
    for document in documents:
        parts = []
        for chunk in document['chunks']:
            values = json.loads(Path(chunk['path']).with_suffix('.result.json').read_text(encoding='utf-8'))
            parts.append((chunk['start'], chunk['count'], values['middle'], values['execution']))
        middle = merge_parts(parts, page_count=document['page_count'], source_name=document['source_name'])
        middle['metadata']['cluster']['source_sha256'] = document['source_sha256']
        result = ContextureResult(middle_json=middle, page_count=document['page_count'])
        _apply_middle_contract(result, middle, {'render_from_middle': True}, output_format='markdown')
        directory = Path(document['directory'])
        write_json(directory/'middle.json', result.middle_json)
        (directory/'document.md').write_text(result.markdown, encoding='utf-8')
        document['status'] = 'done'
        document['finished_at'] = time.time()
        write_json(journal, state)
        print(f"Completed {document['source_name']}: {directory}", flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    parser.add_argument('inputs', type=Path, nargs='+')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--gateway', required=True)
    parser.add_argument('--batch-pages', type=int, default=40)
    args = parser.parse_args()
    run(args.config, args.inputs, args.output, args.gateway, args.batch_pages)
