from __future__ import annotations

import json
import os
import sys
import time
from typing import Any


EVENT_PREFIX = "@@CONTEXTURE_EVENT@@ "
_EVENT_CONTEXT: dict[str, Any] = {}


def set_progress_context(**values: Any) -> None:
    _EVENT_CONTEXT.update({key: value for key, value in values.items() if value is not None})


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
    try:
        sys.stdout.write(EVENT_PREFIX + json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        sys.stdout.flush()
    except (OSError, ValueError):
        return
