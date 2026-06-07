from types import SimpleNamespace

from PIL import Image

from aih_contexture.builders.line import LineBuilder
from aih_contexture.schema.polygon import PolygonBox


class _Page:
    page_id = 0

    def __init__(self):
        self.polygon = PolygonBox.from_bbox([0, 0, 100, 100])
        self.text_extraction_method = "pdftext"
        self.ocr_errors_detected = False
        self._image = Image.new("RGB", (100, 100), "white")

    def get_image(self, highres=False, remove_blocks=None):
        return self._image


class _Document:
    def __init__(self, page):
        self.pages = [page]

    def get_page(self, page_id):
        return self.pages[page_id]


class _Provider:
    page_lines = {0: []}

    def get_page_bbox(self, page_id):
        return PolygonBox.from_bbox([0, 0, 100, 100])


def test_line_builder_force_ocr_skips_text_layer_quality_detection():
    page = _Page()
    builder = LineBuilder.__new__(LineBuilder)
    builder.force_ocr = True
    builder.disable_ocr = False
    builder.detection_line_min_confidence = 0.8
    builder.ocr_remove_blocks = ()

    def fail_if_called(*args, **kwargs):
        raise AssertionError("force_ocr should skip provider text quality checks")

    builder.ocr_error_detection = fail_if_called
    builder.check_layout_coverage = fail_if_called
    builder.check_line_overlaps = fail_if_called
    builder.get_detection_results = lambda page_images, run_detection: [
        SimpleNamespace(
            bboxes=[
                SimpleNamespace(
                    confidence=0.99,
                    polygon=[[10, 10], [90, 10], [90, 20], [10, 20]],
                )
            ]
        )
    ]

    provider_lines, ocr_lines = builder.get_all_lines(_Document(page), _Provider())

    assert provider_lines == {0: []}
    assert len(ocr_lines[0]) == 1
    assert page.text_extraction_method == "surya"
    assert page.ocr_errors_detected is True
