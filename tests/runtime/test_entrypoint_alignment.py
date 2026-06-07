from aih_contexture.backends.layout import default_layout_registry
from aih_contexture.backends.ocr import default_ocr_registry
from aih_contexture.config.parser import ConfigParser
from aih_contexture.runtime.config_builder import config_from_ui_params
from aih_contexture.scripts.server import CommonParams, RuntimeConvertParams


def test_cli_pipeline_backend_options_align_with_registry_names():
    config = ConfigParser(
        {
            "output_format": "markdown",
            "layout_backend": "vlm_layout",
            "ocr_backend": "vlm_ocr",
            "emit_middle_json": True,
            "emit_middle_report": True,
            "emit_middle_debug": True,
            "emit_middle_scholarly": True,
            "emit_middle_scholarly_report": True,
            "emit_layout_overlay": True,
            "emit_span_overlay": True,
            "disable_ocr": False,
        }
    ).generate_config_dict()

    assert config["layout_backend"] in default_layout_registry.names()
    assert config["ocr_backend"] in default_ocr_registry.names()
    assert config["emit_middle_json"] is True
    assert config["emit_middle_report"] is True
    assert config["emit_middle_debug"] is True
    assert config["emit_middle_scholarly"] is True
    assert config["emit_middle_scholarly_report"] is True
    assert config["emit_layout_overlay"] is True
    assert config["emit_span_overlay"] is True


def test_cli_external_layout_sidecar_options_are_preserved():
    config = ConfigParser(
        {
            "output_format": "markdown",
            "layout_backend": "external_layout_sidecar",
            "external_layout_json": "layout.json",
            "external_layout_block_source": "para_blocks",
            "external_layout_backend_name": "mineru_pp_doclayout_v2",
            "external_layout_model": "PP-DocLayoutV2",
            "external_layout_allow_missing_pages": True,
            "ocr_backend": "none",
        }
    ).generate_config_dict()

    assert config["layout_backend"] == "external_layout_sidecar"
    assert config["external_layout_json"] == "layout.json"
    assert config["external_layout_block_source"] == "para_blocks"
    assert config["external_layout_backend_name"] == "mineru_pp_doclayout_v2"
    assert config["external_layout_model"] == "PP-DocLayoutV2"
    assert config["external_layout_allow_missing_pages"] is True


def test_cli_mineru_layout_options_are_preserved():
    config = ConfigParser(
        {
            "output_format": "markdown",
            "layout_backend": "mineru_pp_doclayout_v2",
            "mineru_command": "mineru",
            "mineru_output_dir": "mineru-output",
            "mineru_backend": "pipeline",
            "mineru_method": "ocr",
            "mineru_lang": "latin",
            "mineru_timeout": 120,
            "ocr_backend": "none",
        }
    ).generate_config_dict()

    assert config["layout_backend"] == "mineru_pp_doclayout_v2"
    assert config["mineru_output_dir"] == "mineru-output"
    assert config["mineru_method"] == "ocr"
    assert config["mineru_lang"] == "latin"
    assert config["mineru_timeout"] == 120


def test_cli_paddle_layout_options_are_preserved():
    config = ConfigParser(
        {
            "output_format": "markdown",
            "layout_backend": "paddle_pp_doclayout_plus_l",
            "paddle_layout_model_name": "PP-DocLayout_plus-L",
            "paddle_layout_model_dir": "models/layout",
            "paddle_layout_device": "cpu",
            "paddle_layout_engine": "paddle_static",
            "paddle_layout_enable_mkldnn": False,
            "paddle_layout_cpu_threads": 4,
            "paddle_layout_threshold": 0.5,
            "paddle_layout_img_size": 1024,
            "ocr_backend": "none",
        }
    ).generate_config_dict()

    assert config["layout_backend"] == "paddle_pp_doclayout_plus_l"
    assert config["paddle_layout_model_name"] == "PP-DocLayout_plus-L"
    assert config["paddle_layout_model_dir"] == "models/layout"
    assert config["paddle_layout_device"] == "cpu"
    assert config["paddle_layout_engine"] == "paddle_static"
    assert config["paddle_layout_enable_mkldnn"] is False
    assert config["paddle_layout_cpu_threads"] == 4
    assert config["paddle_layout_threshold"] == 0.5
    assert config["paddle_layout_img_size"] == 1024


def test_cli_paddle_doclayout_v3_options_are_preserved():
    config = ConfigParser(
        {
            "output_format": "markdown",
            "layout_backend": "paddle_pp_doclayout_v3",
            "paddle_layout_model_name": "PP-DocLayoutV3",
            "ocr_backend": "none",
        }
    ).generate_config_dict()

    assert config["layout_backend"] == "paddle_pp_doclayout_v3"
    assert config["paddle_layout_model_name"] == "PP-DocLayoutV3"


def test_cli_paddle_doclayout_v3_does_not_force_plus_l_default():
    config = ConfigParser(
        {
            "output_format": "markdown",
            "layout_backend": "paddle_pp_doclayout_v3",
            "paddle_layout_model_name": None,
            "ocr_backend": "none",
        }
    ).generate_config_dict()

    assert config["layout_backend"] == "paddle_pp_doclayout_v3"
    assert "paddle_layout_model_name" not in config


def test_cli_ocr_backend_none_maps_to_disable_ocr():
    config = ConfigParser(
        {
            "output_format": "markdown",
            "layout_backend": "surya",
            "ocr_backend": "none",
            "disable_ocr": False,
        }
    ).generate_config_dict()

    assert config["ocr_backend"] == "surya"
    assert config["disable_ocr"] is True


def test_api_pipeline_params_expose_backend_and_middle_options():
    params = CommonParams(
        filepath="sample.pdf",
        layout_backend="external_layout_sidecar",
        external_layout_json="layout.json",
        external_layout_block_source="para_blocks",
        external_layout_backend_name="mineru_pp_doclayout_v2",
        paddle_layout_enable_mkldnn=False,
        ocr_backend="none",
        emit_middle_json=True,
        emit_middle_report=True,
        emit_middle_debug=True,
        emit_middle_scholarly=True,
        emit_middle_scholarly_report=True,
        emit_layout_overlay=True,
        emit_span_overlay=True,
    )
    payload = params.model_dump()

    assert payload["layout_backend"] == "external_layout_sidecar"
    assert payload["external_layout_json"] == "layout.json"
    assert payload["external_layout_block_source"] == "para_blocks"
    assert payload["external_layout_backend_name"] == "mineru_pp_doclayout_v2"
    assert payload["paddle_layout_enable_mkldnn"] is False
    assert payload["ocr_backend"] == "none"
    assert payload["emit_middle_json"] is True
    assert payload["emit_middle_report"] is True
    assert payload["emit_middle_debug"] is True
    assert payload["emit_middle_scholarly"] is True
    assert payload["emit_middle_scholarly_report"] is True
    assert payload["emit_layout_overlay"] is True
    assert payload["emit_span_overlay"] is True


def test_ui_pipeline_backend_options_align_with_registry_names():
    config = config_from_ui_params(
        {
            "conversion_mode": "pipeline",
            "layout_backend": "vlm_layout",
            "ocr_backend": "vlm_ocr",
            "emit_middle_json": True,
            "emit_layout_overlay": True,
            "emit_span_overlay": True,
            "vlm_mode": "tile",
            "vlm_layout_max_concurrent": 5,
            "openai_max_concurrent": 7,
        }
    )

    assert config["layout_backend"] in default_layout_registry.names()
    assert config["ocr_backend"] in default_ocr_registry.names()
    assert config["emit_middle_json"] is True
    assert config["emit_layout_overlay"] is True
    assert config["emit_span_overlay"] is True
    assert config["vlm_layout_max_concurrent"] == 5
    assert config["vlm_layout_batch_size"] == 5
    assert config["openai_max_concurrent"] == 7


def test_ui_vlm_generalized_middle_options_are_preserved():
    config = config_from_ui_params(
        {
            "conversion_mode": "vlm_generalized",
            "emit_middle_json": True,
            "emit_middle_report": True,
            "emit_middle_debug": True,
            "emit_middle_scholarly": True,
            "emit_middle_scholarly_report": True,
            "emit_layout_overlay": True,
            "emit_span_overlay": True,
        }
    )

    assert config["emit_middle_json"] is True
    assert config["emit_middle_report"] is True
    assert config["emit_middle_debug"] is True
    assert config["emit_middle_scholarly"] is True
    assert config["emit_middle_scholarly_report"] is True
    assert config["emit_layout_overlay"] is True
    assert config["emit_span_overlay"] is True


def test_ui_vlm_specialized_middle_options_are_preserved():
    config = config_from_ui_params(
        {
            "conversion_mode": "vlm_specialized",
            "ocr_backend": "chandra",
            "vlm_specialized_emit_middle_json": True,
            "vlm_specialized_emit_middle_report": True,
            "vlm_specialized_emit_middle_debug": True,
            "vlm_specialized_emit_middle_scholarly": True,
            "vlm_specialized_emit_middle_scholarly_report": True,
            "vlm_specialized_emit_layout_overlay": True,
            "vlm_specialized_emit_span_overlay": True,
        }
    )

    assert config["emit_middle_json"] is True
    assert config["emit_middle_report"] is True
    assert config["emit_middle_debug"] is True
    assert config["emit_middle_scholarly"] is True
    assert config["emit_middle_scholarly_report"] is True
    assert config["emit_layout_overlay"] is True
    assert config["emit_span_overlay"] is True


def test_api_runtime_params_support_vlm_modes_and_middle_options():
    params = RuntimeConvertParams(
        filepath="sample.pdf",
        mode="vlm_specialized",
        output_format="markdown",
        config={
            "emit_middle_json": True,
            "ocr_backend": "chandra",
        },
    )
    payload = params.model_dump()

    assert payload["mode"] == "vlm_specialized"
    assert payload["config"]["emit_middle_json"] is True
    assert payload["config"]["ocr_backend"] == "chandra"


def test_ui_external_layout_sidecar_options_are_preserved():
    config = config_from_ui_params(
        {
            "conversion_mode": "pipeline",
            "layout_backend": "external_layout_sidecar",
            "external_layout_json": "layout.json",
            "external_layout_block_source": "layout_bboxes",
            "external_layout_backend_name": "paddle_pp_doclayout_v3",
            "external_layout_model": "PP-DocLayoutV3",
            "external_layout_allow_missing_pages": True,
            "ocr_backend": "none",
        }
    )

    assert config["layout_backend"] == "external_layout_sidecar"
    assert config["external_layout_json"] == "layout.json"
    assert config["external_layout_block_source"] == "layout_bboxes"
    assert config["external_layout_backend_name"] == "paddle_pp_doclayout_v3"
    assert config["external_layout_model"] == "PP-DocLayoutV3"
    assert config["external_layout_allow_missing_pages"] is True


def test_ui_mineru_layout_options_are_preserved():
    config = config_from_ui_params(
        {
            "conversion_mode": "pipeline",
            "layout_backend": "mineru_pp_doclayout_v2",
            "mineru_command": "mineru.exe",
            "mineru_output_dir": "mineru-output",
            "mineru_backend": "pipeline",
            "mineru_method": "ocr",
            "mineru_lang": "latin",
            "mineru_timeout": 120,
            "ocr_backend": "none",
        }
    )

    assert config["layout_backend"] == "mineru_pp_doclayout_v2"
    assert config["mineru_command"] == "mineru.exe"
    assert config["mineru_output_dir"] == "mineru-output"
    assert config["mineru_method"] == "ocr"
    assert config["mineru_lang"] == "latin"
    assert config["mineru_timeout"] == 120
    assert config["external_layout_backend_name"] == "mineru_pp_doclayout_v2"


def test_ui_paddle_layout_options_are_preserved():
    config = config_from_ui_params(
        {
            "conversion_mode": "pipeline",
            "layout_backend": "paddle_pp_doclayout_plus_l",
            "paddle_layout_model_name": "PP-DocLayout_plus-L",
            "paddle_layout_model_dir": "models/layout",
            "paddle_layout_device": "cpu",
            "paddle_layout_engine": "paddle_static",
            "paddle_layout_enable_mkldnn": False,
            "paddle_layout_cpu_threads": 4,
            "paddle_layout_threshold": 0.5,
            "paddle_layout_img_size": 1024,
            "ocr_backend": "none",
        }
    )

    assert config["layout_backend"] == "paddle_pp_doclayout_plus_l"
    assert config["paddle_layout_model_name"] == "PP-DocLayout_plus-L"
    assert config["paddle_layout_model_dir"] == "models/layout"
    assert config["paddle_layout_device"] == "cpu"
    assert config["paddle_layout_engine"] == "paddle_static"
    assert config["paddle_layout_enable_mkldnn"] is False
    assert config["paddle_layout_cpu_threads"] == 4
    assert config["paddle_layout_threshold"] == 0.5
    assert config["paddle_layout_img_size"] == 1024
    assert config["external_layout_backend_name"] == "paddle_pp_doclayout_plus_l"
    assert config["external_layout_block_source"] == "boxes"


def test_ui_paddle_doclayout_v3_options_are_preserved():
    config = config_from_ui_params(
        {
            "conversion_mode": "pipeline",
            "layout_backend": "paddle_pp_doclayout_v3",
            "paddle_layout_model_name": "PP-DocLayoutV3",
            "ocr_backend": "none",
        }
    )

    assert config["layout_backend"] == "paddle_pp_doclayout_v3"
    assert config["paddle_layout_model_name"] == "PP-DocLayoutV3"
    assert config["external_layout_backend_name"] == "paddle_pp_doclayout_v3"
    assert config["external_layout_model"] == "PP-DocLayoutV3"
    assert config["external_layout_block_source"] == "boxes"
