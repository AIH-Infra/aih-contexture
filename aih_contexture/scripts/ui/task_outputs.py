from __future__ import annotations

import os
import time
import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from aih_contexture.runtime.output_contract import document_output_basename, document_output_folder
from aih_contexture.runtime.run_summary import batch_summary_payload, utc_now_iso
from aih_contexture.scripts.ui.output_restore import output_file_records


def get_output_folder(
    output_root: str | os.PathLike[str],
    input_path_or_name: str,
    *,
    file_index: int | None = None,
) -> str:
    """Create an isolated timestamped folder for one input document."""
    # file_index is retained for caller compatibility; collision handling is
    # based on the timestamped folder itself.
    return document_output_folder(output_root, input_path_or_name)


def get_output_basename(input_path_or_name: str, start_page=None, end_page=None) -> str:
    return document_output_basename(input_path_or_name, start_page, end_page)

def build_zip(
    paths: Iterable[str | os.PathLike[str]],
    zip_path: str | os.PathLike[str],
    *,
    batch_summary: dict[str, Any] | None = None,
    rename_log: list[dict[str, str]] | None = None,
) -> str:
    """Create a flat download archive without extracted image resources.

    Per-document ``run_summary.json`` files are deliberately omitted because
    a flat archive cannot contain multiple files with that name.  The archive
    gets one root-level batch summary instead.

    ``rename_log`` (when provided) receives one record per archived file:
    ``{"source_artifact_name", "archive_name"}`` so batch summaries can stay
    consistent when flat-name collisions force ``__2`` style renames (P2-2).
    """
    zip_path_str = os.fspath(zip_path)
    parent = os.path.dirname(zip_path_str)
    if parent:
        os.makedirs(parent, exist_ok=True)

    last_error: PermissionError | None = None
    for attempt in range(3):
        try:
            return _write_zip(paths, zip_path_str, batch_summary=batch_summary, rename_log=rename_log)
        except PermissionError as exc:
            # Windows 上杀毒/索引/同步软件常短暂锁住新建文件，退避后重试。
            last_error = exc
            time.sleep(0.5 * (attempt + 1))
    fallback = _fallback_zip_path(zip_path_str)
    return _write_zip(paths, fallback, batch_summary=batch_summary, rename_log=rename_log)


def _fallback_zip_path(zip_path_str: str) -> str:
    """PermissionError 兜底：在同目录生成一个不冲突的新文件名。

    返回的路径一定尚不存在；极端情况下附加时间戳保证唯一。
    """
    path = Path(zip_path_str)
    for index in range(2, 100):
        candidate = path.with_name(f"{path.stem}__{index}{path.suffix}")
        if not candidate.exists():
            return os.fspath(candidate)
    return os.fspath(path.with_name(f"{path.stem}_{int(time.time())}{path.suffix}"))


def _archive_arcname(path: str, used: set[str]) -> str:
    candidate = Path(path).name
    if candidate not in used:
        used.add(candidate)
        return candidate
    stem = Path(candidate).stem
    suffix = Path(candidate).suffix
    index = 2
    while True:
        candidate = f"{stem}__{index}{suffix}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        index += 1


def _write_zip(
    paths: Iterable[str | os.PathLike[str]],
    zip_path_str: str,
    *,
    batch_summary: dict[str, Any] | None = None,
    rename_log: list[dict[str, str]] | None = None,
) -> str:
    used: set[str] = set()
    renames: list[dict[str, str]] = []
    with zipfile.ZipFile(zip_path_str, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in paths:
            if not path or not os.path.isfile(path):
                continue
            source = os.fspath(path)
            suffix = Path(source).suffix.lower()
            if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}:
                continue
            # Per-document summaries are represented by the root batch summary.
            if Path(source).name.lower() == "run_summary.json":
                continue
            arcname = _archive_arcname(source, used)
            if rename_log is not None:
                rename_log.append(
                    {
                        "source_artifact_name": Path(source).name,
                        "archive_name": arcname,
                    }
                )
            if arcname != Path(source).name:
                renames.append(
                    {
                        "source_artifact_name": Path(source).name,
                        "archive_name": arcname,
                    }
                )
            zf.write(source, arcname=arcname)
        if batch_summary is not None:
            if renames:
                # P2-2: 重命名记录必须在 ZIP 内的批次摘要里可见。
                batch_summary["archive_renames"] = renames
            summary_name = _archive_arcname("run_summary.json", used)
            zf.writestr(summary_name, json.dumps(batch_summary, ensure_ascii=False, indent=2) + "\n")
    return zip_path_str

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


def register_document_summary(ctx: dict[str, Any], summary_path: str | os.PathLike[str]) -> None:
    summaries = ctx.setdefault("document_summary_paths", [])
    path = os.fspath(summary_path)
    if path not in summaries:
        summaries.append(path)


def _discover_document_summaries(
    ctx: dict[str, Any],
    output_paths: Iterable[str | os.PathLike[str]],
) -> list[str]:
    # Session state can retain summary paths from a previous run even after
    # its output folder has been cleaned or replaced. Never let a stale path
    # make the current batch look successful.
    paths = [
        os.fspath(path)
        for path in (ctx.get("document_summary_paths") or [])
        if path and Path(os.fspath(path)).is_file()
    ]
    seen = {os.path.normcase(os.path.abspath(path)) for path in paths}
    for raw in output_paths:
        if not raw:
            continue
        candidate = Path(os.fspath(raw)).parent / "run_summary.json"
        key = os.path.normcase(os.path.abspath(candidate))
        if candidate.is_file() and key not in seen:
            paths.append(os.fspath(candidate))
            seen.add(key)
    return paths


def finalize_zip_outputs(
    ctx: dict,
    output_paths: Iterable[str | os.PathLike[str]],
    output_dir: str | os.PathLike[str],
    zip_name: str,
    *,
    mode: str | None = None,
    models: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    started_at: str | None = None,
    status: str | None = None,
) -> str | None:
    output_paths = list(output_paths)
    existing_paths = [
        os.fspath(path)
        for path in output_paths
        if path and os.path.exists(path)
    ]
    summary_paths = _discover_document_summaries(ctx, existing_paths)
    if output_paths and not existing_paths:
        # 调用方明明给了输出路径，磁盘上却一个都不存在：典型的 UI/worker
        # 路径分裂（相对路径 + 两个进程 cwd 不同），或输出被外部清理。
        # 此时绝不允许产出只有批次摘要的空壳 ZIP（2026-09-21 事故），
        # 必须把原因写进 ctx 让调用方呈现给用户，而不是无声消失。
        ctx.setdefault("errors", []).append(
            f"打包取消：{len(output_paths)} 个输出路径在磁盘上均不存在，未生成 ZIP。"
            "若任务刚处理完成，请检查启动方式造成的输出根目录差异；"
            "各文件的成果目录可能仍保留在磁盘上。"
        )
        return None
    if not existing_paths and not summary_paths:
        return None

    started = started_at or ctx.get("batch_started_at") or utc_now_iso()
    warnings = list(ctx.get("warnings") or [])
    errors = list(ctx.get("errors") or [])
    effective_status = str(status or ctx.get("status") or "succeeded")
    if existing_paths and not summary_paths:
        # P1-10: 有正式输出却找不到任何文档摘要时，禁止"成功 ZIP + 0 文档记录"。
        if effective_status == "succeeded":
            effective_status = "partial"
        warnings.append(
            f"{len(existing_paths)} 个输出文件缺少文档级 run_summary.json，"
            "批次摘要无法关联任何文档记录，状态已降级为 partial。"
        )
    batch_summary = batch_summary_payload(
        processing_id=str(ctx.get("processing_id") or "0000"),
        mode=str(mode or ctx.get("mode") or "unknown"),
        models=models or ctx.get("models") or {},
        config=config or ctx.get("config") or {},
        started_at=str(started),
        finished_at=utc_now_iso(),
        document_summary_paths=summary_paths,
        status=effective_status,
        warnings=warnings,
        errors=errors,
    )
    # Do not manufacture a downloadable ZIP whose only member would be an
    # empty batch summary. This happens when a stale Streamlit rerun leaves
    # no live document outputs or valid document summaries.
    # 注意：仅当连文档输出文件也没有时才拒写；有真实输出但缺文档摘要的
    # P1-10 场景必须照常出包（状态降级 partial），否则违背既有契约测试。
    if not existing_paths and int((batch_summary.get("result") or {}).get("document_count") or 0) == 0:
        return None
    rename_log: list[dict[str, str]] = []
    zip_path = build_zip(existing_paths, Path(output_dir) / zip_name, batch_summary=batch_summary, rename_log=rename_log)
    if Path(zip_path).name != Path(zip_name).name:
        # build_zip 的 PermissionError 兜底改了文件名，让调用方能感知。
        ctx.setdefault("warnings", []).append(
            f"ZIP 目标文件被占用，已改用备用文件名：{Path(zip_path).name}"
        )
    ctx["last_zip_path"] = zip_path
    ctx["last_zip_name"] = Path(zip_path).name
    ctx["batch_summary"] = batch_summary
    return zip_path

