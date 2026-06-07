from aih_contexture.backends.pipeline import (
    create_layout_builder,
    create_ocr_builder,
    normalize_layout_backend_name,
    normalize_ocr_backend_name,
)


class DummyLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass


class DummyBuilder:
    pass


def _resolver(builder_class):
    return ("resolved", builder_class)


def test_backend_name_aliases_match_registry_names():
    assert normalize_layout_backend_name("vlm") == "vlm_layout"
    assert normalize_layout_backend_name("VLM-Layout") == "vlm_layout"
    assert normalize_layout_backend_name(None) == "surya"
    assert normalize_ocr_backend_name("vlm") == "vlm_ocr"
    assert normalize_ocr_backend_name("VLM-OCR") == "vlm_ocr"
    assert normalize_ocr_backend_name(None) == "surya"


def test_surya_layout_builder_uses_resolved_default_builder():
    builder = create_layout_builder(
        config={"layout_backend": "surya"},
        resolve_dependencies=_resolver,
        logger=DummyLogger(),
        layout_builder_class=DummyBuilder,
    )

    assert builder == ("resolved", DummyBuilder)


def test_external_layout_sidecar_builder_is_created_directly(tmp_path):
    sidecar_path = tmp_path / "layout.json"
    sidecar_path.write_text('{"pages": [], "schema_version": "contexture-middle-json/0.1"}', encoding="utf-8")

    builder = create_layout_builder(
        config={"layout_backend": "external_layout_sidecar", "external_layout_json": str(sidecar_path)},
        resolve_dependencies=_resolver,
        logger=DummyLogger(),
        layout_builder_class=DummyBuilder,
    )

    assert builder.__class__.__name__ == "ExternalLayoutSidecarBuilder"
    assert builder.external_layout_json == str(sidecar_path)


def test_mineru_layout_builder_is_created_directly():
    builder = create_layout_builder(
        config={"layout_backend": "mineru_pp_doclayout_v2", "mineru_command": "mineru"},
        resolve_dependencies=_resolver,
        logger=DummyLogger(),
        layout_builder_class=DummyBuilder,
    )

    assert builder.__class__.__name__ == "MineruLayoutBuilder"
    assert builder.external_layout_backend_name == "mineru_pp_doclayout_v2"


def test_mineru_direct_layout_builder_is_created_directly():
    builder = create_layout_builder(
        config={"layout_backend": "mineru_pp_doclayout_v2_direct", "mineru_layout_python": "python"},
        resolve_dependencies=_resolver,
        logger=DummyLogger(),
        layout_builder_class=DummyBuilder,
    )

    assert builder.__class__.__name__ == "MineruDirectLayoutBuilder"
    assert builder.external_layout_backend_name == "mineru_pp_doclayout_v2_direct"
    assert builder.external_layout_model == "PP-DocLayoutV2"
    assert builder.external_layout_block_source == "boxes"


def test_paddle_layout_builder_is_created_directly():
    builder = create_layout_builder(
        config={"layout_backend": "paddle_pp_doclayout_plus_l"},
        resolve_dependencies=_resolver,
        logger=DummyLogger(),
        layout_builder_class=DummyBuilder,
    )

    assert builder.__class__.__name__ == "PaddleLayoutDetectionBuilder"
    assert builder.external_layout_backend_name == "paddle_pp_doclayout_plus_l"


def test_paddle_doclayout_v3_builder_sets_v3_model_defaults():
    builder = create_layout_builder(
        config={"layout_backend": "paddle_pp_doclayout_v3"},
        resolve_dependencies=_resolver,
        logger=DummyLogger(),
        layout_builder_class=DummyBuilder,
    )

    assert builder.__class__.__name__ == "PaddleLayoutDetectionBuilder"
    assert builder.external_layout_backend_name == "paddle_pp_doclayout_v3"
    assert builder.external_layout_model == "PP-DocLayoutV3"
    assert builder.runtime.model_name == "PP-DocLayoutV3"


def test_yolo_layout_backend_is_rejected_before_builder_creation():
    try:
        create_layout_builder(
            config={"layout_backend": "yolo"},
            resolve_dependencies=_resolver,
            logger=DummyLogger(),
            layout_builder_class=DummyBuilder,
        )
    except ValueError as exc:
        assert "has been removed" in str(exc)
    else:
        raise AssertionError("layout_backend='yolo' should be rejected")


def test_disable_ocr_does_not_resolve_ocr_model_dependencies():
    def resolver(_builder_class):
        raise AssertionError("disable_ocr should not require the OCR builder dependencies")

    builder = create_ocr_builder(
        config={"disable_ocr": True, "ocr_backend": "unknown_future_backend"},
        resolve_dependencies=resolver,
        logger=DummyLogger(),
        ocr_builder_class=DummyBuilder,
    )

    assert builder.__class__.__name__ == "DisabledOcrBuilder"


def test_unknown_ocr_backend_is_rejected_when_ocr_enabled():
    try:
        create_ocr_builder(
            config={"ocr_backend": "unknown_future_backend"},
            resolve_dependencies=_resolver,
            logger=DummyLogger(),
            ocr_builder_class=DummyBuilder,
        )
    except ValueError as exc:
        assert "Unknown OCR backend" in str(exc)
    else:
        raise AssertionError("unknown OCR backend should be rejected")


def test_declared_but_unimplemented_layout_backend_is_rejected():
    try:
        create_layout_builder(
            config={"layout_backend": "humanities_layout_future"},
            resolve_dependencies=_resolver,
            logger=DummyLogger(),
            layout_builder_class=DummyBuilder,
        )
    except ValueError as exc:
        assert "not implemented yet" in str(exc)
    else:
        raise AssertionError("declared-but-unimplemented layout backend should be rejected")


def test_paddle_ocr_builder_is_created_directly():
    builder = create_ocr_builder(
        config={"ocr_backend": "paddle_ocr_v5"},
        resolve_dependencies=_resolver,
        logger=DummyLogger(),
        ocr_builder_class=DummyBuilder,
    )

    assert builder.__class__.__name__ == "PaddleOcrBuilder"
    assert builder.runtime.ocr_version == "PP-OCRv5"


def test_paddleocr_vl_ocr_builder_is_created_directly():
    builder = create_ocr_builder(
        config={
            "ocr_backend": "paddleocr_vl_ocr",
            "paddleocr_vl_endpoint": "http://localhost:1234/v1/chat/completions",
            "paddleocr_vl_model": "paddleocr-vl-1.6",
        },
        resolve_dependencies=_resolver,
        logger=DummyLogger(),
        ocr_builder_class=DummyBuilder,
    )

    assert builder.__class__.__name__ == "PaddleOCRVLOcrBuilder"
    assert builder.service.get_backend_name() == "paddleocr_vl_ocr"


def test_calamari_fallback_clears_tesseract_line_source(monkeypatch):
    class UnavailableCalamariService:
        def __init__(self, config):
            pass

        def health_check(self):
            return False

    monkeypatch.setattr(
        "aih_contexture.services.ocr_calamari.CalamariOcrService",
        UnavailableCalamariService,
    )
    config = {"ocr_backend": "calamari", "ocr_line_source": "tesseract"}

    builder = create_ocr_builder(
        config=config,
        resolve_dependencies=_resolver,
        logger=DummyLogger(),
        ocr_builder_class=DummyBuilder,
    )

    assert builder == ("resolved", DummyBuilder)
    assert "ocr_line_source" not in config


def test_tesseract_ocr_builder_is_created_directly():
    builder = create_ocr_builder(
        config={"ocr_backend": "tesseract", "tesseract_cmd": "tesseract"},
        resolve_dependencies=_resolver,
        logger=DummyLogger(),
        ocr_builder_class=DummyBuilder,
    )

    assert builder.__class__.__name__ == "TesseractOcrBuilder"
    assert builder.service.tesseract_lang == "eng"


def test_declared_but_unimplemented_ocr_backend_is_rejected():
    try:
        create_ocr_builder(
            config={"ocr_backend": "mineru_pytorch_paddle_ocr"},
            resolve_dependencies=_resolver,
            logger=DummyLogger(),
            ocr_builder_class=DummyBuilder,
        )
    except ValueError as exc:
        assert "not implemented yet" in str(exc)
    else:
        raise AssertionError("declared-but-unimplemented OCR backend should be rejected")
