"""Authenticated, persistent file queue and native Contexture worker.

The gateway uses only the standard library. Workers reuse native ScreenAI,
strict Indra layout, canonical Middle conversion and scholarly rendering.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
import shutil
import time

def process(config_path: str, job_dir: str):
    process_started = time.perf_counter()
    config = json.loads(Path(config_path).read_text())
    screenai_workers = int(config.get('screenai_workers', 2))
    if screenai_workers < 1:
        raise ValueError('screenai_workers must be positive')
    root = Path(job_dir)
    task_path = root / 'task.json'
    task = json.loads(task_path.read_text()) if task_path.exists() else {'stage': 'document'}
    stage = task['stage']
    if stage in ('prepare', 'merge'):
        from aih_contexture.scripts.cluster_worker import process_document_stage
        process_document_stage(config, root, task)
        return
    import pymupdf
    from aih_contexture.runtime.job import ContextureJob
    from aih_contexture.runtime.execution import ContextureExecutionContext
    from aih_contexture.runtime.chrome_screenai_runtime import ChromeScreenAIRuntime
    from aih_contexture.runtime.indra_pipeline import run_indra_pipeline
    from aih_contexture.runtime.pipeline_parallelism import ParallelPlan
    output = root / 'output'
    output.mkdir(exist_ok=True)
    options = dict(layout_backend='indra_layout', ocr_backend='chrome_screenai',
                   indra_model_dir=config['indra_model_dir'],
                   chrome_model_dir=config['screenai_model_dir'],
                   chrome_workers=screenai_workers, indra_cores=config.get('cores', 4),
                   pdftext_workers=1, output_dir=str(output),
                   emit_middle_json=True, disable_ocr=True)
    started = time.perf_counter()
    with pymupdf.open(root/'input.pdf') as document:
        indices = list(range(len(document)))
    chrome = ChromeScreenAIRuntime(model_dir=config['screenai_model_dir'],
                                   workers=screenai_workers, emit_searchable_pdf=True)
    prepared = chrome.process_document(root/'input.pdf', indices)
    screenai_seconds = time.perf_counter()-started
    options['ocr_backend'] = 'none'
    job = ContextureJob(input_path=prepared['searchable_pdf_path'],
                       input_name='input.pdf', config=options,
                       output_formats=['markdown', 'json'])
    # This native service already has an operator-assigned CPU allocation.
    # Keep that allocation explicit instead of re-planning from host free RAM.
    allocation = ParallelPlan(
        mode='manual', workers=config.get('cores', 4),
        pages_per_batch=len(indices), batch_threshold=len(indices),
        worker_vram_gb=None, worker_ram_gb=1.5,
        limits={'managed_cpu': config.get('cores', 4)},
        notes=['Fixed native cluster CPU allocation; host RAM heuristic is not applied.'],
    )
    result = run_indra_pipeline(job, job.input_path, options, ContextureExecutionContext(),
                                parallel_plan=allocation, finalize_document=stage != 'extract')
    result.middle_json.setdefault('metadata', {})['cluster_profile'] = {
        'ocr': 'chrome_screenai', 'layout': 'indra_layout', 'internal_indra_ocr': False}
    if result.failed_pages:
        raise RuntimeError(f'Failed pages: {result.failed_pages}')
    shutil.copyfile(prepared['searchable_pdf_path'], output/'searchable.pdf')
    (output/'document.md').write_text(result.markdown or '', encoding='utf-8')
    (output/'middle.json').write_text(json.dumps(result.middle_json, ensure_ascii=False), encoding='utf-8')
    for name, image in result.images.items():
        destination = output/Path(name).name
        image.save(destination)
    (output/'execution.json').write_text(json.dumps(dict(
        node=config['node'], stage=stage, seconds=time.perf_counter()-started,
        process_seconds=time.perf_counter()-process_started,
        screenai_seconds=screenai_seconds,
        cores=config.get('cores', 4), screenai_workers=screenai_workers,
        page_count=result.page_count,
        warnings=result.warnings, diagnostics=result.diagnostics,
        input_sha256=hashlib.sha256((root/'input.pdf').read_bytes()).hexdigest()
    ), ensure_ascii=False), encoding='utf-8')


def gateway(root: Path, token: str, port: int, **settings):
    from aih_contexture.scripts.cluster_gateway import serve
    serve(root, token, port, **settings)


def worker(config_path: str):
    from aih_contexture.scripts.cluster_worker import run_worker
    run_worker(config_path)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('role', choices=['gateway','worker','process'])
    parser.add_argument('config')
    parser.add_argument('job_dir',nargs='?')
    args = parser.parse_args()
    if args.role == 'gateway':
        settings = json.loads(Path(args.config).read_text())
        gateway(Path(settings.pop('data_dir')), settings.pop('token'), settings.pop('port', 8766), **settings)
    elif args.role == 'worker':
        worker(args.config)
    else:
        process(args.config,args.job_dir)
