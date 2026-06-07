from __future__ import annotations

from collections.abc import Iterable, MutableMapping
from typing import Any


def initial_proc_context(
    *,
    status: str = "idle",
    ocr_paused: bool = False,
    ocr_pause_info: Any = None,
    ocr_resume_batch_start: int = 0,
) -> dict[str, Any]:
    return {
        "log": [],
        "progress": 0.0,
        "status": status,
        "last_zip_path": None,
        "last_zip_name": None,
        "processed_files": {},
        "ocr_paused": ocr_paused,
        "ocr_pause_info": ocr_pause_info,
        "ocr_resume_batch_start": ocr_resume_batch_start,
    }


def preread_uploaded_files(uploaded_files: Iterable[Any]) -> list[tuple[bytes, str]]:
    return [(file_obj.getvalue(), file_obj.name) for file_obj in uploaded_files]


def attach_preread_files(ctx: MutableMapping[str, Any], uploaded_files: Iterable[Any]) -> list[tuple[bytes, str]]:
    preread = preread_uploaded_files(uploaded_files)
    ctx["_preread_files"] = preread
    return preread


def sync_proc_context_to_session(ctx: MutableMapping[str, Any], session_state: MutableMapping[str, Any]) -> None:
    if ctx.get("last_zip_path"):
        session_state["last_zip_path"] = ctx["last_zip_path"]
        session_state["last_zip_name"] = ctx.get("last_zip_name")

    processed_files = session_state.setdefault("processed_files", {})
    for key, value in (ctx.get("processed_files") or {}).items():
        processed_files[key] = value

    if "ocr_paused" in ctx:
        session_state["ocr_paused"] = ctx.get("ocr_paused", False)
    if "ocr_pause_info" in ctx:
        session_state["ocr_pause_info"] = ctx.get("ocr_pause_info")
    if "ocr_resume_batch_start" in ctx:
        session_state["ocr_resume_batch_start"] = ctx.get("ocr_resume_batch_start", 0)
