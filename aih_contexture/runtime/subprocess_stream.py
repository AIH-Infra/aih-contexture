from __future__ import annotations

import subprocess
import sys
import threading
import re
import os
import json
import shutil
import time
import psutil
from collections import deque
from collections.abc import Sequence
from typing import Any, Callable, TextIO

from aih_contexture.runtime.console_dispatcher import ConsoleDispatcher, TextTailBuffer
from aih_contexture.runtime.console_text import sanitize_console_text
from aih_contexture.runtime.progress_events import EVENT_PREFIX

_SINK_LOCK = threading.Lock()
_CONSOLE_PROGRESS_ACTIVE = False
_LATEST_EVENT: dict[str, Any] | None = None
_CONSOLE_DISPATCHER: ConsoleDispatcher | None = None
_CONSOLE_DISPATCHER_LOCK = threading.Lock()
_LOCAL_PROGRESS_GENERATION: int | None = None
_PROGRESS_RE = re.compile(
    r"^\s*.+?:\s*\d{1,3}%\|.*\|\s*\d+/\d+.*(?:it/s|s/it|<\d|,\s*\d)",
)
_PROGRESS_PARTS_RE = re.compile(
    r"^\s*(?P<label>.+?):\s*(?P<pct>\d{1,3})%\|.*\|\s*(?P<done>\d+)/(?P<total>\d+)(?P<tail>.*)$"
)


class _ProgressMetrics:
    """Add stable throughput and ETA metrics to real progress events."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._states: dict[int, dict[str, Any]] = {}

    def reset(self, generation: int) -> None:
        with self._lock:
            self._states = {
                generation: {
                    "started_at": time.monotonic(),
                    "scope": None,
                    "last_current": None,
                    "overall_current": 0,
                    "samples": deque(maxlen=16),
                }
            }

    def enrich(self, generation: int, event: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(event)
        if enriched.get("_formatted_text"):
            return enriched

        now = time.monotonic()
        with self._lock:
            state = self._states.setdefault(
                generation,
                {
                    "started_at": now,
                    "scope": None,
                    "last_current": None,
                    "overall_current": 0,
                    "samples": deque(maxlen=16),
                },
            )
            enriched.setdefault("elapsed_seconds", max(0.0, now - state["started_at"]))
            document_total = int(enriched.get("document_total_pages") or 0)
            if "current" not in enriched and document_total > 0:
                enriched["current"] = int(state.get("overall_current") or 0)
                enriched["total"] = document_total
                enriched["unit"] = "pages"
                enriched["absolute_progress"] = True
            if "current" not in enriched:
                return enriched

            try:
                current = int(enriched.get("current") or 0)
                total = int(enriched.get("total") or 0)
            except (TypeError, ValueError):
                return enriched

            unit = str(enriched.get("unit") or "items").strip() or "items"
            if (
                unit == "pages"
                and document_total > 0
                and not bool(enriched.get("absolute_progress"))
            ):
                current = int(enriched.get("batch_page_offset") or 0) + current
                total = document_total
                current = max(current, int(state.get("overall_current") or 0))
                enriched["current"] = current
                enriched["total"] = total
            if unit == "pages":
                state["overall_current"] = max(
                    int(state.get("overall_current") or 0),
                    current,
                )
            terminal_stage = str(enriched.get("stage") or "").strip().lower()
            terminal_kind = str(enriched.get("kind") or "").strip().lower()
            total_elapsed = float(enriched.get("elapsed_seconds") or 0.0)
            if (
                current > 0
                and total_elapsed > 0
                and (
                    terminal_stage in {"completed", "failed", "cancelled"}
                    or terminal_kind in {"file_completed", "file_failed", "file_cancelled"}
                )
            ):
                enriched["average_rate_per_second"] = current / total_elapsed
            scope = str(enriched.get("rate_scope") or enriched.get("stage") or unit)
            last_current = state.get("last_current")
            if state.get("scope") != scope or (
                last_current is not None and current < int(last_current)
            ):
                state["scope"] = scope
                state["samples"] = deque(maxlen=16)

            samples: deque[tuple[float, int]] = state["samples"]
            if not samples or samples[-1][1] != current:
                samples.append((now, current))
            state["last_current"] = current

            cutoff = now - 30.0
            while len(samples) > 2 and samples[1][0] < cutoff:
                samples.popleft()
            if len(samples) < 2:
                return enriched

            elapsed = samples[-1][0] - samples[0][0]
            completed = samples[-1][1] - samples[0][1]
            if elapsed <= 0.05 or completed <= 0:
                return enriched

            rate = completed / elapsed
            enriched["rate_per_second"] = rate
            enriched["unit"] = unit
            if total > current and rate > 0:
                enriched["eta_seconds"] = (total - current) / rate
            return enriched


_PROGRESS_METRICS = _ProgressMetrics()


class _ProgressWatchdog:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_progress_at = time.monotonic()
        self._last_signature: tuple[Any, ...] | None = None
        self._last_event: dict[str, Any] | None = None

    def observe(self, event: dict[str, Any]) -> None:
        signature = (
            event.get("kind"),
            event.get("stage"),
            event.get("current"),
            event.get("total"),
            event.get("batch_index"),
        )
        with self._lock:
            if signature != self._last_signature:
                self._last_signature = signature
                self._last_progress_at = time.monotonic()
                self._last_event = dict(event)

    def snapshot(self) -> tuple[float, dict[str, Any] | None]:
        with self._lock:
            stalled_for = max(0.0, time.monotonic() - self._last_progress_at)
            event = dict(self._last_event) if self._last_event is not None else None
            return stalled_for, event


def run_streaming_subprocess(
    cmd: Sequence[str],
    *,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    timeout: int | float | None = None,
    progress_timeout: int | float | None = None,
    prefix: str | None = None,
    event_callback: Callable[[dict[str, Any]], None] | None = None,
) -> subprocess.CompletedProcess:
    """Run a subprocess while teeing stdout/stderr to the current console."""

    global _LATEST_EVENT, _LOCAL_PROGRESS_GENERATION
    _LATEST_EVENT = None
    _LOCAL_PROGRESS_GENERATION = None
    async_console = _async_console_enabled()
    dispatcher = _console_dispatcher() if async_console else None
    generation = dispatcher.begin_task(sys.stdout) if dispatcher is not None else 0
    _PROGRESS_METRICS.reset(generation)
    if prefix:
        prefix_line = f"{prefix} {' '.join(str(part) for part in cmd)}\n"
        if dispatcher is not None:
            dispatcher.publish_line(generation, sys.stdout, prefix_line)
        else:
            _write_normal_line(sys.stdout, prefix_line)
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
    stdout_chunks = TextTailBuffer(_tail_limit_chars("CONTEXTURE_STDOUT_TAIL_MB", 2))
    stderr_chunks = TextTailBuffer(_tail_limit_chars("CONTEXTURE_STDERR_TAIL_MB", 4))
    progress_watchdog = _ProgressWatchdog()

    stdout_thread = threading.Thread(
        target=_tee_pipe,
        args=(
            proc.stdout,
            sys.stdout,
            stdout_chunks,
            event_callback,
            dispatcher,
            generation,
            progress_watchdog,
        ),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_tee_pipe,
        args=(
            proc.stderr,
            sys.stderr,
            stderr_chunks,
            event_callback,
            dispatcher,
            generation,
            progress_watchdog,
        ),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    started_at = time.monotonic()
    stalled = False
    stalled_for = 0.0
    last_progress_event: dict[str, Any] | None = None
    timed_out = False
    while True:
        polled = proc.poll()
        if polled is not None:
            returncode = polled
            break
        now = time.monotonic()
        if timeout is not None and now - started_at >= float(timeout):
            timed_out = True
            _terminate_process_tree(proc)
            returncode = _wait_for_terminated_process(proc)
            break
        if progress_timeout is not None and float(progress_timeout) > 0:
            stalled_for, last_progress_event = progress_watchdog.snapshot()
            if stalled_for >= float(progress_timeout):
                stalled = True
                stall_message = _format_stall_message(stalled_for, last_progress_event)
                stderr_chunks.append(stall_message)
                if dispatcher is not None:
                    dispatcher.publish_line(
                        generation,
                        sys.stderr,
                        stall_message,
                        critical=True,
                    )
                else:
                    _write_normal_line(sys.stderr, stall_message)
                _terminate_process_tree(proc)
                returncode = _wait_for_terminated_process(proc)
                break
        time.sleep(0.25)

    join_timeout = 5 if stalled or timed_out else None
    stdout_thread.join(timeout=join_timeout)
    stderr_thread.join(timeout=join_timeout)
    if timed_out:
        raise subprocess.TimeoutExpired(list(cmd), timeout)
    if dispatcher is not None:
        dispatcher.finish_task(generation, sys.stdout)
    else:
        _commit_progress_line(sys.stdout)
        _LATEST_EVENT = None
    completed = subprocess.CompletedProcess(
        list(cmd),
        returncode,
        stdout=stdout_chunks.getvalue(),
        stderr=stderr_chunks.getvalue(),
    )
    completed.stalled = stalled
    completed.stalled_for = stalled_for if stalled else 0.0
    completed.last_progress_event = last_progress_event if stalled else None
    return completed


def _tee_pipe(
    pipe: TextIO | None,
    sink: TextIO,
    chunks: TextTailBuffer,
    event_callback: Callable[[dict[str, Any]], None] | None = None,
    dispatcher: ConsoleDispatcher | None = None,
    generation: int = 0,
    progress_watchdog: _ProgressWatchdog | None = None,
) -> None:
    global _LATEST_EVENT
    if pipe is None:
        return
    compact_progress = _compact_subprocess_progress_enabled()
    try:
        for line in iter(pipe.readline, ""):
            event = _parse_event_line(line)
            if event is not None:
                if progress_watchdog is not None:
                    progress_watchdog.observe(event)
                _publish_progress(dispatcher, generation, sink, event)
                if event_callback is not None:
                    try:
                        event_callback(event)
                    except Exception:
                        pass
                continue
            chunks.append(line)
            if compact_progress and _is_progress_line(line):
                if dispatcher is not None:
                    raw_event = {
                        "_formatted_text": _format_progress_line_for_console(line, sink),
                    }
                    _publish_progress(dispatcher, generation, sink, raw_event)
                else:
                    _write_progress_line(sink, line)
                continue

            if dispatcher is not None:
                dispatcher.publish_line(
                    generation,
                    sink,
                    sanitize_console_text(line),
                    critical=_is_critical_console_line(line),
                )
            else:
                _write_normal_line(sink, sanitize_console_text(line))
    finally:
        pipe.close()


def _format_stall_message(
    stalled_for: float,
    last_event: dict[str, Any] | None,
) -> str:
    detail = "no structured progress event received"
    if last_event:
        stage = str(last_event.get("stage") or "unknown")
        current = int(last_event.get("current") or 0)
        total = int(last_event.get("total") or 0)
        batch_index = int(last_event.get("batch_index") or 0)
        total_batches = int(last_event.get("total_batches") or 0)
        detail = f"last stage={stage}"
        if total > 0:
            detail += f", progress={current}/{total}"
        if batch_index and total_batches:
            detail += f", batch={batch_index}/{total_batches}"
    return (
        f"[WARN] Worker stalled for {int(stalled_for)}s ({detail}); "
        "terminating its process tree and continuing with the next file.\n"
    )


def _terminate_process_tree(proc: subprocess.Popen, grace_seconds: float = 3.0) -> None:
    processes: list[psutil.Process] = []
    try:
        parent = psutil.Process(proc.pid)
        processes.extend(parent.children(recursive=True))
        processes.append(parent)
    except (psutil.Error, OSError):
        processes = []

    termination_order = list(reversed(processes[:-1])) + processes[-1:] if processes else []
    for process in termination_order:
        try:
            process.terminate()
        except (psutil.Error, OSError):
            pass
    if processes:
        _, alive = psutil.wait_procs(processes, timeout=max(0.1, grace_seconds))
        for process in alive:
            try:
                process.kill()
            except (psutil.Error, OSError):
                pass
        if alive:
            psutil.wait_procs(alive, timeout=max(0.1, grace_seconds))

    if proc.poll() is None:
        try:
            proc.kill()
        except (OSError, ProcessLookupError):
            pass


def _wait_for_terminated_process(proc: subprocess.Popen) -> int:
    try:
        return proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except (OSError, ProcessLookupError):
            pass
        try:
            return proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            return -9


def _parse_event_line(line: str) -> dict[str, Any] | None:
    text = line.strip()
    if not text.startswith(EVENT_PREFIX):
        return None
    try:
        payload = json.loads(text[len(EVENT_PREFIX):])
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _update_structured_progress(event: dict[str, Any], sink: TextIO) -> None:
    global _LATEST_EVENT
    _LATEST_EVENT = dict(event)
    _write_console_progress_text(sink, _format_structured_event(_LATEST_EVENT))


def _format_structured_event(event: dict[str, Any]) -> str:
    if event.get("_formatted_text"):
        return str(event["_formatted_text"])
    current = int(event.get("current") or 0)
    total = int(event.get("total") or 0)
    percent = max(0, min(100, int(round(current * 100 / total)))) if total > 0 else 0
    stage_labels = {
        "starting": "Starting",
        "model_loading": "Loading models",
        "preprocess": "Preprocessing",
        "batch": "Document batch",
        "document": "Building pages",
        "layout": "Layout",
        "line_detection": "Line detection",
        "ocr": "OCR",
        "postprocess": "Postprocessing",
        "render": "Rendering",
        "saving": "Saving",
        "completed": "Completed",
    }
    stage_key = str(event.get("stage") or "")
    stage = stage_labels.get(stage_key, stage_key or "Processing")
    message = str(event.get("message") or "").strip()
    elapsed = event.get("elapsed_seconds")
    bar = _progress_bar(percent, sys.stdout)
    count = f" {current}/{total}" if total > 0 else ""
    batch_index = int(event.get("batch_index") or 0)
    total_batches = int(event.get("total_batches") or 0)
    batch = f" | Batch {batch_index}/{total_batches}" if total_batches and batch_index else ""
    mode_label = str(event.get("mode_label") or "Pipeline")
    metrics = []
    average_rate = event.get("average_rate_per_second")
    rate = event.get("rate_per_second")
    if average_rate is not None:
        metrics.append(
            "avg " + _format_rate(float(average_rate), str(event.get("unit") or "items"))
        )
    elif rate is not None:
        metrics.append(_format_rate(float(rate), str(event.get("unit") or "items")))
    eta = event.get("eta_seconds")
    if eta is not None:
        metrics.append(f"ETA {_format_duration(float(eta))}")
    if elapsed is not None:
        metrics.append(_format_duration(float(elapsed)))
    metrics_text = " | ".join(metrics)
    tail = f" | {metrics_text}" if metrics_text else ""
    message_text = f" | {message}" if message else ""
    return f"{mode_label} {bar} {percent:3d}%{count} | {stage}{batch}{tail}{message_text}"


def render_terminal_progress(
    *,
    mode_label: str,
    stage: str,
    message: str,
    current: int = 0,
    total: int = 0,
    unit: str = "items",
    rate_scope: str | None = None,
) -> None:
    event = {
        "mode_label": mode_label,
        "stage": stage,
        "message": message,
        "current": int(current),
        "total": int(total),
        "unit": unit,
        "rate_scope": rate_scope,
    }
    global _LOCAL_PROGRESS_GENERATION, _LATEST_EVENT
    if _async_console_enabled():
        dispatcher = _console_dispatcher()
        if (
            _LOCAL_PROGRESS_GENERATION is None
            or _LOCAL_PROGRESS_GENERATION != dispatcher.current_generation()
        ):
            _LOCAL_PROGRESS_GENERATION = dispatcher.begin_task(sys.stdout)
            _PROGRESS_METRICS.reset(_LOCAL_PROGRESS_GENERATION)
        _publish_progress(dispatcher, _LOCAL_PROGRESS_GENERATION, sys.stdout, event)
    else:
        if _LOCAL_PROGRESS_GENERATION is None:
            _LOCAL_PROGRESS_GENERATION = 0
            _PROGRESS_METRICS.reset(0)
        _publish_progress(None, 0, sys.stdout, event)


def finish_terminal_progress() -> None:
    global _LATEST_EVENT, _LOCAL_PROGRESS_GENERATION
    if _async_console_enabled() and _LOCAL_PROGRESS_GENERATION is not None:
        _console_dispatcher().finish_task(_LOCAL_PROGRESS_GENERATION, sys.stdout)
        _LOCAL_PROGRESS_GENERATION = None
    else:
        _commit_progress_line(sys.stdout)
        _LATEST_EVENT = None
        _LOCAL_PROGRESS_GENERATION = None


def _publish_progress(
    dispatcher: ConsoleDispatcher | None,
    generation: int,
    sink: TextIO,
    event: dict[str, Any],
) -> None:
    global _LATEST_EVENT
    event = _PROGRESS_METRICS.enrich(generation, event)
    _LATEST_EVENT = dict(event)
    if dispatcher is not None:
        dispatcher.publish_progress(generation, sink, event)
    else:
        _update_structured_progress(event, sink)


def _console_dispatcher() -> ConsoleDispatcher:
    global _CONSOLE_DISPATCHER
    if _CONSOLE_DISPATCHER is None:
        with _CONSOLE_DISPATCHER_LOCK:
            if _CONSOLE_DISPATCHER is None:
                _CONSOLE_DISPATCHER = ConsoleDispatcher(
                    render_progress=lambda sink, event: _write_console_progress_text(
                        sink, _format_structured_event(event)
                    ),
                    render_line=_write_normal_line,
                    render_clear=_finish_progress_line,
                    render_finish=_commit_progress_line,
                    max_normal_logs=_env_int("CONTEXTURE_CONSOLE_NORMAL_LOGS", 32),
                    max_critical_logs=_env_int("CONTEXTURE_CONSOLE_CRITICAL_LOGS", 32),
                )
    return _CONSOLE_DISPATCHER


def _async_console_enabled() -> bool:
    value = os.environ.get("CONTEXTURE_ASYNC_CONSOLE", "1")
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


def _tail_limit_chars(name: str, default_mb: int) -> int:
    return _env_int(name, default_mb) * 1024 * 1024


def _is_critical_console_line(line: str) -> bool:
    lowered = line.lower()
    return any(
        marker in lowered
        for marker in (
            "error",
            "warning",
            "traceback",
            "exception",
            "cuda",
            "failed",
            "fatal",
        )
    )


def _safe_write(sink: TextIO, text: str) -> bool:
    try:
        sink.write(text)
    except (OSError, ValueError):
        return False
    return True


def _safe_flush(sink: TextIO) -> bool:
    try:
        sink.flush()
    except (OSError, ValueError):
        return False
    return True


def _compact_subprocess_progress_enabled() -> bool:
    value = os.environ.get("CONTEXTURE_COMPACT_SUBPROCESS_PROGRESS", "true")
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _is_progress_line(line: str) -> bool:
    text = line.replace("\r", "").strip()
    if not text:
        return False
    return bool(_PROGRESS_RE.match(text))


def _write_progress_line(sink: TextIO, line: str) -> None:
    text = _format_progress_line_for_console(line, sink)
    _write_console_progress_text(sink, text)


def _write_console_progress_text(sink: TextIO, text: str) -> None:
    global _CONSOLE_PROGRESS_ACTIVE
    if not text:
        return
    width = _terminal_width(sink)
    if width > 10 and len(text) >= width:
        text = text[: max(1, width - 4)] + "..."
    padding = " " * max(0, width - len(text) - 1) if width > 0 else ""
    with _SINK_LOCK:
        if not _safe_write(sink, "\r" + text + padding):
            _CONSOLE_PROGRESS_ACTIVE = False
            return
        if not _safe_flush(sink):
            _CONSOLE_PROGRESS_ACTIVE = False
            return
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
    style = os.environ.get("CONTEXTURE_PROGRESS_STYLE", "solid").strip().lower()
    if style == "ascii":
        return "[" + ("=" * filled) + ("-" * (width - filled)) + "]"
    if style == "line" and _supports_console_text(sink, "━─"):
        return "[" + ("━" * filled) + ("─" * (width - filled)) + "]"
    if _supports_console_text(sink, "█"):
        return "[" + ("█" * filled) + (" " * (width - filled)) + "]"
    return "[" + ("=" * filled) + ("-" * (width - filled)) + "]"


def _best_bar_fill_char(sink: TextIO) -> str:
    encoding = getattr(sink, "encoding", None) or sys.stdout.encoding or "utf-8"
    try:
        "█".encode(encoding)
    except Exception:
        return "="
    return "█"


def _supports_console_text(sink: TextIO, text: str) -> bool:
    encoding = getattr(sink, "encoding", None) or sys.stdout.encoding or "utf-8"
    try:
        text.encode(encoding)
    except Exception:
        return False
    return True


def _format_progress_tail(tail: str) -> str:
    text = tail.strip()
    if not text:
        return ""
    bracket = re.search(r"\[[^\]]+\]", text)
    return f" {bracket.group(0)}" if bracket else ""


def _format_rate(rate: float, unit: str) -> str:
    if rate <= 0:
        return ""
    plural = unit if unit.endswith("s") else f"{unit}s"
    singular = plural[:-1] if plural.endswith("s") else plural
    if rate >= 10:
        return f"{rate:.1f} {plural}/s"
    if rate >= 1:
        return f"{rate:.2f} {plural}/s"
    return f"{1 / rate:.1f} s/{singular}"


def _format_duration(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def _strip_progress_bar_noise(text: str) -> str:
    return re.sub(r"\|[^|]*\|", "|...|", text)


def _write_normal_line(sink: TextIO, line: str) -> None:
    global _CONSOLE_PROGRESS_ACTIVE
    with _SINK_LOCK:
        if _CONSOLE_PROGRESS_ACTIVE:
            if not _clear_console_line(sink):
                _CONSOLE_PROGRESS_ACTIVE = False
                return
            _CONSOLE_PROGRESS_ACTIVE = False
        if not _safe_write(sink, line):
            return
        if _LATEST_EVENT is not None:
            text = _fit_progress_text(_format_structured_event(_LATEST_EVENT), sink)
            if _safe_write(sink, "\r" + text):
                _CONSOLE_PROGRESS_ACTIVE = True
        _safe_flush(sink)


def _finish_progress_line(sink: TextIO) -> None:
    global _CONSOLE_PROGRESS_ACTIVE
    with _SINK_LOCK:
        if _CONSOLE_PROGRESS_ACTIVE:
            if _clear_console_line(sink):
                _safe_flush(sink)
            _CONSOLE_PROGRESS_ACTIVE = False


def _commit_progress_line(sink: TextIO) -> None:
    global _CONSOLE_PROGRESS_ACTIVE
    with _SINK_LOCK:
        if not _CONSOLE_PROGRESS_ACTIVE:
            return
        if _safe_write(sink, "\n"):
            _safe_flush(sink)
        _CONSOLE_PROGRESS_ACTIVE = False


def _clear_console_line(sink: TextIO) -> bool:
    width = max(1, _terminal_width(sink))
    return _safe_write(sink, "\r" + (" " * max(1, width - 1)) + "\r")


def _fit_progress_text(text: str, sink: TextIO) -> str:
    width = _terminal_width(sink)
    if width > 10 and len(text) >= width:
        return text[: max(1, width - 4)] + "..."
    return text


def _terminal_width(sink: TextIO) -> int:
    try:
        explicit = int(getattr(sink, "columns", 0) or 0)
        if explicit > 0:
            return explicit
        return int(shutil.get_terminal_size(fallback=(120, 20)).columns)
    except Exception:
        return 120
