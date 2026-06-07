from aih_contexture.scripts.ui.pipeline_config_sections import (
    pipeline_config_for_page_range,
    pipeline_layout_backend_config,
    pipeline_llm_config,
    pipeline_markdown_processor_config,
    pipeline_memory_config,
    pipeline_ocr_backend_config,
    pipeline_scholarly_config,
    snapshot_pipeline_ui_values,
)


def test_pipeline_config_for_page_range_combines_core_sections():
    config = pipeline_config_for_page_range(
        (2, 5),
        {
            "conversion_mode": "pipeline",
            "ocr_backend": "none",
            "layout_backend": "surya",
            "ocr_batch_size": 8,
            "use_fp16": True,
            "force_ocr": False,
            "use_llm": False,
            "emit_middle_json": True,
            "emit_layout_overlay": False,
            "emit_span_overlay": True,
            "pages_per_batch": 3,
            "table_enabled": False,
            "equation_enabled": False,
            "footnote_enabled": True,
        },
    )

    assert config["page_range"] == "2-4"
    assert config["ocr_batch_size"] == 32
    assert config["paginate_output"] is True
    assert config["emit_middle_json"] is True
    assert config["llm_printed_page_correction_enabled"] is False
    assert config["superscript_policy"] == "preserve_all"
    assert config["build_highres_images"] is False


def test_pipeline_config_for_page_range_uses_backend_specific_sections():
    config = pipeline_config_for_page_range(
        (0, 1),
        {
            "conversion_mode": "pipeline",
            "ocr_backend": "paddle_ocr_v5",
            "layout_backend": "paddle_pp_doclayout_v3",
            "ocr_batch_size": 99,
            "use_fp16": False,
            "force_ocr": True,
            "use_llm": True,
            "llm_provider": "claude",
            "llm_model": "claude-model",
            "paddle_layout_threshold": 0.4,
            "paddle_ocr_lang": "en",
            "footnote_enabled": False,
        },
    )

    assert config["ocr_batch_size"] == 32
    assert config["paddle_layout_model_name"] == "PP-DocLayoutV3"
    assert config["paddle_layout_threshold"] == 0.4
    assert config["paddle_ocr_lang"] == "en"
    assert config["llm_provider"] == "claude"
    assert config["llm_base_url"] is None
    assert config["superscript_policy"] == "suppress_footnote_like"
    assert "build_highres_images" not in config


def test_pipeline_ui_snapshot_preserves_selected_mineru_layout_and_paddle_ocr():
    values = snapshot_pipeline_ui_values(
        {
            "conversion_mode": "pipeline",
            "layout_backend": "mineru_pp_doclayout_v2",
            "ocr_backend": "paddle_ocr_v5",
            "mineru_command": r"D:\ExternalBackends\MinerU\.venv-mineru\Scripts\mineru.exe",
            "mineru_backend": "pipeline",
            "mineru_method": "txt",
            "mineru_lang": "en",
            "mineru_timeout": 7200,
            "paddle_ocr_lang": "en",
            "paddle_ocr_python": r"D:\ExternalBackends\PaddleOCR\.venv-paddle-gpu\Scripts\python.exe",
            "paddle_ocr_version": "PP-OCRv5",
            "paddle_ocr_device": "cpu",
            "process_mode": "自动",
            "pages_per_batch": 25,
            "unknown_widget": "ignored",
        }
    )
    config = pipeline_config_for_page_range((0, 1), values)

    assert values["layout_backend"] == "mineru_pp_doclayout_v2"
    assert values["ocr_backend"] == "paddle_ocr_v5"
    assert "unknown_widget" not in values
    assert config["layout_backend"] == "mineru_pp_doclayout_v2"
    assert config["ocr_backend"] == "paddle_ocr_v5"
    assert config["mineru_command"].endswith(r"\mineru.exe")
    assert config["mineru_lang"] == "en"
    assert config["paddle_ocr_lang"] == "en"
    assert config["paddle_ocr_python"].endswith(r"\python.exe")
    assert config["paddle_ocr_device"] == "cpu"


def test_pipeline_layout_backend_config_vlm_prefers_manual_prompt():
    config = pipeline_layout_backend_config(
        "vlm_layout",
        {
            "vlm_layout_timeout": 120,
            "vlm_layout_prompt": "manual",
            "vlm_layout_prompt_template": "modern",
            "vlm_layout_base_url": "http://localhost:1234/v1",
            "vlm_layout_model": "qwen-vl",
            "vlm_layout_api_key": "key",
            "vlm_layout_max_concurrent": 2,
            "vlm_layout_image_format": "png",
            "vlm_layout_max_image_dimension": 1600,
            "vlm_layout_jpeg_quality": 90,
        },
    )

    assert config["vlm_layout_prompt"] == "manual"
    assert "vlm_layout_prompt_template" not in config
    assert config["vlm_layout_model"] == "qwen-vl"


def test_pipeline_layout_backend_config_vlm_uses_modern_template_fallback():
    config = pipeline_layout_backend_config("vlm_layout", {})

    assert config["vlm_layout_prompt_template"] == "modern"


def test_pipeline_layout_backend_config_external_sidecar_defaults():
    config = pipeline_layout_backend_config("external_layout_sidecar", {"external_layout_json": "layout.json"})

    assert config == {
        "external_layout_json": "layout.json",
        "external_layout_block_source": "auto",
        "external_layout_backend_name": "external_layout_sidecar",
        "external_layout_model": None,
        "external_layout_allow_missing_pages": False,
    }


def test_pipeline_layout_backend_config_mineru_defaults():
    config = pipeline_layout_backend_config("mineru_pp_doclayout_v2", {})

    assert config["mineru_command"] == "mineru"
    assert config["mineru_backend"] == "pipeline"
    assert config["mineru_method"] == "txt"
    assert config["mineru_lang"] == "ch"
    assert config["mineru_timeout"] == 3600


def test_pipeline_layout_backend_config_mineru_direct_defaults():
    config = pipeline_layout_backend_config("mineru_pp_doclayout_v2_direct", {})

    assert config["mineru_layout_batch_size"] == 1
    assert config["mineru_layout_timeout"] == 3600
    assert config["mineru_layout_python"] is None


def test_pipeline_layout_backend_config_paddle_v3_default_model():
    config = pipeline_layout_backend_config(
        "paddle_pp_doclayout_v3",
        {"paddle_layout_python": r"D:\ExternalBackends\PaddleOCR\.venv-paddle-gpu\Scripts\python.exe"},
    )

    assert config["paddle_layout_model_name"] == "PP-DocLayoutV3"
    assert config["paddle_layout_python"].endswith(r"\python.exe")
    assert config["paddle_layout_enable_mkldnn"] is False


def test_pipeline_ocr_backend_config_vlm_preserves_openai_fields():
    config = pipeline_ocr_backend_config(
        "vlm_ocr",
        {
            "openai_base_url": "http://localhost:1234/v1",
            "openai_model": "model",
            "openai_api_key": "key",
            "openai_max_concurrent": 3,
            "openai_image_format": "webp",
            "vlm_prompt": "prompt",
            "vlm_response_mode": "markdown",
            "openai_use_stop": True,
            "vlm_mode": "tile",
            "vlm_full_page_max_tokens": 2048,
            "vlm_merge_y_threshold": 12,
            "vlm_merge_max_blocks": 4,
        },
    )

    assert config["openai_model"] == "model"
    assert config["openai_max_concurrent"] == 3
    assert config["vlm_merge_max_blocks"] == 4


def test_pipeline_ocr_backend_config_calamari_preserves_flags():
    config = pipeline_ocr_backend_config(
        "calamari",
        {
            "calamari_base_url": "http://localhost:11800",
            "calamari_model": "gt4histocr",
            "calamari_batch_size": 100,
            "calamari_timeout": 120,
            "calamari_sequential_mode": True,
            "calamari_trust_batch_order": False,
            "calamari_footnote_y_frac": 0.9,
            "calamari_require_ordering_info": False,
            "calamari_fallback_to_sequential_on_ordering_failure": False,
            "calamari_binarize_lines": True,
            "calamari_preprocess": "adaptive",
            "calamari_crop_padding_px": 7,
            "calamari_split_large_batches": True,
        },
    )

    assert config["calamari_model"] == "gt4histocr"
    assert config["calamari_sequential_mode"] is True
    assert config["calamari_binarize_lines"] is True
    assert config["calamari_preprocess"] == "adaptive"
    assert config["calamari_crop_padding_px"] == 7
    assert config["calamari_split_large_batches"] is True
    assert config["ocr_line_source"] == "tesseract"
    assert config["tesseract_line_preprocess"] == "adaptive"


def test_pipeline_ocr_backend_config_paddle_defaults():
    config = pipeline_ocr_backend_config("paddle_ocr_v5", {})

    assert config["paddle_ocr_lang"] == "ch"
    assert config["paddle_ocr_version"] == "PP-OCRv5"
    assert config["paddle_ocr_enable_mkldnn"] is False
    assert config["paddle_ocr_use_doc_orientation_classify"] is False
    assert config["paddle_ocr_use_doc_unwarping"] is False
    assert config["paddle_ocr_use_textline_orientation"] is False


def test_pipeline_ocr_backend_config_paddleocr_vl_ocr_preserves_shared_fields():
    config = pipeline_ocr_backend_config(
        "paddleocr_vl_ocr",
        {
            "paddleocr_vl_endpoint": "http://localhost:1234/v1/chat/completions",
            "paddleocr_vl_model": "paddleocr-vl-1.6",
            "paddleocr_vl_api_key": "key",
            "paddleocr_vl_api_style": "openai",
            "paddleocr_vl_block_concurrency": 2,
            "paddleocr_vl_crop_padding_px": 6,
        },
    )

    assert config["ocr_endpoint"] == "http://localhost:1234/v1/chat/completions"
    assert config["ocr_model"] == "paddleocr-vl-1.6"
    assert config["ocr_api_key"] == "key"
    assert config["paddleocr_vl_api_style"] == "openai"
    assert config["paddleocr_vl_block_concurrency"] == 2
    assert config["paddleocr_vl_crop_padding_px"] == 6


def test_pipeline_ocr_backend_config_tesseract_defaults_and_overrides():
    config = pipeline_ocr_backend_config(
        "tesseract",
        {
            "tesseract_lang": "chi_sim+eng",
            "tesseract_cmd": r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            "ocr_crop_preprocess": "none",
        },
    )

    assert config["tesseract_lang"] == "chi_sim+eng"
    assert config["tesseract_cmd"].endswith("tesseract.exe")
    assert config["tesseract_oem"] == 1
    assert config["tesseract_psm"] == 7
    assert config["ocr_crop_preprocess"] == "none"
    assert config["ocr_crop_padding_px"] == 8
    assert config["ocr_crop_padding_frac"] == 0.12
    assert config["ocr_crop_upscale_min_height"] == 32
    assert "ocr_line_source" not in config
    assert config["tesseract_line_psm"] == 1


def test_pipeline_backend_config_unknown_backends_are_empty():
    assert pipeline_layout_backend_config("surya", {}) == {}
    assert pipeline_ocr_backend_config("surya", {}) == {}


def test_pipeline_llm_config_disabled_preserves_non_llm_defaults():
    config = pipeline_llm_config(False, {})

    assert config == {
        "llm_printed_page_correction_enabled": False,
        "markdown_formatting_enabled": True,
        "disable_image_extraction": False,
    }


def test_pipeline_llm_config_enabled_preserves_provider_specific_fields():
    config = pipeline_llm_config(
        True,
        {
            "llm_provider": "azure",
            "llm_base_url": "https://example.openai.azure.com",
            "llm_model": "deployment",
            "llm_api_key": "key",
            "llm_api_version": "2024-02-15-preview",
            "llm_max_concurrency": 2,
            "llm_timeout": 180,
            "llm_thinking_mode": "off",
            "llm_table_enabled": True,
            "llm_equation_enabled": False,
            "llm_image_description_enabled": True,
            "llm_image_description_language": "zh",
            "llm_handwriting_enabled": True,
            "llm_page_correction_enabled": True,
            "llm_section_header_enabled": True,
            "llm_form_enabled": False,
            "llm_complex_region_enabled": True,
            "llm_noise_removal_enabled": True,
            "llm_page_correction_prompt": "prompt",
            "llm_printed_page_correction_enabled": True,
            "llm_heuristic_layout_enabled": False,
        },
    )

    assert config["llm_provider"] == "azure"
    assert config["llm_base_url"] == "https://example.openai.azure.com"
    assert config["llm_api_version"] == "2024-02-15-preview"
    assert config["disable_image_extraction"] is True
    assert config["markdown_formatting_enabled"] is False


def test_pipeline_llm_config_omits_base_url_for_claude_protocol():
    config = pipeline_llm_config(True, {"llm_provider": "claude", "llm_base_url": "ignored"})

    assert config["llm_base_url"] is None
    assert config["llm_api_version"] is None


def test_pipeline_markdown_processor_config_derives_superscript_policy():
    config = pipeline_markdown_processor_config(
        {
            "markdown_noise_removal_enabled": False,
            "markdown_noise_cleaning_level": "aggressive",
            "markdown_noise_custom_symbols": "※",
            "markdown_noise_line_start_only": False,
            "blockquote_enabled": False,
            "line_merge_enabled": False,
            "code_enabled": False,
            "section_header_enabled": False,
            "equation_enabled": False,
            "list_enabled": False,
            "footnote_enabled": True,
            "reference_enabled": False,
            "table_enabled": False,
        }
    )

    assert config["markdown_noise_cleaning_level"] == "aggressive"
    assert config["footnote_enabled"] is True
    assert config["superscript_policy"] == "preserve_all"
    assert config["table_enabled"] is False


def test_pipeline_markdown_processor_config_suppresses_footnote_like_superscripts_when_disabled():
    config = pipeline_markdown_processor_config({"footnote_enabled": False})

    assert config["footnote_enabled"] is False
    assert config["superscript_policy"] == "suppress_footnote_like"


def test_pipeline_memory_config_only_for_surya_native_pipeline_without_heavy_blocks():
    config = pipeline_memory_config(
        "pipeline",
        "surya",
        "none",
        {"table_enabled": False, "equation_enabled": False},
    )

    assert config == {
        "build_highres_images": False,
        "image_extraction_mode": "lowres",
    }


def test_pipeline_memory_config_skips_non_surya_or_heavy_block_modes():
    assert pipeline_memory_config(
        "pipeline",
        "vlm_layout",
        "none",
        {"table_enabled": False, "equation_enabled": False},
    ) == {}
    assert pipeline_memory_config(
        "pipeline",
        "surya",
        "none",
        {"table_enabled": True, "equation_enabled": False},
    ) == {}


def test_pipeline_scholarly_config_disabled_minimal_flags():
    config = pipeline_scholarly_config(
        {
            "custom_id_source": "none",
            "custom_id_data": None,
            "printed_page_enabled": False,
            "emit_page_header_comment": False,
            "emit_page_footer_comment": False,
            "keep_pageheader_in_output": False,
            "keep_pagefooter_in_output": False,
            "enable_marginal_detection": False,
            "enable_inline_detection": False,
        }
    )

    assert config["custom_id_source"] == "none"
    assert config["page_numbering_enabled"] is False
    assert config["enable_marginal_detection"] is False
    assert config["enable_inline_detection"] is False
    assert "printed_page_zones" not in config


def test_pipeline_scholarly_config_printed_page_and_header_footer_zones():
    config = pipeline_scholarly_config(
        {
            "custom_id_source": "list",
            "custom_id_data": "i\nii",
            "printed_page_enabled": True,
            "printed_page_zones": ["footer", "header"],
            "printed_page_header_end": 0.15,
            "printed_page_footer_start": 0.83,
            "printed_page_format": "roman",
            "printed_page_custom_pattern": "",
            "emit_page_header_comment": True,
            "emit_page_footer_comment": False,
            "keep_pageheader_in_output": True,
            "keep_pagefooter_in_output": False,
        }
    )

    assert config["custom_id_source"] == "list"
    assert config["custom_id_data"] == "i\nii"
    assert config["printed_page_zones"] == ["footer", "header"]
    assert config["printed_page_header_y_frac"] == 0.15
    assert config["printed_page_footer_y_frac"] == 0.83
    assert config["use_printed_page_number"] is True
    assert config["page_numbering_enabled"] is True
    assert config["page_number_format"] == "roman"
    assert config["page_number_custom_pattern"] is None
    assert config["emit_page_header_comment"] is True
    assert config["keep_pageheader_in_output"] is True


def test_pipeline_scholarly_config_header_comment_writes_zones_without_printed_page():
    config = pipeline_scholarly_config(
        {
            "printed_page_enabled": False,
            "emit_page_header_comment": True,
            "emit_page_footer_comment": False,
            "keep_pageheader_in_output": False,
            "keep_pagefooter_in_output": False,
            "printed_page_zones": ["header"],
            "printed_page_header_end": 0.2,
            "printed_page_footer_start": 0.8,
        }
    )

    assert config["page_numbering_enabled"] is False
    assert config["printed_page_zones"] == ["header"]
    assert config["printed_page_header_y_frac"] == 0.2


def test_pipeline_scholarly_config_marginal_and_inline_detection():
    config = pipeline_scholarly_config(
        {
            "enable_marginal_detection": True,
            "left_margin_threshold": 0.12,
            "right_margin_threshold": 0.88,
            "top_margin_threshold": 0.1,
            "bottom_margin_threshold": 0.9,
            "vertical_center_tolerance": 0.05,
            "enable_inline_detection": True,
            "font_size_ratio_threshold": 0.75,
            "max_inline_annotation_length": 80,
        }
    )

    assert config["enable_marginal_detection"] is True
    assert config["left_margin_threshold"] == 0.12
    assert config["vertical_center_tolerance"] == 0.05
    assert config["enable_inline_detection"] is True
    assert config["font_size_ratio_threshold"] == 0.75
    assert config["max_inline_annotation_length"] == 80
