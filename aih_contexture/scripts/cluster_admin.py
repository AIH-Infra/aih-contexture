"""Same-origin gateway administration, durable sessions and artifact downloads."""
from __future__ import annotations

import hashlib
import hmac
from http.cookies import CookieError, SimpleCookie
import json
from pathlib import Path
import secrets
import shutil
import tarfile
import time
from urllib.parse import parse_qs, quote, urlparse


COOKIE = 'contexture_admin'
ARTIFACTS = {
    'document.md': ('Markdown', 'text/markdown; charset=utf-8', '.md'),
    'middle.json': ('结构数据', 'application/json', '.middle.json'),
    'execution.json': ('执行摘要', 'application/json', '.execution.json'),
    'searchable.pdf': ('OCR PDF', 'application/pdf', '.ocr.pdf'),
}


class Admin:
    def __init__(self, queue, token, credentials=None):
        self.queue = queue
        self.token = token
        self.credentials = credentials or {}
        if set(self.credentials)-{'clients','workers'}:
            raise ValueError('Unknown credential role')
        for role,values in self.credentials.items():
            if not isinstance(values,dict) or any(not isinstance(value,str) or len(value)<24 for value in values.values()):
                raise ValueError('Role credentials must contain independent access keys')
        keys = [token]+[value for values in self.credentials.values() for value in values.values()]
        if len(keys)!=len(set(keys)):
            raise ValueError('Role access keys must be unique')
        self.key_version = hashlib.sha256(token.encode()).hexdigest()
        with queue.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS admin_sessions
                (id TEXT PRIMARY KEY, csrf TEXT, key_version TEXT, expires REAL)''')

    def cookie_id(self, headers):
        try:
            cookies = SimpleCookie()
            cookies.load(headers.get('Cookie', ''))
            value = cookies.get(COOKIE)
            return hashlib.sha256(value.value.encode()).hexdigest() if value else ''
        except CookieError:
            return ''

    def authenticate(self, headers):
        authorization = headers.get('Authorization')
        if authorization:
            if hmac.compare_digest(authorization.encode(), ('Bearer '+self.token).encode()):
                return {'mode': 'key', 'csrf': '', 'role':'admin'}
            for role,values in self.credentials.items():
                for name,value in values.items():
                    if hmac.compare_digest(authorization.encode(),('Bearer '+value).encode()):
                        return {'mode':'key','csrf':'','role':'worker' if role=='workers' else 'client','node':name}
            return None
        session_id = self.cookie_id(headers)
        if session_id:
            with self.queue.connect() as db:
                row = db.execute('SELECT csrf FROM admin_sessions WHERE id=? AND expires>? AND key_version=?',
                                 (session_id, time.time(), self.key_version)).fetchone()
            if row:
                return {'mode': 'session', 'csrf': row['csrf'], 'role':'admin'}
        return None

    def check_origin(self, handler):
        origin = handler.headers.get('Origin')
        if origin and urlparse(origin).netloc.lower() != handler.headers.get('Host', '').lower():
            raise PermissionError('Request origin is not allowed')

    def check_write(self, handler, principal):
        if principal['mode'] == 'session':
            self.check_origin(handler)
            if not hmac.compare_digest(handler.headers.get('X-CSRF-Token', '').encode(), principal['csrf'].encode()):
                raise PermissionError('Missing or invalid CSRF token')

    def body(self, handler):
        size = int(handler.headers.get('Content-Length', '0'))
        if not 0 <= size <= 8192:
            raise ValueError('Invalid management request size')
        value = json.loads(handler.rfile.read(size)) if size else {}
        if not isinstance(value, dict):
            raise ValueError('Expected a JSON object')
        return value

    def public(self, handler, path):
        assets = {'/': ('index.html', 'text/html; charset=utf-8'),
                  '/admin': ('index.html', 'text/html; charset=utf-8'),
                  '/admin/': ('index.html', 'text/html; charset=utf-8'),
                  '/assets/admin.css': ('admin.css', 'text/css; charset=utf-8'),
                  '/assets/admin.js': ('admin.js', 'text/javascript; charset=utf-8')}
        assets['/assets/logo.png'] = ('logo.png', 'image/png')
        if handler.command == 'GET' and path in assets:
            name, content_type = assets[path]
            data = (Path(__file__).with_name('cluster_ui')/name).read_bytes()
            handler.send_response(200)
            handler.send_header('Content-Type', content_type)
            handler.send_header('Content-Length', str(len(data)))
            handler.send_header('Cache-Control', 'no-store')
            handler.send_header('X-Content-Type-Options', 'nosniff')
            handler.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            handler.end_headers()
            handler.wfile.write(data)
            return True
        if path == '/admin/session' and handler.command == 'GET':
            principal = self.authenticate(handler.headers)
            if principal and principal['role']!='admin':
                principal = None
            handler.reply(200 if principal else 401,
                          {'authenticated': bool(principal), 'csrf_token': principal['csrf'] if principal else ''})
            return True
        if path == '/admin/login' and handler.command == 'POST':
            self.check_origin(handler)
            value = self.body(handler).get('token', '')
            if not isinstance(value, str) or not hmac.compare_digest(value.encode(), self.token.encode()):
                handler.reply(401, {'error': '访问密钥无效'})
                return True
            session = secrets.token_urlsafe(32)
            csrf = secrets.token_urlsafe(32)
            with self.queue.connect() as db:
                db.execute('DELETE FROM admin_sessions WHERE expires<?', (time.time(),))
                db.execute('INSERT INTO admin_sessions VALUES (?,?,?,?)',
                           (hashlib.sha256(session.encode()).hexdigest(), csrf, self.key_version, time.time()+43200))
            handler.reply(200, {'authenticated': True, 'csrf_token': csrf},
                          headers={'Set-Cookie': f'{COOKIE}={session}; Path=/; HttpOnly; SameSite=Strict; Max-Age=43200'})
            return True
        return False

    def artifacts(self, job_id):
        job = self.queue.status(job_id)
        items = []
        if job['status'] == 'done' and not job['artifacts_expired_at']:
            with tarfile.open(self.queue.root/job_id/'result.tar.gz', 'r:gz') as archive:
                members = {member.name: member for member in archive if member.isfile()}
                for name, (label, _, _) in ARTIFACTS.items():
                    member = members.get('output/'+name)
                    if member:
                        items.append(dict(name=name, label=label, size=member.size,
                                          url='/jobs/'+job_id+'/artifacts/'+name))
        return dict(items=items, expired_at=job['artifacts_expired_at'],
                    input_url='/jobs/'+job_id+'/input' if (self.queue.root/job_id/'input.pdf').exists() else None,
                    result_url='/jobs/'+job_id+'/result' if job['status']=='done' and not job['artifacts_expired_at'] else None)

    def download(self, handler, job_id, name):
        if name not in ARTIFACTS:
            raise KeyError('Unknown artifact')
        job = self.queue.status(job_id)
        if job['artifacts_expired_at']:
            raise FileNotFoundError('Intermediate artifacts have expired')
        if job['status'] != 'done':
            raise ValueError('Artifact is not ready')
        _, content_type, extension = ARTIFACTS[name]
        stem = Path(job['details'].get('filename') or job_id).stem
        with tarfile.open(self.queue.root/job_id/'result.tar.gz', 'r:gz') as archive:
            member = archive.getmember('output/'+name)
            if not member.isfile():
                raise KeyError('Unknown artifact')
            handler.send_response(200)
            handler.send_header('Content-Type', content_type)
            handler.send_header('Content-Length', str(member.size))
            handler.send_header('Content-Disposition', "attachment; filename*=UTF-8''"+quote(stem+extension, safe=''))
            handler.send_header('Cache-Control', 'no-store')
            handler.end_headers()
            with archive.extractfile(member) as source:
                shutil.copyfileobj(source, handler.wfile, 1024*1024)

    def route(self, handler, parsed):
        parts = parsed.path.strip('/').split('/')
        query = parse_qs(parsed.query)
        if handler.command == 'GET':
            if parts == ['admin', 'overview']:
                handler.reply(200, self.queue.overview())
            elif parts == ['admin', 'jobs']:
                handler.reply(200, self.queue.list_jobs(search=query.get('search', [''])[0], status=query.get('status', [''])[0],
                    limit=int(query.get('limit', ['20'])[0]), offset=int(query.get('offset', ['0'])[0])))
            elif len(parts) == 3 and parts[0]=='jobs' and parts[2]=='artifacts':
                handler.reply(200, self.artifacts(parts[1]))
            elif len(parts) == 4 and parts[0]=='jobs' and parts[2]=='artifacts':
                self.download(handler, parts[1], parts[3])
            else:
                return False
            return True
        if handler.command == 'POST':
            if parts == ['admin', 'logout']:
                self.body(handler)
                with self.queue.connect() as db:
                    db.execute('DELETE FROM admin_sessions WHERE id=?', (self.cookie_id(handler.headers),))
                handler.reply(200, {'authenticated': False}, headers={'Set-Cookie': f'{COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0'})
            elif len(parts) == 3 and parts[:2]==['admin', 'nodes']:
                handler.reply(200, self.queue.pause_node(parts[2], self.body(handler).get('paused')))
            elif len(parts) == 4 and parts[:2]==['admin', 'jobs'] and parts[3] in ('cancel','retry'):
                self.body(handler)
                operation = self.queue.cancel if parts[3]=='cancel' else self.queue.retry
                handler.reply(200, operation(parts[2]))
            else:
                return False
            return True
        return False
