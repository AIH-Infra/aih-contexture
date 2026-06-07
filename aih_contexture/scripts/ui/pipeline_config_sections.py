from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aih_contexture.runtime.backend_field_sets import (
    external_layout_sidecar_fields,
    mineru_direct_layout_fields,
    mineru_layout_fields,
    paddle_layout_fields,
    paddle_ocr_fields,
    paddleocr_vl_fields,
    tesseract_ocr_fields,
)


PIPELINE_UI_VALUE_KEYS = (
    "conversion_mode",
    "process_mode",
    "batch_threshold",
    "pages_per_batch",
    "use_page_range",
    "start_page_1based",
    "end_page_1based",
    "use_fp16",
    "force_ocr",
    "use_llm",
    "ocr_batch_size",
    "layout_backend",
    "surya_layout_quality",
    "layout_dpi_override",
    "ocr_backend",
    "ocr_quality",
    "ocr_dpi_override",
    "emit_middle_json",
    "emit_middle_report",
    "emit_middle_debug",
    "emit_middle_scholarly",
    "emit_middle_scholarly_report",
    "emit_layout_overlay",
    "emit_span_overlay",
    "vlm_layout_timeout",
    "vlm_layout_prompt",
    "vlm_layout_prompt_template",
    "vlm_layout_base_url",
    "vlm_layout_model",
    "vlm_layout_api_key",
    "vlm_layout_max_concurrent",
    "vlm_layout_image_format",
    "vlm_layout_max_image_dimension",
    "vlm_layout_jpeg_quality",
    "external_layout_json",
    "external_layout_block_source",
    "external_layout_backend_name",
    "external_layout_model",
    "external_layout_allow_missing_pages",
    "mineru_command",
    "mineru_output_dir",
    "mineru_backend",
    "mineru_method",
    "mineru_lang",
    "mineru_api_url",
    "mineru_server_url",
    "mineru_timeout",
    "mineru_extra_args",
    "mineru_layout_python",
    "mineru_layout_model_dir",
    "mineru_layout_device",
    "mineru_layout_batch_size",
    "mineru_layout_use_paddlex_filter_boxes",
    "mineru_layout_timeout",
    "paddle_layout_model_name",
    "paddle_layout_python",
    "paddle_layout_model_dir",
    "paddle_layout_device",
    "paddle_layout_engine",
    "paddle_layout_enable_mkldnn",
    "paddle_layout_cpu_threads",
    "paddle_layout_threshold",
    "paddle_layout_img_size",
    "paddle_layout_batch_size",
    "openai_base_url",
    "openai_model",
    "openai_api_key",
    "openai_max_concurrent",
    "openai_image_format",
    "vlm_prompt",
    "vlm_response_mode",
    "openai_use_stop",
    "vlm_mode",
    "vlm_full_page_max_tokens",
    "vlm_merge_y_threshold",
    "vlm_merge_max_blocks",
    "calamari_base_url",
    "calamari_model",
    "calamari_batch_size",
    "calamari_timeout",
    "calamari_sequential_mode",
    "calamari_trust_batch_order",
    "calamari_footnote_y_frac",
    "calamari_require_ordering_info",
    "calamari_fallback_to_sequential_on_ordering_failure",
    "calamari_binarize_lines",
    "calamari_preprocess",
    "calamari_crop_padding_px",
    "calamari_crop_padding_frac",
    "calamari_upscale_min_height",
    "calamari_split_large_batches",
    "paddle_ocr_lang",
    "paddle_ocr_python",
    "paddle_ocr_version",
    "paddle_ocr_device",
    "paddle_ocr_engine",
    "paddle_ocr_enable_mkldnn",
    "paddle_ocr_cpu_threads",
    "paddle_ocr_use_doc_orientation_classify",
    "paddle_ocr_use_doc_unwarping",
    "paddle_ocr_use_textline_orientation",
    "paddleocr_vl_mode",
    "paddleocr_vl_version",
    "paddleocr_vl_endpoint",
    "paddleocr_vl_layout_parsing_url",
    "paddleocr_vl_model",
    "paddleocr_vl_api_key",
    "paddleocr_vl_api_style",
    "paddleocr_vl_request_concurrency",
    "paddleocr_vl_block_concurrency",
    "paddleocr_vl_prompt_label",
    "paddleocr_vl_image_format",
    "paddleocr_vl_image_quality",
    "paddleocr_vl_crop_padding_px",
    "paddleocr_vl_crop_padding_frac",
    "tesseract_profile",
    "tesseract_cmd",
    "tesseract_lang",
    "tesseract_oem",
    "tesseract_psm",
    "tesseract_line_psm",
    "tesseract_line_preprocess",
    "tesseract_line_upscale_min_height",
    "tesseract_thresholding_method",
    "tesseract_timeout",
    "tesseract_omp_thread_limit",
    "tesseract_tessdata_prefix",
    "tesseract_user_words",
    "tesseract_user_patterns",
    "tesseract_extra_config",
    "ocr_crop_padding_px",
    "ocr_crop_padding_frac",
    "ocr_crop_preprocess",
    "ocr_crop_upscale_min_height",
    "llm_provider",
    "llm_base_url",
    "llm_model",
    "llm_api_key",
    "llm_api_version",
    "llm_max_concurrency",
    "llm_timeout",
    "llm_thinking_mode",
    "llm_table_enabled",
    "llm_equation_enabled",
    "llm_image_description_enabled",
    "llm_image_description_language",
    "llm_handwriting_enabled",
    "llm_page_correction_enabled",
    "llm_section_header_enabled",
    "llm_form_enabled",
    "llm_complex_region_enabled",
    "llm_noise_removal_enabled",
    "llm_page_correction_prompt",
    "llm_printed_page_correction_enabled",
    "llm_heuristic_layout_enabled",
    "markdown_noise_removal_enabled",
    "markdown_noise_cleaning_level",
    "markdown_noise_custom_symbols",
    "markdown_noise_line_start_only",
    "blockquote_enabled",
    "line_merge_enabled",
    "code_enabled",
    "section_header_enabled",
    "equation_enabled",
    "list_enabled",
    "footnote_enabled",
    "reference_enabled",
    "table_enabled",
    "custom_id_source",
    "custom_id_data",
    "emit_page_header_comment",
    "emit_page_footer_comment",
    "keep_pageheader_in_output",
    "keep_pagefooter_in_output",
    "printed_page_enabled",
    "printed_page_format",
    "printed_page_custom_pattern",
    "printed_page_zones",
    "printed_page_header_end",
    "printed_page_footer_start",
    "enable_marginal_detection",
    "left_margin_threshold",
    "right_margin_threshold",
    "top_margin_threshold",
    "bottom_margin_threshold",
    "vertical_center_tolerance",
    "enable_inline_detection",
    "font_size_ratio_threshold",
    "max_inline_annotation_length",
)


def snapshot_pipeline_ui_values(values: Mapping[str, Any]) -> dict[str, Any]:
    """Freeze the Pipeline UI choices before handing work to the background runner."""
    return {key: values[key] for key in PIPELINE_UI_VALUE_KEYS if key in values}


def pipeline_config_for_page_range(page_range: tuple[int, int], values: Mapping[str, Any]) -> dict[str, Any]:
    start, end = page_range
    ocr_backend = values.get("ocr_backend", "surya")
    layout_backend = values.get("layout_backend", "surya")
    use_llm = bool(values.get("use_llm", False))
    conversion_mode = values.get("conversion_mode", "pipeline")
    ocr_batch_size = values.get("ocr_batch_size") or 32

    config: dict[str, Any] = {
        "ocr_batch_size": ocr_batch_size if ocr_backend in ["surya", "vlm", "vlm_ocr"] else 32,
        "use_fp16": values.get("use_fp16"),
        "force_ocr": False if ocr_backend == "none" else True,
        "use_llm": use_llm,
        "page_range": f"{start}-{end - 1}",
        "paginate_output": True,
        "page_separator": "\n\n---\n\n",
        "ocr_backend": ocr_backend,
        "layout_backend": layout_backend,
        "surya_layout_quality": values.get("surya_layout_quality", "fast"),
        "layout_dpi_override": values.get("layout_dpi_override"),
        "ocr_quality": values.get("ocr_quality", "auto"),
        "ocr_dpi_override": values.get("ocr_dpi_override"),
        "emit_middle_json": values.get("emit_middle_json"),
        "emit_middle_report": values.get("emit_middle_report"),
        "emit_middle_debug": values.get("emit_middle_debug"),
        "emit_middle_scholarly": values.get("emit_middle_scholarly"),
        "emit_middle_scholarly_report": values.get("emit_middle_scholarly_report"),
        "emit_layout_overlay": values.get("emit_layout_overlay"),
        "emit_span_overlay": values.get("emit_span_overlay"),
        "pages_per_batch": values.get("pages_per_batch", 25),
    }

    config.update(pipeline_layout_backend_config(str(layout_backend), values))
    config.update(pipeline_scholarly_config(values))
    config.update(pipeline_ocr_backend_config(str(ocr_backend), values))
    config.update(pipeline_llm_config(use_llm, values))
    config.update(pipeline_markdown_processor_config(values))
    config.update(pipeline_memory_config(str(conversion_mode), str(layout_backend), str(ocr_backend), values))
    return config


def pipeline_layout_backend_config(layout_backend: str, values: Mapping[str, Any]) -> dict[str, Any]:
    if layout_backend in ("vlm", "vlm_layout"):
        config = {
            "vlm_layout_timeout": values.get("vlm_layout_timeout"),
        }
        prompt = values.get("vlm_layout_prompt")
        prompt_template = values.get("vlm_layout_prompt_template")
        if prompt and str(prompt).strip():
            config["vlm_layout_prompt"] = prompt
        elif prompt_template and str(prompt_template).strip():
            config["vlm_layout_prompt_template"] = prompt_template
        else:
            config["vlm_layout_prompt_template"] = "modern"
        config.update({
            "vlm_layout_base_url": values.get("vlm_layout_base_url"),
            "vlm_layout_model": values.get("vlm_layout_model"),
            "vlm_layout_api_key": values.get("vlm_layout_api_key"),
            "vlm_layout_max_concurrent": values.get("vlm_layout_max_concurrent"),
            "vlm_layout_image_format": values.get("vlm_layout_image_format"),
            "vlm_layout_max_image_dimension": values.get("vlm_layout_max_image_dimension"),
            "vlm_layout_jpeg_quality": values.get("vlm_layout_jpeg_quality"),
        })
        return config

    if layout_backend == "external_layout_sidecar":
        return external_layout_sidecar_fields(values)

    if layout_backend == "mineru_pp_doclayout_v2":
        return mineru_layout_fields(values)

    if layout_backend == "mineru_pp_doclayout_v2_direct":
        return mineru_direct_layout_fields(values)

    if layout_backend in ("paddle_pp_doclayout_plus_l", "paddle_pp_doclayout_v3"):
        return paddle_layout_fields(layout_backend, values)

    return {}


def pipeline_ocr_backend_config(ocr_backend: str, values: Mapping[str, Any]) -> dict[str, Any]:
    if ocr_backend in ("vlm", "vlm_ocr"):
        return {
            "openai_base_url": values.get("openai_base_url"),
            "openai_model": values.get("openai_model"),
            "openai_api_key": values.get("openai_api_key"),
            "openai_max_concurrent": values.get("openai_max_concurrent"),
            "openai_image_format": values.get("openai_image_format"),
            "vlm_prompt": values.get("vlm_prompt"),
            "vlm_response_mode": values.get("vlm_response_mode"),
            "openai_use_stop": values.get("openai_use_stop"),
            "vlm_mode": values.get("vlm_mode"),
            "vlm_full_page_max_tokens": values.get("vlm_full_page_max_tokens"),
            "vlm_merge_y_threshold": values.get("vlm_merge_y_threshold"),
            "vlm_merge_max_blocks": values.get("vlm_merge_max_blocks"),
        }

    if ocr_backend == "calamari":
        return {
            "ocr_line_source": "tesseract",
            "calamari_base_url": values.get("calamari_base_url"),
            "calamari_model": values.get("calamari_model"),
            "calamari_batch_size": values.get("calamari_batch_size"),
            "calamari_timeout": values.get("calamari_timeout"),
            "calamari_sequential_mode": values.get("calamari_sequential_mode"),
            "calamari_trust_batch_order": values.get("calamari_trust_batch_order"),
            "calamari_footnote_y_frac": values.get("calamari_footnote_y_frac"),
            "calamari_require_ordering_info": values.get("calamari_require_ordering_info"),
            "calamari_fallback_to_sequential_on_ordering_failure": values.get("calamari_fallback_to_sequential_on_ordering_failure"),
            "calamari_binarize_lines": values.get("calamari_binarize_lines"),
            "calamari_preprocess": values.get("calamari_preprocess"),
            "calamari_crop_padding_px": values.get("calamari_crop_padding_px"),
            "calamari_crop_padding_frac": values.get("calamari_crop_padding_frac"),
            "calamari_upscale_min_height": values.get("calamari_upscale_min_height"),
            "calamari_split_large_batches": values.get("calamari_split_large_batches"),
            "tesseract_cmd": values.get("tesseract_cmd"),
            "tesseract_lang": values.get("tesseract_lang", "eng"),
            "tesseract_oem": values.get("tesseract_oem", 1),
            "tesseract_line_psm": values.get("tesseract_line_psm", 1),
            "tesseract_line_preprocess": values.get("tesseract_line_preprocess", values.get("calamari_preprocess", "otsu")),
            "tesseract_line_upscale_min_height": values.get("tesseract_line_upscale_min_height", 0),
            "tesseract_thresholding_method": values.get("tesseract_thresholding_method", "auto"),
        }

    if ocr_backend == "paddle_ocr_v5":
        return paddle_ocr_fields(values)

    if ocr_backend == "paddleocr_vl_ocr":
        return paddleocr_vl_fields(values, pipeline_ocr=True)

    if ocr_backend == "tesseract":
        return tesseract_ocr_fields(values)

    return {}


def pipeline_llm_config(use_llm: bool, values: Mapping[str, Any]) -> dict[str, Any]:
    if not use_llm:
        return {
            "llm_printed_page_correction_enabled": False,
            "markdown_formatting_enabled": True,
            "disable_image_extraction": False,
        }

    llm_provider = values.get("llm_provider")
    config = {
        "llm_provider": llm_provider,
        "llm_base_url": values.get("llm_base_url") if llm_provider in ["lmstudio_native", "openai_compatible", "azure", "ollama", "gemini"] else None,
        "llm_model": values.get("llm_model"),
        "llm_api_key": values.get("llm_api_key"),
        "llm_api_version": values.get("llm_api_version") if llm_provider == "azure" else None,
        "llm_max_concurrency": values.get("llm_max_concurrency"),
        "llm_timeout": values.get("llm_timeout"),
        "llm_thinking_mode": values.get("llm_thinking_mode"),
        "llm_table_enabled": values.get("llm_table_enabled"),
        "llm_equation_enabled": values.get("llm_equation_enabled"),
        "llm_image_description_enabled": values.get("llm_image_description_enabled"),
        "llm_image_description_language": values.get("llm_image_description_language"),
        "llm_handwriting_enabled": values.get("llm_handwriting_enabled"),
        "llm_page_correction_enabled": values.get("llm_page_correction_enabled"),
        "llm_section_header_enabled": values.get("llm_section_header_enabled"),
        "llm_form_enabled": values.get("llm_form_enabled"),
        "llm_complex_region_enabled": values.get("llm_complex_region_enabled"),
        "llm_noise_removal_enabled": values.get("llm_noise_removal_enabled"),
        "llm_page_correction_prompt": values.get("llm_page_correction_prompt"),
    }
    config.update({
        "llm_printed_page_correction_enabled": values.get("llm_printed_page_correction_enabled"),
        "markdown_formatting_enabled": values.get("llm_heuristic_layout_enabled"),
        "disable_image_extraction": values.get("llm_image_description_enabled"),
    })
    return config


def pipeline_markdown_processor_config(values: Mapping[str, Any]) -> dict[str, Any]:
    footnote_enabled = bool(values.get("footnote_enabled", False))
    return {
        "markdown_noise_removal_enabled": values.get("markdown_noise_removal_enabled", True),
        "markdown_noise_cleaning_level": values.get("markdown_noise_cleaning_level", "basic"),
        "markdown_noise_custom_symbols": values.get("markdown_noise_custom_symbols", ""),
        "markdown_noise_line_start_only": values.get("markdown_noise_line_start_only", True),
        "blockquote_enabled": values.get("blockquote_enabled", True),
        "line_merge_enabled": values.get("line_merge_enabled", True),
        "code_enabled": values.get("code_enabled", True),
        "section_header_enabled": values.get("section_header_enabled", True),
        "equation_enabled": values.get("equation_enabled", True),
        "list_enabled": values.get("list_enabled", True),
        "footnote_enabled": footnote_enabled,
        "superscript_policy": "preserve_all" if footnote_enabled else "suppress_footnote_like",
        "reference_enabled": values.get("reference_enabled", True),
        "table_enabled": values.get("table_enabled", True),
    }


def pipeline_memory_config(
    conversion_mode: str,
    layout_backend: str,
    ocr_backend: str,
    values: Mapping[str, Any],
) -> dict[str, Any]:
    memory_optimized_pipeline = (
        conversion_mode == "pipeline"
        and layout_backend == "surya"
        and ocr_backend == "none"
        and not values.get("table_enabled", True)
        and not values.get("equation_enabled", True)
    )
    if not memory_optimized_pipeline:
        return {}
    return {
        "build_highres_images": False,
        "image_extraction_mode": "lowres",
    }


def pipeline_scholarly_config(values: Mapping[str, Any]) -> dict[str, Any]:
    printed_page_enabled = bool(values.get("printed_page_enabled", False))
    emit_page_header_comment = bool(values.get("emit_page_header_comment", False))
    emit_page_footer_comment = bool(values.get("emit_page_footer_comment", False))
    keep_pageheader_in_output = bool(values.get("keep_pageheader_in_output", False))
    keep_pagefooter_in_output = bool(values.get("keep_pagefooter_in_output", False))
    enable_marginal_detection = bool(values.get("enable_marginal_detection", False))
    enable_inline_detection = bool(values.get("enable_inline_detection", False))

    config: dict[str, Any] = {
        "custom_id_source": values.get("custom_id_source"),
        "custom_id_data": values.get("custom_id_data"),
        "emit_page_header_comment": emit_page_header_comment,
        "emit_page_footer_comment": emit_page_footer_comment,
        "keep_pageheader_in_output": keep_pageheader_in_output,
        "keep_pagefooter_in_output": keep_pagefooter_in_output,
    }

    if (
        printed_page_enabled
        or emit_page_header_comment
        or emit_page_footer_comment
        or keep_pageheader_in_output
        or keep_pagefooter_in_output
    ):
        config.update({
            "printed_page_zones": values.get("printed_page_zones"),
            "printed_page_header_y_frac": values.get("printed_page_header_end"),
            "printed_page_footer_y_frac": values.get("printed_page_footer_start"),
        })

    if printed_page_enabled:
        custom_pattern = values.get("printed_page_custom_pattern")
        config.update({
            "use_printed_page_number": True,
            "page_numbering_enabled": True,
            "page_number_format": values.get("printed_page_format"),
            "page_number_custom_pattern": custom_pattern if custom_pattern else None,
        })
    else:
        config["page_numbering_enabled"] = False

    if enable_marginal_detection:
        config.update({
            "enable_marginal_detection": True,
            "left_margin_threshold": values.get("left_margin_threshold"),
            "right_margin_threshold": values.get("right_margin_threshold"),
            "top_margin_threshold": values.get("top_margin_threshold"),
            "bottom_margin_threshold": values.get("bottom_margin_threshold"),
            "vertical_center_tolerance": values.get("vertical_center_tolerance"),
        })
    else:
        config["enable_marginal_detection"] = False

    if enable_inline_detection:
        config.update({
            "enable_inline_detection": True,
            "font_size_ratio_threshold": values.get("font_size_ratio_threshold"),
            "max_inline_annotation_length": values.get("max_inline_annotation_length"),
        })
    else:
        config["enable_inline_detection"] = False

    return config
