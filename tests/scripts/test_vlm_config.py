from aih_contexture.scripts.ui.vlm_config import (
    build_vlm_generalized_config,
    build_vlm_specialized_config,
)


class PromptManager:
    def __init__(self, original="original"):
        self.original = original

    def get_template(self, template_id):
        return self.original

    def list_templates(self):
        return {"modern": {"name": "Modern Template"}}


def test_build_vlm_generalized_config_preserves_json_mode_prompt_and_page_range():
    config, message = build_vlm_generalized_config(
        {
            "vlm_api_provider": "openai",
            "vlm_direct_base_url": "http://localhost:1234/v1",
            "vlm_direct_model": "qwen-vl",
            "vlm_direct_api_key": "key",
            "vlm_direct_max_concurrent": 4,
            "vlm_direct_image_format": "jpeg",
            "vlm_direct_max_image_dimension": 1600,
            "vlm_direct_jpeg_quality": 85,
            "vlm_direct_timeout": 120,
            "vlm_direct_max_retries": 2,
            "vlm_auto_repair_failed_pages": True,
            "vlm_repair_max_concurrent": 2,
            "vlm_repair_rounds": 2,
            "vlm_direct_enable_page_anchors": True,
            "vlm_direct_page_anchor_position": "before",
            "vlm_direct_extract_printed_pages": True,
            "vlm_direct_printed_page_patterns": "pat",
            "vlm_direct_custom_id_source": "list",
            "vlm_direct_custom_id_data": "i\nii",
            "selected_template_id": "modern",
            "edited_prompt": "custom prompt",
            "text_direction": "horizontal",
            "primary_language": "zh",
            "handwriting_mode": "none",
            "describe_images": True,
            "anti_hallucination": True,
            "extract_bboxes": True,
            "include_confidence": True,
            "enhance_tables_equations": True,
            "has_page_numbers": True,
            "enable_marginalia": True,
            "enable_footnotes": True,
            "emit_middle_json": True,
            "emit_middle_report": True,
            "emit_middle_debug": True,
            "emit_middle_scholarly": True,
            "emit_middle_scholarly_report": True,
            "emit_layout_overlay": False,
            "emit_span_overlay": True,
            "vlm_noise_removal": True,
            "vlm_noise_patterns": "",
            "vlm_footnote_fix": True,
            "vlm_hyphenation_fix": True,
            "vlm_filter_page_header": False,
            "vlm_filter_page_footer": False,
            "vlm_filter_margin_notes": True,
            "vlm_direct_temperature": 0.2,
            "vlm_direct_top_p": 0.9,
            "vlm_direct_top_k": 20,
            "vlm_use_page_range": True,
            "vlm_start_page": 2,
            "vlm_end_page": 4,
        },
        output_formats=["markdown", "json"],
        template_manager=PromptManager(original="original"),
    )

    assert config["vlm_direct_output_mode"] == "json"
    assert config["final_output_formats"] == ["markdown", "json"]
    assert config["vlm_direct_max_tokens"] == 0
    assert config["vlm_auto_repair_failed_pages"] is True
    assert config["vlm_repair_max_concurrent"] == 2
    assert config["vlm_repair_rounds"] == 2
    assert config["vlm_direct_disable_thinking"] is True
    assert config["vlm_direct_page_anchor_wrapper"] == "{{{}}}"
    assert config["vlm_direct_prompt_template"] == "modern"
    assert config["vlm_direct_prompt"] == "custom prompt"
    assert config["vlm_direct_prompt_params"]["enable_marginalia"] is True
    assert config["vlm_direct_marginal_note_enabled"] is True
    assert config["emit_middle_report"] is True
    assert config["emit_middle_debug"] is True
    assert config["emit_middle_scholarly"] is True
    assert config["emit_middle_scholarly_report"] is True
    assert config["vlm_direct_temperature"] == 0.2
    assert config["vlm_direct_top_p"] == 0.9
    assert config["vlm_direct_top_k"] == 20
    assert config["vlm_filter_margin_notes"] is True
    assert config["include_margin_comments"] is False
    assert config["page_range"] == "1-3"
    assert message == "ℹ️ 使用编辑后的提示词（临时生效，未保存到模板）"


def test_build_vlm_generalized_config_reports_template_name_without_custom_prompt():
    config, message = build_vlm_generalized_config(
        {
            "selected_template_id": "modern",
            "edited_prompt": "original",
            "vlm_use_page_range": False,
            "vlm_direct_temperature": None,
        },
        output_formats=[],
        template_manager=PromptManager(original="original"),
    )

    assert "vlm_direct_prompt" not in config
    assert "page_range" not in config
    assert message == "ℹ️ 使用模板：Modern Template"


def test_build_vlm_specialized_config_preserves_chandra_official_protocol():
    config = build_vlm_specialized_config(
        {
            "ocr_backend": "chandra",
            "chandra_version": "1.0",
            "ocr_api_style": "lmstudio-native",
            "ocr_endpoint": "http://localhost:1234/api/v1/chat",
            "ocr_model": "chandra",
            "ocr_api_key": "",
            "ocr_concurrency": 3,
            "ocr_batch_size": 5,
            "ocr_batch_rest": 1.0,
            "ocr_max_retries": 2,
            "ocr_resize_max": 1024,
            "ocr_image_format": "JPEG",
            "ocr_image_quality": 70,
            "ocr_timeout": 120,
            "ocr_max_tokens": 4096,
            "enable_page_anchors": True,
            "page_anchor_position": "after",
            "extract_printed_pages": False,
            "vlm_printed_page_patterns": "pat",
            "custom_id_source": "none",
            "custom_id_data": None,
            "emit_middle_json": True,
            "emit_middle_report": True,
            "emit_middle_debug": True,
            "emit_middle_scholarly": True,
            "emit_middle_scholarly_report": True,
            "emit_layout_overlay": True,
            "emit_span_overlay": False,
            "ocr_filter_page_header": True,
            "ocr_filter_page_footer": True,
            "ocr_filter_margin_notes": True,
            "ocr_use_page_range": True,
            "ocr_start_page": 1,
            "ocr_end_page": 2,
        },
        output_formats=["html", "markdown"],
    )

    assert config["ocr_backend"] == "chandra"
    assert config["chandra_version"] == "1.0"
    assert config["ocr_api_key"] is None
    assert config["ocr_output_format"] == "html"
    assert config["ocr_temperature"] == 0.0
    assert config["ocr_page_anchor_wrapper"] == "{{{}}}"
    assert config["emit_middle_report"] is True
    assert config["emit_middle_debug"] is True
    assert config["emit_middle_scholarly"] is True
    assert config["emit_middle_scholarly_report"] is True
    assert config["ocr_filter_page_header"] is True
    assert config["ocr_filter_page_footer"] is True
    assert config["ocr_filter_margin_notes"] is True
    assert config["include_page_header_comments"] is False
    assert config["include_page_footer_comments"] is False
    assert config["include_margin_comments"] is False
    assert config["page_range"] == "0-1"
    assert config["final_output_formats"] == ["html", "markdown"]


def test_build_vlm_specialized_config_preserves_churro_official_protocol_and_defaults():
    config = build_vlm_specialized_config(
        {
            "ocr_backend": "churro",
            "ocr_api_key": "key",
            "enable_page_anchors": False,
        },
        output_formats=["xml"],
    )

    assert config["chandra_version"] is None
    assert config["churro_version"] == "3b"
    assert config["churro_quant"] == "q8_0"
    assert config["ocr_model"] == "churro-3b@q8_0"
    assert config["ocr_api_style"] == "openai"
    assert config["ocr_endpoint"] == "http://localhost:1234/v1/chat/completions"
    assert config["ocr_api_key"] == "key"
    assert config["ocr_output_format"] == "xml"
    assert config["ocr_temperature"] == 0.6
    assert config["ocr_resize_max"] == 2500
    assert config["ocr_image_format"] == "PNG"
    assert config["ocr_image_quality"] == 95
    assert config["ocr_max_tokens"] == 20000
    assert config["ocr_page_anchor_position"] == "before"
    assert config["ocr_extract_printed_pages"] is True
    assert config["ocr_noise_removal"] is True
    assert "page_range" not in config


def test_build_vlm_specialized_config_falls_back_to_openai_keys_when_ocr_keys_missing():
    config = build_vlm_specialized_config(
        {
            "ocr_backend": "paddleocr_vl",
            "ocr_api_style": "openai",
            "openai_base_url": "http://localhost:1234/v1",
            "openai_model": "PaddleOCR-VL-1.5",
            "openai_api_key": "secret",
        },
        output_formats=["json"],
    )

    assert config["ocr_endpoint"] == "http://localhost:1234/v1"
    assert config["ocr_model"] == "PaddleOCR-VL-1.5"
    assert config["ocr_api_key"] == "secret"


def test_build_vlm_specialized_config_sets_mineru_request_gate_without_touching_page_concurrency():
    config = build_vlm_specialized_config(
        {
            "ocr_backend": "mineru_vl",
            "ocr_api_style": "lmstudio-native",
            "ocr_concurrency": 2,
            "mineru_vl_block_concurrency": 4,
        },
        output_formats=["markdown"],
    )

    assert config["ocr_concurrency"] == 2
    assert config["mineru_vl_block_concurrency"] == 4
    assert config["mineru_vl_request_concurrency"] == 1


def test_build_vlm_specialized_config_preserves_paddleocr_vl_request_gate():
    config = build_vlm_specialized_config(
        {
            "ocr_backend": "paddleocr_vl",
            "ocr_api_style": "lmstudio-native",
            "ocr_concurrency": 2,
            "paddleocr_vl_endpoint": "http://localhost:1234/api/v1/chat",
            "paddleocr_vl_model": "paddleocr-vl-1.6",
            "paddleocr_vl_request_concurrency": 2,
            "paddleocr_vl_block_concurrency": 4,
        },
        output_formats=["markdown"],
    )

    assert config["ocr_concurrency"] == 2
    assert config["paddleocr_vl_endpoint"] == "http://localhost:1234/api/v1/chat"
    assert config["paddleocr_vl_model"] == "paddleocr-vl-1.6"
    assert config["paddleocr_vl_request_concurrency"] == 2
    assert config["paddleocr_vl_block_concurrency"] == 4


def test_build_vlm_specialized_config_allows_mineru_remote_request_gate_override():
    config = build_vlm_specialized_config(
        {
            "ocr_backend": "mineru_vl",
            "ocr_api_style": "openai",
            "mineru_vl_block_concurrency": 6,
            "mineru_vl_request_concurrency": 3,
        },
        output_formats=["markdown"],
    )

    assert config["mineru_vl_block_concurrency"] == 6
    assert config["mineru_vl_request_concurrency"] == 3


def test_build_vlm_specialized_config_normalizes_empty_numeric_and_style_values():
    config = build_vlm_specialized_config(
        {
            "ocr_backend": "chandra",
            "ocr_api_style": "none",
            "ocr_concurrency": None,
            "ocr_batch_size": None,
            "ocr_batch_rest": None,
            "ocr_resize_max": None,
            "ocr_image_format": "",
            "ocr_image_quality": None,
            "ocr_timeout": None,
            "ocr_max_tokens": None,
            "enable_page_anchors": None,
        },
        output_formats=["markdown"],
    )

    assert config["ocr_api_style"] == "lmstudio-native"
    assert config["ocr_concurrency"] == 5
    assert config["ocr_batch_size"] == 10
    assert config["ocr_batch_rest"] == 2.0
    assert config["ocr_resize_max"] == 1024
    assert config["ocr_image_format"] == "JPEG"
    assert config["ocr_image_quality"] == 60
    assert config["ocr_timeout"] == 120
    assert config["ocr_max_tokens"] == 4096
    assert config["ocr_page_anchor_enabled"] is True


def test_build_vlm_specialized_config_defaults_to_chandra_when_backend_missing():
    config = build_vlm_specialized_config(
        {},
        output_formats=["xml"],
    )

    assert config["ocr_backend"] == "chandra"
    assert config["chandra_version"] == "2.0"
    assert config["chandra_quant"] == "q8_0"
    assert config["ocr_model"] == "chandra-ocr-2@q8_0"
    assert config["ocr_output_format"] == "html"
