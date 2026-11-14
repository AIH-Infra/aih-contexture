from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Callable


EVENT_PREFIX = "@@CONTEXTURE_EVENT@@ "
_EVENT_CONTEXT: dict[str, Any] = {}
_EVENT_SINK: Callable[[dict[str, Any]], None] | None = None


def set_progress_sink(sink: Callable[[dict[str, Any]], None]) -> None:
    global _EVENT_SINK
    _EVENT_SINK = sink


def set_progress_context(**values: Any) -> None:
    _EVENT_CONTEXT.update({key: value for key, value in values.items() if value is not None})


def clear_progress_context() -> None:
    _EVENT_CONTEXT.clear()


def emit_progress_event(kind: str, stage: str, **payload: Any) -> None:
    enabled = os.environ.get("CONTEXTURE_PROGRESS_EVENTS", "0").strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        return
    event = {
        "schema_version": "1",
        "kind": kind,
        "stage": stage,
        "timestamp": time.time(),
        **_EVENT_CONTEXT,
        **{key: value for key, value in payload.items() if value is not None},
    }
    if _EVENT_SINK is not None:
        _EVENT_SINK(event)
        return
    try:
        sys.stdout.write(EVENT_PREFIX + json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        sys.stdout.flush()
    except (OSError, ValueError):
        return
