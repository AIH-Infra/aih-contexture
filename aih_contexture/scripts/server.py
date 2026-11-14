import click

from pydantic import BaseModel, Field
from starlette.responses import HTMLResponse

import asyncio
import base64
import json
from contextlib import asynccontextmanager
from typing import Optional, Annotated, Any, Literal
import io
import os
import threading
from pathlib import Path

from fastapi import FastAPI, Form, File, HTTPException, UploadFile
from aih_contexture.backends.catalog import backend_catalog
from aih_contexture.backends.external_config import (
    DEFAULT_MINERU_LAYOUT_BATCH_SIZE,
    default_mineru_command,
    default_mineru_layout_model_dir,
    default_mineru_layout_python,
    default_mineru_python,
)
from aih_contexture.models import create_model_dict
from aih_contexture.runtime.job import ContextureJob, ContextureResult
from aih_contexture.runtime.runner import run_job
from aih_contexture.settings import settings
from aih_contexture.logger import get_logger
from aih_contexture.middle.validation import validate_middle_for_publication
from aih_contexture.runtime.errors import ContextureConfigError

app_data = {}
logger = get_logger()
_run_semaphore = asyncio.Semaphore(1)
_run_lock = threading.Lock()
_DEFAULT_MAX_UPLOAD_MB = 512


def _max_upload_bytes() -> int:
    raw_value = os.environ.get("CONTEXTURE_MAX_UPLOAD_MB", str(_DEFAULT_MAX_UPLOAD_MB))
    try:
        max_upload_mb = int(raw_value)
    except ValueError:
        logger.warning(
            "Invalid CONTEXTURE_MAX_UPLOAD_MB=%r; using %s MB",
            raw_value,
            _DEFAULT_MAX_UPLOAD_MB,
        )
        max_upload_mb = _DEFAULT_MAX_UPLOAD_MB
    return max(1, max_upload_mb) * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    app_data["models"] = create_model_dict()

    yield

    if "models" in app_data:
        release_all = getattr(app_data["models"], "release_all", None)
        if callable(release_all):
            release_all()
        del app_data["models"]


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return HTMLResponse(
        """
<h1>Marker API</h1>
<ul>
    <li><a href="/docs">API Documentation</a></li>
    <li><a href="/marker">Run marker (post request only)</a></li>
</ul>
"""
    )


class CommonParams(BaseModel):
    filepath: Annotated[
        Optional[str], Field(description="The path to the PDF file to convert.")
    ]
    page_range: Annotated[
        Optional[str],
        Field(
            description="Page range to convert, specify comma separated page numbers or ranges.  Example: 0,5-10,20",
            example=None,
        ),
    ] = None
    force_ocr: Annotated[
        bool,
        Field(
            description="Compatibility flag. In pipeline mode, selecting any OCR backend forces OCR; set ocr_backend='none' to use the embedded PDF text layer."
        ),
    ] = False
    paginate_output: Annotated[
        bool,
        Field(
            description="Whether to paginate the output.  Defaults to False.  If set to True, each page of the output will be separated by a horizontal rule that contains the page number (2 newlines, {PAGE_NUMBER}, 48 - characters, 2 newlines)."
        ),
    ] = False
    output_format: Annotated[
        str,
        Field(
            description="The format to output the text in.  Can be 'markdown', 'json', or 'html'.  Defaults to 'markdown'."
        ),
    ] = "markdown"
    layout_backend: Annotated[
        str,
        Field(description="Pipeline layout backend. Current implemented values: surya, vlm_layout, external_layout_sidecar, mineru_pp_doclayout_v2_direct, paddle_pp_doclayout_plus_l, paddle_pp_doclayout_v3."),
    ] = "surya"
    surya_layout_quality: Annotated[
        str,
        Field(description="Surya layout quality preset: fast, standard, or high."),
    ] = "fast"
    layout_dpi_override: Annotated[
        Optional[int],
        Field(description="Advanced override for layout render DPI."),
    ] = None
    indra_python: Annotated[Optional[str], Field(description="Python executable for the local Indra OCR sidecar.")] = None
    indra_model_dir: Annotated[Optional[str], Field(description="Local Indra model directory; the API never downloads weights unless explicitly enabled.")] = None
    indra_mode: Annotated[str, Field(description="Indra page mode: auto, ocr, or text.")] = "auto"
    indra_dpi: Annotated[Optional[int], Field(description="Indra render DPI (minimum 72).") ] = None
    indra_math: Annotated[bool, Field(description="Enable Indra math recognition.")] = False
    indra_cores: Annotated[Optional[int], Field(description="Requested Indra CPU worker count.")] = None
    indra_allow_download: Annotated[bool, Field(description="Allow downloading Indra weights when the local model is missing.")] = False
    indra_cache_dir: Annotated[Optional[str], Field(description="Optional per-page Indra result cache directory.")] = None
    indra_review_mean: Annotated[Optional[float], Field(description="Indra mean-confidence review threshold.")] = None
    indra_review_min: Annotated[Optional[float], Field(description="Indra minimum-line-confidence review threshold.")] = None
    external_layout_json: Annotated[
        Optional[str],
        Field(description="Server-side path to external layout JSON for external_layout_sidecar."),
    ] = None
    external_layout_block_source: Annotated[
        str,
        Field(description="External layout block source: auto, all, blocks, layout_bboxes, boxes, bboxes, layout, regions, para_blocks, preproc_blocks, or discarded_blocks."),
    ] = "auto"
    external_layout_backend_name: Annotated[
        str,
        Field(description="Backend name recorded in provenance when importing raw external layout JSON."),
    ] = "external_layout_sidecar"
    external_layout_model: Annotated[
        Optional[str],
        Field(description="Model name recorded in provenance when importing raw external layout JSON."),
    ] = None
    external_layout_allow_missing_pages: Annotated[
        bool,
        Field(description="Allow sidecar JSON to omit pages and use a full-page Text fallback."),
    ] = False
    mineru_command: Annotated[
        str,
        Field(description="Legacy MinerU executable path for full-pipeline diagnostic/import workflows."),
    ] = "mineru"
    mineru_output_dir: Annotated[
        Optional[str],
        Field(description="Directory for MinerU raw outputs. Defaults to a temporary directory."),
    ] = None
    mineru_backend: Annotated[
        str,
        Field(description="MinerU backend passed to -b. Default: pipeline."),
    ] = "pipeline"
    mineru_method: Annotated[
        str,
        Field(description="MinerU parse method passed to -m: txt, ocr, or auto."),
    ] = "txt"
    mineru_lang: Annotated[
        str,
        Field(description="MinerU language passed to -l."),
    ] = "ch"
    mineru_api_url: Annotated[
        Optional[str],
        Field(description="Optional MinerU API URL passed to --api-url."),
    ] = None
    mineru_server_url: Annotated[
        Optional[str],
        Field(description="Optional MinerU VLM/hybrid server URL passed to -u."),
    ] = None
    mineru_timeout: Annotated[
        int,
        Field(description="MinerU CLI timeout in seconds."),
    ] = 3600
    mineru_extra_args: Annotated[
        Optional[str],
        Field(description="Extra arguments appended to the MinerU CLI command."),
    ] = None
    mineru_layout_python: Annotated[
        Optional[str],
        Field(description="Optional Python executable (with PyTorch) for the mineru_pp_doclayout_v2_direct layout sidecar. Defaults to the interpreter running Contexture."),
    ] = None
    mineru_ocr_python: Annotated[
        Optional[str],
        Field(description="Optional Python override for native Paddle OCR Torch. Defaults to Contexture's Python; no MinerU installation required."),
    ] = None
    mineru_ocr_model_dir: Optional[str] = Field(default=None, description="Native Paddle OCR Torch weight folder; existing caches are reused if omitted.")
    mineru_ocr_version: Literal["PP-OCRv5", "PP-OCRv6"] = Field(default="PP-OCRv5", description="Native Paddle OCR Torch model family.")
    mineru_ocr_allow_download: bool = Field(default=False, description="Explicitly allow downloading missing native OCR weights.")
    mineru_ocr_lang: Annotated[
        str,
        Field(description="MinerU PytorchPaddleOCR language code."),
    ] = "ch"
    mineru_ocr_device: Annotated[
        Optional[str],
        Field(description="Native Paddle OCR Torch device, e.g. cpu, cuda, cuda:0."),
    ] = None
    mineru_ocr_timeout: Annotated[
        int,
        Field(description="MinerU OCR sidecar timeout in seconds."),
    ] = 3600
    mineru_layout_model_dir: Annotated[
        Optional[str],
        Field(description="Optional local MinerU PP-DocLayoutV2 model directory."),
    ] = None
    mineru_layout_device: Annotated[
        Optional[str],
        Field(description="Optional MinerU direct layout device, e.g. cpu, cuda, cuda:0."),
    ] = None
    mineru_layout_batch_size: Annotated[
        int,
        Field(description="Batch size for MinerU PP-DocLayoutV2 direct layout inference."),
    ] = DEFAULT_MINERU_LAYOUT_BATCH_SIZE
    mineru_layout_use_paddlex_filter_boxes: Annotated[
        bool,
        Field(description="Enable MinerU/PaddleX-style layout box filtering for direct layout inference."),
    ] = False
    mineru_layout_timeout: Annotated[
        int,
        Field(description="MinerU direct layout sidecar timeout in seconds."),
    ] = 3600
    paddle_layout_model_name: Annotated[
        str,
        Field(description="PaddleOCR LayoutDetection model name."),
    ] = "PP-DocLayout_plus-L"
    paddle_layout_allow_download: bool = Field(default=False, description="Explicitly allow downloading the optional native PP-DocLayoutV3 ONNX model.")
    paddle_layout_batch_size: Optional[int] = Field(default=None, description="Layout inference batch size; native V3 CPU supports 1 to 8.")
    paddle_layout_python: Annotated[
        Optional[str],
        Field(description="Optional external Python executable for Paddle layout sidecar."),
    ] = None
    paddle_layout_model_dir: Annotated[
        Optional[str],
        Field(description="Model directory: inference.onnx plus inference.yml for native PP-DocLayoutV3, or Paddle model files for an explicit SDK engine."),
    ] = None
    paddle_layout_device: Annotated[
        Optional[str],
        Field(description="Optional PaddleOCR device, e.g. cpu, gpu, gpu:0."),
    ] = None
    paddle_layout_engine: Annotated[
        Optional[str],
        Field(description="PP-DocLayoutV3 defaults to native CPU onnxruntime; explicit paddle engines retain the SDK compatibility path."),
    ] = None
    paddle_layout_enable_mkldnn: Annotated[
        bool,
        Field(description="Enable PaddleOCR MKL-DNN acceleration for layout detection. Defaults to false for CPU runtime stability."),
    ] = False
    paddle_layout_cpu_threads: Annotated[
        Optional[int],
        Field(description="Optional CPU thread count for PaddleOCR layout detection."),
    ] = None
    paddle_layout_threshold: Annotated[
        Optional[float],
        Field(description="Optional PaddleOCR layout confidence threshold."),
    ] = None
    paddle_layout_img_size: Annotated[
        Optional[int],
        Field(description="Optional PaddleOCR layout input image size."),
    ] = None
    ocr_backend: Annotated[
        str,
        Field(description="Pipeline OCR backend. Current implemented values: surya, chrome_screenai, calamari, vlm_ocr, paddle_ocr_v5, mineru_pytorch_paddle_ocr, paddleocr_vl_ocr, tesseract. chrome_screenai writes a searchable PDF first, then re-enters Pipeline through embedded PDF text. Use 'none' for the embedded PDF text layer."),
    ] = "surya"
    ocr_quality: Annotated[
        str,
        Field(description="OCR quality preset: auto, low, medium, or high."),
    ] = "auto"
    ocr_dpi_override: Annotated[
        Optional[int],
        Field(description="Advanced override for OCR render DPI."),
    ] = None
    ocr_preprocess_backend: Annotated[
        str,
        Field(description="Compatibility option for hidden OCR preprocessing. Current implemented values: none, chrome_screenai_searchable_pdf. Prefer ocr_backend='chrome_screenai'."),
    ] = "none"
    chrome_screenai_light: Annotated[
        bool,
        Field(description="Enable Chrome ScreenAI light/fast mode for OCR preprocessing."),
    ] = False
    chrome_preprocess_mode: Annotated[
        str,
        Field(description="Chrome ScreenAI PDF preprocessing mode: native, strip_existing_ocr, rasterize_pdf, or strip_then_rasterize."),
    ] = "native"
    chrome_workers: Annotated[
        int,
        Field(description="Chrome ScreenAI OCR worker count for searchable-PDF preprocessing."),
    ] = 4
    chrome_chunk_pages: Annotated[
        int,
        Field(description="Chrome ScreenAI page chunk size for searchable-PDF preprocessing."),
    ] = 4
    chrome_emit_searchable_pdf: Annotated[
        bool,
        Field(description="Export the intermediate Chrome ScreenAI searchable PDF as a pipeline artifact."),
    ] = False
    chrome_rasterize_dpi: Annotated[
        int,
        Field(description="Rasterization DPI when Chrome ScreenAI preprocessing mode uses rasterized PDF pages."),
    ] = 144
    chrome_model_dir: Annotated[
        Optional[str],
        Field(description="Optional local Chrome ScreenAI model directory."),
    ] = None
    tesseract_cmd: Annotated[
        Optional[str],
        Field(description="Optional Tesseract executable path for ocr_backend=tesseract."),
    ] = None
    tesseract_lang: Annotated[
        str,
        Field(description="Tesseract language expression, e.g. eng or chi_sim+eng."),
    ] = "eng"
    tesseract_oem: Annotated[int, Field(description="Tesseract OCR Engine Mode.")] = 1
    tesseract_psm: Annotated[int, Field(description="Tesseract Page Segmentation Mode.")] = 7
    tesseract_timeout: Annotated[int, Field(description="Tesseract per-line timeout in seconds.")] = 30
    tesseract_omp_thread_limit: Annotated[int, Field(description="OMP thread limit for Tesseract subprocesses.")] = 1
    tesseract_tessdata_prefix: Annotated[
        Optional[str],
        Field(description="Optional TESSDATA_PREFIX for Tesseract language data."),
    ] = None
    paddle_ocr_lang: Annotated[
        str,
        Field(description="PaddleOCR language for ocr_backend=paddle_ocr_v5."),
    ] = "ch"
    paddle_ocr_python: Annotated[
        Optional[str],
        Field(description="Optional external Python executable for Paddle OCR sidecar."),
    ] = None
    paddle_ocr_version: Annotated[
        str,
        Field(description="PaddleOCR OCR version for ocr_backend=paddle_ocr_v5."),
    ] = "PP-OCRv5"
    paddle_ocr_device: Annotated[
        Optional[str],
        Field(description="Optional PaddleOCR device, e.g. cpu, gpu, gpu:0."),
    ] = None
    paddle_ocr_engine: Annotated[
        Optional[str],
        Field(description="Optional PaddleOCR inference engine."),
    ] = None
    paddle_ocr_enable_mkldnn: Annotated[
        bool,
        Field(description="Enable PaddleOCR MKL-DNN acceleration. Defaults to false for CPU runtime stability."),
    ] = False
    paddle_ocr_cpu_threads: Annotated[
        Optional[int],
        Field(description="Optional CPU thread count for PaddleOCR."),
    ] = None
    paddle_ocr_use_doc_orientation_classify: Annotated[
        bool,
        Field(description="Enable PaddleOCR document orientation classifier."),
    ] = False
    paddle_ocr_use_doc_unwarping: Annotated[
        bool,
        Field(description="Enable PaddleOCR document unwarping."),
    ] = False
    paddle_ocr_use_textline_orientation: Annotated[
        bool,
        Field(description="Enable PaddleOCR text-line orientation classifier."),
    ] = False
    equation_output_mode: Annotated[
        str,
        Field(description="Equation Markdown output mode: humanities_safe, plain, or math."),
    ] = "humanities_safe"
    emit_middle_json: Annotated[
        bool,
        Field(description="Emit core Contexture Middle JSON in the API response when available."),
    ] = False
    emit_middle_report: Annotated[
        bool,
        Field(description="Emit a Middle JSON validation report when saving artifacts."),
    ] = False
    emit_middle_debug: Annotated[
        bool,
        Field(description="Emit a debug Markdown rendering of Middle JSON when saving artifacts."),
    ] = False
    emit_middle_scholarly: Annotated[
        bool,
        Field(description="Emit scholarly Markdown rendered from Middle JSON when saving artifacts."),
    ] = False
    emit_middle_scholarly_report: Annotated[
        bool,
        Field(description="Emit a quality report for scholarly Markdown rendered from Middle JSON."),
    ] = False
    emit_layout_overlay: Annotated[
        bool,
        Field(description="Emit layout overlay artifacts when saving results from runtime paths that support artifacts."),
    ] = False
    emit_span_overlay: Annotated[
        bool,
        Field(description="Emit span overlay artifacts when saving results from runtime paths that support artifacts."),
    ] = False
    emit_middle_full_json: Annotated[
        bool,
        Field(description="Emit full Middle JSON with spans for diagnostics."),
    ] = False


class RuntimeConvertParams(BaseModel):
    filepath: Annotated[
        Optional[str],
        Field(
            description=(
                "Server-side input path for trusted local deployments. "
                "Public server-mode must use upload/storage-root job submission instead of arbitrary paths."
            )
        ),
    ] = None
    mode: Annotated[
        str,
        Field(description="Runtime mode: pipeline, vlm_generalized, vlm_specialized, or markdown_postprocess."),
    ] = "pipeline"
    output_format: Annotated[str, Field(description="Primary output format.")] = "markdown"
    output_formats: Annotated[Optional[list[str]], Field(description="Optional ordered output formats.")] = None
    page_range: Annotated[Optional[str], Field(description="Page range such as 0,2-4.")] = None
    config: Annotated[dict[str, Any], Field(default_factory=dict, description="Mode-specific runtime config.")]


def _normalize_pipeline_ocr_options(options: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(options)
    ocr_backend = str(normalized.get("ocr_backend") or "surya").strip().lower().replace("-", "_")
    preprocess_backend = str(normalized.get("ocr_preprocess_backend") or "none").strip().lower().replace("-", "_")
    if preprocess_backend == "chrome_screenai":
        preprocess_backend = "chrome_screenai_searchable_pdf"
    if ocr_backend == "none":
        normalized["ocr_backend"] = "surya"
        normalized["disable_ocr"] = True
    else:
        normalized["ocr_backend"] = ocr_backend
    if ocr_backend == "chrome_screenai" and preprocess_backend == "none":
        preprocess_backend = "chrome_screenai_searchable_pdf"
    normalized["ocr_preprocess_backend"] = preprocess_backend
    normalized["disable_ocr"] = bool(normalized.get("disable_ocr", False) or preprocess_backend != "none")
    normalized["force_ocr"] = False if normalized["disable_ocr"] else True
    return normalized


async def _convert_pdf(params: CommonParams):
    if params.output_format not in {"markdown", "json", "html", "chunks"}:
        raise HTTPException(status_code=422, detail=f"Unsupported output format: {params.output_format}")
    options = params.model_dump()
    if not options.get("mineru_command") or options.get("mineru_command") == "mineru":
        options["mineru_command"] = default_mineru_command()
    if not options.get("mineru_layout_python"):
        options["mineru_layout_python"] = default_mineru_layout_python()
    if not options.get("mineru_layout_model_dir"):
        options["mineru_layout_model_dir"] = default_mineru_layout_model_dir()
    options = _normalize_pipeline_ocr_options(options)
    if (
        options.get("layout_backend") == "paddle_pp_doclayout_v3"
        and options.get("paddle_layout_model_name") == "PP-DocLayout_plus-L"
    ):
        options["paddle_layout_model_name"] = "PP-DocLayoutV3"
    options["pdftext_workers"] = 1
    try:
        job = ContextureJob.from_dict(
            {
                "input_path": params.filepath,
                "mode": "pipeline",
                "output_formats": [params.output_format],
                "page_range": params.page_range,
                "config": options,
            }
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await _run_job_response(job, params.output_format)


async def _run_job_response(job: ContextureJob, output_format: str) -> dict:
    async with _run_semaphore:
        return await asyncio.to_thread(_run_job_response_sync, job, output_format)


def _run_job_response_sync(job: ContextureJob, output_format: str) -> dict:
    # asyncio.to_thread cannot stop an in-flight worker when its caller is cancelled.
    # Keep the shared model container serialized even if the async semaphore is released.
    with _run_lock:
        return _run_job_response_unlocked(job, output_format)


def _run_job_response_unlocked(job: ContextureJob, output_format: str) -> dict:
    try:
        result = run_job(job, artifact_dict=app_data["models"])
        output_formats = list(dict.fromkeys(job.output_formats or [output_format]))
        if output_format not in output_formats:
            output_formats.insert(0, output_format)
        outputs = {name: _result_text(result, name) for name in output_formats}
        text = outputs[output_format]
        images = result.images
        metadata = result.metadata
        middle_json = result.middle_json
    except HTTPException:
        raise
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except (ContextureConfigError, ValueError, TypeError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        logger.exception("Runtime conversion failed for mode=%s output_format=%s", job.mode, output_format)
        raise HTTPException(status_code=500, detail=str(e)) from e

    encoded = {}
    for k, v in images.items():
        byte_stream = io.BytesIO()
        v.save(byte_stream, format=settings.OUTPUT_IMAGE_FORMAT)
        encoded[k] = base64.b64encode(byte_stream.getvalue()).decode(
            settings.OUTPUT_ENCODING
        )

    failed_pages = list(result.failed_pages or [])
    if not isinstance(middle_json, dict):
        raise HTTPException(status_code=422, detail="Conversion did not produce a Middle JSON document")
    middle_validation = validate_middle_for_publication(middle_json)
    if not middle_validation.ok and not failed_pages:
        messages = [issue.message for issue in middle_validation.errors]
        raise HTTPException(status_code=422, detail=f"Conversion produced invalid Middle JSON: {'; '.join(messages)}")
    return {
        "format": output_format,
        "output": text,
        "outputs": outputs,
        "images": encoded,
        "metadata": metadata,
        "structured_artifacts": result.structured_artifacts,
        "middle_json": middle_json,
        "middle_validation": {
            "ok": middle_validation.ok,
            "errors": [
                {"path": issue.path, "message": issue.message}
                for issue in middle_validation.errors
            ],
            "warnings": [
                {"path": issue.path, "message": issue.message}
                for issue in middle_validation.warnings
            ],
        },
        "page_count": result.page_count,
        "failed_pages": failed_pages,
        "diagnostics": result.diagnostics,
        "warnings": result.warnings,
        "success": not failed_pages,
        "error": f"Failed pages: {failed_pages}" if failed_pages else None,
    }


def _result_text(result: ContextureResult, output_format: str) -> str:
    match output_format:
        case "markdown":
            return result.markdown or ""
        case "html":
            return result.html or ""
        case "json":
            return result.json_text or ""
        case "chunks":
            return result.chunks or ""
        case "source_package":
            package = (result.structured_artifacts or {}).get("source_package")
            if not isinstance(package, dict):
                raise HTTPException(status_code=422, detail="Structured source package was not generated")
            path = package.get("path")
            manifest = package.get("manifest")
            if not path or not Path(path).is_dir() or not isinstance(manifest, dict) or not manifest:
                raise HTTPException(status_code=422, detail="Structured source package is missing its directory or manifest")
            return json.dumps({"path": str(path), "manifest": manifest}, ensure_ascii=False)
        case _:
            return ""


@app.post("/marker")
async def convert_pdf(params: CommonParams):
    return await _convert_pdf(params)


@app.post("/v1/convert")
async def convert_runtime(params: RuntimeConvertParams):
    output_formats = params.output_formats or [params.output_format]
    try:
        job = ContextureJob.from_dict(
            {
                "input_path": params.filepath,
                "mode": params.mode,
                "output_formats": output_formats,
                "page_range": params.page_range,
                "config": params.config,
            }
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if job.mode == "structured_source":
        allowed_formats = {"markdown", "json", "html", "source_package"}
    else:
        allowed_formats = {"markdown", "json", "html", "chunks"}
    unsupported = [name for name in output_formats if name not in allowed_formats]
    if unsupported:
        raise HTTPException(status_code=422, detail=f"Unsupported output format(s): {', '.join(unsupported)}")
    if job.mode == "structured_source" and "source_package" in output_formats:
        output_dir = job.config.get("output_dir")
        if not isinstance(output_dir, str) or not output_dir.strip():
            raise HTTPException(
                status_code=422,
                detail="structured_source output_format=source_package requires config.output_dir",
            )
    return await _run_job_response(job, output_formats[0] if output_formats else "markdown")


@app.get("/v1/backends")
async def list_backends(
    implemented_only: bool = True,
    include_status: bool = False,
    mineru_command: str | None = None,
    paddle_python: str | None = None,
    probe_services: bool = False,
    health_timeout: float = 3.0,
    openai_base_url: str | None = None,
    ocr_endpoint: str | None = None,
    calamari_base_url: str | None = None,
    paddleocr_vl_endpoint: str | None = None,
):
    return backend_catalog(
        implemented_only=implemented_only,
        include_status=include_status,
        config={
            "mineru_command": mineru_command or default_mineru_command(),
            "paddle_python": paddle_python,
            "probe_services": probe_services,
            "backend_health_timeout": health_timeout,
            "openai_base_url": openai_base_url,
            "ocr_endpoint": ocr_endpoint,
            "calamari_base_url": calamari_base_url,
            "paddleocr_vl_endpoint": paddleocr_vl_endpoint,
        },
    )


@app.post("/marker/upload")
async def convert_pdf_upload(
    page_range: Optional[str] = Form(default=None),
    force_ocr: Optional[bool] = Form(default=False),
    paginate_output: Optional[bool] = Form(default=False),
    output_format: Optional[str] = Form(default="markdown"),
    layout_backend: Optional[str] = Form(default="surya"),
    surya_layout_quality: Optional[str] = Form(default="fast"),
    layout_dpi_override: Optional[int] = Form(default=None),
    external_layout_json: Optional[str] = Form(default=None),
    external_layout_block_source: Optional[str] = Form(default="auto"),
    external_layout_backend_name: Optional[str] = Form(default="external_layout_sidecar"),
    external_layout_model: Optional[str] = Form(default=None),
    external_layout_allow_missing_pages: Optional[bool] = Form(default=False),
    mineru_command: Optional[str] = Form(default=None),
    mineru_output_dir: Optional[str] = Form(default=None),
    mineru_backend: Optional[str] = Form(default="pipeline"),
    mineru_method: Optional[str] = Form(default="txt"),
    mineru_lang: Optional[str] = Form(default="ch"),
    mineru_api_url: Optional[str] = Form(default=None),
    mineru_server_url: Optional[str] = Form(default=None),
    mineru_timeout: Optional[int] = Form(default=3600),
    mineru_extra_args: Optional[str] = Form(default=None),
    mineru_layout_python: Optional[str] = Form(default=None),
    mineru_layout_model_dir: Optional[str] = Form(default=None),
    mineru_layout_device: Optional[str] = Form(default=None),
    mineru_layout_batch_size: Optional[int] = Form(default=DEFAULT_MINERU_LAYOUT_BATCH_SIZE),
    mineru_layout_use_paddlex_filter_boxes: bool = Form(default=False),
    mineru_layout_timeout: Optional[int] = Form(default=3600),
    paddle_layout_model_name: Optional[str] = Form(default="PP-DocLayout_plus-L"),
    paddle_layout_allow_download: bool = Form(default=False),
    paddle_layout_batch_size: Optional[int] = Form(default=None),
    paddle_layout_python: Optional[str] = Form(default=None),
    paddle_layout_model_dir: Optional[str] = Form(default=None),
    paddle_layout_device: Optional[str] = Form(default=None),
    paddle_layout_engine: Optional[str] = Form(default=None),
    paddle_layout_enable_mkldnn: bool = Form(default=False),
    paddle_layout_cpu_threads: Optional[int] = Form(default=None),
    paddle_layout_threshold: Optional[float] = Form(default=None),
    paddle_layout_img_size: Optional[int] = Form(default=None),
    ocr_backend: Optional[str] = Form(default="surya"),
    mineru_ocr_python: Optional[str] = Form(default=None),
    mineru_ocr_model_dir: Optional[str] = Form(default=None),
    mineru_ocr_version: Literal["PP-OCRv5", "PP-OCRv6"] = Form(default="PP-OCRv5"),
    mineru_ocr_allow_download: bool = Form(default=False),
    mineru_ocr_lang: str = Form(default="ch"),
    mineru_ocr_device: Optional[str] = Form(default=None),
    mineru_ocr_timeout: int = Form(default=3600),
    ocr_quality: Optional[str] = Form(default="auto"),
    ocr_dpi_override: Optional[int] = Form(default=None),
    ocr_preprocess_backend: Optional[str] = Form(default="none"),
    chrome_screenai_light: bool = Form(default=False),
    chrome_preprocess_mode: Optional[str] = Form(default="native"),
    chrome_workers: Optional[int] = Form(default=4),
    chrome_chunk_pages: Optional[int] = Form(default=4),
    chrome_emit_searchable_pdf: bool = Form(default=False),
    chrome_rasterize_dpi: Optional[int] = Form(default=144),
    chrome_model_dir: Optional[str] = Form(default=None),
    tesseract_cmd: Optional[str] = Form(default=None),
    tesseract_lang: Optional[str] = Form(default="eng"),
    tesseract_oem: Optional[int] = Form(default=1),
    tesseract_psm: Optional[int] = Form(default=7),
    tesseract_timeout: Optional[int] = Form(default=30),
    tesseract_omp_thread_limit: Optional[int] = Form(default=1),
    tesseract_tessdata_prefix: Optional[str] = Form(default=None),
    paddle_ocr_lang: Optional[str] = Form(default="ch"),
    paddle_ocr_python: Optional[str] = Form(default=None),
    paddle_ocr_version: Optional[str] = Form(default="PP-OCRv5"),
    paddle_ocr_device: Optional[str] = Form(default=None),
    paddle_ocr_engine: Optional[str] = Form(default=None),
    paddle_ocr_enable_mkldnn: bool = Form(default=False),
    paddle_ocr_cpu_threads: Optional[int] = Form(default=None),
    paddle_ocr_use_doc_orientation_classify: bool = Form(default=False),
    paddle_ocr_use_doc_unwarping: bool = Form(default=False),
    paddle_ocr_use_textline_orientation: bool = Form(default=False),
    indra_python: Optional[str] = Form(default=None),
    indra_model_dir: Optional[str] = Form(default=None),
    indra_mode: Optional[str] = Form(default="auto"),
    indra_dpi: Optional[int] = Form(default=None),
    indra_math: bool = Form(default=False),
    indra_cores: Optional[int] = Form(default=None),
    indra_allow_download: bool = Form(default=False),
    indra_cache_dir: Optional[str] = Form(default=None),
    indra_review_mean: Optional[float] = Form(default=None),
    indra_review_min: Optional[float] = Form(default=None),
    equation_output_mode: Optional[str] = Form(default="humanities_safe"),
    emit_middle_json: Optional[bool] = Form(default=False),
    emit_middle_report: Optional[bool] = Form(default=False),
    emit_middle_debug: Optional[bool] = Form(default=False),
    emit_middle_scholarly: Optional[bool] = Form(default=False),
    emit_middle_scholarly_report: Optional[bool] = Form(default=False),
    emit_layout_overlay: Optional[bool] = Form(default=False),
    emit_span_overlay: Optional[bool] = Form(default=False),
    emit_middle_full_json: Optional[bool] = Form(default=False),
    file: UploadFile = File(
        ..., description="The PDF file to convert.", media_type="application/pdf"
    ),
):
    output_format = output_format or "markdown"
    if output_format not in {"markdown", "json", "html", "chunks"}:
        raise HTTPException(status_code=422, detail=f"Unsupported output format: {output_format}")
    max_upload_bytes = _max_upload_bytes()
    file_contents = await file.read(max_upload_bytes + 1)
    if len(file_contents) > max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Uploaded file exceeds the {max_upload_bytes // (1024 * 1024)} MB limit. "
                "Set CONTEXTURE_MAX_UPLOAD_MB to change the local server limit."
            ),
        )
    resolved_layout_backend = layout_backend or "surya"
    default_paddle_model = (
        "PP-DocLayoutV3"
        if resolved_layout_backend == "paddle_pp_doclayout_v3"
        else "PP-DocLayout_plus-L"
    )
    options = {
        "filepath": None,
        "page_range": page_range,
        "force_ocr": force_ocr,
        "paginate_output": paginate_output,
        "output_format": output_format,
        "layout_backend": resolved_layout_backend,
        "surya_layout_quality": surya_layout_quality or "fast",
        "layout_dpi_override": layout_dpi_override,
        "external_layout_json": external_layout_json,
        "external_layout_block_source": external_layout_block_source or "auto",
        "external_layout_backend_name": external_layout_backend_name or "external_layout_sidecar",
        "external_layout_model": external_layout_model,
        "external_layout_allow_missing_pages": bool(external_layout_allow_missing_pages),
        "mineru_command": mineru_command or default_mineru_command(),
        "mineru_output_dir": mineru_output_dir,
        "mineru_backend": mineru_backend or "pipeline",
        "mineru_method": mineru_method or "txt",
        "mineru_lang": mineru_lang or "ch",
        "mineru_api_url": mineru_api_url,
        "mineru_server_url": mineru_server_url,
        "mineru_timeout": int(mineru_timeout or 3600),
        "mineru_extra_args": mineru_extra_args,
        "mineru_layout_python": mineru_layout_python or default_mineru_layout_python(),
        "mineru_layout_model_dir": mineru_layout_model_dir or default_mineru_layout_model_dir(),
        "mineru_layout_device": mineru_layout_device,
        "mineru_layout_batch_size": int(mineru_layout_batch_size or DEFAULT_MINERU_LAYOUT_BATCH_SIZE),
        "mineru_layout_use_paddlex_filter_boxes": mineru_layout_use_paddlex_filter_boxes,
        "mineru_layout_timeout": int(mineru_layout_timeout or 3600),
        "paddle_layout_model_name": paddle_layout_model_name or default_paddle_model,
        "paddle_layout_allow_download": paddle_layout_allow_download,
        "paddle_layout_batch_size": paddle_layout_batch_size,
        "paddle_layout_python": paddle_layout_python,
        "paddle_layout_model_dir": paddle_layout_model_dir,
        "paddle_layout_device": paddle_layout_device,
        "paddle_layout_engine": paddle_layout_engine,
        "paddle_layout_enable_mkldnn": paddle_layout_enable_mkldnn,
        "paddle_layout_cpu_threads": paddle_layout_cpu_threads,
        "paddle_layout_threshold": paddle_layout_threshold,
        "paddle_layout_img_size": paddle_layout_img_size,
        "ocr_backend": ocr_backend or "surya",
        "mineru_ocr_python": mineru_ocr_python,
        "mineru_ocr_model_dir": mineru_ocr_model_dir,
        "mineru_ocr_version": mineru_ocr_version,
        "mineru_ocr_allow_download": mineru_ocr_allow_download,
        "mineru_ocr_lang": mineru_ocr_lang,
        "mineru_ocr_device": mineru_ocr_device,
        "mineru_ocr_timeout": mineru_ocr_timeout,
        "disable_ocr": ocr_backend == "none",
        "ocr_quality": ocr_quality or "auto",
        "ocr_dpi_override": ocr_dpi_override,
        "ocr_preprocess_backend": ocr_preprocess_backend or "none",
        "chrome_screenai_light": chrome_screenai_light,
        "chrome_preprocess_mode": chrome_preprocess_mode or "native",
        "chrome_workers": int(chrome_workers or 4),
        "chrome_chunk_pages": int(chrome_chunk_pages or 4),
        "chrome_emit_searchable_pdf": chrome_emit_searchable_pdf,
        "chrome_rasterize_dpi": int(chrome_rasterize_dpi or 144),
        "chrome_model_dir": chrome_model_dir,
        "tesseract_cmd": tesseract_cmd,
        "tesseract_lang": tesseract_lang or "eng",
        "tesseract_oem": int(tesseract_oem or 1),
        "tesseract_psm": int(tesseract_psm or 7),
        "tesseract_timeout": int(tesseract_timeout or 30),
        "tesseract_omp_thread_limit": int(tesseract_omp_thread_limit or 1),
        "tesseract_tessdata_prefix": tesseract_tessdata_prefix,
        "paddle_ocr_lang": paddle_ocr_lang or "ch",
        "paddle_ocr_python": paddle_ocr_python,
        "paddle_ocr_version": paddle_ocr_version or "PP-OCRv5",
        "paddle_ocr_device": paddle_ocr_device,
        "paddle_ocr_engine": paddle_ocr_engine,
        "paddle_ocr_enable_mkldnn": paddle_ocr_enable_mkldnn,
        "paddle_ocr_cpu_threads": paddle_ocr_cpu_threads,
        "paddle_ocr_use_doc_orientation_classify": paddle_ocr_use_doc_orientation_classify,
        "paddle_ocr_use_doc_unwarping": paddle_ocr_use_doc_unwarping,
        "paddle_ocr_use_textline_orientation": paddle_ocr_use_textline_orientation,
        "indra_python": indra_python,
        "indra_model_dir": indra_model_dir,
        "indra_mode": indra_mode or "auto",
        "indra_dpi": indra_dpi,
        "indra_math": indra_math,
        "indra_cores": indra_cores,
        "indra_allow_download": indra_allow_download,
        "indra_cache_dir": indra_cache_dir,
        "indra_review_mean": indra_review_mean,
        "indra_review_min": indra_review_min,
        "equation_output_mode": equation_output_mode or "humanities_safe",
        "emit_middle_json": bool(emit_middle_json),
        "emit_middle_report": bool(emit_middle_report),
        "emit_middle_debug": bool(emit_middle_debug),
        "emit_middle_scholarly": bool(emit_middle_scholarly),
        "emit_middle_scholarly_report": bool(emit_middle_scholarly_report),
        "emit_layout_overlay": bool(emit_layout_overlay),
        "emit_span_overlay": bool(emit_span_overlay),
        "emit_middle_full_json": bool(emit_middle_full_json),
        "pdftext_workers": 1,
    }
    options = _normalize_pipeline_ocr_options(options)
    if (
        resolved_layout_backend == "paddle_pp_doclayout_v3"
        and options.get("paddle_layout_model_name") == "PP-DocLayout_plus-L"
    ):
        options["paddle_layout_model_name"] = "PP-DocLayoutV3"
    try:
        job = ContextureJob.from_dict(
            {
                "input_bytes": file_contents,
                "input_name": file.filename,
                "mode": "pipeline",
                "output_formats": [output_format],
                "page_range": page_range,
                "config": options,
            }
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await _run_job_response(job, output_format)


@click.command()
@click.option("--port", type=int, default=8000, help="Port to run the server on")
@click.option("--host", type=str, default="127.0.0.1", help="Host to run the server on")
def server_cli(port: int, host: str):
    import uvicorn

    # Run the server
    uvicorn.run(
        app,
        host=host,
        port=port,
    )

if __name__ == "__main__":
    server_cli()
