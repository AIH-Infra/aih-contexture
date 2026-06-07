import json
import os
from typing import Dict

import click

from aih_contexture.converters.pdf import PdfConverter
from aih_contexture.logger import get_logger
from aih_contexture.renderers.chunk import ChunkRenderer
from aih_contexture.renderers.html import HTMLRenderer
from aih_contexture.renderers.json import JSONRenderer
from aih_contexture.renderers.markdown import MarkdownRenderer
from aih_contexture.settings import settings
from aih_contexture.util import classes_to_strings, parse_range_str, strings_to_classes

logger = get_logger()


class ConfigParser:
    def __init__(self, cli_options: dict):
        self.cli_options = cli_options

    @staticmethod
    def common_options(fn):
        fn = click.option(
            "--output_dir",
            type=click.Path(exists=False),
            required=False,
            default=settings.OUTPUT_DIR,
            help="Directory to save output.",
        )(fn)
        fn = click.option("--debug", "-d", is_flag=True, help="Enable debug mode.")(fn)
        fn = click.option(
            "--output_format",
            type=click.Choice(["markdown", "json", "html", "chunks"]),
            default="markdown",
            help="Format to output results in.",
        )(fn)
        fn = click.option(
            "--processors",
            type=str,
            default=None,
            help="Comma separated list of processors to use.  Must use full module path.",
        )(fn)
        fn = click.option(
            "--config_json",
            type=str,
            default=None,
            help="Path to JSON file with additional configuration.",
        )(fn)
        fn = click.option(
            "--disable_multiprocessing",
            is_flag=True,
            default=False,
            help="Disable multiprocessing.",
        )(fn)
        fn = click.option(
            "--disable_image_extraction",
            is_flag=True,
            default=False,
            help="Disable image extraction.",
        )(fn)
        fn = click.option(
            "--layout_backend",
            type=str,
            default="surya",
            help="Pipeline layout backend. Current implemented values: surya, vlm_layout, external_layout_sidecar, mineru_pp_doclayout_v2, mineru_pp_doclayout_v2_direct, paddle_pp_doclayout_plus_l, paddle_pp_doclayout_v3.",
        )(fn)
        fn = click.option(
            "--surya_layout_quality",
            type=click.Choice(["fast", "standard", "high"]),
            default="fast",
            help="Surya layout render quality preset. Ignored by non-Surya layout backends unless layout_dpi_override is set.",
        )(fn)
        fn = click.option(
            "--layout_dpi_override",
            type=int,
            default=None,
            help="Advanced override for layout render DPI.",
        )(fn)
        fn = click.option(
            "--external_layout_json",
            type=click.Path(exists=False),
            default=None,
            help="Path to a MinerU/Paddle/generic layout JSON file or Contexture Middle JSON file for external_layout_sidecar.",
        )(fn)
        fn = click.option(
            "--external_layout_block_source",
            type=str,
            default="auto",
            help="Block list to read from external layout JSON: auto, all, blocks, layout_bboxes, boxes, bboxes, layout, regions, para_blocks, preproc_blocks, or discarded_blocks.",
        )(fn)
        fn = click.option(
            "--external_layout_backend_name",
            type=str,
            default="external_layout_sidecar",
            help="Backend name recorded in provenance when importing raw external layout JSON.",
        )(fn)
        fn = click.option(
            "--external_layout_model",
            type=str,
            default=None,
            help="Model name recorded in provenance when importing raw external layout JSON.",
        )(fn)
        fn = click.option(
            "--external_layout_allow_missing_pages",
            is_flag=True,
            default=False,
            help="Allow sidecar JSON to omit pages; missing pages fall back to one full-page Text block.",
        )(fn)
        fn = click.option(
            "--mineru_command",
            type=str,
            default=None,
            help="MinerU executable path or command name for mineru_pp_doclayout_v2. Defaults to CONTEXTURE_MINERU_COMMAND or PATH.",
        )(fn)
        fn = click.option(
            "--mineru_output_dir",
            type=click.Path(exists=False),
            default=None,
            help="Directory for MinerU raw outputs. Defaults to a temporary directory.",
        )(fn)
        fn = click.option(
            "--mineru_backend",
            type=str,
            default="pipeline",
            help="MinerU backend passed to -b. Default: pipeline.",
        )(fn)
        fn = click.option(
            "--mineru_method",
            type=str,
            default="txt",
            help="MinerU parse method passed to -m: txt, ocr, or auto. Default: txt.",
        )(fn)
        fn = click.option(
            "--mineru_lang",
            type=str,
            default="ch",
            help="MinerU language passed to -l. Default: ch.",
        )(fn)
        fn = click.option(
            "--mineru_api_url",
            type=str,
            default=None,
            help="Optional MinerU API URL passed to --api-url.",
        )(fn)
        fn = click.option(
            "--mineru_server_url",
            type=str,
            default=None,
            help="Optional MinerU VLM/hybrid server URL passed to -u.",
        )(fn)
        fn = click.option(
            "--mineru_timeout",
            type=int,
            default=3600,
            help="MinerU CLI timeout in seconds.",
        )(fn)
        fn = click.option(
            "--mineru_extra_args",
            type=str,
            default=None,
            help="Extra arguments appended to the MinerU CLI command.",
        )(fn)
        fn = click.option(
            "--mineru_layout_python",
            type=click.Path(exists=False),
            default=None,
            help="Optional MinerU sidecar Python executable for mineru_pp_doclayout_v2_direct. Defaults to CONTEXTURE_MINERU_PYTHON.",
        )(fn)
        fn = click.option(
            "--mineru_layout_model_dir",
            type=click.Path(exists=False),
            default=None,
            help="Optional local MinerU PP-DocLayoutV2 model directory.",
        )(fn)
        fn = click.option(
            "--mineru_layout_device",
            type=str,
            default=None,
            help="Optional MinerU direct layout device, e.g. cpu, cuda, cuda:0.",
        )(fn)
        fn = click.option(
            "--mineru_layout_batch_size",
            type=int,
            default=None,
            help="Batch size for MinerU PP-DocLayoutV2 direct layout inference.",
        )(fn)
        fn = click.option(
            "--mineru_layout_use_paddlex_filter_boxes/--no_mineru_layout_use_paddlex_filter_boxes",
            default=None,
            help="Enable or disable MinerU/PaddleX-style layout box filtering for direct layout inference.",
        )(fn)
        fn = click.option(
            "--mineru_layout_timeout",
            type=int,
            default=None,
            help="MinerU direct layout sidecar timeout in seconds.",
        )(fn)
        fn = click.option(
            "--paddle_layout_python",
            type=click.Path(exists=False),
            default=None,
            help="Optional external Python executable for Paddle layout sidecar. Defaults to CONTEXTURE_PADDLE_PYTHON.",
        )(fn)
        fn = click.option(
            "--paddle_layout_model_name",
            type=str,
            default=None,
            help="PaddleOCR LayoutDetection model name. Defaults to PP-DocLayout_plus-L or PP-DocLayoutV3 from --layout_backend.",
        )(fn)
        fn = click.option(
            "--paddle_layout_model_dir",
            type=click.Path(exists=False),
            default=None,
            help="Optional local PaddleOCR layout model directory.",
        )(fn)
        fn = click.option(
            "--paddle_layout_device",
            type=str,
            default=None,
            help="Optional PaddleOCR device, e.g. cpu, gpu, gpu:0.",
        )(fn)
        fn = click.option(
            "--paddle_layout_engine",
            type=str,
            default=None,
            help="Optional PaddleOCR inference engine, e.g. paddle, paddle_static, or paddle_dynamic.",
        )(fn)
        fn = click.option(
            "--paddle_layout_enable_mkldnn/--no_paddle_layout_enable_mkldnn",
            default=None,
            help="Enable or disable PaddleOCR MKL-DNN acceleration for layout detection. Defaults to disabled for runtime stability.",
        )(fn)
        fn = click.option(
            "--paddle_layout_cpu_threads",
            type=int,
            default=None,
            help="Optional CPU thread count for PaddleOCR layout detection.",
        )(fn)
        fn = click.option(
            "--paddle_layout_threshold",
            type=float,
            default=None,
            help="Optional PaddleOCR layout confidence threshold.",
        )(fn)
        fn = click.option(
            "--paddle_layout_img_size",
            type=int,
            default=None,
            help="Optional PaddleOCR layout input image size.",
        )(fn)
        fn = click.option(
            "--ocr_backend",
            type=str,
            default="surya",
            help="Pipeline OCR backend. Current implemented values: surya, calamari, vlm_ocr, paddle_ocr_v5, paddleocr_vl_ocr, tesseract, none. Any selected OCR backend forces OCR; use none or --disable_ocr for the embedded PDF text layer.",
        )(fn)
        fn = click.option(
            "--ocr_quality",
            type=click.Choice(["auto", "low", "medium", "high"]),
            default="auto",
            help="OCR render quality preset. auto uses backend defaults: Surya/Paddle low, Tesseract/Calamari medium.",
        )(fn)
        fn = click.option(
            "--ocr_dpi_override",
            type=int,
            default=None,
            help="Advanced override for OCR render DPI.",
        )(fn)
        fn = click.option("--tesseract_cmd", type=str, default=None, help="Optional Tesseract executable path. Defaults to CONTEXTURE_TESSERACT_CMD or PATH.")(fn)
        fn = click.option("--tesseract_lang", type=str, default=None, help="Tesseract language expression, e.g. eng or chi_sim+eng.")(fn)
        fn = click.option("--tesseract_oem", type=int, default=None, help="Tesseract OCR Engine Mode. Default: 1.")(fn)
        fn = click.option("--tesseract_psm", type=int, default=None, help="Tesseract Page Segmentation Mode. Default: 7 for line crops.")(fn)
        fn = click.option("--tesseract_timeout", type=int, default=None, help="Tesseract per-line timeout in seconds.")(fn)
        fn = click.option("--tesseract_omp_thread_limit", type=int, default=None, help="OMP_THREAD_LIMIT for Tesseract subprocesses.")(fn)
        fn = click.option("--tesseract_tessdata_prefix", type=str, default=None, help="Optional TESSDATA_PREFIX for Tesseract language data.")(fn)
        fn = click.option("--ocr_crop_preprocess", type=str, default=None, help="Line crop preprocessing for OCR: none, otsu, adaptive.")(fn)
        fn = click.option(
            "--paddle_ocr_python",
            type=click.Path(exists=False),
            default=None,
            help="Optional external Python executable for Paddle OCR sidecar. Defaults to CONTEXTURE_PADDLE_PYTHON.",
        )(fn)
        fn = click.option(
            "--paddle_ocr_lang",
            type=str,
            default=None,
            help="PaddleOCR language for ocr_backend=paddle_ocr_v5. Default: ch.",
        )(fn)
        fn = click.option(
            "--paddle_ocr_version",
            type=str,
            default=None,
            help="PaddleOCR version for ocr_backend=paddle_ocr_v5. Default: PP-OCRv5.",
        )(fn)
        fn = click.option(
            "--paddle_ocr_device",
            type=str,
            default=None,
            help="Optional PaddleOCR device, e.g. cpu, gpu, gpu:0.",
        )(fn)
        fn = click.option(
            "--paddle_ocr_engine",
            type=str,
            default=None,
            help="Optional PaddleOCR inference engine.",
        )(fn)
        fn = click.option(
            "--paddle_ocr_enable_mkldnn/--no_paddle_ocr_enable_mkldnn",
            default=None,
            help="Enable or disable PaddleOCR MKL-DNN acceleration. Defaults to disabled for runtime stability.",
        )(fn)
        fn = click.option(
            "--paddle_ocr_cpu_threads",
            type=int,
            default=None,
            help="Optional CPU thread count for PaddleOCR.",
        )(fn)
        fn = click.option(
            "--paddle_ocr_use_doc_orientation_classify/--no_paddle_ocr_use_doc_orientation_classify",
            default=None,
            help="Enable or disable PaddleOCR document orientation classifier. Defaults to disabled.",
        )(fn)
        fn = click.option(
            "--paddle_ocr_use_doc_unwarping/--no_paddle_ocr_use_doc_unwarping",
            default=None,
            help="Enable or disable PaddleOCR document unwarping. Defaults to disabled.",
        )(fn)
        fn = click.option(
            "--paddle_ocr_use_textline_orientation/--no_paddle_ocr_use_textline_orientation",
            default=None,
            help="Enable or disable PaddleOCR text-line orientation classifier. Defaults to disabled.",
        )(fn)
        fn = click.option("--paddleocr_vl_endpoint", type=str, default=None, help="PaddleOCR-VL OpenAI-compatible endpoint for VLM prompt or ocr_backend=paddleocr_vl_ocr.")(fn)
        fn = click.option("--paddleocr_vl_layout_parsing_url", type=str, default=None, help="Official PaddleOCR-VL /layout-parsing endpoint for vlm_specialized:paddleocr_vl.")(fn)
        fn = click.option("--paddleocr_vl_model", type=str, default=None, help="PaddleOCR-VL model name for prompt-based VLM/OCR calls.")(fn)
        fn = click.option("--paddleocr_vl_api_key", type=str, default=None, help="PaddleOCR-VL API key.")(fn)
        fn = click.option("--paddleocr_vl_api_style", type=str, default=None, help="PaddleOCR-VL API style: openai or lmstudio-native.")(fn)
        fn = click.option("--paddleocr_vl_mode", type=str, default=None, help="PaddleOCR-VL mode: auto, layout_parsing, or vl_prompt.")(fn)
        fn = click.option("--paddleocr_vl_version", type=str, default=None, help="PaddleOCR-VL model version, e.g. 1.5 or 1.6.")(fn)
        fn = click.option("--paddleocr_vl_request_concurrency", type=int, default=None, help="Concurrent PaddleOCR-VL VLM/API requests.")(fn)
        fn = click.option("--paddleocr_vl_block_concurrency", type=int, default=None, help="Concurrent PaddleOCR-VL block OCR requests.")(fn)
        fn = click.option("--paddleocr_vl_prompt_label", type=str, default=None, help="PaddleOCR-VL prompt task label for prompt fallback: layout_detection, ocr, table, formula, chart, seal, or spotting.")(fn)
        fn = click.option("--paddleocr_vl_image_format", type=str, default=None, help="Image transport format for PaddleOCR-VL prompt/layout requests, e.g. JPEG or PNG.")(fn)
        fn = click.option("--paddleocr_vl_image_quality", type=int, default=None, help="Image quality for JPEG/WEBP PaddleOCR-VL requests.")(fn)
        fn = click.option("--paddleocr_vl_crop_padding_px", type=int, default=None, help="Pixel padding around Pipeline layout block crops for PaddleOCR-VL OCR.")(fn)
        fn = click.option("--paddleocr_vl_crop_padding_frac", type=float, default=None, help="Fractional padding around Pipeline layout block crops for PaddleOCR-VL OCR.")(fn)
        fn = click.option(
            "--disable_ocr",
            is_flag=True,
            default=False,
            help="Disable OCR and use embedded PDF text where available.",
        )(fn)
        fn = click.option(
            "--emit_middle_json",
            is_flag=True,
            default=False,
            help="Emit the core Contexture Middle JSON alongside the selected output.",
        )(fn)
        fn = click.option(
            "--emit_middle_report",
            is_flag=True,
            default=False,
            help="Emit a Middle JSON validation report.",
        )(fn)
        fn = click.option(
            "--emit_middle_debug",
            is_flag=True,
            default=False,
            help="Emit a debug Markdown rendering of Middle JSON.",
        )(fn)
        fn = click.option(
            "--emit_middle_scholarly",
            is_flag=True,
            default=False,
            help="Emit scholarly Markdown rendered from Middle JSON.",
        )(fn)
        fn = click.option(
            "--emit_middle_scholarly_report",
            is_flag=True,
            default=False,
            help="Emit a quality report for scholarly Markdown rendered from Middle JSON.",
        )(fn)
        fn = click.option(
            "--emit_layout_overlay",
            is_flag=True,
            default=False,
            help="Emit layout bbox overlay PNG/PDF artifacts when Middle JSON is available.",
        )(fn)
        fn = click.option(
            "--emit_span_overlay",
            is_flag=True,
            default=False,
            help="Emit span bbox overlay PNG/PDF artifacts when Middle JSON spans are available.",
        )(fn)
        # these are options that need a list transformation, i.e splitting/parsing a string
        fn = click.option(
            "--page_range",
            type=str,
            default=None,
            help="Page range to convert, specify comma separated page numbers or ranges.  Example: 0,5-10,20",
        )(fn)

        # we put common options here
        fn = click.option(
            "--converter_cls",
            type=str,
            default=None,
            help="Converter class to use.  Defaults to PDF converter.",
        )(fn)
        fn = click.option(
            "--llm_service",
            type=str,
            default=None,
            help="LLM service to use - should be full import path, like aih_contexture.services.gemini.GoogleGeminiService",
        )(fn)
        return fn

    def generate_config_dict(self) -> Dict[str, any]:
        config = {}
        output_dir = self.cli_options.get("output_dir", settings.OUTPUT_DIR)
        for k, v in self.cli_options.items():
            # 🔧 修复：不要过滤 False 值，因为处理器配置需要 False 来禁用
            # 只跳过 None 和空字符串
            if v is None or v == "":
                continue

            match k:
                case "debug":
                    config["debug_pdf_images"] = True
                    config["debug_layout_images"] = True
                    config["debug_json"] = True
                    config["debug_data_folder"] = output_dir
                case "page_range":
                    config["page_range"] = v if isinstance(v, list) else parse_range_str(v)
                case "config_json":
                    with open(v, "r", encoding="utf-8") as f:
                        config.update(json.load(f))
                case "disable_multiprocessing":
                    config["pdftext_workers"] = 1
                case "disable_image_extraction":
                    config["extract_images"] = False
                case "disable_ocr":
                    if v:
                        config["disable_ocr"] = True
                    else:
                        config.setdefault("disable_ocr", False)
                case "emit_layout_overlay":
                    config["emit_layout_overlay"] = bool(v)
                    if v:
                        config["emit_middle_json"] = True
                case "emit_span_overlay":
                    config["emit_span_overlay"] = bool(v)
                    if v:
                        config["emit_middle_json"] = True
                case "emit_middle_report" | "emit_middle_debug" | "emit_middle_scholarly" | "emit_middle_scholarly_report":
                    config[k] = bool(v)
                    if v:
                        config["emit_middle_json"] = True
                case "ocr_backend":
                    if str(v).strip().lower() == "none":
                        config["ocr_backend"] = "surya"
                        config["disable_ocr"] = True
                    else:
                        config["ocr_backend"] = v
                case _:
                    config[k] = v

        # Backward compatibility for google_api_key
        if settings.GOOGLE_API_KEY:
            config["gemini_api_key"] = settings.GOOGLE_API_KEY

        ocr_backend = str(config.get("ocr_backend") or "surya").strip().lower().replace("-", "_")
        disable_ocr = bool(config.get("disable_ocr", False))
        if disable_ocr:
            config["force_ocr"] = False
        else:
            config["ocr_backend"] = ocr_backend
            config["force_ocr"] = True
            if ocr_backend == "calamari":
                config["ocr_line_source"] = "tesseract"

        return config

    def get_llm_service(self):
        # Only return an LLM service when use_llm is enabled
        if not self.cli_options.get("use_llm", False):
            return None

        service_cls = self.cli_options.get("llm_service", None)
        if service_cls is None:
            service_cls = "aih_contexture.services.gemini.GoogleGeminiService"
        return service_cls

    def get_renderer(self):
        match self.cli_options["output_format"]:
            case "json":
                r = JSONRenderer
            case "markdown":
                r = MarkdownRenderer
            case "html":
                r = HTMLRenderer
            case "chunks":
                r = ChunkRenderer
            case _:
                raise ValueError("Invalid output format")
        return classes_to_strings([r])[0]

    def get_processors(self):
        processors = self.cli_options.get("processors", None)
        if processors is not None:
            processors = processors.split(",")
            for p in processors:
                try:
                    strings_to_classes([p])
                except Exception as e:
                    logger.error(f"Error loading processor: {p} with error: {e}")
                    raise

        return processors

    def get_converter_cls(self):
        converter_cls = self.cli_options.get("converter_cls", None)
        if converter_cls is not None:
            try:
                return strings_to_classes([converter_cls])[0]
            except Exception as e:
                logger.error(
                    f"Error loading converter: {converter_cls} with error: {e}"
                )
                raise

        return PdfConverter

    def get_output_folder(self, filepath: str):
        output_dir = self.cli_options.get("output_dir", settings.OUTPUT_DIR)
        fname_base = os.path.splitext(os.path.basename(filepath))[0]
        output_dir = os.path.join(output_dir, fname_base)
        os.makedirs(output_dir, exist_ok=True)
        return output_dir

    def get_base_filename(self, filepath: str):
        basename = os.path.basename(filepath)
        return os.path.splitext(basename)[0]
