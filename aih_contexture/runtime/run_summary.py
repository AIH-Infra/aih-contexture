from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from aih_contexture.runtime.file_lock import exclusive_file_lock, retry_windows_io


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def allocate_processing_id(output_root: str | os.PathLike[str]) -> str:
    """Allocate a human-readable batch number scoped to an output root."""
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    counter = root / ".contexture_processing_counter"
    with exclusive_file_lock(root / ".contexture_processing_counter.lock"):
        try:
            raw = retry_windows_io(lambda: counter.read_text(encoding="ascii"), stage=f"counter read {counter}").strip()
        except FileNotFoundError:
            current = 0
        else:
            try:
                current = int(raw)
            except ValueError as exc:
                raise ValueError(f"Invalid processing counter: {counter}") from exc
            if current < 0:
                raise ValueError(f"Invalid processing counter: {counter}")
        value = current + 1
        fd, temp_name = tempfile.mkstemp(prefix=".contexture_counter.", suffix=".tmp", dir=root)
        try:
            with os.fdopen(fd, "w", encoding="ascii") as stream:
                stream.write(str(value))
                stream.flush()
                os.fsync(stream.fileno())
            retry_windows_io(lambda: os.replace(temp_name, counter), stage=f"counter replace {counter}")
        finally:
            active_error = sys.exception()
            try:
                retry_windows_io(lambda: os.unlink(temp_name), stage=f"counter temporary unlink {temp_name}")
            except FileNotFoundError:
                pass
            except OSError as cleanup_error:
                if active_error is None:
                    raise
                active_error.add_note(f"Counter temporary cleanup also failed: {cleanup_error}")
        return f"{value:04d}"


def ensure_processing_id(ctx: dict[str, Any], output_root: str | os.PathLike[str]) -> str:
    value = ctx.get("processing_id")
    if value is None:
        value = allocate_processing_id(output_root)
        ctx["processing_id"] = value
    return str(value)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in ("api_key", "token", "secret", "password")):
                result[str(key)] = "[REDACTED]"
            elif lowered.endswith("_path") or lowered in {"input_path", "output_dir", "source"}:
                result[str(key)] = os.path.basename(os.fspath(item)) if isinstance(item, (str, os.PathLike)) else item
            else:
                result[str(key)] = _redact(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def artifact_records(paths: Iterable[str | os.PathLike[str]], output_dir: str | os.PathLike[str]) -> list[dict[str, Any]]:
    root = Path(output_dir).resolve()
    records = []
    for raw in paths:
        if not raw:
            continue
        path = Path(os.fspath(raw))
        if not path.is_file():
            continue
        try:
            name = path.resolve().relative_to(root).as_posix()
        except ValueError:
            name = path.name
        lower = path.name.lower()
        if "middle" in lower:
            kind = "middle"
        elif "meta" in lower or lower == "run_summary.json":
            kind = "metadata"
        elif path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}:
            kind = "resource"
        elif path.suffix.lower() in {".md", ".html", ".json", ".xml"}:
            kind = "primary"
        else:
            kind = "auxiliary"
        records.append({"name": name, "format": path.suffix.lower().lstrip("."), "kind": kind, "size_bytes": path.stat().st_size})
    return sorted(records, key=lambda item: item["name"].lower())


def write_json(path: str | os.PathLike[str], payload: dict[str, Any]) -> str:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, destination)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return os.fspath(destination)


def write_document_summary(
    *,
    output_dir: str | os.PathLike[str],
    source_name: str,
    processing_id: str,
    file_index: int | None,
    mode: str,
    strategy: str | None,
    models: dict[str, Any],
    config: dict[str, Any] | None,
    started_at: str,
    finished_at: str | None,
    elapsed_seconds: float,
    status: str,
    page_count: int | None,
    output_paths: Iterable[str | os.PathLike[str]],
    warnings: Iterable[str] = (),
    errors: Iterable[str] = (),
    source_path: str | os.PathLike[str] | None = None,
    source_size_bytes: int | None = None,
    source_sha256: str | None = None,
    extra_result: Mapping[str, Any] | None = None,
) -> str:
    output_root = Path(output_dir)
    source_path_obj = Path(source_path) if source_path else None
    source_payload: dict[str, Any] = {"name": source_name, "extension": Path(source_name).suffix.lower()}
    if source_path_obj and source_path_obj.is_file():
        source_payload.update({"size_bytes": source_path_obj.stat().st_size, "sha256": _sha256(source_path_obj)})
    elif source_size_bytes is not None or source_sha256 is not None:
        # 上传等无落盘路径的输入：由调用方直接提供 size/SHA-256。
        if source_size_bytes is not None:
            source_payload["size_bytes"] = source_size_bytes
        if source_sha256 is not None:
            source_payload["sha256"] = source_sha256
    paths = list(output_paths)
    result_payload: dict[str, Any] = {"status": status, "page_count": page_count}
    if extra_result:
        result_payload.update(extra_result)
    summary = {
        "schema_version": "contexture-run-summary/1.0",
        "scope": "document",
        "processing_id": str(processing_id),
        "file_index": file_index,
        "source": _redact(source_payload),
        "execution": {"mode": mode, "strategy": strategy or mode, "models": _redact(models)},
        "configuration": _redact(config or {}),
        # 保留微秒级精度：round 到毫秒会把亚毫秒操作写成 0.0，与"禁止假耗时"契约冲突。
        "timing": {"started_at": started_at, "finished_at": finished_at or utc_now_iso(), "elapsed_seconds": round(float(elapsed_seconds), 6)},
        "result": result_payload,
        "artifacts": artifact_records(paths, output_root),
        "warnings": list(warnings),
        "errors": list(errors),
    }
    summary_path = output_root / "run_summary.json"
    write_json(summary_path, summary)
    return os.fspath(summary_path)


def _load_document_summary(path: str | os.PathLike[str]) -> dict[str, Any] | None:
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def batch_summary_payload(
    *,
    processing_id: str,
    mode: str,
    models: Mapping[str, Any] | None,
    config: Mapping[str, Any] | None,
    started_at: str,
    finished_at: str | None,
    document_summary_paths: Iterable[str | os.PathLike[str]],
    status: str = "succeeded",
    warnings: Iterable[str] = (),
    errors: Iterable[str] = (),
) -> dict[str, Any]:
    """Create the single root ``run_summary.json`` included in a ZIP.

    Document summaries remain only in their on-disk document folders.  The
    flat archive therefore carries one batch summary with a concise record for
    every document, rather than colliding ``run_summary.json`` filenames.
    """
    documents: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_path in document_summary_paths:
        if not raw_path:
            continue
        path = os.fspath(raw_path)
        normalized = os.path.normcase(os.path.abspath(path))
        if normalized in seen:
            continue
        seen.add(normalized)
        summary = _load_document_summary(path)
        if not summary:
            continue
        documents.append(
            {
                "file_index": summary.get("file_index"),
                "source": summary.get("source"),
                "processing_id": summary.get("processing_id"),
                "execution": summary.get("execution"),
                "timing": summary.get("timing"),
                "result": summary.get("result"),
                "artifacts": summary.get("artifacts", []),
                "warnings": summary.get("warnings", []),
                "errors": summary.get("errors", []),
            }
        )
    documents.sort(key=lambda item: (item.get("file_index") is None, item.get("file_index") or 0, str((item.get("source") or {}).get("name") or "")))
    return {
        "schema_version": "contexture-run-summary/1.0",
        "scope": "batch",
        "processing_id": str(processing_id),
        "execution": {"mode": mode, "models": _redact(dict(models or {}))},
        "configuration": _redact(dict(config or {})),
        "timing": {"started_at": started_at, "finished_at": finished_at or utc_now_iso()},
        "result": {
            "status": status,
            "document_count": len(documents),
            "succeeded_count": sum(1 for item in documents if (item.get("result") or {}).get("status") == "succeeded"),
            "failed_count": sum(1 for item in documents if (item.get("result") or {}).get("status") == "failed"),
        },
        "documents": documents,
        "warnings": list(warnings),
        "errors": list(errors),
    }
