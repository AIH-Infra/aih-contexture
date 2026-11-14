"""Pause cyclic garbage collection for one Middle transaction.

A whole-book Middle holds millions of small dicts and lists. While a save or
re-render builds further copies, the cyclic collector repeatedly traverses
every live object, which measured at roughly 40% of save time on a 300-page
book. Reference counting still frees acyclic garbage immediately; any cycles
are collected after the outermost transaction ends. Results are unchanged.
"""
from __future__ import annotations

import functools
import gc
import threading
from contextlib import contextmanager

_lock = threading.Lock()
_depth = 0
_was_enabled = False


@contextmanager
def paused_gc():
    """Reentrant and thread-safe: collection resumes when the outermost exits."""
    global _depth, _was_enabled
    with _lock:
        if _depth == 0:
            _was_enabled = gc.isenabled()
            gc.disable()
        _depth += 1
    try:
        yield
    finally:
        with _lock:
            _depth -= 1
            if _depth == 0 and _was_enabled:
                gc.enable()


def with_paused_gc(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with paused_gc():
            return func(*args, **kwargs)
    return wrapper
