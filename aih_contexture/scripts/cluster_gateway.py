"""Persistent document workflow, leased native tasks and the LAN HTTP API."""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
import json
import logging
import os
from pathlib import Path
import shutil
import sqlite3
import tarfile
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse
from uuid import uuid4, uuid5, NAMESPACE_URL
import zipfile

from aih_contexture.scripts.cluster_production import AdmissionError, capacity, durable_replace, inspect_pdf, policy, storage_status, sync_directory

LOG = logging.getLogger(__name__)
MAX_BODY = 256 * 1024 * 1024
NODES = ('amd66', 'intel88', 'mac100')
DEFAULTS = dict(lease_seconds=60, offline_seconds=45, attempt_timeout=900,
                queue_timeout=1800, document_timeout=7200, max_attempts=3,
                retry_delay=3)


class Conflict(ValueError):
    pass


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def atomic_copy(source, destination):
    temporary = destination.with_suffix('.incoming')
    shutil.copyfile(source, temporary)
    durable_replace(temporary,destination)


class Queue:
    def __init__(self, root: Path, *, production=None, **settings):
        if set(settings) - DEFAULTS.keys():
            raise ValueError('Unknown gateway settings')
        self.settings = DEFAULTS | settings
        self.production = policy(production)
        self.packaging = threading.Lock()
        if any(not isinstance(value, (int, float)) or value <= 0 for value in self.settings.values()):
            raise ValueError('Gateway timeouts and retry limits must be positive')
        if int(self.settings['max_attempts']) != self.settings['max_attempts']:
            raise ValueError('max_attempts must be an integer')
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.database = root/'queue.sqlite3'
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, status TEXT, node TEXT, target TEXT, updated REAL, error TEXT);
                CREATE TABLE IF NOT EXISTS nodes (id TEXT PRIMARY KEY, updated REAL);
                CREATE TABLE IF NOT EXISTS job_options (id TEXT PRIMARY KEY, stage TEXT);
                CREATE TABLE IF NOT EXISTS task_state (
                    id TEXT PRIMARY KEY, parent TEXT, kind TEXT, details TEXT,
                    created REAL, queued REAL, scheduled REAL, attempts INTEGER,
                    lease TEXT, started REAL, available REAL, last_node TEXT);
                CREATE TABLE IF NOT EXISTS attempts (
                    job_id TEXT, number INTEGER, node TEXT, started REAL, finished REAL,
                    status TEXT, error TEXT, PRIMARY KEY(job_id,number));
                CREATE TABLE IF NOT EXISTS node_state (id TEXT PRIMARY KEY, cooldown REAL);
                CREATE TABLE IF NOT EXISTS submissions (key TEXT PRIMARY KEY, digest TEXT, job_id TEXT);
                CREATE TABLE IF NOT EXISTS manual_retries (id TEXT PRIMARY KEY, baseline INTEGER, restarted REAL);
                CREATE TABLE IF NOT EXISTS node_controls (id TEXT PRIMARY KEY, paused INTEGER, profile TEXT);
                CREATE TABLE IF NOT EXISTS operations (name TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS purged_artifacts (id TEXT PRIMARY KEY, removed REAL);
                CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status);
                CREATE INDEX IF NOT EXISTS task_parent ON task_state(parent);
            ''')
            # Existing jobs retain their direct document/extract execution mode.
            db.execute('''INSERT OR IGNORE INTO task_state
                SELECT j.id,'','legacy',json_object('stage',COALESCE(o.stage,'document')),
                       j.updated,j.updated,j.updated,0,'',0,0,''
                FROM jobs j LEFT JOIN job_options o ON j.id=o.id''')
            db.executemany('INSERT OR IGNORE INTO node_controls VALUES (?,0,\'{}\')', [(node,) for node in NODES])

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def insert(self, db, job_id, kind, details, parent='', target='', source=None):
        now = time.time()
        directory = self.root/job_id
        directory.mkdir(exist_ok=True)
        sync_directory(self.root)
        if source is not None:
            atomic_copy(source, directory/'input.pdf')
        db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?)', (job_id, 'queued', '', target, now, ''))
        db.execute('INSERT INTO task_state VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                   (job_id, parent, kind, json.dumps(details), now, now, now, 0, '', 0, 0, ''))

    def submit(self, files, *, batch_pages=40, target='', stage='document', key=''):
        if target not in ('', *NODES) or stage not in ('document', 'extract'):
            raise ValueError('Unknown node or processing stage')
        if batch_pages < 1:
            raise ValueError('batch_pages must be positive')
        identity = []
        if len(files) > self.production['max_documents_per_request']:
            raise AdmissionError('Too many documents in one request', 413)
        for name, path in files:
            with path.open('rb') as stream:
                if stream.read(5) != b'%PDF-':
                    raise ValueError('Expected PDF bytes')
            identity.append(dict(filename=name, sha256=digest(path)))
        if not files or (stage == 'extract' and len(files) != 1):
            raise ValueError('Expected one or more document files')
        fingerprint = hashlib.sha256(json.dumps([identity, batch_pages, target, stage], sort_keys=True).encode()).hexdigest()
        if key:
            with self.connect() as db:
                existing = db.execute('SELECT * FROM submissions WHERE key=?', (key,)).fetchone()
                if existing:
                    if existing['digest'] != fingerprint:
                        raise Conflict('Idempotency key belongs to different input or settings')
                    return existing['job_id']
        counts = [inspect_pdf(path, self.production['max_document_pages']) for _, path in files]
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if key:
                existing = db.execute('SELECT * FROM submissions WHERE key=?', (key,)).fetchone()
                if existing:
                    if existing['digest'] != fingerprint:
                        raise Conflict('Idempotency key belongs to different input or settings')
                    return existing['job_id']
            capacity(db, self.root, self.production, len(files), sum(counts), sum(path.stat().st_size for _,path in files))
            result_id = uuid4().hex
            group = len(files) > 1
            if group:
                self.insert(db, result_id, 'group', {})
            for (name, path), item, count in zip(files, identity, counts):
                book_id = uuid4().hex if group else result_id
                details = dict(filename=name, source_sha256=item['sha256'], batch_pages=batch_pages,
                               page_count=count, source_bytes=path.stat().st_size, searchable_pdf=True)
                if stage == 'extract':
                    self.insert(db, book_id, 'legacy', details | {'stage': 'extract'}, target=target, source=path)
                else:
                    self.insert(db, book_id, 'book', details, parent=result_id if group else '', source=path)
                    task_id = uuid5(NAMESPACE_URL, book_id+'/prepare').hex
                    self.insert(db, task_id, 'prepare', details, parent=book_id, target=target, source=path)
            if key:
                db.execute('INSERT INTO submissions VALUES (?,?,?)', (key, fingerprint, result_id))
            return result_id

    def fail_or_retry(self, db, row, reason, retryable=True):
        now = time.time()
        budget = db.execute('SELECT baseline FROM manual_retries WHERE id=?', (row['id'],)).fetchone()
        baseline = budget['baseline'] if budget else 0
        retry = retryable and row['attempts']-baseline < self.settings['max_attempts']
        status = 'queued' if retry else 'failed'
        db.execute('UPDATE jobs SET status=?,node=?,updated=?,error=? WHERE id=?',
                   (status, '', now, reason, row['id']))
        delay = min(30, self.settings['retry_delay'] * 2**max(0, row['attempts']-baseline-1))
        db.execute("UPDATE task_state SET lease='',queued=?,available=?,last_node=? WHERE id=?",
                   (now, now+delay, row['node'], row['id']))
        db.execute('UPDATE attempts SET finished=?,status=?,error=? WHERE job_id=? AND number=?',
                   (now, 'retry' if retry else 'failed', reason, row['id'], row['attempts']))
        if row['node']:
            db.execute('INSERT OR REPLACE INTO node_state VALUES (?,?)', (row['node'], now+delay))

    def abort(self, db, job_id, reason, status='failed'):
        now = time.time()
        db.execute("UPDATE jobs SET status=?,updated=?,error=? WHERE id=? AND status NOT IN ('done','failed','cancelled')",
                   (status, now, reason, job_id))
        db.execute('''WITH RECURSIVE descendants(id) AS (
            SELECT id FROM task_state WHERE parent=? UNION ALL
            SELECT t.id FROM task_state t JOIN descendants d ON t.parent=d.id)
            UPDATE jobs SET status='cancelled',updated=?,error=?
            WHERE id IN (SELECT id FROM descendants) AND status IN ('queued','running')''', (job_id, now, reason))
        db.execute("UPDATE task_state SET lease='' WHERE id IN (SELECT id FROM jobs WHERE status='cancelled')")
        db.execute("UPDATE attempts SET status='cancelled',finished=?,error=? WHERE status='running' AND job_id IN (SELECT id FROM jobs WHERE status='cancelled')", (now, reason))

    def sweep(self, db):
        now = time.time()
        for row in db.execute('''SELECT j.*,t.* FROM jobs j JOIN task_state t USING(id)
                                 WHERE j.status='running' AND t.kind NOT IN ('book','group')''').fetchall():
            if now - row['started'] >= self.settings['attempt_timeout']:
                self.fail_or_retry(db, row, 'Attempt execution timeout')
            elif now - row['updated'] >= self.settings['lease_seconds']:
                self.fail_or_retry(db, row, 'Worker lease expired')
        for row in db.execute('''SELECT j.*,t.*,COALESCE(r.restarted,t.created) AS deadline_start
                                 FROM jobs j JOIN task_state t USING(id) LEFT JOIN manual_retries r USING(id)
                                 WHERE j.status IN ('queued','running')''').fetchall():
            if row['kind'] in ('book', 'group') and now-row['deadline_start'] >= self.settings['document_timeout']:
                self.abort(db, row['id'], 'Document deadline exceeded')
            elif row['kind'] not in ('book', 'group') and row['status'] == 'queued' and now-row['queued'] >= self.settings['queue_timeout']:
                self.abort(db, row['id'], 'Queue timeout waiting for an available worker')
        self.advance(db)

    def advance(self, db):
        now = time.time()
        books = db.execute("SELECT j.*,t.details FROM jobs j JOIN task_state t USING(id) WHERE t.kind='book' AND j.status IN ('queued','running')").fetchall()
        for book in books:
            children = db.execute('SELECT j.*,t.kind,t.details FROM jobs j JOIN task_state t USING(id) WHERE t.parent=?', (book['id'],)).fetchall()
            failed = next((child for child in children if child['status'] == 'failed'), None)
            if failed:
                self.abort(db, book['id'], f"Task {failed['id']} failed: {failed['error']}")
                continue
            extracts = [child for child in children if child['kind'] == 'extract']
            merge = next((child for child in children if child['kind'] == 'merge'), None)
            if extracts and all(child['status'] == 'done' for child in extracts):
                details = json.loads(book['details'])
                details['parts'] = [json.loads(child['details']) | {'id': child['id']} for child in extracts]
                if not merge:
                    self.insert(db, uuid5(NAMESPACE_URL, book['id']+'/merge').hex, 'merge', details, parent=book['id'])
                elif merge['status']=='queued':
                    db.execute('UPDATE task_state SET details=? WHERE id=?',(json.dumps(details),merge['id']))
            if merge and merge['status'] == 'done':
                atomic_copy(self.root/merge['id']/'result.tar.gz', self.root/book['id']/'result.tar.gz')
                db.execute("UPDATE jobs SET status='done',updated=?,error='' WHERE id=?", (now, book['id']))
        groups = db.execute("SELECT j.id FROM jobs j JOIN task_state t USING(id) WHERE t.kind='group' AND j.status IN ('queued','running')").fetchall()
        for group in groups:
            children = db.execute('SELECT j.* FROM jobs j JOIN task_state t USING(id) WHERE t.parent=? ORDER BY t.created,j.id', (group['id'],)).fetchall()
            failed = next((child for child in children if child['status'] == 'failed'), None)
            if failed:
                self.abort(db, group['id'], f"Document {failed['id']} failed: {failed['error']}")
            elif children and all(child['status'] == 'done' for child in children):
                db.execute("UPDATE jobs SET status='running' WHERE id=?", (group['id'],))

    def package_groups(self):
        if not self.packaging.acquire(blocking=False):
            return
        try:
            with self.connect() as db:
                groups = db.execute("SELECT j.id FROM jobs j JOIN task_state t USING(id) WHERE t.kind='group' AND j.status='running'").fetchall()
            for group in groups:
                with self.connect() as db:
                    children = db.execute('SELECT j.id,j.status FROM jobs j JOIN task_state t USING(id) WHERE t.parent=? ORDER BY t.created,j.id', (group['id'],)).fetchall()
                if not children or any(child['status']!='done' for child in children):
                    continue
                temporary = self.root/group['id']/('result-'+uuid4().hex+'.incoming')
                try:
                    with tarfile.open(temporary, 'w:gz', compresslevel=1) as output:
                        for child in children:
                            with tarfile.open(self.root/child['id']/'result.tar.gz', 'r:gz') as source:
                                for member in source:
                                    if member.isfile() and member.name.startswith('output/'):
                                        stream = source.extractfile(member)
                                        member.name = 'documents/'+child['id']+'/'+member.name[7:]
                                        output.addfile(member, stream)
                    with self.connect() as db:
                        db.execute('BEGIN IMMEDIATE')
                        status = db.execute('SELECT status FROM jobs WHERE id=?', (group['id'],)).fetchone()['status']
                        if status=='running':
                            durable_replace(temporary,self.root/group['id']/'result.tar.gz')
                            db.execute("UPDATE jobs SET status='done',updated=?,error='' WHERE id=?", (time.time(),group['id']))
                finally:
                    temporary.unlink(missing_ok=True)
        finally:
            self.packaging.release()

    def tick(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.sweep(db)
        self.package_groups()

    def claim(self, node, profile=None):
        now = time.time()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.sweep(db)
            db.execute('INSERT OR REPLACE INTO nodes VALUES (?,?)', (node, now))
            if profile is not None:
                if not isinstance(profile, dict):
                    raise ValueError('Node profile must be an object')
                clean = {}
                for key in ('cores', 'screenai_workers'):
                    value = profile.get(key)
                    if type(value) is not int or not 1 <= value <= 4096:
                        raise ValueError('Invalid node resource allocation')
                    clean[key] = value
                if 'work_free_bytes' in profile:
                    value = profile['work_free_bytes']
                    if type(value) is not int or value<0:
                        raise ValueError('Invalid worker disk status')
                    clean['work_free_bytes'] = value
                if 'accepting' in profile:
                    if type(profile['accepting']) is not bool:
                        raise ValueError('Invalid worker admission status')
                    clean['accepting'] = profile['accepting']
                db.execute('UPDATE node_controls SET profile=? WHERE id=?', (json.dumps(clean), node))
            control = db.execute('SELECT paused FROM node_controls WHERE id=?', (node,)).fetchone()
            if control and control['paused']:
                return {}
            if profile is not None and profile.get('accepting') is False:
                return {}
            cooldown = db.execute('SELECT cooldown FROM node_state WHERE id=?', (node,)).fetchone()
            if cooldown and cooldown['cooldown'] > now:
                return {}
            if db.execute("SELECT 1 FROM jobs WHERE status='running' AND node=?", (node,)).fetchone():
                return {}
            online = {row['id'] for row in db.execute('''SELECT n.id FROM nodes n JOIN node_controls c USING(id)
                WHERE n.updated>? AND c.paused=0 AND COALESCE(json_extract(c.profile,'$.accepting'),1)!=0''', (now-self.settings['offline_seconds'],))}
            unavailable = {row['id'] for row in db.execute("SELECT id FROM node_controls WHERE paused=1 OR json_extract(profile,'$.accepting')=0")}
            pending = db.execute('''SELECT j.*,t.* FROM jobs j JOIN task_state t USING(id)
                LEFT JOIN task_state parent ON t.parent=parent.id
                WHERE j.status='queued' AND t.kind NOT IN ('book','group') AND t.available<=?
                  AND (t.kind!='merge' OR NOT EXISTS (
                    SELECT 1 FROM task_state sibling JOIN jobs pending ON pending.id=sibling.id
                    WHERE sibling.parent=t.parent AND sibling.kind='extract' AND pending.status!='done'))
                  AND (t.kind!='extract' OR NOT EXISTS (
                    SELECT 1 FROM task_state preparation JOIN jobs preparing ON preparing.id=preparation.id
                    WHERE preparation.parent=t.parent AND preparation.kind='prepare' AND preparing.status!='done'))
                ORDER BY COALESCE(parent.scheduled,t.scheduled),t.created,j.id''', (now,)).fetchall()
            for row in pending:
                if row['target'] and row['target'] != node:
                    if row['target'] in online or row['target'] not in unavailable and now-row['created'] < self.settings['offline_seconds']:
                        continue
                if row['last_node'] == node and online-{node} and now-row['queued'] < self.settings['offline_seconds']:
                    continue
                lease = uuid4().hex
                attempt = row['attempts']+1
                db.execute("UPDATE jobs SET status='running',node=?,updated=? WHERE id=?", (node, now, row['id']))
                db.execute('UPDATE task_state SET lease=?,started=?,attempts=?,scheduled=? WHERE id=?', (lease, now, attempt, now, row['id']))
                db.execute('UPDATE task_state SET scheduled=? WHERE id=?', (now, row['parent']))
                db.execute('INSERT INTO attempts VALUES (?,?,?,?,?,?,?)', (row['id'], attempt, node, now, None, 'running', ''))
                if row['parent']:
                    db.execute("UPDATE jobs SET status='running',updated=? WHERE id=? AND status='queued'", (now, row['parent']))
                    db.execute("UPDATE jobs SET status='running',updated=? WHERE id=(SELECT parent FROM task_state WHERE id=?) AND status='queued'",
                               (now, row['parent']))
                details = json.loads(row['details'])
                stage = details.get('stage', 'document') if row['kind'] == 'legacy' else row['kind']
                return dict(id=row['id'], stage=stage, task=details, lease=lease, attempt=attempt,
                            lease_seconds=self.settings['lease_seconds'], heartbeat_seconds=min(10, self.settings['lease_seconds']/3),
                            attempt_timeout=self.settings['attempt_timeout'])
            return {}

    def owned(self, db, job_id, node, lease):
        row = db.execute('SELECT j.*,t.* FROM jobs j JOIN task_state t USING(id) WHERE id=?', (job_id,)).fetchone()
        if row is None:
            raise KeyError('Unknown job')
        if not lease or row['node'] != node or row['lease'] != lease or row['status'] not in ('running', 'done'):
            raise Conflict('Worker lease is no longer current')
        return row

    def renew(self, job_id, node, lease):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.sweep(db)
            row = self.owned(db, job_id, node, lease)
            if row['status'] != 'running':
                raise Conflict('Task already completed')
            now = time.time()
            db.execute('UPDATE jobs SET updated=? WHERE id=?', (now, job_id))
            db.execute('INSERT OR REPLACE INTO nodes VALUES (?,?)', (node, now))
        return {'status': 'running'}

    def accept_prepared(self, db, row, archive):
        details = json.loads(row['details'])
        manifest = json.load(archive.extractfile('output/manifest.json'))
        if manifest['source_sha256'] != details['source_sha256']:
            raise ValueError('Prepared PDF hash differs from submitted input')
        count = manifest['page_count']
        if details.get('page_count',count)!=count:
            raise ValueError('Prepared page count differs from admitted document')
        position = 0
        for chunk in manifest['chunks']:
            if chunk['start'] != position or not 0 < chunk['count'] <= details['batch_pages']:
                raise ValueError('Prepared batches have gaps or overlaps')
            task_id = uuid5(NAMESPACE_URL, row['parent']+'/extract/'+str(position)).hex
            directory = self.root/task_id
            directory.mkdir(exist_ok=True)
            temporary = directory/'input.incoming'
            with archive.extractfile('output/'+chunk['file']) as source, temporary.open('wb') as destination:
                shutil.copyfileobj(source, destination, 1024*1024)
            if digest(temporary) != chunk['sha256']:
                raise ValueError('Prepared batch hash mismatch')
            durable_replace(temporary,directory/'input.pdf')
            child = dict(start=position, count=chunk['count'], sha256=chunk['sha256'], filename=details['filename'])
            existing = db.execute('SELECT id FROM jobs WHERE id=?', (task_id,)).fetchone()
            if existing:
                db.execute("UPDATE jobs SET status='queued',node='',updated=?,error='' WHERE id=?", (time.time(),task_id))
                db.execute('UPDATE task_state SET details=?,queued=?,available=? WHERE id=?', (json.dumps(child),time.time(),time.time(),task_id))
            else:
                self.insert(db, task_id, 'extract', child, parent=row['parent'], target=row['target'])
            db.execute('DELETE FROM purged_artifacts WHERE id=?', (task_id,))
            position += chunk['count']
        if position != count or count <= 0:
            raise ValueError('Prepared page coverage differs from source PDF')
        details['page_count'] = count
        db.execute('UPDATE task_state SET details=? WHERE id=?', (json.dumps(details), row['parent']))

    def complete(self, job_id, node, lease, payload):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.sweep(db)
            row = self.owned(db, job_id, node, lease)
            if row['status'] == 'done':
                return {'status': 'done'}
            with tarfile.open(payload, 'r:gz') as archive:
                for member in archive:
                    if not member.name.startswith('output') or '..' in Path(member.name).parts or member.issym() or member.islnk():
                        raise ValueError('Invalid task result path')
                if row['kind'] == 'prepare':
                    self.accept_prepared(db, row, archive)
                else:
                    archive.getmember('output/middle.json')
                if row['kind'] in ('extract', 'merge'):
                    execution = json.load(archive.extractfile('output/execution.json'))
                    details = json.loads(row['details'])
                    expected = details['sha256'] if row['kind'] == 'extract' else details['source_sha256']
                    if execution['input_sha256'] != expected or execution['stage'] != row['kind']:
                        raise ValueError('Task result does not match input and stage')
                    requires_pdf = details.get('searchable_pdf', False)
                    if row['kind']=='extract':
                        parent = db.execute('SELECT details FROM task_state WHERE id=?', (row['parent'],)).fetchone()
                        requires_pdf = json.loads(parent['details']).get('searchable_pdf', False)
                    if requires_pdf:
                        archive.getmember('output/searchable.pdf')
            atomic_copy(payload, self.root/job_id/'result.tar.gz')
            now = time.time()
            db.execute("UPDATE jobs SET status='done',updated=?,error='' WHERE id=?", (now, job_id))
            db.execute("UPDATE attempts SET status='done',finished=? WHERE job_id=? AND number=?", (now, job_id, row['attempts']))
            self.advance(db)
        self.package_groups()
        return {'status': 'done'}

    def fail(self, job_id, node, lease, error):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.sweep(db)
            row = self.owned(db, job_id, node, lease)
            if row['status'] == 'done':
                return {'status': 'done'}
            self.fail_or_retry(db, row, error[-8000:])
            self.advance(db)
        return {'status': 'recorded'}

    def status(self, job_id):
        with self.connect() as db:
            row = db.execute('''SELECT j.*,t.kind,t.details,t.attempts,t.parent,t.created,r.restarted AS retried_at,p.removed AS artifacts_expired_at
                FROM jobs j JOIN task_state t USING(id) LEFT JOIN manual_retries r USING(id)
                LEFT JOIN purged_artifacts p USING(id) WHERE j.id=?''', (job_id,)).fetchone()
            if not row:
                raise KeyError('Unknown job')
            result = dict(row)
            result['details'] = json.loads(result['details'])
            result['attempt_history'] = [dict(attempt) for attempt in db.execute('SELECT number,node,started,finished,status,error FROM attempts WHERE job_id=? ORDER BY number', (job_id,))]
            children = [dict(child) for child in db.execute('''SELECT j.id,j.status,j.node,j.error,t.kind,t.attempts,t.details
                FROM jobs j JOIN task_state t USING(id) WHERE t.parent=? ORDER BY t.created,j.id''', (job_id,))]
            for child in children:
                child['details'] = json.loads(child['details'])
            result['children'] = children
            extracts = [child for child in children if child['kind'] == 'extract']
            total_pages = result['details'].get('page_count')
            if result['kind'] == 'group':
                extracts = [dict(child) for child in db.execute('''SELECT j.status,t.details FROM jobs j
                    JOIN task_state t USING(id) WHERE t.kind='extract' AND t.parent IN
                    (SELECT id FROM task_state WHERE parent=?)''', (job_id,))]
                for child in extracts:
                    child['details'] = json.loads(child['details'])
                total_pages = sum(child['details']['page_count'] for child in children) if all('page_count' in child['details'] for child in children) else None
            result['progress'] = dict(completed_pages=sum(child['details']['count'] for child in extracts if child['status'] == 'done'),
                                      total_pages=total_pages,
                                      completed_batches=sum(child['status'] == 'done' for child in extracts), total_batches=len(extracts))
            if result['kind'] == 'group':
                result['progress'].update(completed_documents=sum(child['status']=='done' for child in children), total_documents=len(children))
            return result

    def list_jobs(self, *, search='', status='', limit=20, offset=0):
        if status not in ('', 'queued', 'running', 'done', 'failed', 'cancelled'):
            raise ValueError('Unknown task status')
        if not 1 <= limit <= 100 or offset < 0 or len(search) > 200:
            raise ValueError('Invalid task list parameters')
        conditions = ["t.parent=''"]
        parameters = []
        if status:
            conditions.append('j.status=?')
            parameters.append(status)
        if search:
            conditions.append("(instr(lower(j.id),lower(?))>0 OR instr(lower(COALESCE(json_extract(t.details,'$.filename'),'')),lower(?))>0)")
            parameters.extend([search, search])
        where = ' AND '.join(conditions)
        with self.connect() as db:
            total = db.execute('SELECT count(*) FROM jobs j JOIN task_state t USING(id) WHERE '+where, parameters).fetchone()[0]
            ids = [row['id'] for row in db.execute('SELECT j.id FROM jobs j JOIN task_state t USING(id) WHERE '+where+' ORDER BY t.created DESC,j.id DESC LIMIT ? OFFSET ?', parameters+[limit, offset])]
        return dict(items=[self.status(job_id) for job_id in ids], total=total, limit=limit, offset=offset)

    def overview(self):
        with self.connect() as db:
            counts = {row['status']: row['count'] for row in db.execute('''SELECT j.status,count(*) AS count
                FROM jobs j JOIN task_state t USING(id) WHERE t.parent='' GROUP BY j.status''')}
        return dict(counts={status: counts.get(status, 0) for status in ('queued','running','done','failed','cancelled')},
                    health=self.health(), recent=self.list_jobs(limit=8)['items'],
                    production=storage_status(self),
                    upload_limit_bytes=self.production['max_upload_bytes'], server_time=time.time())

    def pause_node(self, node, paused):
        if node not in NODES or type(paused) is not bool:
            raise ValueError('Invalid node control')
        with self.connect() as db:
            db.execute('UPDATE node_controls SET paused=? WHERE id=?', (int(paused), node))
        return {'id': node, 'paused': paused}

    def cancel(self, job_id):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT j.status,t.parent FROM jobs j JOIN task_state t USING(id) WHERE id=?', (job_id,)).fetchone()
            if not row:
                raise KeyError('Unknown job')
            if row['parent'] or row['status'] not in ('queued','running'):
                raise Conflict('Only an active top-level task can be cancelled')
            self.abort(db, job_id, 'Cancelled by operator', status='cancelled')
        return self.status(job_id)

    def retry(self, job_id):
        now = time.time()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            root = db.execute('SELECT j.status,t.parent FROM jobs j JOIN task_state t USING(id) WHERE id=?', (job_id,)).fetchone()
            if not root:
                raise KeyError('Unknown job')
            if root['parent'] or root['status'] not in ('failed','cancelled'):
                raise Conflict('Only a failed or cancelled top-level task can be retried')
            books = db.execute('''WITH RECURSIVE tree(id) AS (SELECT ? UNION ALL
                SELECT t.id FROM task_state t JOIN tree ON t.parent=tree.id)
                SELECT j.id,t.kind,t.details FROM jobs j JOIN task_state t USING(id)
                WHERE j.id IN (SELECT id FROM tree) AND t.kind IN ('book','legacy') AND j.status IN ('failed','cancelled')''', (job_id,)).fetchall()
            capacity(db,self.root,self.production,len(books),sum(json.loads(book['details']).get('page_count',self.production['max_document_pages']) for book in books),0)
            for book in books:
                expired = db.execute('SELECT 1 FROM purged_artifacts p JOIN task_state t USING(id) WHERE t.parent=? LIMIT 1', (book['id'],)).fetchone()
                if not expired:
                    continue
                preparation = db.execute("SELECT id FROM task_state WHERE parent=? AND kind='prepare'", (book['id'],)).fetchone()['id']
                atomic_copy(self.root/book['id']/'input.pdf',self.root/preparation/'input.pdf')
                db.execute("UPDATE jobs SET status='cancelled',error='Rebuilding expired intermediate artifacts' WHERE id IN (SELECT id FROM task_state WHERE parent=?)", (book['id'],))
                db.execute('DELETE FROM purged_artifacts WHERE id=?', (preparation,))
            rows = db.execute('''WITH RECURSIVE tree(id) AS (
                SELECT ? UNION ALL SELECT t.id FROM task_state t JOIN tree ON t.parent=tree.id)
                SELECT j.id,t.attempts FROM jobs j JOIN task_state t USING(id)
                WHERE j.id IN (SELECT id FROM tree) AND j.status IN ('failed','cancelled')''', (job_id,)).fetchall()
            for row in rows:
                db.execute("UPDATE jobs SET status='queued',node='',updated=?,error='' WHERE id=?", (now, row['id']))
                db.execute("UPDATE task_state SET lease='',queued=?,available=?,started=0,last_node='',scheduled=? WHERE id=?", (now, now, now, row['id']))
                db.execute('INSERT OR REPLACE INTO manual_retries VALUES (?,?,?)', (row['id'], row['attempts'], now))
            self.advance(db)
        return self.status(job_id)

    def health(self):
        now = time.time()
        with self.connect() as db:
            nodes = {row['id']: dict(row) for row in db.execute('SELECT n.*,COALESCE(s.cooldown,0) AS cooldown FROM nodes n LEFT JOIN node_state s USING(id)')}
            busy = {row['node'] for row in db.execute("SELECT DISTINCT node FROM jobs WHERE status='running' AND node!=''")}
            controls = {row['id']: dict(row) for row in db.execute('SELECT * FROM node_controls')}
            active = {}
            for task in db.execute("SELECT j.id,j.node,t.parent,t.details,t.kind FROM jobs j JOIN task_state t USING(id) WHERE j.status='running' AND j.node!=''"):
                active[task['node']] = dict(id=task['id'], parent=task['parent'], kind=task['kind'], filename=json.loads(task['details']).get('filename'))
        return dict(status='ok', protocol=2, settings=self.settings, nodes=[
            dict(id=node, updated=nodes.get(node, {}).get('updated'),
                 online=node in nodes and now-nodes[node]['updated']<self.settings['offline_seconds'],
                 busy=node in busy,
                 paused=bool(controls[node]['paused']), profile=json.loads(controls[node]['profile']), active_task=active.get(node),
                 available=node in nodes and node not in busy and not controls[node]['paused'] and json.loads(controls[node]['profile']).get('accepting',True) and now-nodes[node]['updated']<self.settings['offline_seconds'] and nodes[node]['cooldown']<=now)
            for node in NODES])


def serve(root, token, port, *, production=None, credentials=None, **settings):
    from aih_contexture.scripts.cluster_admin import Admin
    queue = Queue(root, production=production, **settings)
    admin = Admin(queue, token, credentials=credentials)
    uploads = threading.BoundedSemaphore(queue.production['max_concurrent_uploads'])
    stopped = threading.Event()

    def maintain():
        while not stopped.wait(1):
            try:
                queue.tick()
            except Exception:
                LOG.exception('Queue maintenance failed')

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, value, headers=None):
            data = json.dumps(value, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        def send_file(self, path, name=None):
            self.send_response(200)
            self.send_header('Content-Type', 'application/pdf' if path.suffix=='.pdf' else 'application/gzip')
            self.send_header('Content-Length', str(path.stat().st_size))
            self.send_header('Content-Disposition', "attachment; filename*=UTF-8''"+quote(name or path.name,safe=''))
            self.end_headers()
            with path.open('rb') as source:
                shutil.copyfileobj(source, self.wfile, 1024*1024)

        def load_files(self, payload, temporary):
            if zipfile.is_zipfile(payload):
                files = []
                total = 0
                with zipfile.ZipFile(payload) as archive:
                    for member in archive.infolist():
                        if member.is_dir():
                            continue
                        total += member.file_size
                        if total > queue.production['max_upload_bytes'] or not member.filename.lower().endswith('.pdf'):
                            raise ValueError('ZIP must contain PDFs within the configured expanded-size limit')
                        if len(files)>=queue.production['max_documents_per_request']:
                            raise AdmissionError('Too many documents in one request',413)
                        destination = temporary/str(len(files))
                        with archive.open(member) as source, destination.open('wb') as output:
                            shutil.copyfileobj(source, output, 1024*1024)
                        files.append((unquote(member.filename.replace('\\', '/').split('/')[-1]), destination))
                return files
            name = unquote(self.headers.get('X-Filename', 'document.pdf')).replace('\\', '/').split('/')[-1]
            return [(name or 'document.pdf', payload)]

        def do_GET(self):
            self.handle_request()

        def do_POST(self):
            self.handle_request()

        def do_PUT(self):
            self.handle_request()

        def handle_request(self):
            parsed = urlparse(self.path)
            parts = parsed.path.strip('/').split('/')
            query = parse_qs(parsed.query)
            upload_slot = False
            unread = 0
            try:
                if admin.public(self, parsed.path):
                    return
                principal = admin.authenticate(self.headers)
                if not principal:
                    return self.reply(401, {'error': 'Authentication required'})
                if principal['role']!='admin':
                    if parts[0]=='admin':
                        raise PermissionError('Administrator access required')
                    if self.command in ('POST','PUT'):
                        worker_route = parts==['claim'] or len(parts)==3 and parts[0]=='jobs'
                        if principal['role']=='worker' and not worker_route:
                            raise PermissionError('Worker access is limited to task execution')
                        if principal['role']=='client' and parts not in (['jobs'],['process']):
                            raise PermissionError('Client access is limited to file submission')
                if self.command in ('POST','PUT'):
                    admin.check_write(self, principal)
                if admin.route(self, parsed):
                    return
                if self.command == 'GET':
                    if parts == ['health']:
                        return self.reply(200, queue.health())
                    if len(parts) in (2, 3) and parts[0] == 'jobs':
                        job = queue.status(parts[1])
                        if len(parts) == 2:
                            return self.reply(200, job)
                        if parts[2] in ('input', 'result'):
                            if parts[2] == 'result' and job['status'] != 'done':
                                raise Conflict('Result not ready')
                            path = root/parts[1]/('input.pdf' if parts[2]=='input' else 'result.tar.gz')
                            if not path.exists():
                                if job['artifacts_expired_at']:
                                    raise FileNotFoundError('Intermediate artifacts have expired')
                                raise KeyError('No file for this workflow stage')
                            original = job['details'].get('filename') or job['id']+'.pdf'
                            return self.send_file(path,original if parts[2]=='input' else Path(original).stem+'.tar.gz')
                    return self.reply(404, {'error': 'Unknown endpoint'})
                size = int(self.headers.get('Content-Length', '0'))
                limit = queue.production['max_upload_bytes'] if parts in (['jobs'],['process']) else queue.production['max_result_bytes']
                if not 0 <= size <= limit:
                    return self.reply(413, {'error': 'Payload exceeds the configured size limit'})
                unread = size
                if parts in (['jobs'],['process']):
                    if not uploads.acquire(blocking=False):
                        raise AdmissionError('Concurrent upload capacity reached; retry later',503)
                    upload_slot = True
                    if shutil.disk_usage(root).free < queue.production['min_free_bytes']+size*4:
                        raise AdmissionError('Gateway disk reserve reached; retry later',503)
                with tempfile.TemporaryDirectory(prefix='request-', dir=root) as temporary_name:
                    temporary = Path(temporary_name)
                    payload = temporary/'body'
                    with payload.open('wb') as output:
                        remaining = size
                        while remaining:
                            chunk = self.rfile.read(min(1024*1024, remaining))
                            if not chunk:
                                raise ValueError('Incomplete request body')
                            output.write(chunk)
                            remaining -= len(chunk)
                            unread = remaining
                    if parts in (['jobs'], ['process']) and self.command in ('POST', 'PUT'):
                        files = self.load_files(payload, temporary)
                        job_id = queue.submit(files, batch_pages=int(query.get('batch_pages', ['40'])[0]),
                                              target=query.get('node', [''])[0], stage=query.get('stage', ['document'])[0],
                                              key=self.headers.get('Idempotency-Key', ''))
                        uploads.release()
                        upload_slot = False
                        if parts == ['jobs']:
                            return self.reply(202, {'id': job_id, 'status_url': '/jobs/'+job_id, 'result_url': '/jobs/'+job_id+'/result'})
                        while True:
                            job = queue.status(job_id)
                            if job['status'] in ('done', 'failed', 'cancelled'):
                                break
                            time.sleep(1)
                        if job['status'] == 'cancelled':
                            return self.reply(409, {'id': job_id, 'error': job['error']})
                        if job['status'] == 'failed':
                            return self.reply(504 if 'timeout' in job['error'].lower() or 'deadline' in job['error'].lower() else 422,
                                              {'id': job_id, 'error': job['error']})
                        books = job['children'] if job['kind'] == 'group' else [job]
                        documents = []
                        for book in books:
                            with tarfile.open(root/book['id']/'result.tar.gz', 'r:gz') as archive:
                                markdown = archive.extractfile('output/document.md').read().decode('utf-8')
                            documents.append(dict(page_content=markdown, metadata=dict(source=book['details']['filename'],
                                page_count=book['details']['page_count'], contexture_job_id=book['id'],
                                contexture_status_url='/jobs/'+book['id'],contexture_artifacts_url='/jobs/'+book['id']+'/artifacts')))
                        return self.reply(200, documents if job['kind'] == 'group' else documents[0])
                    if parts == ['claim'] and self.command == 'POST':
                        request = json.loads(payload.read_text())
                        if request.get('protocol') != 2:
                            return self.reply(426, {'error': 'Worker protocol 2 is required'})
                        if request['node'] not in NODES:
                            raise ValueError('Unknown node')
                        if principal['role']=='worker' and request['node']!=principal['node']:
                            raise PermissionError('Worker identity differs from requested node')
                        return self.reply(200, queue.claim(request['node'], request.get('profile')))
                    if len(parts) >= 2 and parts[0] == 'jobs':
                        job_id = parts[1]
                        job = queue.status(job_id)
                        if len(parts) == 3:
                            action = parts[2]
                            node = self.headers.get('X-Node', '')
                            if principal['role']=='worker' and node!=principal['node']:
                                raise PermissionError('Worker identity differs from task owner')
                            lease = self.headers.get('X-Lease-Token', '')
                            if self.command == 'POST' and action == 'heartbeat':
                                return self.reply(200, queue.renew(job_id, node, lease))
                            if self.command == 'POST' and action == 'complete':
                                return self.reply(200, queue.complete(job_id, node, lease, payload))
                            if self.command == 'POST' and action == 'fail':
                                return self.reply(200, queue.fail(job_id, node, lease, payload.read_text(errors='replace')))
                    self.reply(404, {'error': 'Unknown endpoint'})
            except AdmissionError as exc:
                if unread:
                    self.connection.settimeout(10)
                    try:
                        while unread:
                            chunk = self.rfile.read(min(1024*1024,unread))
                            if not chunk:
                                break
                            unread -= len(chunk)
                    except (OSError,TimeoutError):
                        LOG.info('Capacity-rejected upload disconnected')
                self.reply(exc.status, {'error':str(exc)},headers={'Retry-After':'60'} if exc.status in (429,503) else None)
            except Conflict as exc:
                self.reply(409, {'error': str(exc)})
            except PermissionError as exc:
                self.reply(403, {'error': str(exc)})
            except KeyError as exc:
                self.reply(404, {'error': str(exc)})
            except FileNotFoundError:
                self.reply(410, {'error':'Intermediate artifacts have expired'})
            except (ValueError, tarfile.TarError, zipfile.BadZipFile) as exc:
                self.reply(422, {'error': str(exc)})
            except (BrokenPipeError, ConnectionResetError):
                LOG.info('Client disconnected from %s', parsed.path)
            except Exception:
                LOG.exception('Gateway request failed')
                self.reply(500, {'error': 'Gateway request failed; see server log'})
            finally:
                if upload_slot:
                    uploads.release()

    maintenance = threading.Thread(target=maintain, daemon=True)
    maintenance.start()
    server = ThreadingHTTPServer(('0.0.0.0', port), Handler)
    try:
        server.serve_forever()
    finally:
        stopped.set()
        server.server_close()
        maintenance.join(timeout=5)
