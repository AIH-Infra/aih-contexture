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
from typing import Any, Sequence

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
    source_page_indices: tuple[int, ...]
    input_pdf: Path
    output_pdf: Path
    progress_json: Path
    result_json: Path
    process: subprocess.Popen[str] | None = None
    stdout: str = ""
    stderr: str = ""

    @property
    def page_count(self) -> int:
        return len(self.source_page_indices)

    @property
    def page_label(self) -> str:
        if all(
            right == left + 1
            for left, right in zip(self.source_page_indices, self.source_page_indices[1:])
        ):
            return f"{self.start_page + 1}-{self.end_page + 1}"
        return f"{self.page_count} selected pages from {self.start_page + 1} to {self.end_page + 1}"


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
    page_indices: Sequence[int] | None = None,
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
            page_indices=page_indices,
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
    page_indices: Sequence[int] | None = None,
) -> Path:
    with fitz.open(staged_input) as doc:
        page_count = doc.page_count

    if page_count <= 0:
        empty_output = work_dir / f"{fname_base}.chrome_screenai.searchable.pdf"
        shutil.copy2(staged_input, empty_output)
        return empty_output

    selected_pages = list(range(page_count)) if page_indices is None else sorted(set(int(index) for index in page_indices))
    invalid_pages = [index for index in selected_pages if not 0 <= index < page_count]
    if invalid_pages:
        raise ValueError(f"ScreenAI page indices are outside the {page_count}-page document: {invalid_pages}")

    merged_output = work_dir / f"{fname_base}.chrome_screenai.searchable.pdf"
    if not selected_pages:
        shutil.copy2(staged_input, merged_output)
        return merged_output

    worker_count = max(1, min(int(config.get("chrome_workers", 4) or 4), len(selected_pages)))
    chunk_jobs = _prepare_chrome_chunk_jobs(
        staged_input=staged_input,
        work_dir=work_dir,
        page_indices=selected_pages,
        worker_count=worker_count,
    )
    _run_chrome_chunk_jobs(chunk_jobs, config=config)

    _merge_selected_chunk_pdfs(
        staged_input=staged_input,
        chunk_jobs=chunk_jobs,
        selected_pages=selected_pages,
        output_pdf=merged_output,
    )
    return merged_output


def _prepare_chrome_chunk_jobs(
    *,
    staged_input: Path,
    work_dir: Path,
    page_indices: Sequence[int],
    worker_count: int,
) -> list[_ChromeChunkJob]:
    selected_pages = list(page_indices)
    chunk_size = max(1, math.ceil(len(selected_pages) / worker_count))
    jobs: list[_ChromeChunkJob] = []

    with fitz.open(staged_input) as source_doc:
        for chunk_index, selected_start in enumerate(range(0, len(selected_pages), chunk_size)):
            chunk_pages = tuple(selected_pages[selected_start:selected_start + chunk_size])
            start_page = chunk_pages[0]
            end_page = chunk_pages[-1]
            chunk_input = work_dir / f"chunk_{chunk_index:03d}_input.pdf"
            subdoc = fitz.open()
            try:
                run_start = previous_page = chunk_pages[0]
                for source_page in chunk_pages[1:]:
                    if source_page == previous_page + 1:
                        previous_page = source_page
                        continue
                    subdoc.insert_pdf(source_doc, from_page=run_start, to_page=previous_page)
                    run_start = previous_page = source_page
                subdoc.insert_pdf(source_doc, from_page=run_start, to_page=previous_page)
                subdoc.save(chunk_input, deflate=True)
            finally:
                subdoc.close()

            jobs.append(
                _ChromeChunkJob(
                    chunk_index=chunk_index,
                    start_page=start_page,
                    end_page=end_page,
                    source_page_indices=chunk_pages,
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
            "remove_annotations": bool(config.get("chrome_remove_annotations", True)),
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
            "[Chrome ScreenAI] Processing chunk %s/%s (%s pages; source %s)",
            job.chunk_index + 1,
            len(jobs),
            job.page_count,
            job.page_label,
        )
        job.process = subprocess.Popen(
            command,
            cwd=os.fspath(repo_root),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
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

            proc.communicate()
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
        f"Chrome ScreenAI chunk {job.chunk_index} (source pages {job.page_label}) failed: {reason}"
    )
    stdout = str(job.stdout or "").strip()
    stderr = str(job.stderr or "").strip()
    if stdout:
        message += f". STDOUT: {stdout}"
    if stderr:
        message += f". STDERR: {stderr}"
    return message


def _merge_selected_chunk_pdfs(
    *,
    staged_input: Path,
    chunk_jobs: list[_ChromeChunkJob],
    selected_pages: Sequence[int],
    output_pdf: Path,
) -> None:
    source_locations: dict[int, tuple[int, int]] = {}
    chunk_documents: dict[int, fitz.Document] = {}
    try:
        for job in chunk_jobs:
            chunk_doc = fitz.open(job.output_pdf)
            actual_page_count = chunk_doc.page_count
            if actual_page_count != job.page_count:
                chunk_doc.close()
                raise ValueError(
                    f"ScreenAI chunk {job.chunk_index} returned {actual_page_count} pages; "
                    f"expected {job.page_count}"
                )
            chunk_documents[job.chunk_index] = chunk_doc
            for local_page, source_page in enumerate(job.source_page_indices):
                if source_page in source_locations:
                    raise ValueError(f"ScreenAI page {source_page} was assigned to multiple chunks")
                source_locations[source_page] = (job.chunk_index, local_page)

        if set(source_locations) != set(selected_pages):
            raise ValueError("ScreenAI chunks did not cover exactly the selected pages")

        output_doc = fitz.open()
        try:
            with fitz.open(staged_input) as source_doc:
                source_page = 0
                while source_page < source_doc.page_count:
                    location = source_locations.get(source_page)
                    if location is None:
                        run_end = source_page
                        while run_end + 1 < source_doc.page_count and run_end + 1 not in source_locations:
                            run_end += 1
                        output_doc.insert_pdf(source_doc, from_page=source_page, to_page=run_end)
                        source_page = run_end + 1
                        continue

                    chunk_index, local_page = location
                    source_end, local_end = source_page, local_page
                    while source_end + 1 < source_doc.page_count:
                        next_location = source_locations.get(source_end + 1)
                        if next_location != (chunk_index, local_end + 1):
                            break
                        source_end += 1
                        local_end += 1
                    output_doc.insert_pdf(
                        chunk_documents[chunk_index], from_page=local_page, to_page=local_end
                    )
                    source_page = source_end + 1
            from aih_contexture.utils.pdf_text_layer import COMPACT_PDF_SAVE_OPTIONS
            output_doc.save(output_pdf, **COMPACT_PDF_SAVE_OPTIONS)
        finally:
            output_doc.close()
    finally:
        for chunk_doc in chunk_documents.values():
            chunk_doc.close()


def _read_json_file(path: Path, *, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
