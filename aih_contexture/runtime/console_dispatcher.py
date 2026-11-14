from __future__ import annotations

import threading
from collections import deque
from typing import Any, Callable, TextIO


RenderProgress = Callable[[TextIO, dict[str, Any]], None]
RenderLine = Callable[[TextIO, str], None]
RenderTerminalState = Callable[[TextIO], None]


class TextTailBuffer:
    def __init__(self, max_chars: int, max_line_chars: int = 65536):
        self.max_chars = max(1024, int(max_chars))
        self.max_line_chars = max(1024, int(max_line_chars))
        self._items: deque[str] = deque()
        self._size = 0
        self._truncated = False
        self._lock = threading.Lock()

    def append(self, text: str) -> None:
        if len(text) > self.max_line_chars:
            half = max(1, (self.max_line_chars - 32) // 2)
            text = text[:half] + "\n[... line truncated ...]\n" + text[-half:]
        with self._lock:
            self._items.append(text)
            self._size += len(text)
            while self._size > self.max_chars and self._items:
                self._size -= len(self._items.popleft())
                self._truncated = True

    def getvalue(self) -> str:
        with self._lock:
            prefix = "[... earlier subprocess output truncated ...]\n" if self._truncated else ""
            return prefix + "".join(self._items)

    @property
    def size(self) -> int:
        with self._lock:
            return self._size

    @property
    def truncated(self) -> bool:
        with self._lock:
            return self._truncated


class ConsoleDispatcher:
    """Serialize terminal rendering without allowing console I/O to block producers."""

    def __init__(
        self,
        *,
        render_progress: RenderProgress,
        render_line: RenderLine,
        render_clear: RenderTerminalState,
        render_finish: RenderTerminalState,
        max_normal_logs: int = 32,
        max_critical_logs: int = 32,
    ):
        self.render_progress = render_progress
        self.render_line = render_line
        self.render_clear = render_clear
        self.render_finish = render_finish
        self.max_normal_logs = max(1, int(max_normal_logs))
        self.max_critical_logs = max(1, int(max_critical_logs))

        self._condition = threading.Condition()
        self._normal_logs: deque[tuple[int, TextIO, str]] = deque()
        self._critical_logs: deque[tuple[int, TextIO, str]] = deque()
        self._latest_progress: tuple[int, TextIO, dict[str, Any]] | None = None
        self._clear_request: tuple[int, TextIO] | None = None
        self._finish_request: tuple[int, TextIO] | None = None
        self._generation = 0
        self._dropped_normal = 0
        self._thread = threading.Thread(
            target=self._run,
            name="contexture-console-writer",
            daemon=True,
        )
        self._thread.start()

    def begin_task(self, sink: TextIO) -> int:
        with self._condition:
            self._generation += 1
            generation = self._generation
            self._normal_logs.clear()
            self._critical_logs.clear()
            self._latest_progress = None
            self._finish_request = None
            self._dropped_normal = 0
            self._clear_request = (generation, sink)
            self._condition.notify()
            return generation

    def publish_progress(
        self,
        generation: int,
        sink: TextIO,
        event: dict[str, Any],
    ) -> None:
        with self._condition:
            if generation != self._generation:
                return
            self._latest_progress = (generation, sink, dict(event))
            self._condition.notify()

    def publish_line(
        self,
        generation: int,
        sink: TextIO,
        line: str,
        *,
        critical: bool = False,
    ) -> None:
        with self._condition:
            if generation != self._generation:
                return
            if critical:
                while len(self._critical_logs) >= self.max_critical_logs:
                    self._critical_logs.popleft()
                self._critical_logs.append((generation, sink, line))
            elif len(self._normal_logs) >= self.max_normal_logs:
                self._dropped_normal += 1
            else:
                self._normal_logs.append((generation, sink, line))
            self._condition.notify()

    def finish_task(self, generation: int, sink: TextIO) -> None:
        with self._condition:
            if generation != self._generation:
                return
            self._finish_request = (generation, sink)
            self._condition.notify()

    def current_generation(self) -> int:
        with self._condition:
            return self._generation

    def snapshot(self) -> dict[str, int | bool]:
        with self._condition:
            return {
                "generation": self._generation,
                "normal_logs": len(self._normal_logs),
                "critical_logs": len(self._critical_logs),
                "has_progress": self._latest_progress is not None,
                "dropped_normal": self._dropped_normal,
            }

    def _run(self) -> None:
        while True:
            item = self._next_item()
            if item is None:
                continue
            kind, generation, sink, payload = item
            if generation != self.current_generation():
                continue
            try:
                if kind == "clear":
                    self.render_clear(sink)
                elif kind == "critical" or kind == "normal":
                    self.render_line(sink, str(payload))
                elif kind == "suppressed":
                    self.render_line(
                        sink,
                        f"[Console output resumed; {int(payload)} routine display lines suppressed]\n",
                    )
                elif kind == "progress":
                    self.render_progress(sink, payload)
                elif kind == "finish":
                    self.render_finish(sink)
            except Exception:
                continue

    def _next_item(self) -> tuple[str, int, TextIO, Any] | None:
        with self._condition:
            while not self._has_pending_locked():
                self._condition.wait()
            if self._clear_request is not None:
                generation, sink = self._clear_request
                self._clear_request = None
                return "clear", generation, sink, None
            if self._critical_logs:
                generation, sink, line = self._critical_logs.popleft()
                return "critical", generation, sink, line
            if self._dropped_normal:
                dropped = self._dropped_normal
                self._dropped_normal = 0
                sink = self._sink_for_notice_locked()
                return "suppressed", self._generation, sink, dropped
            if self._normal_logs:
                generation, sink, line = self._normal_logs.popleft()
                return "normal", generation, sink, line
            if self._latest_progress is not None:
                generation, sink, event = self._latest_progress
                self._latest_progress = None
                return "progress", generation, sink, event
            if self._finish_request is not None:
                generation, sink = self._finish_request
                self._finish_request = None
                return "finish", generation, sink, None
            return None

    def _sink_for_notice_locked(self) -> TextIO:
        if self._normal_logs:
            return self._normal_logs[0][1]
        if self._latest_progress is not None:
            return self._latest_progress[1]
        if self._finish_request is not None:
            return self._finish_request[1]
        if self._clear_request is not None:
            return self._clear_request[1]
        raise RuntimeError("No console sink available")

    def _has_pending_locked(self) -> bool:
        return any(
            (
                self._clear_request is not None,
                bool(self._critical_logs),
                self._dropped_normal > 0,
                bool(self._normal_logs),
                self._latest_progress is not None,
                self._finish_request is not None,
            )
        )
