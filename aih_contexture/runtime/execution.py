from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from aih_contexture.runtime.errors import ContextureCancelledError


ProgressCallback = Callable[[dict[str, Any]], None]
CancellationCheck = Callable[[], bool]


@dataclass(slots=True)
class ContextureExecutionContext:
    """Non-serializable controls and callbacks for one runtime execution."""

    progress_callback: ProgressCallback | None = None
    cancellation_check: CancellationCheck | None = None
    checkpoint_dir: str | None = None
    checkpoint_name: str | None = None

    def raise_if_cancelled(self) -> None:
        if self.cancellation_check is not None and self.cancellation_check():
            raise ContextureCancelledError("Contexture job was cancelled")

    def emit(self, event: dict[str, Any]) -> None:
        self.raise_if_cancelled()
        if self.progress_callback is not None:
            try:
                self.progress_callback(dict(event))
            except ContextureCancelledError:
                raise
            except Exception:
                # Progress reporting must not make an otherwise valid conversion fail.
                pass
        self.raise_if_cancelled()
