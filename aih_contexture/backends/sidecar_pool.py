from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class SidecarProcessSpec:
    """Stable process identity for a reusable sidecar."""

    backend: str
    task: str
    command: tuple[str, ...]
    cwd: str | None = None
    env: tuple[tuple[str, str], ...] = ()
    timeout: int = 3600

    @classmethod
    def from_parts(
        cls,
        *,
        backend: str,
        task: str,
        command: list[str],
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        timeout: int = 3600,
    ) -> "SidecarProcessSpec":
        return cls(
            backend=backend,
            task=task,
            command=tuple(str(part) for part in command),
            cwd=str(cwd) if cwd is not None else None,
            env=tuple(sorted((str(key), str(value)) for key, value in (env or {}).items())),
            timeout=int(timeout),
        )

    def popen_env(self) -> dict[str, str] | None:
        return dict(self.env) if self.env else None


class JsonlSidecarClient:
    """Small JSON-lines client for long-lived model sidecars."""

    def __init__(
        self,
        spec: SidecarProcessSpec,
        *,
        popen_factory: Any = subprocess.Popen,
    ):
        self.spec = spec
        self._popen_factory = popen_factory
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._stderr_tail: list[str] = []
        self._stderr_thread: threading.Thread | None = None

    def request(self, task: str, payload: dict[str, Any]) -> Any:
        with self._lock:
            proc = self._ensure_started()
            request_id = uuid4().hex
            message = dict(payload)
            message["request_id"] = request_id
            message["task"] = task
            self._write_message(proc, message)
            response = self._read_response(proc, request_id)
            if not response.get("ok"):
                error = response.get("error") or "sidecar request failed"
                stderr_tail = response.get("stderr_tail") or self.stderr_tail()
                raise RuntimeError(f"{error}\nSTDERR tail:\n{stderr_tail}")
            return response.get("result")

    def close(self) -> None:
        with self._lock:
            proc = self._proc
            self._proc = None
            if proc is None:
                return
            try:
                if proc.poll() is None:
                    self._write_message(proc, {"request_id": uuid4().hex, "task": "shutdown"})
            except Exception:
                pass
            try:
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

    def stderr_tail(self) -> str:
        return "".join(self._stderr_tail[-50:])

    def _ensure_started(self) -> subprocess.Popen:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        self._proc = self._popen_factory(
            list(self.spec.command),
            cwd=self.spec.cwd,
            env=self.spec.popen_env(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self._stderr_tail = []
        self._stderr_thread = threading.Thread(target=self._read_stderr, args=(self._proc,), daemon=True)
        self._stderr_thread.start()
        return self._proc

    def _read_stderr(self, proc: subprocess.Popen) -> None:
        stderr = proc.stderr
        if stderr is None:
            return
        for line in stderr:
            self._stderr_tail.append(line)
            if len(self._stderr_tail) > 100:
                del self._stderr_tail[:50]

    def _write_message(self, proc: subprocess.Popen, message: dict[str, Any]) -> None:
        if proc.stdin is None:
            raise RuntimeError("sidecar stdin is not available")
        proc.stdin.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
        proc.stdin.flush()

    def _read_response(self, proc: subprocess.Popen, request_id: str) -> dict[str, Any]:
        if proc.stdout is None:
            raise RuntimeError("sidecar stdout is not available")
        while True:
            line = proc.stdout.readline()
            if line == "":
                raise RuntimeError(
                    "sidecar process exited before returning a response. "
                    f"returncode={proc.poll()}; stderr_tail={self.stderr_tail()}"
                )
            try:
                response = json.loads(line)
            except json.JSONDecodeError:
                continue
            if response.get("request_id") == request_id:
                return response


class SidecarRuntimePool:
    """Per-worker cache of persistent sidecar clients."""

    def __init__(self, *, popen_factory: Any = subprocess.Popen):
        self._popen_factory = popen_factory
        self._clients: dict[SidecarProcessSpec, JsonlSidecarClient] = {}

    def request(self, spec: SidecarProcessSpec, task: str, payload: dict[str, Any]) -> Any:
        client = self._clients.get(spec)
        if client is None:
            client = JsonlSidecarClient(spec, popen_factory=self._popen_factory)
            self._clients[spec] = client
        return client.request(task, payload)

    def close_all(self) -> None:
        clients = list(self._clients.values())
        self._clients.clear()
        for client in clients:
            client.close()

    def __enter__(self) -> "SidecarRuntimePool":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.close_all()
        return False
