from aih_contexture.scripts.ui.backend_selectors import (
    layout_backend_options,
    normalize_backend_session_state,
    normalize_layout_backend_state,
    normalize_ocr_backend_state,
    ocr_backend_options,
)


def test_layout_backend_options_follow_registry_without_yolo():
    assert layout_backend_options() == [
        "surya",
        "paddle_pp_doclayout_plus_l",
        "paddle_pp_doclayout_v3",
        "mineru_pp_doclayout_v2_direct",
        "external_layout_sidecar",
        "mineru_pp_doclayout_v2",
    ]
    assert "yolo" not in layout_backend_options()
    assert "vlm_layout" not in layout_backend_options()


def test_ocr_backend_options_follow_registry_with_tesseract():
    assert ocr_backend_options() == [
        "none",
        "calamari",
        "paddle_ocr_v5",
        "paddleocr_vl_ocr",
        "surya",
        "tesseract",
        "vlm_ocr",
    ]


def test_legacy_layout_state_is_migrated_or_rejected():
    backend, warning = normalize_layout_backend_state("vlm")
    assert backend == "surya"
    assert "VLM Layout" in warning

    backend, warning = normalize_layout_backend_state("vlm_layout")
    assert backend == "surya"
    assert "VLM Layout" in warning

    backend, warning = normalize_layout_backend_state("yolo")
    assert backend == "surya"
    assert "YOLO" in warning


def test_legacy_ocr_state_is_migrated_or_rejected():
    assert normalize_ocr_backend_state("vlm") == ("vlm_ocr", None)
    assert normalize_ocr_backend_state("tesseract") == ("tesseract", None)


def test_backend_session_state_normalization_updates_both_selectors():
    session_state = {"layout_backend": "yolo", "ocr_backend": "tesseract"}

    warnings = normalize_backend_session_state(session_state)

    assert session_state == {"layout_backend": "surya", "ocr_backend": "tesseract"}
    assert len(warnings) == 1
