from aih_contexture.builders.ocr_line_crops import (
    DEFAULT_OCR_CROP_PADDING_FRAC,
    DEFAULT_OCR_CROP_PADDING_PX,
    DEFAULT_OCR_CROP_UPSCALE_MIN_HEIGHT,
    OcrLineCropper,
    _int_bbox,
    _pad_bbox,
)
from aih_contexture.builders.tesseract_line_detection import _pad_bbox as _pad_detected_line_bbox


def test_ocr_line_crop_defaults_are_conservative_against_tight_line_boxes():
    cropper = OcrLineCropper({})

    assert cropper.padding_px == DEFAULT_OCR_CROP_PADDING_PX
    assert cropper.padding_frac == DEFAULT_OCR_CROP_PADDING_FRAC
    assert cropper.upscale_min_height == DEFAULT_OCR_CROP_UPSCALE_MIN_HEIGHT


def test_int_bbox_rounds_outward_to_avoid_clipping_glyph_edges():
    assert _int_bbox([10.8, 20.2, 30.1, 40.9]) == (10, 20, 31, 41)


def test_line_crop_padding_expands_and_clips_to_image_bounds():
    assert _pad_bbox(
        (2, 3, 20, 13),
        image_size=(100, 80),
        padding_px=8,
        padding_frac=0.12,
    ) == (0, 0, 28, 21)


def test_tesseract_detected_line_bbox_is_padded_before_writeback():
    assert _pad_detected_line_bbox(
        (40, 30, 140, 50),
        image_size=(200, 100),
        padding_px=8,
        padding_frac=0.12,
    ) == (28, 22, 152, 58)
