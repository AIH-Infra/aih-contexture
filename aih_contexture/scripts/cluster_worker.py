"""Native workflow stages and a worker that owns one fenced attempt at a time."""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.request

LOG = logging.getLogger(__name__)


def request(config, path, data=None, *, lease='', timeout=60):
    url = config['gateway'].rstrip('/')+path
    headers = {'Authorization': 'Bearer '+config['token'], 'X-Node': config['node']}
    if lease:
        headers['X-Lease-Token'] = lease
    if config.get('http_transport') == 'curl':
        settings = 'silent\nshow-error\nmax-time = '+str(timeout)+'\n'
        settings += ''.join('header = '+json.dumps(key+': '+value)+'\n' for key, value in headers.items())
        with tempfile.NamedTemporaryFile(dir=config['work_dir']) as payload:
            command = ['/usr/bin/curl', '--config', '-', '--write-out', '\n%{http_code}', url]
            if data is not None:
                payload.write(data)
                payload.flush()
                command += ['--data-binary', '@'+payload.name]
            result = subprocess.run(command, input=settings.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        body, status = result.stdout.rsplit(b'\n', 1)
        if int(status) >= 400:
            raise urllib.error.HTTPError(url, int(status), body.decode(errors='replace'), {}, io.BytesIO(body))
        result.check_returncode()
        return body
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def process_document_stage(config, root, task):
    import pymupdf
    from aih_contexture.scripts.cluster_batch import merge_parts, write_json
    started = time.perf_counter()
    output = root/'output'
    output.mkdir(exist_ok=True)
    if task['stage'] == 'prepare':
        chunks = []
        directory = output/'chunks'
        directory.mkdir(exist_ok=True)
        with pymupdf.open(root/'input.pdf') as pdf:
            page_count = len(pdf)
            if not pdf.is_pdf or not page_count:
                raise ValueError('Expected a nonempty PDF')
            for start in range(0, page_count, task['batch_pages']):
                count = min(task['batch_pages'], page_count-start)
                path = directory/f'{start:06d}.pdf'
                with pymupdf.open() as part:
                    part.insert_pdf(pdf, from_page=start, to_page=start+count-1)
                    part.save(path)
                chunks.append(dict(start=start, count=count, file='chunks/'+path.name,
                                   sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        write_json(output/'manifest.json', dict(page_count=page_count, chunks=chunks,
                   source_sha256=hashlib.sha256((root/'input.pdf').read_bytes()).hexdigest()))
    else:
        from aih_contexture.runtime.job import ContextureResult
        from aih_contexture.runtime.runner import _apply_middle_contract
        parts = []
        searchable = pymupdf.open() if task.get('searchable_pdf') else None
        for part in sorted(task['parts'], key=lambda item: item['start']):
            payload = request(config, '/jobs/'+part['id']+'/result')
            with tarfile.open(fileobj=io.BytesIO(payload), mode='r:gz') as archive:
                middle = json.load(archive.extractfile('output/middle.json'))
                execution = json.load(archive.extractfile('output/execution.json'))
                if searchable is not None:
                    with pymupdf.open(stream=archive.extractfile('output/searchable.pdf').read(), filetype='pdf') as batch_pdf:
                        if len(batch_pdf)!=part['count']:
                            raise ValueError('Searchable PDF batch page count differs')
                        searchable.insert_pdf(batch_pdf)
            if execution['input_sha256'] != part['sha256']:
                raise ValueError('Batch result belongs to a different PDF')
            parts.append((part['start'], part['count'], middle, execution))
        middle = merge_parts(parts, page_count=task['page_count'], source_name=task['filename'])
        middle['metadata']['cluster']['source_sha256'] = task['source_sha256']
        result = ContextureResult(middle_json=middle, page_count=task['page_count'])
        _apply_middle_contract(result, middle, {'render_from_middle': True}, output_format='markdown')
        write_json(output/'middle.json', result.middle_json)
        (output/'document.md').write_text(result.markdown, encoding='utf-8')
        if searchable is not None:
            try:
                if len(searchable)!=task['page_count']:
                    raise ValueError('Searchable PDF coverage differs from the document')
                searchable.save(output/'searchable.pdf', deflate=True)
            finally:
                searchable.close()
    write_json(output/'execution.json', dict(node=config['node'], stage=task['stage'],
               seconds=time.perf_counter()-started, page_count=page_count if task['stage']=='prepare' else task['page_count'],
               input_sha256=task['source_sha256'], cores=config['cores'], screenai_workers=config.get('screenai_workers', 2)))


def terminate_group(process):
    # Descendants can remain after their parent exits. The process group belongs
    # to this attempt because Popen created it with start_new_session.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=5)


def clean_previous_attempt(root):
    import psutil
    path = root/'active-attempt.json'
    if not path.exists():
        return
    previous = json.loads(path.read_text())
    # Match the inherited attempt ID before signalling a group left by a crash.
    for process in psutil.process_iter():
        try:
            if os.getpgid(process.pid) == previous['pid'] and process.environ().get('CONTEXTURE_CLUSTER_ATTEMPT') == previous['lease']:
                os.killpg(previous['pid'], signal.SIGKILL)
                break
        except (ProcessLookupError, psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    path.unlink()


def cleanup_attempts(config, root):
    from aih_contexture.scripts.cluster_production import JOB_ID
    now = time.time()
    removed = 0
    for job in root.iterdir():
        if not job.is_dir() or job.is_symlink() or not JOB_ID.fullmatch(job.name):
            continue
        for directory in job.iterdir():
            if not directory.is_dir() or directory.is_symlink() or not JOB_ID.fullmatch(directory.name):
                continue
            marker = directory/'finished.json'
            age = now-(marker.stat().st_mtime if marker.exists() else directory.stat().st_mtime)
            if age < 7*86400:
                continue
            if marker.exists():
                state = json.loads(marker.read_text())['status']
            else:
                try:
                    state = json.loads(request(config,'/jobs/'+job.name))['status']
                except urllib.error.HTTPError as error:
                    if error.code!=404:
                        raise
                    state = 'interrupted'
                if state not in ('done','failed','cancelled'):
                    continue
            days = 7 if state=='done' else 14
            if age>=days*86400:
                target = directory.resolve()
                if not target.is_relative_to(root.resolve()):
                    raise ValueError('Attempt cleanup target escapes the worker directory')
                shutil.rmtree(target)
                removed += 1
        if not any(job.iterdir()):
            job.rmdir()
    return removed


def run_worker(config_path):
    config = json.loads(Path(config_path).read_text())
    root = Path(config['work_dir'])
    root.mkdir(parents=True, exist_ok=True)
    profile = {'cores': config['cores'], 'screenai_workers': config.get('screenai_workers', 2)}
    clean_previous_attempt(root)
    next_cleanup = 0
    shutdown = threading.Event()
    for event in (signal.SIGTERM, signal.SIGINT):
        signal.signal(event, lambda *_: shutdown.set())
    while not shutdown.is_set():
        try:
            if time.time()>=next_cleanup:
                cleanup_attempts(config,root)
                next_cleanup = time.time()+3600
            profile['work_free_bytes'] = shutil.disk_usage(root).free
            profile['accepting'] = profile['work_free_bytes']>=config.get('min_free_bytes',10*1024**3)
            job = json.loads(request(config, '/claim', json.dumps({'node': config['node'], 'protocol': 2, 'profile': profile}).encode()))
            if not job:
                shutdown.wait(3)
                continue
        except (OSError, subprocess.SubprocessError, ValueError):
            LOG.exception('Cannot claim work')
            shutdown.wait(5)
            continue
        directory = root/job['id']/job['lease']
        directory.mkdir(parents=True, exist_ok=True)
        (directory/'task.json').write_text(json.dumps(job['task'] | {'stage': job['stage']}))
        stopped = threading.Event()
        lost = threading.Event()
        last_ack = [time.monotonic()]
        deadline = time.monotonic()+job['attempt_timeout']
        process = None
        completed = False

        def heartbeat():
            while not stopped.wait(job['heartbeat_seconds']):
                try:
                    request(config, '/jobs/'+job['id']+'/heartbeat', b'', lease=job['lease'], timeout=10)
                    last_ack[0] = time.monotonic()
                except urllib.error.HTTPError as exc:
                    if exc.code in (404, 409):
                        lost.set()
                        return
                    LOG.warning('Heartbeat HTTP %s', exc.code)
                except (OSError, subprocess.SubprocessError, ValueError):
                    LOG.warning('Heartbeat connection failed')
                if time.monotonic()-last_ack[0] >= job['lease_seconds']:
                    lost.set()
                    return

        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            if job['stage'] != 'merge':
                (directory/'input.pdf').write_bytes(request(config, '/jobs/'+job['id']+'/input'))
            if time.monotonic()-last_ack[0] >= job['lease_seconds']:
                lost.set()
            if shutdown.is_set() or lost.is_set():
                continue
            with (directory/'process.log').open('wb') as log:
                environment = dict(os.environ, CONTEXTURE_CLUSTER_ATTEMPT=job['lease'])
                process = subprocess.Popen([sys.executable, '-m', 'aih_contexture.scripts.cluster', 'process', config_path, str(directory)],
                                           stdout=log, stderr=subprocess.STDOUT, start_new_session=True, env=environment)
                (root/'active-attempt.json').write_text(json.dumps({'pid': process.pid, 'lease': job['lease']}))
                while process.poll() is None:
                    if time.monotonic()-last_ack[0] >= job['lease_seconds']:
                        lost.set()
                    if shutdown.wait(.5) or lost.is_set() or time.monotonic() >= deadline:
                        terminate_group(process)
                        break
                if shutdown.is_set() or lost.is_set():
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError('Attempt execution timeout')
                if process.returncode:
                    raise RuntimeError('Task process exited with code '+str(process.returncode))
            archive_path = directory/'result.tar.gz'
            with tarfile.open(archive_path, 'w:gz') as archive:
                archive.add(directory/'output', arcname='output')
            payload = archive_path.read_bytes()
            # A lost completion response can be retried with the same lease.
            while not shutdown.is_set() and not lost.is_set():
                try:
                    request(config, '/jobs/'+job['id']+'/complete', payload, lease=job['lease'])
                    completed = True
                    break
                except urllib.error.HTTPError as exc:
                    if exc.code in (404, 409):
                        lost.set()
                        break
                    if exc.code < 500:
                        raise
                    stopped.wait(2)
                except (OSError, subprocess.SubprocessError):
                    stopped.wait(2)
                if time.monotonic() >= deadline:
                    raise TimeoutError('Task result upload timeout')
        except Exception as exc:
            LOG.exception('Task %s failed', job['id'])
            log_path = directory/'process.log'
            error = str(exc)+'\n'+(log_path.read_text(errors='replace')[-7000:] if log_path.exists() else '')
            if not shutdown.is_set() and not lost.is_set():
                try:
                    request(config, '/jobs/'+job['id']+'/fail', error.encode(), lease=job['lease'])
                except (OSError, subprocess.SubprocessError):
                    LOG.warning('Cannot report failure; lease expiry will recover this task')
        finally:
            if process is not None:
                terminate_group(process)
            stopped.set()
            thread.join(timeout=15)
            (root/'active-attempt.json').unlink(missing_ok=True)
            (directory/'finished.json').write_text(json.dumps(dict(status='done' if completed else 'interrupted',finished=time.time())))
