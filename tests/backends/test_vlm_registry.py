from aih_contexture.backends.vlm.registry import (
    VlmBackendRegistry,
    VlmBackendSpec,
    default_vlm_registry,
)
from aih_contexture.backends.capabilities import BackendCapabilities


def test_default_vlm_registry_exposes_current_backends():
    assert default_vlm_registry.names() == [
        "chandra",
        "churro",
        "mineru_vl",
        "paddleocr_vl",
        "vlm_generalized",
    ]

    chandra = default_vlm_registry.capabilities("chandra")
    assert chandra.kind == "vlm"
    assert chandra.supports_bbox is True
    assert chandra.implemented is True


def test_vlm_registry_normalizes_names_and_rejects_duplicates():
    registry = VlmBackendRegistry()
    spec = VlmBackendSpec(
        name="example_vlm",
        display_name="Example VLM",
        capabilities=BackendCapabilities(
            name="example_vlm",
            kind="vlm",
            display_name="Example VLM",
        ),
    )

    registry.register(spec)
    assert registry.get("Example-VLM") is spec

    try:
        registry.register(spec)
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("duplicate backend registration should fail")


def test_specialized_vlm_backends_are_declared_with_upstream_protocol_notes():
    all_names = default_vlm_registry.names(implemented_only=False)

    assert "paddleocr_vl" in all_names
    assert "mineru_vl" in all_names
    assert default_vlm_registry.capabilities("paddleocr_vl").implemented is True
    assert default_vlm_registry.capabilities("mineru_vl").implemented is True

    paddle_notes = default_vlm_registry.capabilities("paddleocr_vl").notes
    mineru_notes = default_vlm_registry.capabilities("mineru_vl").notes

    assert "PaddleOCR-VL" in paddle_notes
    assert "1.6" in paddle_notes
    assert "/layout-parsing" in paddle_notes
    assert "PP-DocLayoutV3" in paddle_notes
    assert "VLRecognition" in paddle_notes
    assert "OpenAI-compatible" in paddle_notes
    assert "MinerU-VL" in mineru_notes
    assert "2.5pro-2605" in mineru_notes
    assert "OpenAI-compatible" in mineru_notes
    assert "Layout Detection" in mineru_notes
    assert "official-compatible" in mineru_notes
