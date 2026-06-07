from __future__ import annotations

import subprocess
import sys
import threading
import re
import os
from collections.abc import Sequence
from typing import TextIO

_SINK_LOCK = threading.Lock()
_CONSOLE_PROGRESS_ACTIVE = False
_PROGRESS_RE = re.compile(
    r"^\s*.+?:\s*\d{1,3}%\|.*\|\s*\d+/\d+.*(?:it/s|s/it|<\d|,\s*\d)",
)
_PROGRESS_PARTS_RE = re.compile(
    r"^\s*(?P<label>.+?):\s*(?P<pct>\d{1,3})%\|.*\|\s*(?P<done>\d+)/(?P<total>\d+)(?P<tail>.*)$"
)


def run_streaming_subprocess(
    cmd: Sequence[str],
    *,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    timeout: int | float | None = None,
    prefix: str | None = None,
) -> subprocess.CompletedProcess:
    """Run a subprocess while teeing stdout/stderr to the current console."""

    if prefix:
        sys.stdout.write(f"{prefix} {' '.join(str(part) for part in cmd)}\n")
        sys.stdout.flush()

    proc = subprocess.Popen(
        list(cmd),
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    stdout_thread = threading.Thread(
        target=_tee_pipe,
        args=(proc.stdout, sys.stdout, stdout_chunks),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_tee_pipe,
        args=(proc.stderr, sys.stderr, stderr_chunks),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    try:
        returncode = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        returncode = proc.wait()
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)
        raise

    stdout_thread.join()
    stderr_thread.join()
    return subprocess.CompletedProcess(
        list(cmd),
        returncode,
        stdout="".join(stdout_chunks),
        stderr="".join(stderr_chunks),
    )


def _tee_pipe(pipe: TextIO | None, sink: TextIO, chunks: list[str]) -> None:
    if pipe is None:
        return
    compact_progress = _compact_subprocess_progress_enabled()
    try:
        for line in iter(pipe.readline, ""):
            chunks.append(line)
            if compact_progress and _is_progress_line(line):
                _write_progress_line(sink, line)
                continue

            _write_normal_line(sink, line)
    finally:
        _finish_progress_line(sink)
        pipe.close()


def _compact_subprocess_progress_enabled() -> bool:
    value = os.environ.get("CONTEXTURE_COMPACT_SUBPROCESS_PROGRESS", "true")
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _is_progress_line(line: str) -> bool:
    text = line.replace("\r", "").strip()
    if not text:
        return False
    return bool(_PROGRESS_RE.match(text))


def _write_progress_line(sink: TextIO, line: str) -> None:
    global _CONSOLE_PROGRESS_ACTIVE
    text = _format_progress_line_for_console(line, sink)
    if not text:
        return
    width = _terminal_width(sink)
    if width > 10 and len(text) >= width:
        text = text[: max(1, width - 4)] + "..."
    padding = " " * max(0, width - len(text) - 1) if width > 0 else ""
    with _SINK_LOCK:
        sink.write("\r" + text + padding)
        sink.flush()
        _CONSOLE_PROGRESS_ACTIVE = True


def _format_progress_line_for_console(line: str, sink: TextIO) -> str:
    text = line.replace("\r", "").replace("\n", "").strip()
    match = _PROGRESS_PARTS_RE.match(text)
    if not match:
        return _strip_progress_bar_noise(text)

    label = match.group("label").strip()
    pct = max(0, min(100, int(match.group("pct"))))
    done = int(match.group("done"))
    total = int(match.group("total"))
    tail = _format_progress_tail(match.group("tail"))
    bar = _progress_bar(pct, sink)
    return f"{label}: {bar} {pct:3d}% {done}/{total}{tail}"


def _progress_bar(percent: int, sink: TextIO, width: int = 30) -> str:
    filled = int(round(width * percent / 100))
    fill_char = _best_bar_fill_char(sink)
    if fill_char == "█":
        return "[" + (fill_char * filled) + (" " * (width - filled)) + "]"
    return "[" + ("=" * filled) + (" " * (width - filled)) + "]"


def _best_bar_fill_char(sink: TextIO) -> str:
    encoding = getattr(sink, "encoding", None) or sys.stdout.encoding or "utf-8"
    try:
        "█".encode(encoding)
    except Exception:
        return "="
    return "█"


def _format_progress_tail(tail: str) -> str:
    text = tail.strip()
    if not text:
        return ""
    bracket = re.search(r"\[[^\]]+\]", text)
    return f" {bracket.group(0)}" if bracket else ""


def _strip_progress_bar_noise(text: str) -> str:
    return re.sub(r"\|[^|]*\|", "|...|", text)


def _write_normal_line(sink: TextIO, line: str) -> None:
    global _CONSOLE_PROGRESS_ACTIVE
    with _SINK_LOCK:
        if _CONSOLE_PROGRESS_ACTIVE:
            sink.write("\n")
            _CONSOLE_PROGRESS_ACTIVE = False
        sink.write(line)
        sink.flush()


def _finish_progress_line(sink: TextIO) -> None:
    global _CONSOLE_PROGRESS_ACTIVE
    with _SINK_LOCK:
        if _CONSOLE_PROGRESS_ACTIVE:
            sink.write("\n")
            sink.flush()
            _CONSOLE_PROGRESS_ACTIVE = False


def _terminal_width(sink: TextIO) -> int:
    try:
        return int(getattr(sink, "columns", 0) or 0)
    except Exception:
        return 0
