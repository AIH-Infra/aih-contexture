from __future__ import annotations

from collections.abc import Iterable, MutableMapping
import os
from pathlib import Path
import shutil
import tempfile
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


def _safe_upload_suffix(file_name: str) -> str:
    suffix = Path(str(file_name or "")).suffix
    return suffix if suffix else ".pdf"


def stage_uploaded_files(uploaded_files: Iterable[Any], *, temp_dir: str | os.PathLike[str] | None = None) -> tuple[list[tuple[str, str]], str]:
    upload_temp_dir = os.fspath(temp_dir) if temp_dir is not None else tempfile.mkdtemp(prefix="aih_contexture_upload_")
    Path(upload_temp_dir).mkdir(parents=True, exist_ok=True)
    staged: list[tuple[str, str]] = []

    for idx, file_obj in enumerate(uploaded_files):
        file_name = str(getattr(file_obj, "name", f"upload_{idx:04d}.pdf"))
        suffix = _safe_upload_suffix(file_name)
        staged_path = Path(upload_temp_dir) / f"upload_{idx:04d}{suffix}"
        with open(staged_path, "wb") as f:
            f.write(file_obj.getvalue())
        staged.append((os.fspath(staged_path), file_name))

    return staged, upload_temp_dir


def attach_preread_files(ctx: MutableMapping[str, Any], uploaded_files: Iterable[Any]) -> list[tuple[str, str]]:
    cleanup_staged_uploads(ctx)
    staged, upload_temp_dir = stage_uploaded_files(uploaded_files)
    ctx["_staged_upload_files"] = staged
    ctx["_upload_temp_dir"] = upload_temp_dir
    ctx.pop("_preread_files", None)
    return staged


def cleanup_staged_uploads(ctx: MutableMapping[str, Any]) -> None:
    upload_temp_dir = ctx.pop("_upload_temp_dir", None)
    ctx.pop("_staged_upload_files", None)
    ctx.pop("_preread_files", None)
    if upload_temp_dir and os.path.isdir(os.fspath(upload_temp_dir)):
        shutil.rmtree(os.fspath(upload_temp_dir), ignore_errors=True)


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

    if ctx.get("status") in {"done", "cancelled", "error"} and not ctx.get("ocr_paused"):
        cleanup_staged_uploads(ctx)
