import pytest

from aih_contexture.config.dpi_presets import (
    get_layout_dpi,
    get_ocr_dpi,
    get_ocr_quality_for_backend,
)


@pytest.mark.parametrize(
    ("quality", "dpi"),
    [
        ("fast", 96),
        ("standard", 144),
        ("high", 192),
    ],
)
def test_surya_layout_quality_presets(quality, dpi):
    assert get_layout_dpi("surya", surya_quality=quality) == dpi


@pytest.mark.parametrize(
    ("backend", "dpi"),
    [
        ("mineru_pp_doclayout_v2", 200),
        ("mineru_pp_doclayout_v2_direct", 200),
        ("paddle_pp_doclayout_plus_l", 144),
        ("paddle_pp_doclayout_v3", 144),
        ("vlm", 96),
        ("vlm_layout", 96),
    ],
)
def test_layout_backend_default_dpi(backend, dpi):
    assert get_layout_dpi(backend) == dpi


@pytest.mark.parametrize(
    ("backend", "quality", "dpi"),
    [
        ("surya", "auto", 192),
        ("paddle_ocr_v5", "auto", 192),
        ("paddleocr_vl_ocr", "auto", 300),
        ("tesseract", "auto", 300),
        ("calamari", "auto", 300),
        ("vlm", "auto", 300),
        ("vlm_ocr", "auto", 300),
        ("surya", "medium", 300),
        ("tesseract", "high", 400),
    ],
)
def test_ocr_backend_default_and_explicit_quality_dpi(backend, quality, dpi):
    assert get_ocr_dpi(backend, quality=quality) == dpi


def test_ocr_quality_aliases_and_override():
    assert get_ocr_quality_for_backend("surya", "standard") == "medium"
    assert get_ocr_dpi("surya", quality="low", override=450) == 450
    with pytest.raises(ValueError):
        get_ocr_dpi("surya", override=0)
