from __future__ import annotations

import threading
import traceback
from collections.abc import Callable, MutableMapping
from contextlib import contextmanager
from typing import Any


STREAMLIT_LOG_METHODS = ("write", "error", "success", "info", "warning")


def streamlit_log_message(method_name: str, args: tuple[Any, ...]) -> str:
    if method_name == "write":
        return " ".join(str(item) for item in args)
    return str(args[0]) if args else ""


@contextmanager
def patch_streamlit_thread_log(st: Any, log: list[tuple[str, str]], thread_id: int | None = None):
    active_thread_id = threading.get_ident() if thread_id is None else thread_id
    originals = {name: getattr(st, name) for name in STREAMLIT_LOG_METHODS}

    def make_wrapper(name: str):
        original = originals[name]

        def wrapper(*args, **kwargs):
            if threading.get_ident() == active_thread_id:
                log.append((name, streamlit_log_message(name, args)))
                return None
            return original(*args, **kwargs)

        return wrapper

    for method_name in STREAMLIT_LOG_METHODS:
        setattr(st, method_name, make_wrapper(method_name))

    try:
        yield
    finally:
        for method_name, original in originals.items():
            setattr(st, method_name, original)


def run_proc_body_with_streamlit_log(
    *,
    st: Any,
    ctx: MutableMapping[str, Any],
    cancel: Any,
    output_dir: str,
    proc_body: Callable[[MutableMapping[str, Any], Any, str], Any],
) -> None:
    log = ctx.setdefault("log", [])
    with patch_streamlit_thread_log(st, log):
        try:
            proc_body(ctx, cancel, output_dir)
            if ctx["status"] == "running":
                ctx["status"] = "done"
        except Exception as exc:
            ctx["status"] = "error"
            log.append(("error", f"处理异常: {exc}"))
            log.append(("error", traceback.format_exc()))
