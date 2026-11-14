"""Resumable, file-parallel embedded-text PDF to mirrored Markdown batch runner."""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import click

from aih_contexture.runtime.job import ContextureJob
from aih_contexture.runtime.runner import run_job


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass


def _relative_output_path(source: Path, input_root: Path, output_root: Path) -> Path:
    return output_root / source.relative_to(input_root).with_suffix(".md")


def _convert_one(
    source_text: str,
    input_root_text: str,
    output_root_text: str,
    *,
    overwrite: bool,
    hyphenation_repair: bool,
) -> dict[str, Any]:
    source = Path(source_text)
    input_root = Path(input_root_text)
    output_path = _relative_output_path(source, input_root, Path(output_root_text))
    relative_output = str(output_path.relative_to(Path(output_root_text)))
    started = time.perf_counter()
    source_stat = source.stat()
    if output_path.exists() and not overwrite:
        return {
            "status": "skipped_existing",
            "source": str(source),
            "output": relative_output,
            "source_size": source_stat.st_size,
            "source_mtime_ns": source_stat.st_mtime_ns,
            "elapsed_seconds": 0.0,
        }

    try:
        result = run_job(
            ContextureJob(
                input_path=str(source),
                input_name=source.name,
                mode="pipeline",
                output_formats=["markdown"],
                config={
                    "layout_backend": "none",
                    "ocr_backend": "none",
                    "disable_ocr": True,
                    "pdftext_workers": 1,
                    "text_layer_hyphenation_repair": hyphenation_repair,
                },
            )
        )
        _atomic_write_text(output_path, result.markdown or "")
        text_layer = (result.metadata or {}).get("text_layer") or {}
        return {
            "status": "completed",
            "source": str(source),
            "output": relative_output,
            "source_size": source_stat.st_size,
            "source_mtime_ns": source_stat.st_mtime_ns,
            "page_count": result.page_count,
            "markdown_characters": len(result.markdown or ""),
            "warnings": result.warnings,
            "text_layer": text_layer,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
    except Exception as exc:
        return {
            "status": "failed",
            "source": str(source),
            "output": relative_output,
            "source_size": source_stat.st_size,
            "source_mtime_ns": source_stat.st_mtime_ns,
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }


def _safe_console_text(value: object) -> str:
    """Avoid a non-UTF-8 Windows console stopping a long-running batch."""
    encoding = sys.stdout.encoding or "utf-8"
    return str(value).encode(encoding, errors="backslashreplace").decode(encoding)


def _pdf_sources(input_root: Path, scan_errors_path: Path) -> Iterator[Path]:
    """Yield PDFs deterministically while skipping unreadable NAS directories."""
    def report_scan_error(error: OSError) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "path": str(error.filename or ""),
            "error": f"{type(error).__name__}: {error}",
        }
        with scan_errors_path.open("a", encoding="utf-8") as error_file:
            error_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        click.echo(_safe_console_text(f"[scan warning] skipped unreadable directory: {error.filename}: {error}"), err=True)

    for directory, directory_names, file_names in os.walk(input_root, onerror=report_scan_error):
        directory_names.sort()
        for file_name in sorted(file_names):
            if file_name.lower().endswith(".pdf"):
                yield Path(directory) / file_name


def _manifest_sources(input_root: Path, source_manifest: Path) -> Iterator[Path]:
    """Yield PDF paths from a UTF-8 JSONL source manifest.

    This deliberately keeps enumeration separate from conversion.  It is used
    for SMB shares whose directory enumeration is unreliable while a native
    host (for example macOS) can still enumerate the same volume correctly.
    Every record must contain a relative_path field; absolute paths and parent
    traversal are rejected so the output mirror remains rooted at INPUT_ROOT.
    """
    with source_manifest.open("r", encoding="utf-8") as manifest_file:
        for line_number, line in enumerate(manifest_file, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                relative = Path(record["relative_path"])
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise click.UsageError(
                    f"Invalid source manifest record at line {line_number}: {exc}"
                ) from exc
            if relative.is_absolute() or ".." in relative.parts:
                raise click.UsageError(
                    f"Unsafe relative_path at line {line_number}: {relative}"
                )
            if relative.suffix.lower() != ".pdf":
                raise click.UsageError(
                    f"source manifest line {line_number} is not a PDF: {relative}"
                )
            yield input_root / relative


def _append_record(manifest, record: dict[str, Any], *, run_id: str) -> None:
    payload = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **record,
    }
    manifest.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    manifest.flush()


@click.command("contexture_text_layer_batch")
@click.argument("input_root", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("output_root", type=click.Path(file_okay=False, path_type=Path))
@click.option("--workers", type=click.IntRange(1, 16), default=8, show_default=True,
              help="Persistent file-worker processes. Each process completes one whole PDF before taking the next.")
@click.option("--limit", type=click.IntRange(1, None), default=None,
              help="Process at most this many PDFs; useful for a pilot run.")
@click.option("--overwrite", is_flag=True, default=False, help="Replace existing mirrored Markdown instead of skipping it.")
@click.option("--manifest", type=click.Path(dir_okay=False, path_type=Path), default=None,
              help="JSONL status manifest. Defaults to .contexture-text-layer-manifest.jsonl under OUTPUT_ROOT.")
@click.option("--source-manifest", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None,
              help="UTF-8 JSONL of native-enumerated PDF relative paths; bypasses local recursive scanning.")
@click.option("--no-hyphenation-repair", is_flag=True, default=False,
              help="Disable the conservative Latin end-of-line hyphen repair.")
def text_layer_batch_cli(
    input_root: Path,
    output_root: Path,
    workers: int,
    limit: int | None,
    overwrite: bool,
    manifest: Path | None,
    source_manifest: Path | None,
    no_hyphenation_repair: bool,
) -> None:
    """Mirror every INPUT_ROOT PDF as Markdown below OUTPUT_ROOT."""
    input_root = input_root.resolve()
    output_root = output_root.resolve()
    if output_root == input_root or input_root in output_root.parents:
        raise click.UsageError("OUTPUT_ROOT must not be INPUT_ROOT or a directory inside INPUT_ROOT.")
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest.resolve() if manifest is not None else output_root / ".contexture-text-layer-manifest.jsonl"
    scan_errors_path = output_root / ".contexture-text-layer-scan-errors.jsonl"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    sources = (
        _manifest_sources(input_root, source_manifest.resolve())
        if source_manifest is not None
        else _pdf_sources(input_root, scan_errors_path)
    )
    pending: dict[Any, Path] = {}
    submitted = completed = failed = skipped = 0
    started = time.perf_counter()

    with manifest_path.open("a", encoding="utf-8") as manifest_file:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            def submit_next() -> bool:
                nonlocal submitted
                if limit is not None and submitted >= limit:
                    return False
                try:
                    source = next(sources)
                except StopIteration:
                    return False
                future = pool.submit(
                    _convert_one,
                    str(source),
                    str(input_root),
                    str(output_root),
                    overwrite=overwrite,
                    hyphenation_repair=not no_hyphenation_repair,
                )
                pending[future] = source
                submitted += 1
                return True

            for _ in range(workers * 2):
                if not submit_next():
                    break
            while pending:
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    pending.pop(future)
                    record = future.result()
                    _append_record(manifest_file, record, run_id=run_id)
                    status = record["status"]
                    completed += status == "completed"
                    failed += status == "failed"
                    skipped += status == "skipped_existing"
                    click.echo(_safe_console_text(
                        f"[{submitted} submitted | {completed} done | {skipped} skipped | {failed} failed] "
                        f"{status}: {record['output']}"
                    ))
                    submit_next()

    elapsed = time.perf_counter() - started
    click.echo(json.dumps({
        "run_id": run_id,
        "submitted": submitted,
        "completed": completed,
        "skipped_existing": skipped,
        "failed": failed,
        "elapsed_seconds": round(elapsed, 3),
        "manifest": str(manifest_path),
    }, ensure_ascii=False))


if __name__ == "__main__":
    text_layer_batch_cli()
