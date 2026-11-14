"""One persistent, isolated Pipeline process, with per-file stall detection."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import tempfile
import threading
import uuid

from aih_contexture.runtime.console_dispatcher import TextTailBuffer
from aih_contexture.runtime.subprocess_stream import (
    _ProgressWatchdog, _parse_event_line, _terminate_process_tree,
)
from aih_contexture.scripts.pipeline_file_worker import RESULT_PREFIX
from aih_contexture.scripts.ui.pipeline_subprocess import (
    _format_returncode, _pipeline_worker_env, _prepare_pipeline_job_spec, pipeline_python_executable,
)


class PipelineFileProcess:
    """Owned by one queue worker thread; at most one request is in flight."""

    def __init__(self, repo_root):
        self.repo_root = os.fspath(repo_root)
        self.process = None
        self.lines = queue.Queue()
        self.readers = []

    def _start(self):
        if self.process is not None and self.process.poll() is None:
            return
        self.close()
        self.lines = queue.Queue()
        self.process = subprocess.Popen(
            [pipeline_python_executable(self.repo_root), "-u", "-m", "aih_contexture.scripts.pipeline_file_worker"],
            cwd=self.repo_root, env=_pipeline_worker_env(), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", bufsize=1,
        )
        self.readers = []
        for name, pipe in (("stdout", self.process.stdout), ("stderr", self.process.stderr)):
            reader = threading.Thread(target=self._read_lines, args=(self.lines, name, pipe), daemon=True)
            reader.start()
            self.readers.append(reader)

    @staticmethod
    def _read_lines(lines, name, pipe):
        try:
            for line in pipe:
                lines.put((name, line))
        finally:
            lines.put((name, None))
            pipe.close()

    def run(self, job_spec, *, repo_root=None, progress_timeout=None, progress_callback=None):
        # A killed/crashed worker starts fresh for the next file, without retrying
        # or hiding the failure of its previous file.
        fd, result_path = tempfile.mkstemp(suffix=".pipeline_result.json")
        os.close(fd)
        stdout, stderr = TextTailBuffer(2 * 1024**2), TextTailBuffer(4 * 1024**2)
        watchdog = _ProgressWatchdog()
        stalled = False
        stalled_for = 0.0
        last_event = None
        failure = None
        returncode = 0
        try:
            self._start()
            request_id = uuid.uuid4().hex
            self.process.stdin.write(json.dumps({
                "request_id": request_id, "job": _prepare_pipeline_job_spec(job_spec),
                "result_path": result_path,
            }, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
            stage = None
            while True:
                stalled_for, last_event = watchdog.snapshot()
                if progress_timeout and stalled_for >= progress_timeout:
                    stalled = True
                    failure = f"子进程连续 {int(stalled_for)} 秒无进展，已终止并跳过当前文件"
                    self.close(force=True)
                    returncode = -9
                    break
                try:
                    channel, line = self.lines.get(timeout=0.1)
                except queue.Empty:
                    continue
                if line is None:
                    if channel != "stdout":
                        continue
                    returncode = self.process.wait(timeout=5)
                    failure = f"常驻子进程异常退出（返回码 {_format_returncode(returncode)}）"
                    self.close(force=True)
                    break
                if line.rstrip() == RESULT_PREFIX + request_id:
                    break
                event = _parse_event_line(line)
                if event is not None:
                    watchdog.observe(event)
                    if progress_callback is not None:
                        progress_callback(event)
                    if event.get("stage") != stage:
                        stage = event.get("stage")
                        print(f"[Pipeline] {job_spec.get('file_name', '')}: {stage}", flush=True)
                else:
                    (stderr if channel == "stderr" else stdout).append(line)
            if os.path.getsize(result_path):
                with open(result_path, encoding="utf-8") as stream:
                    result = json.load(stream)
            else:
                result = {"success": False, "file_name": job_spec.get("file_name"), "file_outputs": [],
                          "error": failure or "常驻子进程未写入结果", "traceback": ""}
            if failure:
                result["success"] = False
                result["partial"] = bool(result.get("partial") or result.get("file_outputs"))
                result["error"] = failure + (f"；{result['error']}" if result.get("error") and result["error"] != failure else "")
            result.update(returncode=returncode, stdout=stdout.getvalue(), stderr=stderr.getvalue(),
                          stalled=stalled, stalled_for=stalled_for if stalled else 0,
                          last_progress_event=last_event)
            return result
        except Exception:
            self.close(force=True)
            raise
        finally:
            os.unlink(result_path)

    def close(self, *, force=False):
        proc = self.process
        if proc is None:
            return
        try:
            if force:
                _terminate_process_tree(proc)
            elif proc.poll() is None:
                proc.stdin.write('{"shutdown":true}\n')
                proc.stdin.flush()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    _terminate_process_tree(proc)
            proc.wait(timeout=5)
        except (BrokenPipeError, OSError):
            _terminate_process_tree(proc)
        finally:
            if proc.stdin:
                proc.stdin.close()
            for reader in self.readers:
                reader.join(timeout=5)
            self.process = None
            self.readers = []
