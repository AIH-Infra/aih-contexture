"""Disk-backed uploads and bounded-memory downloads for the local Web UI."""
from __future__ import annotations

from dataclasses import dataclass
import html
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import secrets
import shutil
import tempfile
import threading
import time
from urllib.parse import parse_qs, quote, unquote, urlparse


TRANSFER_CHUNK = 256 * 1024
MAX_UPLOAD_BYTES = 4 * 1024**3
ALLOWED_SUFFIXES = {'.pdf', '.xml', '.tei', '.epub', '.md', '.markdown', '.json'}
WINDOWS_RESERVED_NAMES = {
    'CON', 'PRN', 'AUX', 'NUL',
    'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
    'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
}
SESSION_LIFETIME = 3 * 86400


@dataclass(frozen=True)
class DiskUpload(os.PathLike):
    path: str
    name: str
    size: int

    def __fspath__(self) -> str:
        return self.path


class UploadQueue:
    def __init__(self, cache_root: Path):
        self.cache_root = cache_root.resolve()
        self.directory = self.cache_root / secrets.token_hex(16)
        self.files: dict[str, DiskUpload] = {}
        self.uploading: set[str] = set()
        self.incoming_batches: set[str] = set()
        self.running = False
        self.lock = threading.RLock()

    def _save(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.directory / 'manifest.tmp'
        temporary.write_text(json.dumps({
            'running': self.running,
            'files': [vars(item) for item in self.files.values()],
            'uploading': sorted(self.uploading),
            'incoming_batches': sorted(self.incoming_batches),
        }, ensure_ascii=False), encoding='utf-8')
        temporary.replace(self.directory / 'manifest.json')

    def ready(self, suffixes=None) -> list[DiskUpload]:
        with self.lock:
            return [item for item in self.files.values()
                    if suffixes is None or Path(item.name).suffix.lower() in suffixes]

    def start_upload_batch(self, identifier: str) -> None:
        if not identifier or len(identifier) > 128:
            raise ValueError('上传批次标识无效')
        with self.lock:
            if self.running:
                raise ValueError('任务处理中，请等待任务结束后上传')
            self.incoming_batches.add(identifier)
            try:
                self._save()
            except OSError:
                self.incoming_batches.discard(identifier)
                raise

    def end_upload_batch(self, identifier: str) -> None:
        with self.lock:
            if identifier in self.incoming_batches:
                self.incoming_batches.remove(identifier)
                self._save()

    def receive(self, stream, name: str, length: int, *, batch: str | None = None) -> DiskUpload:
        name = name.replace('\\', '/').rsplit('/', 1)[-1]
        if not name or Path(name).suffix.lower() not in ALLOWED_SUFFIXES:
            raise ValueError('不支持的文件类型')
        if any(ord(char) < 32 for char in name):
            raise ValueError('文件名包含控制字符')
        if os.name == 'nt' and (
            any(char in '<>:"|?*' for char in name)
            or name.split('.')[0].upper() in WINDOWS_RESERVED_NAMES
        ):
            raise ValueError('文件名不适用于 Windows，请重命名后上传')
        if not 0 < length <= MAX_UPLOAD_BYTES:
            raise ValueError('文件大小须在 1 字节至 4 GiB 之间')
        identifier = secrets.token_hex(16)
        with self.lock:
            if self.running:
                raise ValueError('任务处理中，请等待任务结束后上传')
            if batch is not None and batch not in self.incoming_batches:
                raise ValueError('本批上传已取消，请重新选择文件')
            self.directory.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(self.directory).free < length + 256 * 1024**2:
                raise ValueError('暂存磁盘空间不足')
            self.uploading.add(identifier)
            try:
                if batch is None:
                    self._save()
            except OSError:
                self.uploading.remove(identifier)
                raise
        partial = self.directory / (identifier + '.part')
        destination = self.directory / identifier / name
        committed = False
        try:
            with partial.open('xb') as target:
                remaining = length
                while remaining:
                    chunk = stream.read(min(TRANSFER_CHUNK, remaining))
                    if not chunk:
                        raise ConnectionError('上传中断，请重新上传该文件')
                    target.write(chunk)
                    remaining -= len(chunk)
            with self.lock:
                destination.parent.mkdir()
                partial.replace(destination)
                item = DiskUpload(str(destination), name, length)
                self.files[identifier] = item
                self.uploading.remove(identifier)
                if batch is None:
                    self._save()
                committed = True
                return item
        finally:
            if not committed:
                with self.lock:
                    partial.unlink(missing_ok=True)
                    if destination.exists():
                        destination.unlink()
                    if destination.parent.exists():
                        destination.parent.rmdir()
                    self.files.pop(identifier, None)
                    self.uploading.discard(identifier)
                    if batch is None:
                        self._save()

    def begin(self, selected: list[DiskUpload], suffixes) -> None:
        with self.lock:
            if self.running or self.uploading or self.incoming_batches:
                raise ValueError('文件上传或处理尚未结束')
            if selected != self.ready(suffixes):
                raise ValueError('待处理文件已变化，请检查列表后重新开始')
            for item in selected:
                if not Path(item.path).is_file() or Path(item.path).stat().st_size != item.size:
                    raise ValueError(f'暂存文件不完整，请重新上传 {item.name}')
            self.running = True
            try:
                self._save()
            except OSError:
                self.running = False
                raise

    def finish(self, completed_paths: set[str]) -> None:
        with self.lock:
            try:
                for identifier, item in list(self.files.items()):
                    if item.path in completed_paths:
                        Path(item.path).unlink(missing_ok=True)
                        Path(item.path).parent.rmdir()
                        del self.files[identifier]
            finally:
                self.running = False
                self._save()

    def remove(self, selected_paths: set[str] | None = None) -> None:
        with self.lock:
            if self.running or self.uploading:
                raise ValueError('上传或处理期间不能清理暂存文件')
            for identifier, item in list(self.files.items()):
                if selected_paths is None or item.path in selected_paths:
                    Path(item.path).unlink(missing_ok=True)
                    Path(item.path).parent.rmdir()
                    del self.files[identifier]
            if selected_paths is None:
                self.incoming_batches.clear()
            if self.files or self.incoming_batches:
                self._save()
            elif self.directory.exists():
                if self.directory.resolve().parent != self.cache_root:
                    raise ValueError('暂存目录超出所属缓存目录')
                shutil.rmtree(self.directory)


class TransferSession:
    def __init__(self, cache_root: Path):
        self.token = secrets.token_urlsafe(32)
        self.queue = UploadQueue(cache_root)
        self.downloads: dict[str, Path] = {}
        self.last_seen = time.monotonic()


class TransferServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address=('0.0.0.0', 0)):
        self.sessions: dict[str, TransferSession] = {}
        self.lock = threading.RLock()
        super().__init__(address, TransferHandler)

    def register(self, session: TransferSession) -> None:
        with self.lock:
            for token, existing in list(self.sessions.items()):
                if time.monotonic() - existing.last_seen > SESSION_LIFETIME:
                    with existing.queue.lock:
                        if not existing.queue.running and not existing.queue.uploading:
                            existing.queue.remove()
                            del self.sessions[token]
            session.last_seen = time.monotonic()
            self.sessions[session.token] = session

    def session(self, token: str) -> TransferSession | None:
        with self.lock:
            session = self.sessions.get(token)
            if session is not None:
                session.last_seen = time.monotonic()
            return session

    def download(self, session: TransferSession, path: str) -> str:
        source = Path(path).resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        self.register(session)
        with self.lock:
            for identifier, existing in session.downloads.items():
                if existing == source:
                    return identifier
            identifier = secrets.token_hex(16)
            session.downloads[identifier] = source
            return identifier


class TransferHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    disable_nagle_algorithm = True

    def log_message(self, *_args):
        pass

    def _reply(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        if status >= 400:
            self.send_header('Connection', 'close')
            self.close_connection = True
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-File-Name, X-Upload-Batch')
        self.send_header('Access-Control-Max-Age', '600')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_POST(self):
        self.connection.settimeout(120)
        url = urlparse(self.path)
        query = parse_qs(url.query)
        session = self.server.session(query.get('token', [''])[0])
        if url.path not in {'/upload', '/upload-batch'} or session is None:
            self._reply(403, {'error': '上传会话已失效，请刷新页面'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if url.path == '/upload-batch':
                if not 0 < length <= 1024:
                    raise ValueError('上传批次信息过大或为空')
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict) or not isinstance(payload.get('id'), str):
                    raise ValueError('上传批次信息无效')
                if payload.get('complete') is True:
                    session.queue.end_upload_batch(payload['id'])
                else:
                    session.queue.start_upload_batch(payload['id'])
            else:
                name = unquote(self.headers.get('X-File-Name', '')) or query.get('name', [''])[0]
                session.queue.receive(self.rfile, name, length, batch=self.headers.get('X-Upload-Batch'))
        except (ValueError, ConnectionError, OSError) as exc:
            self._reply(400, {'error': str(exc)})
        else:
            self._reply(200, {'ok': True})

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        session = self.server.session(query.get('token', [''])[0])
        if url.path != '/download' or session is None:
            self._reply(403, {'error': '下载会话已失效，请刷新页面'})
            return
        with self.server.lock:
            source = session.downloads.get(query.get('id', [''])[0])
        if source is None:
            self._reply(404, {'error': '下载文件不存在'})
            return
        try:
            stream = source.open('rb')
        except OSError:
            self._reply(404, {'error': '下载文件已移动或删除'})
            return
        with stream:
            self.send_response(200)
            self.send_header('Content-Type', mimetypes.guess_type(source.name)[0] or 'application/octet-stream')
            self.send_header('Content-Length', str(os.fstat(stream.fileno()).st_size))
            self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(source.name))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            try:
                shutil.copyfileobj(stream, self.wfile, length=TRANSFER_CHUNK)
            except (BrokenPipeError, ConnectionResetError):
                return


_server: TransferServer | None = None
_server_lock = threading.Lock()


def get_transfer_server() -> TransferServer:
    global _server
    with _server_lock:
        if _server is None:
            port = int(os.environ.get('CONTEXTURE_TRANSFER_PORT', '0'))
            _server = TransferServer(('0.0.0.0', port))
            threading.Thread(target=_server.serve_forever, name='contexture-file-transfer', daemon=True).start()
    return _server


def get_transfer_session(st) -> TransferSession:
    session = st.session_state.get('_file_transfer_session')
    if session is None:
        instance = hashlib.sha256(str(Path(__file__).resolve().parents[3]).encode()).hexdigest()[:12]
        root = Path(os.environ.get('CONTEXTURE_UPLOAD_ROOT', Path(tempfile.gettempdir()) / 'contexture-upload-cache' / instance))
        root.mkdir(parents=True, exist_ok=True)
        # Recover disk space left by terminated processes. Only owned, inactive
        # batch directories older than the retention period are eligible.
        server = get_transfer_server()
        with server.lock:
            active = {existing.queue.directory for existing in server.sessions.values()}
        for directory in root.iterdir():
            if (directory.is_dir() and len(directory.name) == 32
                    and directory not in active
                    and all(char in '0123456789abcdef' for char in directory.name)
                    and time.time() - directory.stat().st_mtime > SESSION_LIFETIME):
                if directory.resolve().parent == root.resolve():
                    shutil.rmtree(directory)
        session = TransferSession(root)
        st.session_state['_file_transfer_session'] = session
    get_transfer_server().register(session)
    return session


def render_file_download(st, path: str, label: str) -> None:
    import streamlit.components.v1 as components

    session = get_transfer_session(st)
    server = get_transfer_server()
    identifier = server.download(session, path)
    query = f'/download?token={session.token}&id={identifier}'
    config = json.dumps({'port': server.server_port, 'query': query})
    components.html('''<html lang="zh-CN"><meta charset="utf-8"><style>
body{margin:0;font:14px system-ui,sans-serif}a{display:inline-block;padding:9px 14px;color:#252a35;border:1px solid #d9dce5;border-radius:8px;text-decoration:none;background:#fafaf8}
</style><a id="download" target="_blank" rel="noopener">''' + html.escape(label) + '''</a><script>
const config=''' + config + ''';
let host=window.location.hostname||'127.0.0.1';
try{host=window.parent.location.hostname||host;}catch(error){if(document.referrer)host=new URL(document.referrer).hostname;}
document.getElementById('download').href='http://'+host+':'+config.port+config.query;
</script></html>''', height=48)
