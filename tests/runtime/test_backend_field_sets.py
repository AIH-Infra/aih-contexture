from aih_contexture.runtime.backend_field_sets import (
    external_layout_sidecar_fields,
    mineru_direct_layout_fields,
    mineru_layout_fields,
    paddle_layout_default_model,
    paddle_layout_fields,
    paddle_ocr_fields,
)


def test_paddle_layout_default_model_tracks_backend_name():
    assert paddle_layout_default_model("paddle_pp_doclayout_v3") == "PP-DocLayoutV3"
    assert paddle_layout_default_model("paddle_pp_doclayout_plus_l") == "PP-DocLayout_plus-L"


def test_external_layout_sidecar_fields_preserve_defaults_and_bool_flag():
    fields = external_layout_sidecar_fields({"external_layout_json": "layout.json", "external_layout_allow_missing_pages": 1})

    assert fields == {
        "external_layout_json": "layout.json",
        "external_layout_block_source": "auto",
        "external_layout_backend_name": "external_layout_sidecar",
        "external_layout_model": None,
        "external_layout_allow_missing_pages": True,
    }


def test_mineru_layout_fields_can_include_external_mapping():
    fields = mineru_layout_fields({"mineru_method": "ocr", "mineru_timeout": 120}, include_external_mapping=True)

    assert fields["mineru_command"] == "mineru"
    assert fields["mineru_method"] == "ocr"
    assert fields["mineru_timeout"] == 120
    assert fields["external_layout_backend_name"] == "mineru_pp_doclayout_v2"
    assert fields["external_layout_model"] == "PP-DocLayoutV2"
    assert fields["external_layout_block_source"] == "para_blocks"


def test_mineru_direct_layout_fields_can_include_external_mapping():
    fields = mineru_direct_layout_fields(
        {
            "mineru_layout_python": r"D:\MinerU\.venv\Scripts\python.exe",
            "mineru_layout_device": "cuda:0",
            "mineru_layout_batch_size": 4,
        },
        include_external_mapping=True,
    )

    assert fields["mineru_layout_python"].endswith(r"\python.exe")
    assert fields["mineru_layout_device"] == "cuda:0"
    assert fields["mineru_layout_batch_size"] == 4
    assert fields["external_layout_backend_name"] == "mineru_pp_doclayout_v2_direct"
    assert fields["external_layout_model"] == "PP-DocLayoutV2"
    assert fields["external_layout_block_source"] == "boxes"


def test_paddle_layout_fields_can_include_external_mapping():
    fields = paddle_layout_fields(
        "paddle_pp_doclayout_v3",
        {
            "paddle_layout_model_name": "custom-v3",
            "paddle_layout_enable_mkldnn": False,
            "paddle_layout_threshold": 0.4,
            "paddle_layout_batch_size": 32,
        },
        include_external_mapping=True,
    )

    assert fields["paddle_layout_model_name"] == "custom-v3"
    assert fields["paddle_layout_threshold"] == 0.4
    assert fields["paddle_layout_batch_size"] == 32
    assert fields["external_layout_backend_name"] == "paddle_pp_doclayout_v3"
    assert fields["external_layout_model"] == "custom-v3"
    assert fields["external_layout_block_source"] == "boxes"


def test_paddle_ocr_fields_preserve_defaults_and_bool_flags():
    fields = paddle_ocr_fields(
        {
            "paddle_ocr_lang": "en",
            "paddle_ocr_enable_mkldnn": 1,
            "paddle_ocr_use_doc_orientation_classify": 0,
            "paddle_ocr_use_doc_unwarping": 1,
            "paddle_ocr_use_textline_orientation": 0,
        }
    )

    assert fields["paddle_ocr_lang"] == "en"
    assert fields["paddle_ocr_version"] == "PP-OCRv5"
    assert fields["paddle_ocr_enable_mkldnn"] is True
    assert fields["paddle_ocr_use_doc_orientation_classify"] is False
    assert fields["paddle_ocr_use_doc_unwarping"] is True
    assert fields["paddle_ocr_use_textline_orientation"] is False
