from aih_contexture.backends.capabilities import BackendCapabilities
from aih_contexture.backends.layout.registry import (
    LayoutBackendRegistry,
    LayoutBackendSpec,
    default_layout_registry,
)


def test_default_layout_registry_exposes_current_backends():
    assert default_layout_registry.names() == [
        "external_layout_sidecar",
        "mineru_pp_doclayout_v2",
        "mineru_pp_doclayout_v2_direct",
        "paddle_pp_doclayout_plus_l",
        "paddle_pp_doclayout_v3",
        "surya",
        "vlm_layout",
    ]
    surya = default_layout_registry.capabilities("surya")
    assert surya.kind == "layout"
    assert surya.supports_bbox is True
    assert surya.implemented is True
    sidecar = default_layout_registry.capabilities("external_layout_sidecar")
    assert sidecar.kind == "layout"
    assert sidecar.implemented is True
    assert sidecar.supports_gpu is False
    mineru = default_layout_registry.capabilities("mineru_pp_doclayout_v2")
    assert mineru.implemented is True
    assert mineru.optional_dependency == "mineru"
    mineru_direct = default_layout_registry.capabilities("mineru_pp_doclayout_v2_direct")
    assert mineru_direct.implemented is True
    assert mineru_direct.optional_dependency == "mineru"
    assert "layout-only" in mineru_direct.notes
    paddle = default_layout_registry.capabilities("paddle_pp_doclayout_plus_l")
    assert paddle.implemented is True
    assert paddle.optional_dependency == "paddleocr"
    paddle_v3 = default_layout_registry.capabilities("paddle_pp_doclayout_v3")
    assert paddle_v3.implemented is True
    assert paddle_v3.optional_dependency == "paddleocr"


def test_layout_registry_normalizes_names_and_rejects_duplicates():
    registry = LayoutBackendRegistry()
    spec = LayoutBackendSpec(
        name="example_backend",
        display_name="Example",
        capabilities=BackendCapabilities(
            name="example_backend",
            kind="layout",
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


def test_yolo_is_not_registered():
    assert "yolo" not in default_layout_registry.names(implemented_only=False)
    try:
        default_layout_registry.get("yolo")
    except ValueError as exc:
        assert "Unknown layout backend" in str(exc)
    else:
        raise AssertionError("yolo should not be registered")


def test_planned_layout_backends_are_declared_but_not_implemented():
    all_names = default_layout_registry.names(implemented_only=False)

    assert "mineru_pp_doclayout_v2" in all_names
    assert "mineru_pp_doclayout_v2_direct" in all_names
    assert "paddle_pp_doclayout_plus_l" in all_names
    assert "paddle_pp_doclayout_v3" in all_names
    assert "humanities_layout_future" in all_names
    assert default_layout_registry.capabilities("humanities_layout_future").implemented is False
    assert default_layout_registry.names() == [
        "external_layout_sidecar",
        "mineru_pp_doclayout_v2",
        "mineru_pp_doclayout_v2_direct",
        "paddle_pp_doclayout_plus_l",
        "paddle_pp_doclayout_v3",
        "surya",
        "vlm_layout",
    ]
