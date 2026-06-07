from __future__ import annotations

import os
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from aih_contexture.scripts.ui.output_restore import output_file_records


def get_output_basename(input_path_or_name: str, start_page=None, end_page=None) -> str:
    stem = Path(input_path_or_name).stem
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if start_page is not None and end_page is not None:
        return f"{stem}_p{start_page}-{end_page}_{ts}"
    return f"{stem}_{ts}"


def build_zip(paths: Iterable[str | os.PathLike[str]], zip_path: str | os.PathLike[str]) -> str:
    zip_path_str = os.fspath(zip_path)
    parent = os.path.dirname(zip_path_str)
    if parent:
        os.makedirs(parent, exist_ok=True)

    try:
        return _write_zip(paths, zip_path_str)
    except PermissionError:
        fallback = _fallback_zip_path(zip_path_str)
        return _write_zip(paths, fallback)


def _write_zip(paths: Iterable[str | os.PathLike[str]], zip_path_str: str) -> str:
    with zipfile.ZipFile(zip_path_str, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in paths:
            if path and os.path.exists(path):
                zf.write(path, arcname=os.path.basename(os.fspath(path)))
    return zip_path_str


def _fallback_zip_path(zip_path_str: str) -> str:
    path = Path(zip_path_str)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return str(path.with_name(f"{path.stem}_{stamp}{path.suffix}"))


def record_processed_outputs(
    ctx: dict,
    result_key: str,
    output_files: Iterable[str | os.PathLike[str]],
) -> list[dict[str, str]]:
    records = output_file_records(output_files)
    ctx.setdefault("processed_files", {})[result_key] = records
    return records


def output_paths_from_records(records: Iterable[dict[str, Any]]) -> list[str]:
    return [
        os.fspath(record["path"])
        for record in records
        if record.get("path")
    ]


def record_worker_file_outputs(
    ctx: dict,
    result: dict[str, Any],
    fallback_result_key: str,
) -> tuple[str, list[dict[str, Any]]]:
    file_outputs = list(result.get("file_outputs") or [])
    result_key = result.get("result_key") or fallback_result_key
    ctx.setdefault("processed_files", {})[result_key] = file_outputs
    return result_key, file_outputs


def worker_elapsed_seconds(result: dict[str, Any], started_at: float, now: float | None = None) -> float:
    elapsed = result.get("elapsed_seconds")
    if elapsed is not None:
        return float(elapsed)
    return (time.time() if now is None else now) - started_at


def worker_error_details(result: dict[str, Any], default_error: str = "子进程处理失败") -> tuple[str, str]:
    error = result.get("error") or default_error
    details = result.get("traceback") or result.get("stderr") or result.get("stdout") or ""
    return str(error), str(details)


def finalize_zip_outputs(
    ctx: dict,
    output_paths: Iterable[str | os.PathLike[str]],
    output_dir: str | os.PathLike[str],
    zip_name: str,
) -> str | None:
    existing_paths = [
        os.fspath(path)
        for path in output_paths
        if path and os.path.exists(path)
    ]
    if not existing_paths:
        return None

    zip_path = build_zip(existing_paths, Path(output_dir) / zip_name)
    ctx["last_zip_path"] = zip_path
    ctx["last_zip_name"] = zip_name
    return zip_path
