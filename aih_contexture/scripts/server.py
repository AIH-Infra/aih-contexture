import click

from pydantic import BaseModel, Field
from starlette.responses import HTMLResponse

import base64
from contextlib import asynccontextmanager
from typing import Optional, Annotated, Any
import io

from fastapi import FastAPI, Form, File, UploadFile
from aih_contexture.backends.catalog import backend_catalog
from aih_contexture.backends.external_config import default_mineru_command, default_mineru_python
from aih_contexture.models import create_model_dict
from aih_contexture.runtime.job import ContextureJob, ContextureResult
from aih_contexture.runtime.runner import run_job
from aih_contexture.settings import settings
from aih_contexture.logger import get_logger

app_data = {}
logger = get_logger()


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
        Field(description="Pipeline layout backend. Current implemented values: surya, vlm_layout, external_layout_sidecar, mineru_pp_doclayout_v2, mineru_pp_doclayout_v2_direct, paddle_pp_doclayout_plus_l, paddle_pp_doclayout_v3."),
    ] = "surya"
    surya_layout_quality: Annotated[
        str,
        Field(description="Surya layout quality preset: fast, standard, or high."),
    ] = "fast"
    layout_dpi_override: Annotated[
        Optional[int],
        Field(description="Advanced override for layout render DPI."),
    ] = None
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
        Field(description="MinerU executable path or command name for mineru_pp_doclayout_v2."),
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
        Field(description="Optional MinerU sidecar Python executable for mineru_pp_doclayout_v2_direct."),
    ] = None
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
    ] = 1
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
    paddle_layout_python: Annotated[
        Optional[str],
        Field(description="Optional external Python executable for Paddle layout sidecar."),
    ] = None
    paddle_layout_model_dir: Annotated[
        Optional[str],
        Field(description="Optional local PaddleOCR layout model directory."),
    ] = None
    paddle_layout_device: Annotated[
        Optional[str],
        Field(description="Optional PaddleOCR device, e.g. cpu, gpu, gpu:0."),
    ] = None
    paddle_layout_engine: Annotated[
        Optional[str],
        Field(description="Optional PaddleOCR inference engine, e.g. paddle, paddle_static, or paddle_dynamic."),
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
        Field(description="Pipeline OCR backend. Current implemented values: surya, calamari, vlm_ocr, paddle_ocr_v5, tesseract. Any selected backend forces OCR; use 'none' for the embedded PDF text layer."),
    ] = "surya"
    ocr_quality: Annotated[
        str,
        Field(description="OCR quality preset: auto, low, medium, or high."),
    ] = "auto"
    ocr_dpi_override: Annotated[
        Optional[int],
        Field(description="Advanced override for OCR render DPI."),
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


async def _convert_pdf(params: CommonParams):
    assert params.output_format in ["markdown", "json", "html", "chunks"], (
        "Invalid output format"
    )
    options = params.model_dump()
    if not options.get("mineru_command") or options.get("mineru_command") == "mineru":
        options["mineru_command"] = default_mineru_command()
    if not options.get("mineru_layout_python"):
        options["mineru_layout_python"] = default_mineru_python()
    if options.get("ocr_backend") == "none":
        options["ocr_backend"] = "surya"
        options["disable_ocr"] = True
    if (
        options.get("layout_backend") == "paddle_pp_doclayout_v3"
        and options.get("paddle_layout_model_name") == "PP-DocLayout_plus-L"
    ):
        options["paddle_layout_model_name"] = "PP-DocLayoutV3"
    options["pdftext_workers"] = 1
    job = ContextureJob.from_dict(
        {
            "input_path": params.filepath,
            "mode": "pipeline",
            "output_formats": [params.output_format],
            "page_range": params.page_range,
            "config": options,
        }
    )
    return _run_job_response(job, params.output_format)


def _run_job_response(job: ContextureJob, output_format: str) -> dict:
    try:
        result = run_job(job, artifact_dict=app_data["models"])
        text = _result_text(result, output_format)
        images = result.images
        metadata = result.metadata
        middle_json = result.middle_json
    except Exception as e:
        logger.exception("Runtime conversion failed for mode=%s output_format=%s", job.mode, output_format)
        return {
            "success": False,
            "error": str(e),
        }

    encoded = {}
    for k, v in images.items():
        byte_stream = io.BytesIO()
        v.save(byte_stream, format=settings.OUTPUT_IMAGE_FORMAT)
        encoded[k] = base64.b64encode(byte_stream.getvalue()).decode(
            settings.OUTPUT_ENCODING
        )

    return {
        "format": output_format,
        "output": text,
        "images": encoded,
        "metadata": metadata,
        "middle_json": middle_json,
        "success": True,
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
        case _:
            return ""


@app.post("/marker")
async def convert_pdf(params: CommonParams):
    return await _convert_pdf(params)


@app.post("/v1/convert")
async def convert_runtime(params: RuntimeConvertParams):
    output_formats = params.output_formats or [params.output_format]
    job = ContextureJob.from_dict(
        {
            "input_path": params.filepath,
            "mode": params.mode,
            "output_formats": output_formats,
            "page_range": params.page_range,
            "config": params.config,
        }
    )
    return _run_job_response(job, output_formats[0] if output_formats else "markdown")


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
    mineru_layout_batch_size: Optional[int] = Form(default=1),
    mineru_layout_use_paddlex_filter_boxes: bool = Form(default=False),
    mineru_layout_timeout: Optional[int] = Form(default=3600),
    paddle_layout_model_name: Optional[str] = Form(default="PP-DocLayout_plus-L"),
    paddle_layout_python: Optional[str] = Form(default=None),
    paddle_layout_model_dir: Optional[str] = Form(default=None),
    paddle_layout_device: Optional[str] = Form(default=None),
    paddle_layout_engine: Optional[str] = Form(default=None),
    paddle_layout_enable_mkldnn: bool = Form(default=False),
    paddle_layout_cpu_threads: Optional[int] = Form(default=None),
    paddle_layout_threshold: Optional[float] = Form(default=None),
    paddle_layout_img_size: Optional[int] = Form(default=None),
    ocr_backend: Optional[str] = Form(default="surya"),
    ocr_quality: Optional[str] = Form(default="auto"),
    ocr_dpi_override: Optional[int] = Form(default=None),
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
    emit_middle_json: Optional[bool] = Form(default=False),
    emit_middle_report: Optional[bool] = Form(default=False),
    emit_middle_debug: Optional[bool] = Form(default=False),
    emit_middle_scholarly: Optional[bool] = Form(default=False),
    emit_middle_scholarly_report: Optional[bool] = Form(default=False),
    emit_layout_overlay: Optional[bool] = Form(default=False),
    emit_span_overlay: Optional[bool] = Form(default=False),
    file: UploadFile = File(
        ..., description="The PDF file to convert.", media_type="application/pdf"
    ),
):
    output_format = output_format or "markdown"
    assert output_format in ["markdown", "json", "html", "chunks"], (
        "Invalid output format"
    )
    file_contents = await file.read()
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
        "mineru_layout_python": mineru_layout_python or default_mineru_python(),
        "mineru_layout_model_dir": mineru_layout_model_dir,
        "mineru_layout_device": mineru_layout_device,
        "mineru_layout_batch_size": int(mineru_layout_batch_size or 1),
        "mineru_layout_use_paddlex_filter_boxes": mineru_layout_use_paddlex_filter_boxes,
        "mineru_layout_timeout": int(mineru_layout_timeout or 3600),
        "paddle_layout_model_name": paddle_layout_model_name or default_paddle_model,
        "paddle_layout_python": paddle_layout_python,
        "paddle_layout_model_dir": paddle_layout_model_dir,
        "paddle_layout_device": paddle_layout_device,
        "paddle_layout_engine": paddle_layout_engine,
        "paddle_layout_enable_mkldnn": paddle_layout_enable_mkldnn,
        "paddle_layout_cpu_threads": paddle_layout_cpu_threads,
        "paddle_layout_threshold": paddle_layout_threshold,
        "paddle_layout_img_size": paddle_layout_img_size,
        "ocr_backend": "surya" if ocr_backend == "none" else (ocr_backend or "surya"),
        "disable_ocr": ocr_backend == "none",
        "ocr_quality": ocr_quality or "auto",
        "ocr_dpi_override": ocr_dpi_override,
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
        "emit_middle_json": bool(emit_middle_json),
        "emit_middle_report": bool(emit_middle_report),
        "emit_middle_debug": bool(emit_middle_debug),
        "emit_middle_scholarly": bool(emit_middle_scholarly),
        "emit_middle_scholarly_report": bool(emit_middle_scholarly_report),
        "emit_layout_overlay": bool(emit_layout_overlay),
        "emit_span_overlay": bool(emit_span_overlay),
        "pdftext_workers": 1,
    }
    if (
        resolved_layout_backend == "paddle_pp_doclayout_v3"
        and options.get("paddle_layout_model_name") == "PP-DocLayout_plus-L"
    ):
        options["paddle_layout_model_name"] = "PP-DocLayoutV3"
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
    return _run_job_response(job, output_format)


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
