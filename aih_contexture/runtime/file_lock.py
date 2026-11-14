"""Directory lock for state shared by threads, processes, and SMB clients."""

from __future__ import annotations

import json
import logging
import os
import socket
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, TypeVar

_T = TypeVar("_T")
_log = logging.getLogger(__name__)


def retry_windows_io(operation: Callable[[], _T], *, stage: str, timeout: float = 2.0) -> _T:
    """Retry Windows sharing/access races without hiding permanent failures.

    Only the individual filesystem operation is repeated. In particular, a
    counter increment is never recomputed. Non-Windows and unrelated errors
    propagate immediately; access denied can also be permanent and is bounded.
    """
    deadline = time.monotonic() + max(0.0, timeout)
    delay = 0.01
    attempts = 0
    while True:
        try:
            return operation()
        except OSError as exc:
            if getattr(exc, "winerror", None) not in {5, 32, 33}:
                raise
            attempts += 1
            if attempts == 1:
                _log.warning("Filesystem retry: stage=%s errno=%s winerror=%s", stage, exc.errno, exc.winerror)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                exc.add_note(f"stage={stage}; bounded Windows retries exhausted after {attempts} attempts")
                raise
            time.sleep(min(delay, remaining))
            delay = min(delay * 2, 0.1)


@contextmanager
def exclusive_file_lock(path: str | os.PathLike[str], *, timeout: float = 30.0) -> Iterator[None]:
    """Reserve a stable directory with an exclusive filesystem operation.

    Advisory flock is not sufficient on all SMB mounts. mkdir is coordinated
    by the filesystem server as well as local filesystems. A crashed process
    leaves its lock and owner record behind: never evict it by an arbitrary
    age, since another host could still be working. Time out with its location
    so recovery can check the recorded owner before removing the directory.
    """
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    while True:
        try:
            retry_windows_io(lambda: lock_path.mkdir(exist_ok=False), stage=f"lock mkdir {lock_path}",
                             timeout=min(2.0, max(0.0, deadline - time.monotonic())))
            break
        except FileExistsError as exc:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Timed out acquiring state lock: {lock_path}. "
                    "Check owner.json and remove the lock only after confirming its owner has stopped."
                ) from exc
            time.sleep(0.01)

    owner_path = lock_path / "owner.json"
    try:
        retry_windows_io(lambda: owner_path.write_text(
            json.dumps({"host": socket.gethostname(), "pid": os.getpid(), "created_at": time.time()}),
            encoding="utf-8",
        ), stage=f"lock owner write {owner_path}")
        yield
    finally:
        active_error = sys.exception()
        try:
            try:
                retry_windows_io(owner_path.unlink, stage=f"lock owner unlink {owner_path}")
            except FileNotFoundError:
                pass
            retry_windows_io(lock_path.rmdir, stage=f"lock rmdir {lock_path}")
        except OSError as cleanup_error:
            if active_error is None:
                raise
            active_error.add_note(f"Lock cleanup also failed at {lock_path}: {cleanup_error}")
