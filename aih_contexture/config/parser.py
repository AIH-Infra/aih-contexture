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
from aih_contexture.runtime.output_contract import document_output_folder, document_output_basename
from aih_contexture.util import classes_to_strings, parse_range_str, strings_to_classes

logger = get_logger()


class ConfigParser:
    def __init__(self, cli_options: dict, *, explicit_options=None, click_context=None):
        self.cli_options = dict(cli_options or {})
        self._explicit_options, self._click_defaults = self._resolve_option_sources(
            explicit_options, click_context
        )
        self._effective_options = None

    @classmethod
    def from_click(cls, cli_options: dict, *, context=None):
        """Build a parser using Click's actual parameter sources.

        Call this only from a Click callback. Ordinary ConfigParser instances
        treat their supplied mapping as explicit, even if created while an
        unrelated Click context happens to be active.
        """
        context = context or click.get_current_context(silent=True)
        return cls(cli_options, click_context=context)

    def _resolve_option_sources(self, explicit_options, click_context):
        """Return explicit and Click-default option names.

        API and internal callers have no Click parameter source, so every value
        they pass is an explicit option. During a matching Click invocation,
        Click defaults form the lowest-precedence layer, followed by config_json
        and then command line/environment/prompt values.
        """
        if explicit_options is not None:
            if isinstance(explicit_options, dict):
                return (
                    {key for key, is_explicit in explicit_options.items() if is_explicit},
                    set(),
                )
            return set(explicit_options), set()

        context = click_context
        if context is None:
            return set(self.cli_options), set()

        context_params = getattr(context, "params", {}) or {}
        matching_params = set(context_params).intersection(self.cli_options)
        if not matching_params:
            return set(self.cli_options), set()

        explicit = set()
        defaults = set()
        for key in self.cli_options:
            if key not in context_params:
                # Preserve caller-supplied/internal configuration values that
                # are not Click parameters.
                explicit.add(key)
                continue
            source = context.get_parameter_source(key)
            if source == click.core.ParameterSource.DEFAULT:
                defaults.add(key)
            else:
                explicit.add(key)
        return explicit, defaults

    def get_effective_options(self) -> dict:
        """Return options merged as JSON configuration, then explicit options.

        Click-injected defaults are omitted from the override layer, preventing
        defaults such as output_format=markdown from masking an explicit value
        in config_json. False values are retained so negative boolean flags and
        explicit API configuration remain effective.
        """
        if self._effective_options is not None:
            return dict(self._effective_options)

        # Click defaults remain available when no JSON value replaces them.
        # This preserves the CLI's normal behavior while giving the file
        # priority over an injected default.
        effective = {
            key: self.cli_options[key]
            for key in self._click_defaults
            if key in self.cli_options
            and key != "config_json"
            and self.cli_options[key] is not None
            and self.cli_options[key] != ""
        }
        config_json = self.cli_options.get("config_json")
        if config_json:
            with open(config_json, "r", encoding="utf-8") as f:
                file_options = json.load(f)
            if not isinstance(file_options, dict):
                raise ValueError(
                    f"Configuration JSON must contain an object: {config_json}"
                )
            effective.update(
                {
                    key: value
                    for key, value in file_options.items()
                    if value is not None and value != ""
                }
            )

        for key in self._explicit_options:
            if key == "config_json" or key not in self.cli_options:
                continue
            value = self.cli_options[key]
            # Empty/None values mean unspecified; False remains meaningful.
            if value is None or value == "":
                continue
            effective[key] = value

        effective.pop("config_json", None)
        self._effective_options = effective
        return dict(effective)

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
            help="Pipeline layout backend. Current implemented values: surya, vlm_layout, external_layout_sidecar, mineru_pp_doclayout_v2_direct, mineru_vl_layout, surya2_layout, paddle_pp_doclayout_plus_l, paddle_pp_doclayout_v3, indra_layout (Indra labels + reading order; pair with --disable_ocr / chrome_screenai / another OCR, or with indra_ocr for the direct CPU route).",
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
            help="Legacy MinerU executable path for full-pipeline diagnostic/import workflows. Not used by layout_backend=mineru_pp_doclayout_v2_direct.",
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
            help="Optional Python executable (with PyTorch) for the mineru_pp_doclayout_v2_direct layout sidecar. Defaults to CONTEXTURE_MINERU_LAYOUT_PYTHON, then this instance's GPU runtime env, then the interpreter running Contexture.",
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
        fn = click.option("--mineru_vl_endpoint", type=str, default=None, help="MinerU-VL layout/OCR endpoint.")(fn)
        fn = click.option("--mineru_vl_api_key", type=str, default=None, help="MinerU-VL API key.")(fn)
        fn = click.option("--mineru_vl_api_style", type=str, default=None, help="MinerU-VL API style: openai or lmstudio-native.")(fn)
        fn = click.option("--mineru_vl_version", type=str, default=None, help="MinerU-VL model version, e.g. 2.5pro-2605.")(fn)
        fn = click.option("--mineru_vl_quant", type=str, default=None, help="MinerU-VL model quant/spec, e.g. 1.2b.")(fn)
        fn = click.option("--mineru_vl_model", type=str, default=None, help="MinerU-VL model name.")(fn)
        fn = click.option("--mineru_vl_layout_timeout", type=int, default=None, help="MinerU-VL layout request timeout in seconds.")(fn)
        fn = click.option("--mineru_vl_layout_max_tokens", type=int, default=None, help="MinerU-VL layout max output tokens.")(fn)
        fn = click.option("--mineru_vl_layout_concurrency", type=int, default=None, help="MinerU-VL layout request concurrency.")(fn)
        fn = click.option("--mineru_vl_request_concurrency", type=int, default=None, help="MinerU-VL VLM request concurrency.")(fn)
        fn = click.option("--mineru_vl_image_quality", type=int, default=None, help="MinerU-VL image quality for encoded requests.")(fn)
        fn = click.option("--surya2_endpoint", type=str, default=None, help="Surya 2 OpenAI-compatible layout/OCR endpoint.")(fn)
        fn = click.option("--surya2_api_key", type=str, default=None, help="Surya 2 API key.")(fn)
        fn = click.option("--surya2_api_style", type=str, default=None, help="Surya 2 API style: openai or lmstudio-native.")(fn)
        fn = click.option("--surya2_version", type=str, default=None, help="Surya 2 model version. Default: 2.0.")(fn)
        fn = click.option("--surya2_model", type=str, default=None, help="Surya 2 model name. Default: surya-ocr-2-lmstudio.")(fn)
        fn = click.option("--surya2_layout_timeout", type=int, default=None, help="Surya 2 layout request timeout in seconds.")(fn)
        fn = click.option("--surya2_layout_max_tokens", type=int, default=None, help="Surya 2 layout max output tokens.")(fn)
        fn = click.option("--surya2_layout_concurrency", type=int, default=None, help="Surya 2 layout request concurrency. Recommended: 4-6 for LM Studio.")(fn)
        fn = click.option("--surya2_request_concurrency", type=int, default=None, help="Surya 2 VLM request concurrency. Recommended: 4-6 for layout-only LM Studio tests.")(fn)
        fn = click.option("--surya2_block_concurrency", type=int, default=None, help="Surya 2 block OCR crop concurrency.")(fn)
        fn = click.option("--surya2_image_format", type=str, default=None, help="Image transport format for Surya 2 requests, e.g. PNG or JPEG.")(fn)
        fn = click.option("--surya2_image_quality", type=int, default=None, help="Image quality for JPEG/WEBP Surya 2 requests.")(fn)
        fn = click.option("--surya2_crop_padding_px", type=int, default=None, help="Pixel padding around Pipeline layout block crops for Surya 2 OCR.")(fn)
        fn = click.option("--surya2_crop_padding_frac", type=float, default=None, help="Fractional padding around Pipeline layout block crops for Surya 2 OCR.")(fn)
        fn = click.option("--glm_ocr_endpoint", type=str, default=None, help="GLM-OCR OpenAI-compatible endpoint (e.g. LM Studio http://127.0.0.1:1234/v1).")(fn)
        fn = click.option("--glm_ocr_model", type=str, default=None, help="GLM-OCR model id on the service. Default: glm-ocr@q8_0.")(fn)
        fn = click.option("--glm_ocr_quant", type=str, default=None, help="GLM-OCR preset quantization when --glm_ocr_model is unset: f16 or q8_0.")(fn)
        fn = click.option("--glm_ocr_api_key", type=str, default=None, help="GLM-OCR API key.")(fn)
        fn = click.option("--glm_ocr_block_concurrency", type=int, default=None, help="GLM-OCR block crop concurrency. LM Studio measured 4 -> 8: 1.05 -> 1.39 blocks/s.")(fn)
        fn = click.option("--glm_ocr_timeout", type=int, default=None, help="GLM-OCR request timeout in seconds.")(fn)
        fn = click.option("--glm_ocr_max_tokens", type=int, default=None, help="GLM-OCR max output tokens per block; a cut-off block is marked ocr_failure.")(fn)
        fn = click.option("--glm_ocr_recognize_formulas", is_flag=True, default=False, help="Also send Equation blocks to GLM-OCR (formula prompt is not yet validated).")(fn)
        fn = click.option("--indra_python", type=click.Path(exists=False), default=None, help="Python executable of the Indra OCR environment (indra-ocr + onnxruntime). Defaults to CONTEXTURE_INDRA_PYTHON, else this interpreter if it can import indra_ocr.")(fn)
        fn = click.option("--indra_model_dir", type=click.Path(exists=False), default=None, help="Folder with Indra's det.onnx, rec.onnx, meta.json (order.onnx for layout). Defaults to INDRA_OCR_MODEL_DIR. Weights are not bundled.")(fn)
        fn = click.option("--indra_mode", type=click.Choice(["auto", "ocr", "text"]), default=None, help="Indra text source: auto trusts a verified PDF text layer and OCRs the rest; ocr always recognizes; text only reads the layer.")(fn)
        fn = click.option("--indra_dpi", type=int, default=None, help="Indra render DPI. Default 200.")(fn)
        fn = click.option("--indra_math", is_flag=True, default=False, help="Recognize formulas to LaTeX (needs the math model files in the model folder).")(fn)
        fn = click.option("--indra_cores", type=int, default=None, help="CPU cores for Indra. Default: planned from physical cores, free RAM (~1.5 GB per worker) and page count. A value beyond the safe limit is clamped with a note.")(fn)
        fn = click.option("--indra_allow_download", is_flag=True, default=False, help="Let Indra fetch its weights from Hugging Face when the model folder is missing. Off by default.")(fn)
        fn = click.option("--indra_cache_dir", type=click.Path(exists=False), default=None, help="Cache folder for per-page Indra results, keyed by PDF content, page and settings.")(fn)
        fn = click.option("--indra_review_mean", type=float, default=None, help="Flag an Indra page for review when its mean line confidence is below this. Default 0.92 (a starting point, not calibrated).")(fn)
        fn = click.option("--indra_review_min", type=float, default=None, help="Flag an Indra page for review when its worst line confidence is below this. Default 0.60 (a starting point, not calibrated).")(fn)
        fn = click.option("--mineru_ocr_python", type=click.Path(exists=False), default=None, help="Optional Python override for native Paddle OCR Torch. Defaults to Contexture's Python; MinerU is not required.")(fn)
        fn = click.option("--mineru_ocr_model_dir", type=click.Path(exists=False), default=None, help="Native Paddle OCR Torch weight folder. Existing local caches are reused when omitted.")(fn)
        fn = click.option("--mineru_ocr_version", type=click.Choice(["PP-OCRv5", "PP-OCRv6"]), default=None, help="Native Paddle OCR Torch model family. Default PP-OCRv5.")(fn)
        fn = click.option("--mineru_ocr_allow_download", is_flag=True, default=False, help="Explicitly allow downloading missing Paddle OCR Torch weights. Off by default.")(fn)
        fn = click.option("--mineru_ocr_lang", type=str, default=None, help="Native Paddle OCR Torch language profile. Default: ch.")(fn)
        fn = click.option("--mineru_ocr_device", type=str, default=None, help="Native Paddle OCR Torch device, e.g. cpu, cuda, cuda:0. Defaults to available Torch device.")(fn)
        fn = click.option("--mineru_ocr_timeout", type=int, default=None, help="MinerU OCR sidecar timeout in seconds.")(fn)
        fn = click.option("--paddle_layout_allow_download", is_flag=True, default=False, help="Explicitly allow downloading the optional native PP-DocLayoutV3 ONNX model. Off by default.")(fn)
        fn = click.option("--paddle_layout_batch_size", type=int, default=None, help="Layout inference batch size. Native PP-DocLayoutV3 CPU supports 1 to 8; default 1.")(fn)
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
            help="PP-DocLayoutV3 defaults to native CPU onnxruntime. Explicit paddle engines retain the SDK compatibility path.",
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
            help="Pipeline OCR backend. Current implemented values: surya, chrome_screenai, calamari, vlm_ocr, paddle_ocr_v5, paddleocr_vl_ocr, surya2_ocr, glm_ocr, mineru_pytorch_paddle_ocr, indra_ocr (any layout backend; with layout_backend=indra_layout too it runs the direct CPU route), tesseract, none. chrome_screenai first writes a searchable PDF, then re-enters Pipeline through embedded PDF text. Use none or --disable_ocr for the embedded PDF text layer.",
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
        fn = click.option(
            "--ocr_preprocess_backend",
            type=str,
            default="none",
            help="Compatibility option for hidden OCR preprocessing. Current implemented values: none, chrome_screenai_searchable_pdf. Prefer --ocr_backend=chrome_screenai.",
        )(fn)
        fn = click.option(
            "--chrome_screenai_light/--no_chrome_screenai_light",
            default=False,
            help="Enable Chrome ScreenAI light/fast mode for OCR preprocessing.",
        )(fn)
        fn = click.option(
            "--chrome_preprocess_mode",
            type=str,
            default="native",
            help="Chrome ScreenAI PDF preprocessing mode: native, strip_existing_ocr, rasterize_pdf, or strip_then_rasterize.",
        )(fn)
        fn = click.option(
            "--chrome_remove_annotations/--no_chrome_remove_annotations",
            default=True,
            help="Remove PDF annotations and links before ScreenAI recognition.",
        )(fn)
        fn = click.option(
            "--chrome_workers",
            type=int,
            default=4,
            help="Chrome ScreenAI OCR worker count for searchable-PDF preprocessing.",
        )(fn)
        fn = click.option(
            "--chrome_chunk_pages",
            type=int,
            default=4,
            help="Chrome ScreenAI page chunk size for searchable-PDF preprocessing.",
        )(fn)
        fn = click.option(
            "--chrome_emit_searchable_pdf/--no_chrome_emit_searchable_pdf",
            default=False,
            help="Export the intermediate Chrome ScreenAI searchable PDF as a pipeline artifact.",
        )(fn)
        fn = click.option(
            "--chrome_rasterize_dpi",
            type=int,
            default=144,
            help="Rasterization DPI when Chrome ScreenAI preprocessing mode uses rasterized PDF pages.",
        )(fn)
        fn = click.option(
            "--chrome_model_dir",
            type=click.Path(exists=False),
            default=None,
            help="Optional local Chrome ScreenAI model directory.",
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
        fn = click.option("--running_furniture_enabled", is_flag=True, default=False, help="Enable conservative running header/footer suppression.")(fn)
        fn = click.option("--text_layer_quality_enabled", type=bool, default=True, help="Record block-level text-layer quality diagnostics.")(fn)
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
            "--render_from_middle",
            is_flag=True,
            default=False,
            help="Validate generated Middle JSON and use it as the source for Markdown rendering.",
        )(fn)
        fn = click.option(
            "--emit_middle_report",
            is_flag=True,
            default=False,
            help="Emit a Middle JSON validation report.",
        )(fn)
        fn = click.option(
            '--emit_reading_diagnostics', '--reading-diagnostics',
            is_flag=True, default=False,
            help='Write separate reading diagnostics; disabled by default. Publication formats remain unchanged.',
        )(fn)
        fn = click.option(
            "--middle_geometry_profile",
            type=click.Choice(["full", "lean"]),
            default=None,
            help="Middle word geometry: full (default) keeps word spans; lean omits them for faster save and smaller files. "
                 "Lean is not applied when classical marginalia, span overlays or full Middle JSON are requested.",
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
        fn = click.option(
            "--emit_middle_full_json",
            is_flag=True,
            default=False,
            help="Emit a full Middle JSON artifact including spans for diagnostics.",
        )(fn)
        fn = click.option(
            "--enable_marginal_detection",
            is_flag=True,
            default=False,
            help="Enable marginal line-number and marginal annotation detection.",
        )(fn)
        fn = click.option(
            "--native_marginalia_enabled/--no_native_marginalia_enabled",
            default=None,
            help="Receive backend-native marginalia labels separately from heuristic recovery.",
        )(fn)
        fn = click.option(
            "--heuristic_marginal_detection_enabled/--no_heuristic_marginal_detection_enabled",
            default=None,
            help="Enable coordinate heuristic recovery of marginalia from Text blocks.",
        )(fn)
        fn = click.option(
            "--marginal_output_mode",
            type=click.Choice(["line_markers", "margin_comments", "plain", "drop"]),
            default=None,
            help="Markdown output mode for recognized marginalia: line_markers, margin_comments, plain, or drop.",
        )(fn)
        fn = click.option(
            "--classical_marginalia_mode",
            type=click.Choice(["off", "page_locators"]),
            default="off",
            help="Classical marginalia rendering: off (legacy) or page_locators (page-level locator annotations).",
        )(fn)
        fn = click.option(
            "--classical_text_marginalia_mode",
            type=click.Choice(["separate", "drop"]),
            default="separate",
            help="When classical marginalia is enabled, keep textual marginalia separately or omit it from rendered Markdown.",
        )(fn)
        fn = click.option(
            "--generic_line_output_mode",
            type=click.Choice(["drop", "page_comments"]),
            default="drop",
            help="Universal line number output mode: drop (omit confirmed line numbers from reading Markdown, default) or page_comments (preserve at page top comments). Requires classical_marginalia_mode=page_locators; affects only confirmed line numbers. Body numbers are preserved; Bekker locators are controlled separately.",
        )(fn)
        fn = click.option("--left_margin_threshold", type=float, default=None, help="Left marginal region width as a page-width fraction.")(fn)
        fn = click.option("--right_margin_threshold", type=float, default=None, help="Right marginal region start as a page-width fraction.")(fn)
        fn = click.option("--top_margin_threshold", type=float, default=None, help="Top marginal region height as a page-height fraction.")(fn)
        fn = click.option("--bottom_margin_threshold", type=float, default=None, help="Bottom marginal region start as a page-height fraction.")(fn)
        fn = click.option("--vertical_center_tolerance", type=float, default=None, help="Vertical-center tolerance for marginal code detection.")(fn)
        fn = click.option(
            "--equation_output_mode",
            type=click.Choice(["humanities_safe", "plain", "math"]),
            default=None,
            help="Markdown output mode for Equation blocks: humanities_safe, plain, or math.",
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
        options = self.get_effective_options()
        config = {}
        output_dir = options.get("output_dir", settings.OUTPUT_DIR)
        emit_middle_json_for_artifacts = False
        disable_ocr_for_backend = False
        for k, v in options.items():
            # 🔧 修复：不要过滤 False 值，因为处理器配置需要 False 来禁用
            # 只跳过 None 和空字符串
            if v is None or v == "":
                continue

            match k:
                case "debug":
                    # is_flag，只有显式传 --debug 才成立；v=False 时不得打开调试产物
                    if v:
                        config["debug_pdf_images"] = True
                        config["debug_layout_images"] = True
                        config["debug_json"] = True
                        config["debug_data_folder"] = output_dir
                case "page_range":
                    if isinstance(v, (list, tuple)):
                        config["page_range"] = list(v)
                    elif isinstance(v, str):
                        config["page_range"] = parse_range_str(v)
                    else:
                        raise TypeError(
                            "page_range must be a string, list, or tuple; "
                            f"got {type(v).__name__}"
                        )
                case "config_json":
                    # get_effective_options has already loaded the file before
                    # applying explicit values. Keep this for direct callers
                    # that include the key in a manually-built options dict.
                    continue
                case "disable_multiprocessing":
                    if v:
                        config["pdftext_workers"] = 1
                case "disable_image_extraction":
                    if v:
                        config["extract_images"] = False
                case "disable_ocr":
                    config["disable_ocr"] = bool(v)
                case "emit_layout_overlay":
                    config["emit_layout_overlay"] = bool(v)
                    if v:
                        emit_middle_json_for_artifacts = True
                case "emit_span_overlay":
                    config["emit_span_overlay"] = bool(v)
                    if v:
                        emit_middle_json_for_artifacts = True
                case "emit_middle_report" | "emit_middle_debug" | "emit_middle_scholarly" | "emit_middle_scholarly_report" | "emit_middle_full_json":
                    config[k] = bool(v)
                    if v:
                        emit_middle_json_for_artifacts = True
                case "ocr_backend":
                    if str(v).strip().lower() == "none":
                        config["ocr_backend"] = "surya"
                        disable_ocr_for_backend = True
                    else:
                        config["ocr_backend"] = v
                case _:
                    config[k] = v

        if emit_middle_json_for_artifacts:
            config["emit_middle_json"] = True
        if disable_ocr_for_backend:
            # The explicit backend alias ocr_backend=none always means that
            # OCR must be disabled, regardless of dictionary insertion order.
            config["disable_ocr"] = True

        # Backward compatibility for google_api_key without overriding an
        # explicit key supplied in JSON or by the caller.
        if settings.GOOGLE_API_KEY:
            config.setdefault("gemini_api_key", settings.GOOGLE_API_KEY)

        ocr_backend = str(config.get("ocr_backend") or "surya").strip().lower().replace("-", "_")
        preprocess_backend = str(config.get("ocr_preprocess_backend") or "none").strip().lower().replace("-", "_")
        if preprocess_backend == "chrome_screenai":
            preprocess_backend = "chrome_screenai_searchable_pdf"
        if ocr_backend == "chrome_screenai" and preprocess_backend == "none":
            preprocess_backend = "chrome_screenai_searchable_pdf"
        if preprocess_backend != "none":
            config["ocr_preprocess_backend"] = preprocess_backend
            config["disable_ocr"] = True
        config["ocr_backend"] = "surya" if ocr_backend == "none" else ocr_backend
        disable_ocr = bool(config.get("disable_ocr", False))
        if disable_ocr:
            config["force_ocr"] = False
        else:
            config["force_ocr"] = True
            if ocr_backend == "calamari":
                config["ocr_line_source"] = "tesseract"

        return config

    def get_llm_service(self):
        # Only return an LLM service when use_llm is enabled
        options = self.get_effective_options()
        if not options.get("use_llm", False):
            return None

        service_cls = options.get("llm_service", None)
        if service_cls is None:
            service_cls = "aih_contexture.services.gemini.GoogleGeminiService"
        return service_cls

    def get_renderer(self):
        match self.get_effective_options().get("output_format", "markdown"):
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
        processors = self.get_effective_options().get("processors", None)
        if processors is not None:
            if isinstance(processors, str):
                processors = [item.strip() for item in processors.split(",") if item.strip()]
            elif isinstance(processors, (list, tuple)):
                if not all(isinstance(item, str) and item.strip() for item in processors):
                    raise ValueError("processors must contain only non-empty class path strings")
                processors = [item.strip() for item in processors]
            else:
                raise TypeError(
                    "processors must be a comma-separated string, list, or tuple; "
                    f"got {type(processors).__name__}"
                )
            for p in processors:
                try:
                    strings_to_classes([p])
                except Exception as e:
                    logger.error(f"Error loading processor: {p} with error: {e}")
                    raise

        return processors

    def get_converter_cls(self):
        converter_cls = self.get_effective_options().get("converter_cls", None)
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
        output_dir = self.get_effective_options().get("output_dir", settings.OUTPUT_DIR)
        return document_output_folder(output_dir, filepath)

    def get_base_filename(self, filepath: str):
        return document_output_basename(filepath)
