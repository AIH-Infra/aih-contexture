from __future__ import annotations

from typing import Any

from aih_contexture.config.marginal_output import normalize_marginal_output_mode

from aih_contexture.config.parser import ConfigParser
from aih_contexture.runtime.backend_field_sets import (
    chrome_screenai_preprocess_fields,
    external_layout_sidecar_fields,
    mineru_direct_layout_fields,
    mineru_vl_layout_fields,
    mineru_ocr_fields,
    paddle_layout_fields,
    paddle_ocr_fields,
    paddleocr_vl_fields,
    tesseract_ocr_fields,
)
from aih_contexture.config.vlm_model_presets import (
    default_quant,
    default_version,
    normalize_quant,
    normalize_version,
    resolve_vlm_model,
)
from aih_contexture.scripts.ui.vlm_config import build_vlm_generalized_config
from aih_contexture.util import parse_range_str


def _param_value(config_params: dict[str, Any], key: str, default: Any) -> Any:
    value = config_params.get(key)
    return default if value is None else value


def _int_param(config_params: dict[str, Any], key: str, default: int) -> int:
    return int(_param_value(config_params, key, default))


def _float_param(config_params: dict[str, Any], key: str, default: float) -> float:
    return float(_param_value(config_params, key, default))


def _default_vlm_ocr_api_style(ocr_backend: str) -> str:
    return "openai" if ocr_backend == "churro" else "lmstudio-native"


def _default_vlm_ocr_endpoint(api_style: str) -> str:
    if api_style in {"openai", "openai-compatible"}:
        return "http://localhost:1234/v1/chat/completions"
    return "http://localhost:1234/api/v1/chat"


def vlm_specialized_cli_config(config_params: dict[str, Any]) -> dict[str, Any]:
    ocr_backend = config_params.get("ocr_backend", "chandra")
    is_chrome_screenai = ocr_backend == "chrome_screenai"
    default_api_style = _default_vlm_ocr_api_style(ocr_backend)
    ocr_api_style = config_params.get("ocr_api_style", default_api_style)
    ocr_endpoint = config_params.get("ocr_endpoint", _default_vlm_ocr_endpoint(ocr_api_style))
    chandra_version = normalize_version("chandra", config_params.get("chandra_version", default_version("chandra")))
    chandra_quant = normalize_quant("chandra", chandra_version, config_params.get("chandra_quant", default_quant("chandra")))
    churro_version = normalize_version("churro", config_params.get("churro_version", default_version("churro")))
    churro_quant = normalize_quant("churro", churro_version, config_params.get("churro_quant", default_quant("churro")))
    paddleocr_vl_version = normalize_version(
        "paddleocr_vl",
        config_params.get("paddleocr_vl_version", default_version("paddleocr_vl")),
    )
    mineru_vl_version = normalize_version("mineru_vl", config_params.get("mineru_vl_version", default_version("mineru_vl")))
    mineru_vl_quant = normalize_quant(
        "mineru_vl",
        mineru_vl_version,
        config_params.get("mineru_vl_quant", default_quant("mineru_vl")),
    )
    if is_chrome_screenai:
        resolved_model = "chrome-screenai-local"
    elif ocr_backend == "chandra":
        resolved_model = resolve_vlm_model(ocr_backend, version=chandra_version, quant=chandra_quant)
    elif ocr_backend == "churro":
        resolved_model = resolve_vlm_model(ocr_backend, version=churro_version, quant=churro_quant)
    elif ocr_backend == "paddleocr_vl":
        resolved_model = resolve_vlm_model(ocr_backend, version=paddleocr_vl_version)
    else:
        resolved_model = resolve_vlm_model(ocr_backend, version=mineru_vl_version, quant=mineru_vl_quant)
    ocr_model = config_params.get("ocr_model") or resolved_model
    default_output_format = "html"
    if is_chrome_screenai:
        default_output_format = "html"
    elif ocr_backend == "churro":
        default_output_format = "xml"
    elif ocr_backend in ("paddleocr_vl", "mineru_vl"):
        default_output_format = "json"
    default_resize_max = 2500 if ocr_backend == "churro" else 1024
    default_image_quality = 95 if ocr_backend == "churro" else 60
    default_image_format = "PNG" if ocr_backend == "churro" else "JPEG"
    default_max_tokens = 20000 if ocr_backend == "churro" else 4096
    emit_middle_json = bool(config_params.get("emit_middle_json", config_params.get("vlm_specialized_emit_middle_json", False)))
    emit_middle_report = bool(config_params.get("emit_middle_report", config_params.get("vlm_specialized_emit_middle_report", False)))
    emit_middle_debug = bool(config_params.get("emit_middle_debug", config_params.get("vlm_specialized_emit_middle_debug", False)))
    emit_middle_scholarly = bool(config_params.get("emit_middle_scholarly", config_params.get("vlm_specialized_emit_middle_scholarly", False)))
    emit_middle_scholarly_report = bool(
        config_params.get("emit_middle_scholarly_report", config_params.get("vlm_specialized_emit_middle_scholarly_report", False))
    )
    emit_layout_overlay = bool(config_params.get("emit_layout_overlay", config_params.get("vlm_specialized_emit_layout_overlay", False)))
    emit_span_overlay = bool(config_params.get("emit_span_overlay", config_params.get("vlm_specialized_emit_span_overlay", False)))
    emit_middle_full_json = bool(config_params.get("emit_middle_full_json", config_params.get("vlm_specialized_emit_middle_full_json", False)))
    emit_middle_json = bool(
        emit_middle_json
        or emit_middle_report
        or emit_middle_debug
        or emit_middle_scholarly
        or emit_middle_scholarly_report
        or emit_layout_overlay
        or emit_span_overlay
        or emit_middle_full_json
    )
    cli = {
        "converter_cls": "aih_contexture.converters.ocr_direct_async.OcrDirectAsyncConverter",
        "ocr_backend": ocr_backend,
        "chandra_version": chandra_version,
        "chandra_quant": chandra_quant,
        "churro_version": churro_version,
        "churro_quant": churro_quant,
        "paddleocr_vl_version": paddleocr_vl_version,
        "mineru_vl_version": mineru_vl_version,
        "mineru_vl_quant": mineru_vl_quant,
        "ocr_api_style": None if is_chrome_screenai else ocr_api_style,
        "ocr_endpoint": None if is_chrome_screenai else ocr_endpoint,
        "ocr_model": None if is_chrome_screenai else ocr_model,
        "ocr_api_key": None if is_chrome_screenai else config_params.get("ocr_api_key"),
        "ocr_output_format": config_params.get("ocr_output_format", default_output_format),
        "ocr_concurrency": _int_param(config_params, "ocr_concurrency", 2 if is_chrome_screenai else 5),
        "ocr_batch_size": _int_param(config_params, "ocr_batch_size", 4 if is_chrome_screenai else 10),
        "ocr_batch_rest": _float_param(config_params, "ocr_batch_rest", 2.0),
        "ocr_max_retries": _int_param(config_params, "ocr_max_retries", 3),
        "ocr_resize_max": _int_param(config_params, "ocr_resize_max", default_resize_max),
        "ocr_image_format": config_params.get("ocr_image_format", default_image_format),
        "ocr_image_quality": _int_param(config_params, "ocr_image_quality", default_image_quality),
        "ocr_page_anchor_enabled": bool(config_params.get("ocr_page_anchor_enabled", True)),
        "ocr_page_anchor_position": config_params.get("ocr_page_anchor_position", "before"),
        "ocr_extract_printed_pages": bool(config_params.get("ocr_extract_printed_pages", True)),
        "ocr_printed_page_patterns": config_params.get("ocr_printed_page_patterns"),
        "ocr_custom_id_source": config_params.get("ocr_custom_id_source", "none"),
        "ocr_custom_id_data": config_params.get("ocr_custom_id_data"),
        "ocr_timeout": _int_param(config_params, "ocr_timeout", 120),
        "ocr_max_tokens": _int_param(config_params, "ocr_max_tokens", default_max_tokens),
        "ocr_temperature": _float_param(config_params, "ocr_temperature", 0.6 if ocr_backend == "churro" else 0.0),
        "paddleocr_vl_prompt_label": config_params.get("paddleocr_vl_prompt_label", "layout_detection"),
        "paddleocr_vl_mode": config_params.get("paddleocr_vl_mode", "auto"),
        "paddleocr_vl_layout_parsing_url": config_params.get("paddleocr_vl_layout_parsing_url"),
        "paddleocr_vl_api_style": config_params.get("paddleocr_vl_api_style", ocr_api_style),
        "paddleocr_vl_endpoint": config_params.get("paddleocr_vl_endpoint", ocr_endpoint),
        "paddleocr_vl_model": config_params.get("paddleocr_vl_model", ocr_model),
        "paddleocr_vl_api_key": config_params.get("paddleocr_vl_api_key", config_params.get("ocr_api_key")),
        "paddleocr_vl_request_concurrency": _int_param(
            config_params,
            "paddleocr_vl_request_concurrency",
            _int_param(config_params, "ocr_concurrency", 5),
        ),
        "paddleocr_vl_block_concurrency": _int_param(
            config_params,
            "paddleocr_vl_block_concurrency",
            _int_param(config_params, "ocr_concurrency", 5),
        ),
        "paddleocr_vl_image_format": config_params.get("paddleocr_vl_image_format", default_image_format),
        "paddleocr_vl_image_quality": _int_param(config_params, "paddleocr_vl_image_quality", default_image_quality),
        "paddleocr_vl_crop_padding_px": _int_param(config_params, "paddleocr_vl_crop_padding_px", 4),
        "paddleocr_vl_crop_padding_frac": _float_param(config_params, "paddleocr_vl_crop_padding_frac", 0.02),
        "ocr_filter_page_header": bool(config_params.get("ocr_filter_page_header", False)),
        "ocr_filter_page_footer": bool(config_params.get("ocr_filter_page_footer", False)),
        "ocr_filter_margin_notes": bool(config_params.get("ocr_filter_margin_notes", False)),
        "ocr_filter_blockquote_markers": bool(config_params.get("ocr_filter_blockquote_markers", False)),
        "include_page_header_comments": not bool(config_params.get("ocr_filter_page_header", False)),
        "include_page_footer_comments": not bool(config_params.get("ocr_filter_page_footer", False)),
        "include_margin_comments": not bool(config_params.get("ocr_filter_margin_notes", False)),
        "include_blockquote_markers": not bool(config_params.get("ocr_filter_blockquote_markers", False)),
        "mineru_vl_block_concurrency": _int_param(config_params, "mineru_vl_block_concurrency", 4),
        "mineru_vl_request_concurrency": _int_param(
            config_params,
            "mineru_vl_request_concurrency",
            1 if ocr_api_style == "lmstudio-native" else _int_param(config_params, "mineru_vl_block_concurrency", 4),
        ),
        "mineru_vl_layout_image_size": config_params.get("mineru_vl_layout_image_size", (1036, 1036)),
        "churro_marginal_note_enabled": bool(config_params.get("enable_marginal_detection", False)),
        "emit_middle_json": emit_middle_json,
        "emit_middle_report": emit_middle_report,
        "emit_middle_debug": emit_middle_debug,
        "emit_middle_scholarly": emit_middle_scholarly,
        "emit_middle_scholarly_report": emit_middle_scholarly_report,
        "emit_layout_overlay": emit_layout_overlay,
        "emit_span_overlay": emit_span_overlay,
        "emit_middle_full_json": emit_middle_full_json,
        "chrome_screenai_light": bool(config_params.get("chrome_screenai_light", False)),
        "chrome_preprocess_mode": config_params.get("chrome_preprocess_mode", "native"),
        "chrome_workers": _int_param(config_params, "chrome_workers", _int_param(config_params, "ocr_concurrency", 2)),
        "chrome_chunk_pages": _int_param(config_params, "chrome_chunk_pages", _int_param(config_params, "ocr_batch_size", 4)),
        "chrome_emit_searchable_pdf": bool(config_params.get("chrome_emit_searchable_pdf", False)),
        "chrome_rasterize_dpi": _int_param(config_params, "chrome_rasterize_dpi", 144),
        "chrome_model_dir": config_params.get("chrome_model_dir"),
    }
    if config_params.get("page_range"):
        cli["page_range"] = parse_range_str(config_params["page_range"])
    return cli


def pipeline_base_cli_config(
    config_params: dict[str, Any],
    *,
    ocr_backend: str,
    layout_backend: str,
    disable_ocr: bool,
    disable_layout: bool,
) -> dict[str, Any]:
    emit_middle_report = bool(config_params.get("emit_middle_report", False))
    emit_middle_debug = bool(config_params.get("emit_middle_debug", False))
    emit_middle_scholarly = bool(config_params.get("emit_middle_scholarly", False))
    emit_middle_scholarly_report = bool(config_params.get("emit_middle_scholarly_report", False))
    emit_layout_overlay = bool(config_params.get("emit_layout_overlay", False))
    emit_span_overlay = bool(config_params.get("emit_span_overlay", False))
    emit_middle_full_json = bool(config_params.get("emit_middle_full_json", False))
    emit_middle_json = bool(
        config_params.get("emit_middle_json", False)
        or emit_middle_report
        or emit_middle_debug
        or emit_middle_scholarly
        or emit_middle_scholarly_report
        or emit_layout_overlay
        or emit_span_overlay
        or emit_middle_full_json
    )
    cli = {
        "ocr_batch_size": _int_param(config_params, "ocr_batch_size", 32),
        "use_pdf_text_fallback": True,
        "use_pdf_objects": True,
        "use_fp16": bool(config_params.get("use_fp16", False)),
        "force_ocr": False if disable_ocr else True,
        "paginate_output": bool(config_params.get("paginate_output", True)),
        "page_separator": config_params.get("page_separator", "\n\n---\n\n"),
        "use_llm": bool(config_params.get("use_llm", False)),
        "ocr_backend": ocr_backend if (disable_ocr and ocr_backend == "chrome_screenai") else ("surya" if disable_ocr else ocr_backend),
        "disable_ocr": disable_ocr,
        "layout_backend": "surya" if disable_layout else layout_backend,
        "disable_layout": disable_layout,
        "surya_layout_quality": config_params.get("surya_layout_quality", "fast"),
        "layout_dpi_override": config_params.get("layout_dpi_override"),
        "ocr_quality": config_params.get("ocr_quality", "auto"),
        "ocr_dpi_override": config_params.get("ocr_dpi_override"),
        "emit_middle_json": emit_middle_json,
        "emit_middle_report": emit_middle_report,
        "emit_middle_debug": emit_middle_debug,
        "emit_middle_scholarly": emit_middle_scholarly,
        "emit_middle_scholarly_report": emit_middle_scholarly_report,
        "emit_layout_overlay": emit_layout_overlay,
        "emit_span_overlay": emit_span_overlay,
        "emit_middle_full_json": emit_middle_full_json,
        "printed_page_correction_enabled": bool(config_params.get("printed_page_correction_enabled", True)),
        "markdown_formatting_enabled": bool(config_params.get("markdown_formatting_enabled", True)),
        "markdown_postprocess_enabled": bool(config_params.get("markdown_postprocess_enabled", False)),
        "markdown_postprocess_review_only": bool(config_params.get("markdown_postprocess_review_only", True)),
        "markdown_postprocess_enable_cleanup": bool(config_params.get("markdown_postprocess_enable_cleanup", True)),
        "markdown_postprocess_enable_printed_page_repair": bool(config_params.get("markdown_postprocess_enable_printed_page_repair", False)),
        "markdown_postprocess_enable_llm": bool(config_params.get("markdown_postprocess_enable_llm", False)),
        "markdown_postprocess_llm_provider": config_params.get("markdown_postprocess_llm_provider", "openai"),
        "markdown_postprocess_llm_base_url": config_params.get("markdown_postprocess_llm_base_url"),
        "markdown_postprocess_llm_model": config_params.get("markdown_postprocess_llm_model"),
        "markdown_postprocess_llm_api_key": config_params.get("markdown_postprocess_llm_api_key"),
        "markdown_postprocess_llm_timeout": _int_param(config_params, "markdown_postprocess_llm_timeout", 60),
        "markdown_postprocess_llm_max_retries": _int_param(config_params, "markdown_postprocess_llm_max_retries", 1),
        "markdown_noise_removal_enabled": bool(config_params.get("markdown_noise_removal_enabled", True)),
        "markdown_noise_cleaning_level": config_params.get("markdown_noise_cleaning_level", "basic"),
        "markdown_noise_custom_symbols": config_params.get("markdown_noise_custom_symbols", ""),
        "markdown_noise_line_start_only": bool(config_params.get("markdown_noise_line_start_only", True)),
        "blockquote_enabled": bool(config_params.get("blockquote_enabled", True)),
        "line_merge_enabled": bool(config_params.get("line_merge_enabled", True)),
        "code_enabled": bool(config_params.get("code_enabled", True)),
        "section_header_enabled": bool(config_params.get("section_header_enabled", True)),
        "equation_enabled": bool(config_params.get("equation_enabled", True)),
        "equation_output_mode": config_params.get("equation_output_mode", "humanities_safe"),
        "list_enabled": bool(config_params.get("list_enabled", True)),
        "footnote_enabled": bool(config_params.get("footnote_enabled", True)),
        "superscript_policy": config_params.get("superscript_policy", "auto"),
        "reference_enabled": bool(config_params.get("reference_enabled", True)),
        "table_enabled": bool(config_params.get("table_enabled", True)),
        "emit_page_header_comment": bool(config_params.get("emit_page_header_comment", False)),
        "emit_page_footer_comment": bool(config_params.get("emit_page_footer_comment", False)),
        "keep_pageheader_in_output": bool(config_params.get("keep_pageheader_in_output", False)),
        "keep_pagefooter_in_output": bool(config_params.get("keep_pagefooter_in_output", False)),
    }
    if "build_highres_images" in config_params:
        build_highres_images = bool(config_params.get("build_highres_images"))
        cli["build_highres_images"] = build_highres_images
        cli["image_extraction_mode"] = config_params.get(
            "image_extraction_mode",
            "highres" if build_highres_images else "lowres",
        )
    elif disable_ocr:
        cli["build_highres_images"] = False
        cli["image_extraction_mode"] = "lowres"
    if config_params.get("page_range"):
        cli["page_range"] = parse_range_str(config_params["page_range"])
    return cli


def preprocess_backend_cli_config(config_params: dict[str, Any]) -> dict[str, Any]:
    backend = _resolve_pipeline_ocr_preprocess_backend(
        str(config_params.get("ocr_backend", "surya") or "surya"),
        config_params.get("ocr_preprocess_backend", "none"),
    )
    config = chrome_screenai_preprocess_fields(config_params)
    config["ocr_preprocess_backend"] = backend
    return config


def _resolve_pipeline_ocr_preprocess_backend(ocr_backend: str, configured_backend: Any) -> str:
    backend = str(configured_backend or "none").strip().lower().replace("-", "_")
    if backend == "chrome_screenai":
        backend = "chrome_screenai_searchable_pdf"
    if str(ocr_backend or "surya").strip().lower().replace("-", "_") == "chrome_screenai":
        return "chrome_screenai_searchable_pdf"
    return backend


def page_numbering_cli_config(config_params: dict[str, Any]) -> dict[str, Any]:
    cli: dict[str, Any] = {}
    needs_page_margin_capture = bool(
        config_params.get("page_numbering_enabled", True)
        or config_params.get("emit_page_header_comment", False)
        or config_params.get("emit_page_footer_comment", False)
        or config_params.get("keep_pageheader_in_output", False)
        or config_params.get("keep_pagefooter_in_output", False)
    )
    if needs_page_margin_capture:
        cli["printed_page_zones"] = config_params.get("printed_page_zones", ["footer", "header"])
        cli["printed_page_header_y_frac"] = config_params.get("printed_page_header_y_frac", 0.15)
        cli["printed_page_footer_y_frac"] = config_params.get("printed_page_footer_y_frac", 0.83)

    cli["page_numbering_enabled"] = config_params.get("page_numbering_enabled", True)
    if cli["page_numbering_enabled"]:
        cli["use_printed_page_number"] = config_params.get("use_printed_page_number", True)
        cli["page_number_format"] = config_params.get("page_number_format", "auto")
        if config_params.get("page_number_custom_pattern"):
            cli["page_number_custom_pattern"] = config_params["page_number_custom_pattern"]
    return cli


def layout_backend_cli_config(layout_backend: str, config_params: dict[str, Any]) -> dict[str, Any]:
    if layout_backend in ("vlm", "vlm_layout"):
        vlm_config = {
            "vlm_layout_timeout": _int_param(config_params, "vlm_layout_timeout", 120),
        }
        has_prompt = False
        if config_params.get("vlm_layout_prompt"):
            vlm_config["vlm_layout_prompt"] = config_params["vlm_layout_prompt"]
            has_prompt = True
        if config_params.get("vlm_layout_prompt_template"):
            vlm_config["vlm_layout_prompt_template"] = config_params["vlm_layout_prompt_template"]
            has_prompt = True
        if not has_prompt:
            vlm_config["vlm_layout_prompt_template"] = "modern"
        if config_params.get("vlm_layout_base_url"):
            vlm_config["vlm_layout_base_url"] = config_params["vlm_layout_base_url"]
        if config_params.get("vlm_layout_model"):
            vlm_config["vlm_layout_model"] = config_params["vlm_layout_model"]
        if config_params.get("vlm_layout_api_key"):
            vlm_config["vlm_layout_api_key"] = config_params["vlm_layout_api_key"]
        if config_params.get("vlm_layout_image_format"):
            vlm_config["vlm_layout_image_format"] = config_params["vlm_layout_image_format"]
        if config_params.get("vlm_layout_max_image_dimension"):
            vlm_config["vlm_layout_max_image_dimension"] = int(config_params["vlm_layout_max_image_dimension"])
        if config_params.get("vlm_layout_jpeg_quality"):
            vlm_config["vlm_layout_jpeg_quality"] = int(config_params["vlm_layout_jpeg_quality"])
        if config_params.get("vlm_layout_max_concurrent"):
            vlm_config["vlm_layout_max_concurrent"] = int(config_params["vlm_layout_max_concurrent"])
            vlm_config["vlm_layout_batch_size"] = int(config_params["vlm_layout_max_concurrent"])
        if config_params.get("vlm_layout_batch_size"):
            vlm_config["vlm_layout_batch_size"] = int(config_params["vlm_layout_batch_size"])
        return vlm_config

    if layout_backend == "external_layout_sidecar":
        return external_layout_sidecar_fields(config_params)

    if layout_backend == "mineru_pp_doclayout_v2_direct":
        config = mineru_direct_layout_fields(config_params, include_external_mapping=True)
        config["mineru_layout_timeout"] = _int_param(config_params, "mineru_layout_timeout", 3600)
        config["mineru_layout_batch_size"] = _int_param(config_params, "mineru_layout_batch_size", 1)
        return config

    if layout_backend == "mineru_vl_layout":
        return mineru_vl_layout_fields(config_params)

    if layout_backend in ("paddle_pp_doclayout_plus_l", "paddle_pp_doclayout_v3"):
        return paddle_layout_fields(layout_backend, config_params, include_external_mapping=True)

    return {}


def ocr_backend_cli_config(ocr_backend: str, config_params: dict[str, Any]) -> dict[str, Any]:
    if ocr_backend == "chrome_screenai":
        return preprocess_backend_cli_config(config_params)

    if ocr_backend in ("vlm", "vlm_ocr"):
        vlm_mode = config_params.get("vlm_mode", "tile")
        return {
            "openai_base_url": config_params.get("openai_base_url", "http://127.0.0.1:1234/v1"),
            "openai_model": config_params.get("openai_model", "churro-3b"),
            "openai_api_key": config_params.get("openai_api_key", "lm-studio"),
            "openai_max_concurrent": _int_param(config_params, "openai_max_concurrent", 3),
            "openai_image_format": config_params.get("openai_image_format", "jpeg"),
            "vlm_prompt": config_params.get("vlm_prompt", ""),
            "vlm_response_mode": config_params.get("vlm_response_mode", "text"),
            "openai_use_stop": bool(config_params.get("openai_use_stop", False)),
            "vlm_full_page_ocr": vlm_mode == "full_page",
            "vlm_full_page_max_tokens": _int_param(config_params, "vlm_full_page_max_tokens", 2048),
            "vlm_merge_enabled": vlm_mode == "merge",
            "vlm_merge_y_threshold": _int_param(config_params, "vlm_merge_y_threshold", 80),
            "vlm_merge_max_blocks": _int_param(config_params, "vlm_merge_max_blocks", 15),
        }

    if ocr_backend == "calamari":
        return {
            "ocr_line_source": "tesseract",
            "calamari_base_url": config_params.get("calamari_base_url", "http://localhost:11800"),
            "calamari_model": config_params.get("calamari_model", "gt4histocr"),
            "calamari_batch_size": _int_param(config_params, "calamari_batch_size", 100),
            "calamari_timeout": _int_param(config_params, "calamari_timeout", 120),
            "calamari_sequential_mode": bool(config_params.get("calamari_sequential_mode", False)),
            "calamari_trust_batch_order": bool(config_params.get("calamari_trust_batch_order", True)),
            "calamari_require_ordering_info": bool(config_params.get("calamari_require_ordering_info", True)),
            "calamari_footnote_y_frac": _float_param(config_params, "calamari_footnote_y_frac", 0.83),
            "calamari_fallback_to_sequential_on_ordering_failure": bool(config_params.get("calamari_fallback_to_sequential_on_ordering_failure", True)),
            "calamari_binarize_lines": bool(config_params.get("calamari_binarize_lines", True)),
            "calamari_preprocess": config_params.get("calamari_preprocess", "otsu"),
            "calamari_crop_padding_px": _int_param(config_params, "calamari_crop_padding_px", 5),
            "calamari_crop_padding_frac": _float_param(config_params, "calamari_crop_padding_frac", 0.08),
            "calamari_upscale_min_height": _int_param(config_params, "calamari_upscale_min_height", 0),
            "calamari_split_large_batches": bool(config_params.get("calamari_split_large_batches", True)),
            "tesseract_cmd": config_params.get("tesseract_cmd"),
            "tesseract_lang": config_params.get("tesseract_lang", "eng"),
            "tesseract_oem": _int_param(config_params, "tesseract_oem", 1),
            "tesseract_line_psm": _int_param(config_params, "tesseract_line_psm", 1),
            "tesseract_line_preprocess": config_params.get("tesseract_line_preprocess", config_params.get("calamari_preprocess", "otsu")),
            "tesseract_line_upscale_min_height": _int_param(config_params, "tesseract_line_upscale_min_height", 0),
            "tesseract_thresholding_method": config_params.get("tesseract_thresholding_method", "auto"),
            "pages_per_batch": _int_param(config_params, "pages_per_batch", 1),
        }

    if ocr_backend == "paddle_ocr_v5":
        return paddle_ocr_fields(config_params)

    if ocr_backend == "paddleocr_vl_ocr":
        return paddleocr_vl_fields(config_params, pipeline_ocr=True)

    if ocr_backend == "mineru_pytorch_paddle_ocr":
        config = mineru_ocr_fields(config_params)
        config["mineru_ocr_timeout"] = _int_param(config_params, "mineru_ocr_timeout", 3600)
        return config

    if ocr_backend == "tesseract":
        return tesseract_ocr_fields(config_params)

    return {}


def llm_cli_config(config_params: dict[str, Any]) -> dict[str, Any]:
    if not config_params.get("use_llm"):
        return {}

    llm_provider = config_params.get("llm_provider", "gemini")
    cli = {
        "use_llm": True,
        "llm_max_concurrency": config_params.get("llm_max_concurrency", 3),
        "llm_table_enabled": config_params.get("llm_table_enabled", False),
        "llm_equation_enabled": config_params.get("llm_equation_enabled", False),
        "llm_image_description_enabled": config_params.get("llm_image_description_enabled", False),
        "image_description_language": config_params.get("llm_image_description_language", "auto"),
        "llm_handwriting_enabled": config_params.get("llm_handwriting_enabled", False),
        "llm_page_correction_enabled": config_params.get("llm_page_correction_enabled", False),
        "llm_section_header_enabled": config_params.get("llm_section_header_enabled", False),
        "llm_form_enabled": config_params.get("llm_form_enabled", False),
        "llm_complex_region_enabled": config_params.get("llm_complex_region_enabled", False),
        "llm_noise_removal_enabled": config_params.get("llm_noise_removal_enabled", False),
        "llm_printed_page_correction_enabled": config_params.get("llm_printed_page_correction_enabled", False),
        "llm_heuristic_layout_enabled": config_params.get("llm_heuristic_layout_enabled", False),
        "llm_thinking_mode": config_params.get("llm_thinking_mode", "off"),
    }
    if config_params.get("llm_image_description_enabled", False):
        cli["disable_image_extraction"] = True
    if config_params.get("llm_page_correction_prompt"):
        cli["llm_page_correction_prompt"] = config_params["llm_page_correction_prompt"]

    provider_to_service = {
        "lmstudio_native": "aih_contexture.services.lmstudio_native.LMStudioNativeService",
        "openai_compatible": "aih_contexture.services.openai.OpenAIService",
        "gemini": "aih_contexture.services.gemini.GoogleGeminiService",
        "azure": "aih_contexture.services.azure_openai.AzureOpenAIService",
        "claude": "aih_contexture.services.claude.ClaudeService",
        "ollama": "aih_contexture.services.ollama.OllamaService",
    }
    if llm_provider in provider_to_service:
        cli["llm_service"] = provider_to_service[llm_provider]

    if llm_provider == "lmstudio_native":
        cli["llm_provider"] = "lmstudio_native"
        if config_params.get("llm_base_url"):
            cli["lmstudio_base_url"] = config_params["llm_base_url"]
        if config_params.get("llm_model"):
            cli["lmstudio_model"] = config_params["llm_model"]
        if config_params.get("llm_api_key"):
            cli["lmstudio_api_key"] = config_params["llm_api_key"]
        cli["lmstudio_thinking_mode"] = config_params.get("llm_thinking_mode", "off")
    elif llm_provider == "openai_compatible":
        cli["llm_provider"] = "openai_compatible"
        if config_params.get("llm_base_url"):
            cli["openai_base_url"] = config_params["llm_base_url"]
        if config_params.get("llm_model"):
            cli["openai_model"] = config_params["llm_model"]
        if config_params.get("llm_api_key"):
            cli["openai_api_key"] = config_params["llm_api_key"]
        cli["vlm_response_mode"] = "json"
    elif llm_provider == "gemini":
        cli["llm_provider"] = "gemini"
        if config_params.get("llm_api_key"):
            cli["gemini_api_key"] = config_params["llm_api_key"]
        if config_params.get("llm_model"):
            cli["gemini_model_name"] = config_params["llm_model"]
        if config_params.get("llm_base_url"):
            cli["gemini_base_url"] = config_params["llm_base_url"]
    elif llm_provider == "azure":
        cli["llm_provider"] = "azure"
        if config_params.get("llm_base_url"):
            cli["azure_endpoint"] = config_params["llm_base_url"]
        if config_params.get("llm_api_key"):
            cli["azure_api_key"] = config_params["llm_api_key"]
        if config_params.get("llm_model"):
            cli["deployment_name"] = config_params["llm_model"]
        cli["azure_api_version"] = config_params.get("llm_api_version", "2024-08-01-preview")
    elif llm_provider == "claude":
        cli["llm_provider"] = "claude"
        if config_params.get("llm_api_key"):
            cli["claude_api_key"] = config_params["llm_api_key"]
        if config_params.get("llm_model"):
            cli["claude_model_name"] = config_params["llm_model"]
    elif llm_provider == "ollama":
        cli["llm_provider"] = "ollama"
        if config_params.get("llm_base_url"):
            cli["ollama_base_url"] = config_params["llm_base_url"]
        if config_params.get("llm_model"):
            cli["ollama_model"] = config_params["llm_model"]
        if config_params.get("llm_api_key"):
            cli["ollama_api_key"] = config_params["llm_api_key"]
    return cli


def scholarly_detection_cli_config(config_params: dict[str, Any]) -> dict[str, Any]:
    cli: dict[str, Any] = {}
    legacy_marginal_detection = bool(config_params.get("enable_marginal_detection", False))
    native_marginalia_enabled = bool(config_params.get("native_marginalia_enabled", legacy_marginal_detection))
    heuristic_marginal_detection_enabled = bool(
        config_params.get("heuristic_marginal_detection_enabled", legacy_marginal_detection)
    )
    enable_marginal_detection = native_marginalia_enabled or heuristic_marginal_detection_enabled
    cli["marginal_output_mode"] = normalize_marginal_output_mode(
        config_params.get("marginal_output_mode"),
        enable_marginal_detection=enable_marginal_detection,
    )
    if enable_marginal_detection:
        cli["enable_marginal_detection"] = True
        cli["native_marginalia_enabled"] = native_marginalia_enabled
        cli["heuristic_marginal_detection_enabled"] = heuristic_marginal_detection_enabled
        if heuristic_marginal_detection_enabled:
            cli["left_margin_threshold"] = _float_param(config_params, "left_margin_threshold", 0.15)
            cli["right_margin_threshold"] = _float_param(config_params, "right_margin_threshold", 0.85)
            cli["top_margin_threshold"] = _float_param(config_params, "top_margin_threshold", 0.10)
            cli["bottom_margin_threshold"] = _float_param(config_params, "bottom_margin_threshold", 0.90)
            cli["vertical_center_tolerance"] = _float_param(config_params, "vertical_center_tolerance", 0.05)

    if config_params.get("enable_inline_detection"):
        cli["enable_inline_detection"] = True
        cli["font_size_ratio_threshold"] = _float_param(config_params, "font_size_ratio_threshold", 0.75)
        cli["max_inline_annotation_length"] = _int_param(config_params, "max_inline_annotation_length", 100)
    return cli


def build_config_dict(config_params: dict[str, Any]) -> dict[str, Any]:
    conversion_mode = config_params.get("conversion_mode", "pipeline")

    if conversion_mode == "vlm_generalized":
        output_formats = (
            config_params.get("final_output_formats")
            or config_params.get("output_formats")
            or [config_params.get("output_format", "markdown")]
        )
        config, _ = build_vlm_generalized_config(
            config_params,
            output_formats=output_formats if isinstance(output_formats, (list, tuple)) else [output_formats],
            template_manager=None,
        )
        config["conversion_mode"] = conversion_mode
        return config

    if conversion_mode == "markdown_postprocess":
        return {
            "conversion_mode": conversion_mode,
            "markdown_postprocess_enabled": True,
            "markdown_postprocess_input_kind": config_params.get("markdown_postprocess_input_kind", "markdown"),
            "middle_rerender_include_provenance": bool(config_params.get("middle_rerender_include_provenance", False)),
            "middle_rerender_include_printed_page_comments": bool(config_params.get("middle_rerender_include_printed_page_comments", True)),
            "middle_rerender_include_page_header_comments": bool(config_params.get("middle_rerender_include_page_header_comments", True)),
            "middle_rerender_include_page_footer_comments": bool(config_params.get("middle_rerender_include_page_footer_comments", True)),
            "middle_rerender_include_margin_comments": bool(config_params.get("middle_rerender_include_margin_comments", True)),
            "middle_rerender_include_page_separators": bool(config_params.get("middle_rerender_include_page_separators", True)),
            "middle_rerender_apply_postprocess": bool(config_params.get("middle_rerender_apply_postprocess", False)),
            "markdown_postprocess_review_only": bool(config_params.get("markdown_postprocess_review_only", True)),
            "markdown_postprocess_enable_cleanup": bool(config_params.get("markdown_postprocess_enable_cleanup", True)),
            "markdown_postprocess_enable_printed_page_repair": bool(config_params.get("markdown_postprocess_enable_printed_page_repair", False)),
            "markdown_postprocess_enable_llm": bool(config_params.get("markdown_postprocess_enable_llm", False)),
            "markdown_postprocess_llm_provider": config_params.get("markdown_postprocess_llm_provider", "openai"),
            "markdown_postprocess_llm_base_url": config_params.get("markdown_postprocess_llm_base_url"),
            "markdown_postprocess_llm_model": config_params.get("markdown_postprocess_llm_model"),
            "markdown_postprocess_llm_api_key": config_params.get("markdown_postprocess_llm_api_key"),
            "markdown_postprocess_llm_timeout": _int_param(config_params, "markdown_postprocess_llm_timeout", 60),
            "markdown_postprocess_llm_max_retries": _int_param(config_params, "markdown_postprocess_llm_max_retries", 1),
            "markdown_postprocess_strict_null_policy": bool(config_params.get("markdown_postprocess_strict_null_policy", True)),
        }

    if conversion_mode == "vlm_specialized":
        return vlm_specialized_cli_config(config_params)

    ocr_backend = config_params.get("ocr_backend", "surya")
    layout_backend = config_params.get("layout_backend", "surya")
    ocr_preprocess_backend = _resolve_pipeline_ocr_preprocess_backend(
        str(ocr_backend),
        config_params.get("ocr_preprocess_backend", "none"),
    )
    if layout_backend == "yolo":
        raise ValueError(
            "layout_backend='yolo' 已从 Contexture 主线移除。"
            "请将历史配置迁移到 surya；后续强版面识别将通过 MinerU/Paddle layout adapter 接入。"
        )
    disable_ocr = ocr_backend == "none" or ocr_preprocess_backend != "none"
    disable_layout = layout_backend == "none"

    cli = pipeline_base_cli_config(
        config_params,
        ocr_backend=ocr_backend,
        layout_backend=layout_backend,
        disable_ocr=disable_ocr,
        disable_layout=disable_layout,
    )
    cli.update(preprocess_backend_cli_config(config_params))
    cli.update(page_numbering_cli_config(config_params))
    cli.update(layout_backend_cli_config(layout_backend, config_params))
    cli.update(ocr_backend_cli_config(ocr_backend, config_params))
    cli.update(llm_cli_config(config_params))
    cli.update(scholarly_detection_cli_config(config_params))

    config_parser = ConfigParser(cli)
    config_dict = config_parser.generate_config_dict()
    config_dict["pdftext_workers"] = 1
    config_dict["disable_ocr"] = disable_ocr
    return config_dict
