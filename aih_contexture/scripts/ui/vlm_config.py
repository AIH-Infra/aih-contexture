from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from aih_contexture.config.vlm_model_presets import (
    default_quant,
    default_version,
    normalize_quant,
    normalize_version,
    resolve_vlm_model,
)


def _fallback(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str) and value.strip().lower() in {"", "none"}:
        return default
    return value


def _default_vlm_ocr_api_style(ocr_backend: str) -> str:
    if ocr_backend == "surya2":
        return "openai"
    return "openai" if ocr_backend == "churro" else "lmstudio-native"


def _default_vlm_ocr_endpoint(api_style: str) -> str:
    if api_style in {"openai", "openai-compatible"}:
        return "http://localhost:1234/v1/chat/completions"
    return "http://localhost:1234/api/v1/chat"


def _page_range_value(use_range: bool, start_page: Any, end_page: Any) -> str | None:
    if use_range and start_page and end_page:
        start0 = max(0, int(start_page) - 1)
        end0 = int(end_page) - 1
        return f"{start0}-{end0}"
    return None


def build_vlm_generalized_config(
    values: Mapping[str, Any],
    *,
    output_formats: Sequence[str],
    template_manager: Any | None = None,
) -> tuple[dict[str, Any], str | None]:
    selected_template_id = values.get("selected_template_id")
    selected_preset = values.get("selected_preset")
    preset_options = values.get("preset_options") or {
        "高准确性（默认）": "high_accuracy",
        "平衡": "balanced",
        "创意": "creative",
        "自定义": "custom",
    }
    api_preset = preset_options.get(selected_preset, selected_preset) or "high_accuracy"
    config: dict[str, Any] = {
        "vlm_api_provider": values.get("vlm_api_provider"),
        "vlm_direct_base_url": values.get("vlm_direct_base_url"),
        "vlm_direct_model": values.get("vlm_direct_model"),
        "vlm_direct_api_key": values.get("vlm_direct_api_key"),
        "vlm_direct_output_mode": "json",
        "final_output_formats": list(output_formats),
        "vlm_direct_max_concurrent": values.get("vlm_direct_max_concurrent"),
        "vlm_direct_image_format": values.get("vlm_direct_image_format"),
        "vlm_direct_max_image_dimension": values.get("vlm_direct_max_image_dimension"),
        "vlm_direct_jpeg_quality": values.get("vlm_direct_jpeg_quality"),
        "vlm_direct_timeout": values.get("vlm_direct_timeout"),
        "vlm_direct_max_tokens": 0,
        "vlm_direct_max_retries": values.get("vlm_direct_max_retries"),
        "vlm_auto_repair_failed_pages": values.get("vlm_auto_repair_failed_pages"),
        "vlm_repair_max_concurrent": values.get("vlm_repair_max_concurrent"),
        "vlm_repair_rounds": values.get("vlm_repair_rounds"),
        "vlm_direct_disable_thinking": True,
        "vlm_direct_enable_page_anchors": values.get("vlm_direct_enable_page_anchors"),
        "vlm_direct_page_anchor_wrapper": "{{{}}}",
        "vlm_direct_page_anchor_position": values.get("vlm_direct_page_anchor_position"),
        "vlm_direct_extract_printed_pages": values.get("vlm_direct_extract_printed_pages"),
        "vlm_direct_printed_page_patterns": values.get("vlm_direct_printed_page_patterns"),
        "vlm_direct_custom_id_source": values.get("vlm_direct_custom_id_source"),
        "vlm_direct_custom_id_data": values.get("vlm_direct_custom_id_data"),
        "vlm_direct_prompt_template": selected_template_id,
        "vlm_direct_api_preset": api_preset,
        "vlm_direct_prompt_params": {
            "text_direction": values.get("text_direction"),
            "primary_language": values.get("primary_language"),
            "handwriting_mode": values.get("handwriting_mode"),
            "describe_images": values.get("describe_images"),
            "anti_hallucination": values.get("anti_hallucination"),
            "extract_bboxes": values.get("extract_bboxes"),
            "include_confidence": values.get("include_confidence"),
            "enhance_tables_equations": values.get("enhance_tables_equations"),
            "may_have_page_numbers": values.get("has_page_numbers"),
            "enable_marginalia": values.get("enable_marginalia"),
            "may_have_footnotes": values.get("enable_footnotes"),
        },
        "vlm_direct_marginal_note_enabled": values.get("enable_marginalia"),
        "vlm_direct_use_markdown_footnotes": False,
        "vlm_direct_footnote_backlink": False,
        "emit_middle_json": values.get("emit_middle_json"),
        "emit_middle_report": values.get("emit_middle_report"),
        "emit_middle_debug": values.get("emit_middle_debug"),
        "emit_middle_scholarly": values.get("emit_middle_scholarly"),
        "emit_middle_scholarly_report": values.get("emit_middle_scholarly_report"),
        "emit_layout_overlay": values.get("emit_layout_overlay"),
        "emit_span_overlay": values.get("emit_span_overlay"),
        "emit_middle_full_json": values.get("emit_middle_full_json"),
        "vlm_noise_removal": values.get("vlm_noise_removal"),
        "vlm_noise_patterns": values.get("vlm_noise_patterns"),
        "vlm_footnote_fix": values.get("vlm_footnote_fix"),
        "vlm_hyphenation_fix": values.get("vlm_hyphenation_fix"),
        "vlm_filter_page_header": values.get("vlm_filter_page_header"),
        "vlm_filter_page_footer": values.get("vlm_filter_page_footer"),
        "vlm_filter_margin_notes": values.get("vlm_filter_margin_notes"),
        "vlm_filter_blockquote_markers": values.get("vlm_filter_blockquote_markers"),
        "include_page_header_comments": not bool(values.get("vlm_filter_page_header")),
        "include_page_footer_comments": not bool(values.get("vlm_filter_page_footer")),
        "include_margin_comments": not bool(values.get("vlm_filter_margin_notes")),
        "include_blockquote_markers": not bool(values.get("vlm_filter_blockquote_markers")),
    }

    preset_api_params = {
        "high_accuracy": {"vlm_direct_temperature": 0.0, "vlm_direct_top_p": 0.1},
        "balanced": {"vlm_direct_temperature": 0.2, "vlm_direct_top_p": 0.3},
        "creative": {"vlm_direct_temperature": 0.5, "vlm_direct_top_p": 0.8},
    }
    if api_preset in preset_api_params:
        config.update(preset_api_params[api_preset])

    for source_key, target_key in (
        ("vlm_direct_temperature", "vlm_direct_temperature"),
        ("vlm_direct_top_p", "vlm_direct_top_p"),
        ("vlm_direct_top_k", "vlm_direct_top_k"),
    ):
        if values.get(source_key) is not None:
            config[target_key] = values[source_key]

    page_range = _page_range_value(
        bool(values.get("vlm_use_page_range")),
        values.get("vlm_start_page"),
        values.get("vlm_end_page"),
    )
    if page_range:
        config["page_range"] = page_range

    prompt_message = None
    edited_prompt = values.get("edited_prompt")
    if template_manager is not None and selected_template_id:
        original_prompt = template_manager.get_template(selected_template_id)
        if edited_prompt != original_prompt:
            config["vlm_direct_prompt"] = edited_prompt
            prompt_message = "ℹ️ 使用编辑后的提示词（临时生效，未保存到模板）"
        else:
            templates = template_manager.list_templates()
            template_name = templates.get(selected_template_id, {}).get("name", selected_template_id)
            prompt_message = f"ℹ️ 使用模板：{template_name}"

    return config, prompt_message


def build_vlm_specialized_config(
    values: Mapping[str, Any],
    *,
    output_formats: Sequence[str],
) -> dict[str, Any]:
    ocr_backend = values.get("ocr_backend", "chandra")
    is_chrome_screenai = ocr_backend == "chrome_screenai"
    default_api_style = _default_vlm_ocr_api_style(ocr_backend)
    ocr_api_style = _fallback(values.get("ocr_api_style"), default_api_style)
    default_endpoint = _fallback(values.get("openai_base_url"), _default_vlm_ocr_endpoint(ocr_api_style))
    ocr_endpoint = _fallback(values.get("ocr_endpoint"), default_endpoint)
    chandra_version = normalize_version("chandra", _fallback(values.get("chandra_version"), default_version("chandra")))
    chandra_quant = normalize_quant("chandra", chandra_version, _fallback(values.get("chandra_quant"), default_quant("chandra")))
    churro_version = normalize_version("churro", _fallback(values.get("churro_version"), default_version("churro")))
    churro_quant = normalize_quant("churro", churro_version, _fallback(values.get("churro_quant"), default_quant("churro")))
    paddleocr_vl_version = normalize_version(
        "paddleocr_vl",
        _fallback(values.get("paddleocr_vl_version"), default_version("paddleocr_vl")),
    )
    mineru_vl_version = normalize_version("mineru_vl", _fallback(values.get("mineru_vl_version"), default_version("mineru_vl")))
    mineru_vl_quant = normalize_quant(
        "mineru_vl",
        mineru_vl_version,
        _fallback(values.get("mineru_vl_quant"), default_quant("mineru_vl")),
    )
    surya2_version = normalize_version("surya2", _fallback(values.get("surya2_version"), default_version("surya2")))
    if is_chrome_screenai:
        default_model = "chrome-screenai-local"
    elif ocr_backend == "chandra":
        default_model = resolve_vlm_model(ocr_backend, version=chandra_version, quant=chandra_quant)
    elif ocr_backend == "churro":
        default_model = resolve_vlm_model(ocr_backend, version=churro_version, quant=churro_quant)
    elif ocr_backend == "paddleocr_vl":
        default_model = resolve_vlm_model(ocr_backend, version=paddleocr_vl_version)
    elif ocr_backend == "surya2":
        default_model = resolve_vlm_model(ocr_backend, version=surya2_version)
    else:
        default_model = resolve_vlm_model(ocr_backend, version=mineru_vl_version, quant=mineru_vl_quant)
    ocr_model = _fallback(values.get("ocr_model"), _fallback(values.get("openai_model"), default_model))
    ocr_api_key = values.get("ocr_api_key")
    if not ocr_api_key:
        ocr_api_key = values.get("openai_api_key")
    output_format = "html"
    if is_chrome_screenai:
        output_format = "html"
    elif ocr_backend == "churro":
        output_format = "xml"
    elif ocr_backend in {"paddleocr_vl", "mineru_vl", "surya2"}:
        output_format = "json"
    ocr_timeout = _fallback(values.get("ocr_timeout"), 120)
    if ocr_backend == "mineru_vl" and ocr_api_style == "lmstudio-native":
        ocr_timeout = max(int(ocr_timeout), 600)
    default_resize_max = 2500 if ocr_backend == "churro" else 1024
    default_image_quality = 95 if ocr_backend == "churro" else 60
    default_image_format = "PNG" if ocr_backend == "churro" else "JPEG"
    default_max_tokens = 20000 if ocr_backend == "churro" else 4096

    config: dict[str, Any] = {
        "ocr_backend": ocr_backend,
        "chandra_version": chandra_version if ocr_backend == "chandra" else None,
        "chandra_quant": chandra_quant if ocr_backend == "chandra" else None,
        "churro_version": churro_version if ocr_backend == "churro" else None,
        "churro_quant": churro_quant if ocr_backend == "churro" else None,
        "paddleocr_vl_version": paddleocr_vl_version if ocr_backend == "paddleocr_vl" else None,
        "mineru_vl_version": mineru_vl_version if ocr_backend == "mineru_vl" else None,
        "mineru_vl_quant": mineru_vl_quant if ocr_backend == "mineru_vl" else None,
        "surya2_version": surya2_version if ocr_backend == "surya2" else None,
        "ocr_api_style": None if is_chrome_screenai else ocr_api_style,
        "ocr_endpoint": None if is_chrome_screenai else ocr_endpoint,
        "ocr_model": None if is_chrome_screenai else ocr_model,
        "ocr_api_key": None if is_chrome_screenai else (ocr_api_key if ocr_api_key else None),
        "ocr_output_format": output_format,
        "final_output_formats": list(output_formats),
        "ocr_concurrency": _fallback(values.get("ocr_concurrency"), 2 if is_chrome_screenai else 5),
        "ocr_batch_size": _fallback(values.get("ocr_batch_size"), 4 if is_chrome_screenai else 10),
        "ocr_batch_rest": _fallback(values.get("ocr_batch_rest"), 2.0),
        "ocr_max_retries": _fallback(values.get("ocr_max_retries"), 3),
        "ocr_resize_max": _fallback(values.get("ocr_resize_max"), default_resize_max),
        "ocr_image_format": _fallback(values.get("ocr_image_format"), default_image_format),
        "ocr_image_quality": _fallback(values.get("ocr_image_quality"), default_image_quality),
        "ocr_timeout": ocr_timeout,
        "ocr_max_tokens": _fallback(values.get("ocr_max_tokens"), 0 if is_chrome_screenai else default_max_tokens),
        "ocr_temperature": 0.6 if ocr_backend == "churro" else 0.0,
        "paddleocr_vl_endpoint": _fallback(values.get("paddleocr_vl_endpoint"), ocr_endpoint),
        "paddleocr_vl_model": _fallback(values.get("paddleocr_vl_model"), ocr_model),
        "paddleocr_vl_api_key": _fallback(values.get("paddleocr_vl_api_key"), ocr_api_key) if ocr_api_key else values.get("paddleocr_vl_api_key"),
        "paddleocr_vl_api_style": _fallback(values.get("paddleocr_vl_api_style"), ocr_api_style),
        "paddleocr_vl_request_concurrency": _fallback(
            values.get("paddleocr_vl_request_concurrency"),
            _fallback(values.get("ocr_concurrency"), 5),
        ),
        "paddleocr_vl_block_concurrency": _fallback(
            values.get("paddleocr_vl_block_concurrency"),
            _fallback(values.get("ocr_concurrency"), 5),
        ),
        "paddleocr_vl_prompt_label": values.get("paddleocr_vl_prompt_label", "layout_detection"),
        "paddleocr_vl_image_format": _fallback(values.get("paddleocr_vl_image_format"), default_image_format),
        "paddleocr_vl_image_quality": _fallback(values.get("paddleocr_vl_image_quality"), default_image_quality),
        "paddleocr_vl_crop_padding_px": _fallback(values.get("paddleocr_vl_crop_padding_px"), 4),
        "paddleocr_vl_crop_padding_frac": _fallback(values.get("paddleocr_vl_crop_padding_frac"), 0.02),
        "mineru_vl_block_concurrency": _fallback(values.get("mineru_vl_block_concurrency"), 4),
        "mineru_vl_request_concurrency": _fallback(
            values.get("mineru_vl_request_concurrency"),
            1 if ocr_api_style == "lmstudio-native" else _fallback(values.get("mineru_vl_block_concurrency"), 4),
        ),
        "mineru_vl_layout_image_size": _fallback(values.get("mineru_vl_layout_image_size"), (1036, 1036)),
        "surya2_endpoint": _fallback(values.get("surya2_endpoint"), ocr_endpoint),
        "surya2_model": _fallback(values.get("surya2_model"), ocr_model),
        "surya2_api_key": _fallback(values.get("surya2_api_key"), ocr_api_key) if ocr_api_key else values.get("surya2_api_key"),
        "surya2_api_style": _fallback(values.get("surya2_api_style"), ocr_api_style),
        "surya2_request_concurrency": _fallback(
            values.get("surya2_request_concurrency"),
            _fallback(values.get("ocr_concurrency"), 6),
        ),
        "surya2_block_concurrency": _fallback(values.get("surya2_block_concurrency"), 4),
        "surya2_image_format": _fallback(values.get("surya2_image_format"), "PNG"),
        "surya2_image_quality": _fallback(values.get("surya2_image_quality"), 90),
        "ocr_page_anchor_enabled": _fallback(values.get("enable_page_anchors"), True),
        "ocr_page_anchor_wrapper": "{{{}}}",
        "ocr_page_anchor_position": _fallback(values.get("page_anchor_position"), "before"),
        "ocr_extract_printed_pages": _fallback(values.get("extract_printed_pages"), True),
        "ocr_printed_page_patterns": values.get("vlm_printed_page_patterns"),
        "ocr_custom_id_source": _fallback(values.get("custom_id_source"), "none"),
        "ocr_custom_id_data": values.get("custom_id_data"),
        "ocr_noise_removal": _fallback(values.get("ocr_noise_removal"), True),
        "ocr_noise_patterns": _fallback(values.get("ocr_noise_patterns"), ""),
        "ocr_footnote_fix": _fallback(values.get("ocr_footnote_fix"), True),
        "ocr_hyphenation_fix": _fallback(values.get("ocr_hyphenation_fix"), True),
        "ocr_filter_page_header": _fallback(values.get("ocr_filter_page_header"), False),
        "ocr_filter_page_footer": _fallback(values.get("ocr_filter_page_footer"), False),
        "ocr_filter_margin_notes": _fallback(values.get("ocr_filter_margin_notes"), False),
        "ocr_filter_blockquote_markers": _fallback(values.get("ocr_filter_blockquote_markers"), False),
        "include_page_header_comments": not bool(_fallback(values.get("ocr_filter_page_header"), False)),
        "include_page_footer_comments": not bool(_fallback(values.get("ocr_filter_page_footer"), False)),
        "include_margin_comments": not bool(_fallback(values.get("ocr_filter_margin_notes"), False)),
        "include_blockquote_markers": not bool(_fallback(values.get("ocr_filter_blockquote_markers"), False)),
        "emit_middle_json": values.get("emit_middle_json"),
        "emit_middle_report": values.get("emit_middle_report"),
        "emit_middle_debug": values.get("emit_middle_debug"),
        "emit_middle_scholarly": values.get("emit_middle_scholarly"),
        "emit_middle_scholarly_report": values.get("emit_middle_scholarly_report"),
        "emit_layout_overlay": values.get("emit_layout_overlay"),
        "emit_span_overlay": values.get("emit_span_overlay"),
        "emit_middle_full_json": values.get("emit_middle_full_json"),
        "chrome_screenai_light": bool(_fallback(values.get("chrome_screenai_light"), False)),
        "chrome_preprocess_mode": _fallback(values.get("chrome_preprocess_mode"), "native"),
        "chrome_workers": _fallback(values.get("chrome_workers"), _fallback(values.get("ocr_concurrency"), 2)),
        "chrome_chunk_pages": _fallback(values.get("chrome_chunk_pages"), _fallback(values.get("ocr_batch_size"), 4)),
        "chrome_emit_searchable_pdf": bool(_fallback(values.get("chrome_emit_searchable_pdf"), False)),
        "chrome_rasterize_dpi": _fallback(values.get("chrome_rasterize_dpi"), 144),
        "chrome_model_dir": _fallback(values.get("chrome_model_dir"), None),
    }

    page_range = _page_range_value(
        bool(values.get("ocr_use_page_range")),
        values.get("ocr_start_page"),
        values.get("ocr_end_page"),
    )
    if page_range:
        config["page_range"] = page_range

    return config
