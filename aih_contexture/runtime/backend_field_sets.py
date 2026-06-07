from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aih_contexture.builders.ocr_line_crops import (
    DEFAULT_OCR_CROP_PADDING_FRAC,
    DEFAULT_OCR_CROP_PADDING_PX,
    DEFAULT_OCR_CROP_UPSCALE_MIN_HEIGHT,
)
from aih_contexture.config.vlm_model_presets import default_version, resolve_vlm_model


def paddle_layout_default_model(layout_backend: str) -> str:
    return "PP-DocLayoutV3" if layout_backend == "paddle_pp_doclayout_v3" else "PP-DocLayout_plus-L"


def external_layout_sidecar_fields(values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "external_layout_json": values.get("external_layout_json"),
        "external_layout_block_source": values.get("external_layout_block_source", "auto"),
        "external_layout_backend_name": values.get("external_layout_backend_name", "external_layout_sidecar"),
        "external_layout_model": values.get("external_layout_model"),
        "external_layout_allow_missing_pages": bool(values.get("external_layout_allow_missing_pages", False)),
    }


def mineru_layout_fields(values: Mapping[str, Any], *, include_external_mapping: bool = False) -> dict[str, Any]:
    fields = {
        "mineru_command": values.get("mineru_command", "mineru"),
        "mineru_output_dir": values.get("mineru_output_dir"),
        "mineru_backend": values.get("mineru_backend", "pipeline"),
        "mineru_method": values.get("mineru_method", "txt"),
        "mineru_lang": values.get("mineru_lang", "ch"),
        "mineru_api_url": values.get("mineru_api_url"),
        "mineru_server_url": values.get("mineru_server_url"),
        "mineru_timeout": values.get("mineru_timeout", 3600),
        "mineru_extra_args": values.get("mineru_extra_args"),
    }
    if include_external_mapping:
        fields.update({
            "external_layout_backend_name": "mineru_pp_doclayout_v2",
            "external_layout_model": "PP-DocLayoutV2",
            "external_layout_block_source": "para_blocks",
        })
    return fields


def mineru_direct_layout_fields(values: Mapping[str, Any], *, include_external_mapping: bool = False) -> dict[str, Any]:
    fields = {
        "mineru_layout_python": values.get("mineru_layout_python") or values.get("mineru_python"),
        "mineru_layout_model_dir": values.get("mineru_layout_model_dir"),
        "mineru_layout_device": values.get("mineru_layout_device"),
        "mineru_layout_batch_size": values.get("mineru_layout_batch_size", 1),
        "mineru_layout_use_paddlex_filter_boxes": values.get("mineru_layout_use_paddlex_filter_boxes"),
        "mineru_layout_timeout": values.get("mineru_layout_timeout", values.get("mineru_timeout", 3600)),
    }
    if include_external_mapping:
        fields.update({
            "external_layout_backend_name": "mineru_pp_doclayout_v2_direct",
            "external_layout_model": "PP-DocLayoutV2",
            "external_layout_block_source": "boxes",
        })
    return fields


def paddle_layout_fields(
    layout_backend: str,
    values: Mapping[str, Any],
    *,
    include_external_mapping: bool = False,
) -> dict[str, Any]:
    default_model = paddle_layout_default_model(layout_backend)
    model_name = values.get("paddle_layout_model_name", default_model)
    fields = {
        "paddle_layout_python": values.get("paddle_layout_python"),
        "paddle_layout_model_name": model_name,
        "paddle_layout_model_dir": values.get("paddle_layout_model_dir"),
        "paddle_layout_device": values.get("paddle_layout_device"),
        "paddle_layout_engine": values.get("paddle_layout_engine"),
        "paddle_layout_enable_mkldnn": values.get("paddle_layout_enable_mkldnn", False),
        "paddle_layout_cpu_threads": values.get("paddle_layout_cpu_threads"),
        "paddle_layout_threshold": values.get("paddle_layout_threshold"),
        "paddle_layout_img_size": values.get("paddle_layout_img_size"),
        "paddle_layout_batch_size": values.get("paddle_layout_batch_size"),
    }
    if include_external_mapping:
        fields.update({
            "external_layout_backend_name": layout_backend,
            "external_layout_model": model_name,
            "external_layout_block_source": "boxes",
        })
    return fields


def paddle_ocr_fields(values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "paddle_ocr_python": values.get("paddle_ocr_python"),
        "paddle_ocr_lang": values.get("paddle_ocr_lang", "ch"),
        "paddle_ocr_version": values.get("paddle_ocr_version", "PP-OCRv5"),
        "paddle_ocr_device": values.get("paddle_ocr_device"),
        "paddle_ocr_engine": values.get("paddle_ocr_engine"),
        "paddle_ocr_enable_mkldnn": bool(values.get("paddle_ocr_enable_mkldnn", False)),
        "paddle_ocr_cpu_threads": values.get("paddle_ocr_cpu_threads"),
        "paddle_ocr_use_doc_orientation_classify": bool(values.get("paddle_ocr_use_doc_orientation_classify", False)),
        "paddle_ocr_use_doc_unwarping": bool(values.get("paddle_ocr_use_doc_unwarping", False)),
        "paddle_ocr_use_textline_orientation": bool(values.get("paddle_ocr_use_textline_orientation", False)),
    }


def paddleocr_vl_fields(values: Mapping[str, Any], *, pipeline_ocr: bool = False) -> dict[str, Any]:
    version = values.get("paddleocr_vl_version", default_version("paddleocr_vl"))
    api_style = values.get("paddleocr_vl_api_style", values.get("ocr_api_style", "openai"))
    endpoint = values.get("paddleocr_vl_endpoint")
    if endpoint is None:
        endpoint = values.get("ocr_endpoint", values.get("openai_base_url"))
    endpoint = _paddleocr_vl_endpoint(endpoint, api_style=api_style)
    model = values.get("paddleocr_vl_model")
    if model is None:
        model = values.get("ocr_model", values.get("openai_model"))
    if model is None:
        model = resolve_vlm_model("paddleocr_vl", version=version)
    api_key = values.get("paddleocr_vl_api_key")
    if api_key is None:
        api_key = values.get("ocr_api_key", values.get("openai_api_key"))
    block_concurrency_default = 4 if pipeline_ocr else values.get("ocr_concurrency", 5)
    prompt_label_default = "ocr" if pipeline_ocr else "layout_detection"
    return {
        "ocr_api_style": api_style,
        "ocr_endpoint": endpoint,
        "ocr_model": model,
        "ocr_api_key": api_key,
        "paddleocr_vl_mode": values.get("paddleocr_vl_mode", "auto"),
        "paddleocr_vl_version": version,
        "paddleocr_vl_endpoint": endpoint,
        "paddleocr_vl_layout_parsing_url": values.get("paddleocr_vl_layout_parsing_url"),
        "paddleocr_vl_model": model,
        "paddleocr_vl_api_key": api_key,
        "paddleocr_vl_api_style": api_style,
        "paddleocr_vl_request_concurrency": values.get("paddleocr_vl_request_concurrency", block_concurrency_default),
        "paddleocr_vl_block_concurrency": values.get("paddleocr_vl_block_concurrency", block_concurrency_default),
        "paddleocr_vl_prompt_label": values.get("paddleocr_vl_prompt_label", prompt_label_default),
        "paddleocr_vl_image_format": values.get("paddleocr_vl_image_format", "JPEG"),
        "paddleocr_vl_image_quality": values.get("paddleocr_vl_image_quality", values.get("ocr_image_quality", 90)),
        "paddleocr_vl_crop_padding_px": values.get("paddleocr_vl_crop_padding_px", 4),
        "paddleocr_vl_crop_padding_frac": values.get("paddleocr_vl_crop_padding_frac", 0.02),
    }


def _paddleocr_vl_endpoint(endpoint: Any, *, api_style: Any) -> str:
    style = str(api_style or "openai").strip().lower()
    if not endpoint:
        if style == "lmstudio-native":
            return "http://localhost:1234/api/v1/chat"
        return "http://127.0.0.1:1234/v1/chat/completions"
    text = str(endpoint).strip()
    if style == "openai-compatible":
        style = "openai"
    if style == "openai":
        stripped = text.rstrip("/")
        if stripped.endswith("/v1"):
            return f"{stripped}/chat/completions"
    return text


def tesseract_ocr_fields(values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "tesseract_profile": values.get("tesseract_profile", "printed_latin"),
        "tesseract_cmd": values.get("tesseract_cmd"),
        "tesseract_lang": values.get("tesseract_lang", "eng"),
        "tesseract_oem": values.get("tesseract_oem", 1),
        "tesseract_psm": values.get("tesseract_psm", 7),
        "tesseract_line_psm": values.get("tesseract_line_psm", 1),
        "tesseract_line_preprocess": values.get("tesseract_line_preprocess", values.get("ocr_crop_preprocess", "otsu")),
        "tesseract_line_upscale_min_height": values.get("tesseract_line_upscale_min_height", 0),
        "tesseract_thresholding_method": values.get("tesseract_thresholding_method", "auto"),
        "tesseract_timeout": values.get("tesseract_timeout", 30),
        "tesseract_omp_thread_limit": values.get("tesseract_omp_thread_limit", 1),
        "tesseract_tessdata_prefix": values.get("tesseract_tessdata_prefix"),
        "tesseract_user_words": values.get("tesseract_user_words"),
        "tesseract_user_patterns": values.get("tesseract_user_patterns"),
        "tesseract_extra_config": values.get("tesseract_extra_config"),
        "ocr_crop_padding_px": values.get("ocr_crop_padding_px", DEFAULT_OCR_CROP_PADDING_PX),
        "ocr_crop_padding_frac": values.get("ocr_crop_padding_frac", DEFAULT_OCR_CROP_PADDING_FRAC),
        "ocr_crop_preprocess": values.get("ocr_crop_preprocess", "otsu"),
        "ocr_crop_upscale_min_height": values.get(
            "ocr_crop_upscale_min_height",
            DEFAULT_OCR_CROP_UPSCALE_MIN_HEIGHT,
        ),
    }
