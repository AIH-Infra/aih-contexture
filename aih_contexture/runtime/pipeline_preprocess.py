from __future__ import annotations

import base64
import json
import math
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz

from aih_contexture.logger import get_logger
from aih_contexture.scripts.ui.pipeline_subprocess import pipeline_python_executable

logger = get_logger()

_POLL_INTERVAL_SECONDS = 0.2
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass(slots=True)
class PipelinePreprocessResult:
    effective_file_path: str
    backend: str = "none"
    cleanup_dir: str | None = None
    exported_artifact_path: str | None = None


@dataclass(slots=True)
class _ChromeChunkJob:
    chunk_index: int
    start_page: int
    end_page: int
    input_pdf: Path
    output_pdf: Path
    progress_json: Path
    result_json: Path
    process: subprocess.Popen[str] | None = None
    stdout: str = ""
    stderr: str = ""

    @property
    def page_count(self) -> int:
        return (self.end_page - self.start_page) + 1


def normalize_ocr_preprocess_backend(value: Any) -> str:
    normalized = str(value or "none").strip().lower().replace("-", "_")
    if normalized in {"chrome_screenai", "chrome_searchable_pdf", "screenai_searchable_pdf"}:
        return "chrome_screenai_searchable_pdf"
    if normalized in {"", "none", "off", "disabled"}:
        return "none"
    return normalized


def apply_pipeline_pdf_preprocess(
    *,
    file_path: str,
    output_dir: str,
    fname_base: str,
    config: dict[str, Any],
) -> PipelinePreprocessResult:
    backend = normalize_ocr_preprocess_backend(config.get("ocr_preprocess_backend"))
    selected_ocr_backend = str(config.get("ocr_backend") or "").strip().lower().replace("-", "_")
    if backend == "none" and selected_ocr_backend == "chrome_screenai":
        backend = "chrome_screenai_searchable_pdf"
    if backend == "none":
        return PipelinePreprocessResult(effective_file_path=file_path)
    if backend != "chrome_screenai_searchable_pdf":
        raise ValueError(f"Unsupported OCR preprocess backend: {backend}")

    work_dir = Path(tempfile.mkdtemp(prefix=f"{fname_base}.chrome_screenai.", dir=output_dir))
    source_path = Path(file_path)
    staged_input = work_dir / source_path.name
    try:
        shutil.copy2(source_path, staged_input)

        merged_searchable_pdf = _run_chrome_screenai_searchable_pdf_pipeline(
            staged_input=staged_input,
            work_dir=work_dir,
            fname_base=fname_base,
            config=config,
        )

        exported_artifact_path = None
        if bool(config.get("chrome_emit_searchable_pdf", False)):
            export_path = Path(output_dir) / f"{fname_base}_screenai_searchable.pdf"
            shutil.copy2(merged_searchable_pdf, export_path)
            exported_artifact_path = str(export_path)

        logger.info(
            "[pipeline-preprocess] backend=%s source=%s searchable_pdf=%s",
            backend,
            file_path,
            merged_searchable_pdf,
        )
        return PipelinePreprocessResult(
            effective_file_path=str(merged_searchable_pdf),
            backend=backend,
            cleanup_dir=str(work_dir),
            exported_artifact_path=exported_artifact_path,
        )
    except Exception:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise


def cleanup_pipeline_preprocess(result: PipelinePreprocessResult | None) -> None:
    if result is None or not result.cleanup_dir:
        return
    try:
        shutil.rmtree(result.cleanup_dir, ignore_errors=True)
    except Exception:
        logger.exception("[pipeline-preprocess] Failed to clean temporary directory: %s", result.cleanup_dir)


def _run_chrome_screenai_searchable_pdf_pipeline(
    *,
    staged_input: Path,
    work_dir: Path,
    fname_base: str,
    config: dict[str, Any],
) -> Path:
    with fitz.open(staged_input) as doc:
        page_count = doc.page_count

    if page_count <= 0:
        empty_output = work_dir / f"{fname_base}.chrome_screenai.searchable.pdf"
        shutil.copy2(staged_input, empty_output)
        return empty_output

    worker_count = max(1, min(int(config.get("chrome_workers", 2) or 2), page_count))
    chunk_jobs = _prepare_chrome_chunk_jobs(
        staged_input=staged_input,
        work_dir=work_dir,
        page_count=page_count,
        worker_count=worker_count,
    )
    _run_chrome_chunk_jobs(chunk_jobs, config=config)

    merged_output = work_dir / f"{fname_base}.chrome_screenai.searchable.pdf"
    _merge_chunk_pdfs([job.output_pdf for job in chunk_jobs], merged_output)
    return merged_output


def _prepare_chrome_chunk_jobs(
    *,
    staged_input: Path,
    work_dir: Path,
    page_count: int,
    worker_count: int,
) -> list[_ChromeChunkJob]:
    chunk_size = max(1, math.ceil(page_count / worker_count))
    jobs: list[_ChromeChunkJob] = []

    with fitz.open(staged_input) as source_doc:
        for chunk_index, start_page in enumerate(range(0, page_count, chunk_size)):
            end_page = min(page_count - 1, start_page + chunk_size - 1)
            chunk_input = work_dir / f"chunk_{chunk_index:03d}_input.pdf"
            subdoc = fitz.open()
            try:
                subdoc.insert_pdf(source_doc, from_page=start_page, to_page=end_page)
                subdoc.save(chunk_input, deflate=True)
            finally:
                subdoc.close()

            jobs.append(
                _ChromeChunkJob(
                    chunk_index=chunk_index,
                    start_page=start_page,
                    end_page=end_page,
                    input_pdf=chunk_input,
                    output_pdf=work_dir / f"chunk_{chunk_index:03d}_searchable.pdf",
                    progress_json=work_dir / f"chunk_{chunk_index:03d}_progress.json",
                    result_json=work_dir / f"chunk_{chunk_index:03d}_result.json",
                )
            )

    return jobs


def _run_chrome_chunk_jobs(
    jobs: list[_ChromeChunkJob],
    *,
    config: dict[str, Any],
) -> None:
    if not jobs:
        return

    repo_root = Path(__file__).resolve().parents[2]
    python_executable = pipeline_python_executable(repo_root)
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")

    for job in jobs:
        payload = {
            "input_pdf": str(job.input_pdf),
            "output_pdf": str(job.output_pdf),
            "progress_json": str(job.progress_json),
            "result_json": str(job.result_json),
            "model_dir": config.get("chrome_model_dir"),
            "light_mode": bool(config.get("chrome_screenai_light", False)),
            "preprocess_mode": str(config.get("chrome_preprocess_mode", "native")),
            "rasterize_dpi": max(72, int(config.get("chrome_rasterize_dpi", 144) or 144)),
            "page_count": job.page_count,
            "max_retries": 1,
        }
        token = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")
        command = [
            python_executable,
            "-m",
            "aih_contexture.scripts.chrome_screenai_chunk_worker",
            token,
        ]
        logger.info(
            "[Chrome ScreenAI] Processing chunk %s-%s/%s with %s worker(s)",
            job.start_page + 1,
            job.end_page + 1,
            jobs[-1].end_page + 1,
            len(jobs),
        )
        job.process = subprocess.Popen(
            command,
            cwd=os.fspath(repo_root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_CREATE_NO_WINDOW,
        )

    try:
        _wait_for_chrome_chunk_jobs(jobs)
    except Exception:
        _terminate_chrome_chunk_jobs(jobs)
        raise


def _wait_for_chrome_chunk_jobs(jobs: list[_ChromeChunkJob]) -> None:
    remaining = set(range(len(jobs)))
    last_logged_progress = -1
    while remaining:
        completed_pages = 0
        total_pages = 0
        for job in jobs:
            total_pages += job.page_count
            progress = _read_json_file(job.progress_json, default=None)
            if isinstance(progress, dict):
                completed_pages += max(0, min(int(progress.get("page_current", 0) or 0), job.page_count))
            elif job.chunk_index not in remaining:
                completed_pages += job.page_count
        if completed_pages != last_logged_progress:
            last_logged_progress = completed_pages
            logger.info("[Chrome ScreenAI] OCR progress %s/%s pages", completed_pages, total_pages)

        for index in list(remaining):
            job = jobs[index]
            proc = job.process
            if proc is None:
                raise RuntimeError(f"Chrome ScreenAI chunk process missing for chunk {job.chunk_index}")
            if proc.poll() is None:
                continue

            stdout, stderr = proc.communicate()
            job.stdout = stdout
            job.stderr = stderr
            if proc.returncode != 0:
                raise RuntimeError(_format_chrome_chunk_failure(job, f"exit code {proc.returncode}"))

            result = _read_json_file(job.result_json, default=None)
            if not isinstance(result, dict):
                raise RuntimeError(_format_chrome_chunk_failure(job, "missing result json"))
            if not result.get("ok"):
                error = str(result.get("error") or "unknown worker error")
                raise RuntimeError(_format_chrome_chunk_failure(job, error))
            if not job.output_pdf.is_file():
                raise RuntimeError(_format_chrome_chunk_failure(job, "searchable PDF not produced"))

            remaining.remove(index)
        if remaining:
            time.sleep(_POLL_INTERVAL_SECONDS)


def _terminate_chrome_chunk_jobs(jobs: list[_ChromeChunkJob]) -> None:
    for job in jobs:
        proc = job.process
        if proc is None or proc.poll() is not None:
            continue
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def _format_chrome_chunk_failure(job: _ChromeChunkJob, reason: str) -> str:
    message = (
        f"Chrome ScreenAI chunk {job.chunk_index} ({job.start_page + 1}-{job.end_page + 1}) failed: {reason}"
    )
    stdout = job.stdout.strip()
    stderr = job.stderr.strip()
    if stdout:
        message += f". STDOUT: {stdout}"
    if stderr:
        message += f". STDERR: {stderr}"
    return message


def _merge_chunk_pdfs(chunk_pdfs: list[Path], output_pdf: Path) -> None:
    output_doc = fitz.open()
    try:
        for chunk_pdf in chunk_pdfs:
            with fitz.open(chunk_pdf) as chunk_doc:
                output_doc.insert_pdf(chunk_doc)
        output_doc.save(output_pdf, deflate=True)
    finally:
        output_doc.close()


def _read_json_file(path: Path, *, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
