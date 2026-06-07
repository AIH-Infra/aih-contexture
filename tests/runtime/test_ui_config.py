from aih_contexture.runtime.ui_config import (
    layout_backend_cli_config,
    llm_cli_config,
    ocr_backend_cli_config,
    page_numbering_cli_config,
    pipeline_base_cli_config,
    scholarly_detection_cli_config,
    vlm_specialized_cli_config,
)


def test_vlm_specialized_cli_config_preserves_official_protocol_fields():
    config = vlm_specialized_cli_config(
        {
            "ocr_backend": "churro",
            "ocr_api_style": "openai-compatible",
            "ocr_endpoint": "http://localhost:1234/v1/chat/completions",
            "ocr_model": "churro-model",
            "ocr_output_format": "xml",
            "ocr_temperature": 0.7,
            "enable_marginal_detection": True,
            "vlm_specialized_emit_middle_json": True,
            "vlm_specialized_emit_layout_overlay": True,
            "vlm_specialized_emit_span_overlay": True,
            "page_range": "0-2",
        }
    )

    assert config["converter_cls"] == "aih_contexture.converters.ocr_direct_async.OcrDirectAsyncConverter"
    assert config["ocr_backend"] == "churro"
    assert config["ocr_output_format"] == "xml"
    assert config["ocr_temperature"] == 0.7
    assert config["churro_marginal_note_enabled"] is True
    assert config["emit_middle_json"] is True
    assert config["emit_layout_overlay"] is True
    assert config["emit_span_overlay"] is True
    assert config["page_range"] == [0, 1, 2]


def test_vlm_specialized_cli_config_preserves_paddleocr_and_mineru_fields():
    paddle = vlm_specialized_cli_config(
        {
            "ocr_backend": "paddleocr_vl",
            "ocr_api_style": "openai",
            "ocr_endpoint": "https://llmapi.paratera.com",
            "ocr_model": "PaddleOCR-VL-1.5",
            "paddleocr_vl_prompt_label": "ocr",
        }
    )
    mineru = vlm_specialized_cli_config(
        {
            "ocr_backend": "mineru_vl",
            "ocr_model": "MinerU2.5-Pro-2604-1.2B",
            "ocr_filter_page_header": True,
            "ocr_filter_page_footer": True,
            "ocr_filter_margin_notes": True,
        }
    )

    assert paddle["ocr_output_format"] == "json"
    assert paddle["paddleocr_vl_prompt_label"] == "ocr"
    assert paddle["ocr_endpoint"] == "https://llmapi.paratera.com"
    assert paddle["paddleocr_vl_endpoint"] == "https://llmapi.paratera.com"
    assert paddle["paddleocr_vl_request_concurrency"] == 5
    assert mineru["ocr_output_format"] == "json"
    assert "mineru_vl_mode" not in mineru
    assert mineru["mineru_vl_block_concurrency"] == 4
    assert mineru["mineru_vl_request_concurrency"] == 1
    assert mineru["mineru_vl_layout_image_size"] == (1036, 1036)
    assert mineru["ocr_filter_page_header"] is True
    assert mineru["ocr_filter_page_footer"] is True
    assert mineru["ocr_filter_margin_notes"] is True
    assert mineru["include_page_header_comments"] is False
    assert mineru["include_page_footer_comments"] is False
    assert mineru["include_margin_comments"] is False


def test_vlm_specialized_cli_config_uses_model_profile_defaults():
    chandra = vlm_specialized_cli_config({"ocr_backend": "chandra"})
    churro = vlm_specialized_cli_config({"ocr_backend": "churro"})
    paddle = vlm_specialized_cli_config({"ocr_backend": "paddleocr_vl"})
    mineru = vlm_specialized_cli_config({"ocr_backend": "mineru_vl"})

    assert chandra["chandra_version"] == "2.0"
    assert chandra["chandra_quant"] == "q8_0"
    assert chandra["ocr_model"] == "chandra-ocr-2@q8_0"
    assert churro["churro_quant"] == "q8_0"
    assert churro["ocr_model"] == "churro-3b@q8_0"
    assert churro["ocr_api_style"] == "openai"
    assert churro["ocr_endpoint"] == "http://localhost:1234/v1/chat/completions"
    assert churro["ocr_resize_max"] == 2500
    assert churro["ocr_image_format"] == "PNG"
    assert churro["ocr_image_quality"] == 95
    assert churro["ocr_max_tokens"] == 20000
    assert paddle["paddleocr_vl_version"] == "1.5"
    assert paddle["ocr_model"] == "paddleocr-vl-1.5"
    assert mineru["mineru_vl_version"] == "2.5pro-2605"
    assert mineru["mineru_vl_quant"] == "q8_0"
    assert mineru["ocr_model"] == "mineru2.5-pro-2605-1.2b@q8_0"


def test_vlm_specialized_cli_config_preserves_paddleocr_vl_request_gate():
    config = vlm_specialized_cli_config(
        {
            "ocr_backend": "paddleocr_vl",
            "ocr_concurrency": 2,
            "paddleocr_vl_request_concurrency": 2,
            "paddleocr_vl_block_concurrency": 4,
            "paddleocr_vl_crop_padding_frac": 0.03,
        }
    )

    assert config["ocr_concurrency"] == 2
    assert config["paddleocr_vl_request_concurrency"] == 2
    assert config["paddleocr_vl_block_concurrency"] == 4
    assert config["paddleocr_vl_crop_padding_frac"] == 0.03


def test_pipeline_base_cli_config_maps_disable_ocr_without_forcing_ocr():
    config = pipeline_base_cli_config(
        {"ocr_batch_size": 9, "force_ocr": True, "page_range": "1-3", "equation_enabled": False},
        ocr_backend="none",
        layout_backend="surya",
        disable_ocr=True,
        disable_layout=False,
    )

    assert config["ocr_backend"] == "surya"
    assert config["disable_ocr"] is True
    assert config["force_ocr"] is False
    assert config["ocr_batch_size"] == 9
    assert config["page_range"] == [1, 2, 3]
    assert config["equation_enabled"] is False


def test_pipeline_base_cli_config_forces_all_selected_ocr_backends():
    for backend in ["surya", "calamari", "paddle_ocr_v5", "paddleocr_vl_ocr", "tesseract", "vlm_ocr"]:
        config = pipeline_base_cli_config(
            {"force_ocr": False},
            ocr_backend=backend,
            layout_backend="surya",
            disable_ocr=False,
            disable_layout=False,
        )

        assert config["ocr_backend"] == backend
        assert config["disable_ocr"] is False
        assert config["force_ocr"] is True


def test_page_numbering_cli_config_emits_margin_capture_when_header_footer_requested():
    config = page_numbering_cli_config(
        {
            "page_numbering_enabled": False,
            "emit_page_header_comment": True,
            "printed_page_zones": ["header"],
            "printed_page_header_y_frac": 0.2,
            "printed_page_footer_y_frac": 0.8,
        }
    )

    assert config["page_numbering_enabled"] is False
    assert config["printed_page_zones"] == ["header"]
    assert config["printed_page_header_y_frac"] == 0.2
    assert config["printed_page_footer_y_frac"] == 0.8


def test_layout_backend_cli_config_vlm_defaults_to_modern_template():
    config = layout_backend_cli_config("vlm_layout", {"vlm_layout_max_concurrent": 3})

    assert config["vlm_layout_timeout"] == 120
    assert config["vlm_layout_prompt_template"] == "modern"
    assert config["vlm_layout_max_concurrent"] == 3
    assert config["vlm_layout_batch_size"] == 3


def test_build_config_dict_treats_none_numeric_values_as_defaults():
    from aih_contexture.runtime.ui_config import build_config_dict

    config = build_config_dict(
        {
            "conversion_mode": "pipeline",
            "layout_backend": "vlm_layout",
            "ocr_backend": "vlm_ocr",
            "ocr_batch_size": None,
            "vlm_layout_timeout": None,
            "openai_max_concurrent": None,
            "vlm_full_page_max_tokens": None,
            "vlm_merge_y_threshold": None,
            "vlm_merge_max_blocks": None,
            "use_llm": False,
        }
    )

    assert config["ocr_batch_size"] == 32
    assert config["vlm_layout_timeout"] == 120
    assert config["openai_max_concurrent"] == 3
    assert config["vlm_full_page_max_tokens"] == 2048
    assert config["vlm_merge_y_threshold"] == 80
    assert config["vlm_merge_max_blocks"] == 15


def test_build_config_dict_handles_vlm_generalized_mode_via_shared_builder():
    from aih_contexture.runtime.ui_config import build_config_dict

    config = build_config_dict(
        {
            "conversion_mode": "vlm_generalized",
            "emit_middle_json": True,
            "emit_middle_report": True,
            "emit_middle_debug": True,
            "emit_middle_scholarly": True,
            "emit_middle_scholarly_report": True,
            "emit_layout_overlay": True,
            "emit_span_overlay": True,
            "vlm_direct_base_url": "http://localhost:1234/v1",
            "vlm_direct_model": "qwen-vl",
            "vlm_direct_api_key": "key",
        }
    )

    assert config["conversion_mode"] == "vlm_generalized"
    assert config["vlm_direct_output_mode"] == "json"
    assert config["final_output_formats"] == ["markdown"]
    assert config["emit_middle_json"] is True
    assert config["emit_middle_report"] is True
    assert config["emit_layout_overlay"] is True
    assert config["vlm_direct_base_url"] == "http://localhost:1234/v1"


def test_build_config_dict_handles_markdown_postprocess_mode_via_shared_builder():
    from aih_contexture.runtime.ui_config import build_config_dict

    config = build_config_dict(
        {
            "conversion_mode": "markdown_postprocess",
            "markdown_postprocess_input_kind": "middle_json",
            "middle_rerender_include_provenance": True,
            "middle_rerender_include_printed_page_comments": False,
            "middle_rerender_include_page_header_comments": False,
            "middle_rerender_include_page_footer_comments": False,
            "middle_rerender_include_margin_comments": False,
            "middle_rerender_include_page_separators": False,
            "middle_rerender_apply_postprocess": True,
            "markdown_postprocess_review_only": False,
            "markdown_postprocess_enable_cleanup": False,
            "markdown_postprocess_enable_printed_page_repair": True,
            "markdown_postprocess_enable_llm": True,
            "markdown_postprocess_llm_provider": "openai",
        }
    )

    assert config["conversion_mode"] == "markdown_postprocess"
    assert config["markdown_postprocess_enabled"] is True
    assert config["markdown_postprocess_input_kind"] == "middle_json"
    assert config["middle_rerender_include_provenance"] is True
    assert config["middle_rerender_include_printed_page_comments"] is False
    assert config["middle_rerender_include_page_header_comments"] is False
    assert config["middle_rerender_include_page_footer_comments"] is False
    assert config["middle_rerender_include_margin_comments"] is False
    assert config["middle_rerender_include_page_separators"] is False
    assert config["middle_rerender_apply_postprocess"] is True
    assert config["markdown_postprocess_review_only"] is False
    assert config["markdown_postprocess_enable_cleanup"] is False
    assert config["markdown_postprocess_enable_printed_page_repair"] is True
    assert config["markdown_postprocess_enable_llm"] is True


def test_layout_backend_cli_config_paddle_v3_sets_external_mapping():
    config = layout_backend_cli_config("paddle_pp_doclayout_v3", {})

    assert config["paddle_layout_model_name"] == "PP-DocLayoutV3"
    assert config["external_layout_backend_name"] == "paddle_pp_doclayout_v3"
    assert config["external_layout_model"] == "PP-DocLayoutV3"
    assert config["external_layout_block_source"] == "boxes"


def test_layout_backend_cli_config_mineru_direct_sets_external_mapping():
    config = layout_backend_cli_config(
        "mineru_pp_doclayout_v2_direct",
        {"mineru_layout_python": "python", "mineru_layout_batch_size": 4},
    )

    assert config["mineru_layout_python"] == "python"
    assert config["mineru_layout_batch_size"] == 4
    assert config["external_layout_backend_name"] == "mineru_pp_doclayout_v2_direct"
    assert config["external_layout_model"] == "PP-DocLayoutV2"
    assert config["external_layout_block_source"] == "boxes"


def test_ocr_backend_cli_config_vlm_modes_and_paddle_defaults():
    vlm = ocr_backend_cli_config("vlm_ocr", {"vlm_mode": "merge"})
    paddle = ocr_backend_cli_config("paddle_ocr_v5", {})
    paddle_vl = ocr_backend_cli_config(
        "paddleocr_vl_ocr",
        {
            "paddleocr_vl_endpoint": "http://localhost:1234/v1/chat/completions",
            "paddleocr_vl_model": "paddleocr-vl-1.6",
            "paddleocr_vl_block_concurrency": 2,
        },
    )
    paddle_vl_defaults = ocr_backend_cli_config("paddleocr_vl_ocr", {})
    tesseract = ocr_backend_cli_config("tesseract", {"tesseract_lang": "eng+deu"})

    assert vlm["vlm_merge_enabled"] is True
    assert vlm["vlm_full_page_ocr"] is False
    assert paddle["paddle_ocr_lang"] == "ch"
    assert paddle["paddle_ocr_version"] == "PP-OCRv5"
    assert paddle["paddle_ocr_enable_mkldnn"] is False
    assert paddle_vl["ocr_endpoint"] == "http://localhost:1234/v1/chat/completions"
    assert paddle_vl["ocr_model"] == "paddleocr-vl-1.6"
    assert paddle_vl["paddleocr_vl_block_concurrency"] == 2
    assert paddle_vl["paddleocr_vl_prompt_label"] == "ocr"
    assert paddle_vl_defaults["ocr_endpoint"] == "http://127.0.0.1:1234/v1/chat/completions"
    assert paddle_vl_defaults["ocr_model"] == "paddleocr-vl-1.5"
    assert paddle_vl_defaults["paddleocr_vl_block_concurrency"] == 4
    assert tesseract["tesseract_lang"] == "eng+deu"
    assert tesseract["tesseract_oem"] == 1


def test_pipeline_base_cli_config_enables_non_llm_printed_page_correction_by_default():
    config = pipeline_base_cli_config(
        {},
        ocr_backend="surya",
        layout_backend="surya",
        disable_ocr=False,
        disable_layout=False,
    )

    assert config["printed_page_correction_enabled"] is True


def test_backend_field_sets_align_pipeline_sections_and_runtime_config_helpers():
    from aih_contexture.scripts.ui.pipeline_config_sections import (
        pipeline_layout_backend_config,
        pipeline_ocr_backend_config,
    )

    paddle_values = {"paddle_layout_model_name": "PP-DocLayoutV3", "paddle_layout_threshold": 0.5}
    pipeline_paddle = pipeline_layout_backend_config("paddle_pp_doclayout_v3", paddle_values)
    runtime_paddle = layout_backend_cli_config("paddle_pp_doclayout_v3", paddle_values)

    assert pipeline_paddle["paddle_layout_model_name"] == runtime_paddle["paddle_layout_model_name"]
    assert pipeline_paddle["paddle_layout_threshold"] == runtime_paddle["paddle_layout_threshold"]
    assert runtime_paddle["external_layout_backend_name"] == "paddle_pp_doclayout_v3"

    ocr_values = {"paddle_ocr_lang": "en", "paddle_ocr_enable_mkldnn": True}
    assert pipeline_ocr_backend_config("paddle_ocr_v5", ocr_values) == ocr_backend_cli_config("paddle_ocr_v5", ocr_values)

    paddle_vl_values = {"paddleocr_vl_model": "paddleocr-vl-1.6", "paddleocr_vl_block_concurrency": 2}
    assert pipeline_ocr_backend_config("paddleocr_vl_ocr", paddle_vl_values) == ocr_backend_cli_config("paddleocr_vl_ocr", paddle_vl_values)

    tesseract_values = {"tesseract_lang": "chi_sim+eng", "ocr_crop_preprocess": "none"}
    assert pipeline_ocr_backend_config("tesseract", tesseract_values) == ocr_backend_cli_config("tesseract", tesseract_values)


def test_llm_cli_config_maps_provider_specific_fields():
    config = llm_cli_config(
        {
            "use_llm": True,
            "llm_provider": "azure",
            "llm_base_url": "https://example.openai.azure.com",
            "llm_api_key": "key",
            "llm_model": "deployment",
            "llm_api_version": "2024-02-15-preview",
            "llm_image_description_enabled": True,
            "llm_page_correction_prompt": "prompt",
        }
    )

    assert config["use_llm"] is True
    assert config["llm_provider"] == "azure"
    assert config["llm_service"] == "aih_contexture.services.azure_openai.AzureOpenAIService"
    assert config["azure_endpoint"] == "https://example.openai.azure.com"
    assert config["azure_api_key"] == "key"
    assert config["deployment_name"] == "deployment"
    assert config["azure_api_version"] == "2024-02-15-preview"
    assert config["disable_image_extraction"] is True
    assert config["llm_page_correction_prompt"] == "prompt"


def test_llm_cli_config_maps_openai_compatible_provider():
    config = llm_cli_config(
        {
            "use_llm": True,
            "llm_provider": "openai_compatible",
            "llm_base_url": "http://localhost:1234/v1",
            "llm_api_key": "key",
            "llm_model": "local-model",
        }
    )

    assert config["llm_provider"] == "openai_compatible"
    assert config["llm_service"] == "aih_contexture.services.openai.OpenAIService"
    assert config["openai_base_url"] == "http://localhost:1234/v1"
    assert config["openai_api_key"] == "key"
    assert config["openai_model"] == "local-model"
    assert config["vlm_response_mode"] == "json"


def test_scholarly_detection_cli_config_preserves_thresholds():
    config = scholarly_detection_cli_config(
        {
            "enable_marginal_detection": True,
            "left_margin_threshold": 0.12,
            "right_margin_threshold": 0.88,
            "top_margin_threshold": 0.1,
            "bottom_margin_threshold": 0.9,
            "vertical_center_tolerance": 0.04,
            "enable_inline_detection": True,
            "font_size_ratio_threshold": 0.7,
            "max_inline_annotation_length": 80,
        }
    )

    assert config["enable_marginal_detection"] is True
    assert config["left_margin_threshold"] == 0.12
    assert config["vertical_center_tolerance"] == 0.04
    assert config["enable_inline_detection"] is True
    assert config["font_size_ratio_threshold"] == 0.7
    assert config["max_inline_annotation_length"] == 80
