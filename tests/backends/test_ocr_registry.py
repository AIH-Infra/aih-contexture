from aih_contexture.backends.capabilities import BackendCapabilities
from aih_contexture.backends.ocr.registry import (
    OcrBackendRegistry,
    OcrBackendSpec,
    default_ocr_registry,
)


def test_default_ocr_registry_exposes_current_backends():
    assert default_ocr_registry.names() == [
        "calamari",
        "paddle_ocr_v5",
        "paddleocr_vl_ocr",
        "surya",
        "tesseract",
        "vlm_ocr",
    ]
    surya = default_ocr_registry.capabilities("surya")
    assert surya.kind == "ocr"
    assert surya.supports_bbox is True
    assert surya.implemented is True


def test_ocr_registry_normalizes_names_and_rejects_duplicates():
    registry = OcrBackendRegistry()
    spec = OcrBackendSpec(
        name="example_backend",
        display_name="Example",
        capabilities=BackendCapabilities(
            name="example_backend",
            kind="ocr",
            display_name="Example",
        ),
    )

    registry.register(spec)
    assert registry.get("Example-Backend") is spec

    try:
        registry.register(spec)
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("duplicate backend registration should fail")


def test_yolo_is_not_registered_as_ocr_backend():
    assert "yolo" not in default_ocr_registry.names(implemented_only=False)
    try:
        default_ocr_registry.get("yolo")
    except ValueError as exc:
        assert "Unknown OCR backend" in str(exc)
    else:
        raise AssertionError("yolo should not be registered")


def test_optional_and_planned_ocr_backends_are_declared():
    all_names = default_ocr_registry.names(implemented_only=False)

    assert "paddle_ocr_v5" in all_names
    assert "paddleocr_vl_ocr" in all_names
    assert "tesseract" in all_names
    assert "mineru_pytorch_paddle_ocr" in all_names
    assert default_ocr_registry.capabilities("paddle_ocr_v5").implemented is True
    assert default_ocr_registry.capabilities("paddleocr_vl_ocr").implemented is True
    assert default_ocr_registry.capabilities("tesseract").implemented is True
    assert default_ocr_registry.capabilities("mineru_pytorch_paddle_ocr").implemented is False
    assert default_ocr_registry.names() == [
        "calamari",
        "paddle_ocr_v5",
        "paddleocr_vl_ocr",
        "surya",
        "tesseract",
        "vlm_ocr",
    ]
