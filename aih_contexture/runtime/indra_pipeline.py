"""Direct route for ``layout_backend=indra_layout`` + ``ocr_backend=indra_ocr``.

Indra reads layout, text and reading order in one CPU pass, so this route does not build the Surya Pipeline
(no GPU model is loaded): PDF pages -> Indra sidecar -> Middle JSON -> Markdown rendered from the Middle.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pymupdf

from aih_contexture.backends.ocr.indra import IndraRuntime, IndraSettings, pages_to_middle, review_summary
from aih_contexture.runtime.errors import ContextureConfigError
from aih_contexture.runtime.execution import ContextureExecutionContext
from aih_contexture.runtime.job import ContextureJob, ContextureResult

LAYOUT_NAME = "indra_layout"
OCR_NAME = "indra_ocr"


def is_indra_direct(config: dict[str, Any]) -> bool:
    def name(key: str) -> str:
        return str(config.get(key) or "").strip().lower().replace("-", "_")

    return name("layout_backend") == LAYOUT_NAME and name("ocr_backend") == OCR_NAME and not config.get("disable_ocr")


def run_indra_pipeline(
    job: ContextureJob,
    input_path: str,
    config: dict[str, Any],
    execution_context: ContextureExecutionContext,
) -> ContextureResult:
    from aih_contexture.runtime.runner import _apply_middle_contract, _copy_middle_debug_artifact_flags

    if any(name not in ("markdown", "json") for name in job.output_formats):
        raise ContextureConfigError("indra_layout/indra_ocr supports Markdown and JSON (the Middle document) output only")
    if Path(input_path).suffix.lower() != ".pdf":
        raise ContextureConfigError("indra_layout/indra_ocr reads PDF input only")
    try:
        settings = IndraSettings.from_config(config)
    except ValueError as exc:
        raise ContextureConfigError(str(exc)) from exc

    with pymupdf.open(input_path) as document:
        page_count = len(document)
        requested = config.get("page_range")
        if requested is not None and not requested:
            raise ContextureConfigError("Indra page_range must not be empty")
        pages = [index for index in requested if 0 <= index < page_count] if requested else list(range(page_count))
        if requested and len(pages) != len(requested):
            raise ContextureConfigError(f"page_range has pages outside the document ({page_count} pages)")
        sizes = {index: (float(document[index].rect.width), float(document[index].rect.height)) for index in pages}

    from aih_contexture.runtime.pipeline_parallelism import plan_indra_workers

    plan = plan_indra_workers(config, total_pages=len(pages))
    execution_context.emit({"event": "indra_started", "stage": "ocr", "mode": "pipeline", "pages": len(pages), "cores": plan.workers})
    runtime = IndraRuntime(settings)
    try:
        indra_pages = runtime.run(input_path, pages, cores=plan.workers)
    except RuntimeError as exc:
        raise ContextureConfigError(f"Indra OCR failed: {exc}") from exc
    finally:
        runtime.close()

    failed = [index for index, page in indra_pages.items() if page.get("source") == "error"]
    review = review_summary(indra_pages, review_mean=settings.review_mean, review_min=settings.review_min)
    middle = pages_to_middle(
        indra_pages, page_sizes=sizes, source_name=job.input_name or Path(input_path).name, version=runtime.version,
        metadata={"indra": {"mode": settings.mode, "dpi": settings.dpi, "math": settings.math, "parallel_plan": plan.to_dict(), "review": review}},
    )
    from aih_contexture.backends.ocr.indra.evidence import make_indra_evidence
    from aih_contexture.middle.indra_evidence import collect_indra_evidence
    from aih_contexture.runtime.reading_diagnostics import reading_diagnostics_enabled
    for page in middle["pages"]:
        page["attrs"]["indra"] = {
            stage: make_indra_evidence(indra_pages[page["index"]], stage=stage, settings=settings, version=runtime.version)
            for stage in ("layout", "ocr")
        }
    evidence = collect_indra_evidence(middle["pages"])
    middle["metadata"]["indra"].update(evidence)
    flagged = [item["page_index"] + 1 for item in review["review_pages"] if item["page_index"] not in failed]
    result = ContextureResult(
        middle_json=middle,
        page_count=len(pages),
        failed_pages=failed,
        warnings=[f"Indra could not read page {index + 1}." for index in failed]
        + ([f"Indra was unsure about page(s) {', '.join(map(str, flagged))}; consider another backend for them."] if flagged and reading_diagnostics_enabled(config) else []),
        metadata={"indra": {"version": runtime.version, "wall_seconds": runtime.last_wall_seconds, "parallel_plan": plan.to_dict(), "review": review, **evidence}},
    )
    _apply_middle_contract(result, middle, {**config, "render_from_middle": True}, output_format="markdown")
    if "json" in job.output_formats:  # the Middle document is this route's structured output
        result.json_text = json.dumps(result.middle_json, ensure_ascii=False)
    _copy_middle_debug_artifact_flags(config, result)
    execution_context.emit({"event": "indra_done", "stage": "completed", "mode": "pipeline", "page_count": len(pages), "failed_pages": failed})
    return result


def process_indra_pipeline_job(job: dict[str, Any]) -> dict[str, Any]:
    """Use the same native route for GUI jobs, including their selected page slices.

    Indra schedules pages through its own CPU worker plan. GUI page batches are
    combined before that plan, rather than starting a Surya Pipeline per slice.
    """
    from aih_contexture.runtime.artifacts import atomic_write_text, save_contexture_result
    from aih_contexture.runtime.job import normalize_page_range
    from aih_contexture.runtime.progress_events import emit_progress_event, set_progress_context
    from aih_contexture.runtime.run_summary import utc_now_iso, write_document_summary
    from aih_contexture.runtime.runner import run_job

    started = time.time()
    batches = job["batch_jobs"]
    config = dict(batches[0]["config_dict"])
    settings = IndraSettings.from_config(config)
    selected: set[int] = set()
    whole_document = False
    for batch in batches:
        batch_config = batch["config_dict"]
        if IndraSettings.from_config(batch_config) != settings:
            raise ContextureConfigError("Indra batches must use the same runtime settings")
        if {key: value for key, value in batch_config.items() if key != "page_range"} != {
            key: value for key, value in config.items() if key != "page_range"
        }:
            raise ContextureConfigError("Indra batches must use the same output and processing options")
        pages = normalize_page_range(batch_config.get("page_range"))
        if pages is None:
            whole_document = True
        else:
            if not pages:
                raise ContextureConfigError("Indra page_range must not be empty")
            selected.update(pages)
    config["page_range"] = None if whole_document else sorted(selected)
    formats = list(job["output_formats"])
    file_name = job["file_name"]
    set_progress_context(file_name=file_name, total_batches=1, batch_page_offset=0)
    emit_progress_event("file_started", "starting", message=f"Starting {file_name}")

    def progress(event):
        payload = dict(event)
        kind = payload.pop("event", "stage_changed")
        stage = payload.pop("stage", "ocr")
        emit_progress_event(kind, stage, **payload)

    result = run_job(
        ContextureJob(
            input_path=job["file_path"], input_name=file_name,
            config=config, output_formats=formats,
        ),
        execution_context=ContextureExecutionContext(progress_callback=progress),
    )
    if result.failed_pages:
        raise ContextureConfigError(
            "Indra could not read page(s): " + ", ".join(str(index + 1) for index in result.failed_pages)
        )
    output_dir, basename = job["output_dir"], job["fname_base"]
    # Save the reading pair once, including optional Middle/debug artifacts.
    primary = "markdown" if "markdown" in formats else "json"
    saved = save_contexture_result(result, output_dir, basename, primary)
    outputs = [{"format": primary, "path": saved["path"], "name": Path(saved["path"]).name}]
    for key, path in saved.items():
        if key.endswith("_path"):
            outputs.append({"format": key[:-5], "path": path, "name": Path(path).name})
    if "json" in formats and primary != "json":
        path = str(Path(output_dir) / f"{basename}.json")
        atomic_write_text(path, result.json_text)
        outputs.append({"format": "json", "path": path, "name": Path(path).name})
    meta_path = str(Path(output_dir) / f"{basename}_meta.json")
    outputs.append({"format": "metadata", "path": meta_path, "name": Path(meta_path).name})
    elapsed = time.time() - started
    models = {"layout": LAYOUT_NAME, "ocr": OCR_NAME}
    summary_path = write_document_summary(
        output_dir=output_dir, source_name=file_name,
        processing_id=str(job.get("processing_id") or "0000"), file_index=job.get("file_index"),
        mode="pipeline", strategy="indra_direct", models=models, config=config,
        started_at=datetime.fromtimestamp(started).astimezone().isoformat(timespec="seconds"),
        finished_at=utc_now_iso(), elapsed_seconds=elapsed, status="succeeded",
        page_count=result.page_count, output_paths=[item["path"] for item in outputs],
        warnings=result.warnings, source_path=job["file_path"],
    )
    emit_progress_event("file_completed", "completed", current=result.page_count,
                        total=result.page_count, unit="pages", absolute_progress=True,
                        elapsed_seconds=elapsed, message=f"Completed {file_name}")
    return {
        "success": True, "file_name": file_name,
        "result_key": f"{file_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "file_outputs": outputs, "elapsed_seconds": elapsed,
        "backend_summary": {"layout_backends": [LAYOUT_NAME], "ocr_backends": [OCR_NAME],
                            "disable_ocr": [False], "ocr_preprocess_backends": []},
        "warnings": result.warnings, "metadata": result.metadata,
        "summary_path": summary_path, "error": None, "traceback": None,
    }
