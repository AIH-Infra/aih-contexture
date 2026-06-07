from PIL import Image

from surya.layout.schema import LayoutBox, LayoutResult

from aih_contexture.builders.document import DocumentBuilder
from aih_contexture.builders.layout import LayoutBuilder
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.groups.page import PageGroup
from aih_contexture.schema.polygon import PolygonBox


class _Provider:
    filepath = "fake.pdf"
    page_range = [0]

    def __init__(self):
        self.image_calls = []

    def get_images(self, idxs, dpi):
        self.image_calls.append((list(idxs), dpi))
        return [Image.new("RGB", (dpi, dpi * 2), "white") for _ in idxs]

    def get_page_bbox(self, _page_id):
        return PolygonBox.from_bbox([0, 0, 72, 144])

    def get_page_refs(self, _page_id):
        return []


def test_document_builder_uses_backend_auto_dpi_defaults():
    provider = _Provider()
    builder = DocumentBuilder(
        {
            "layout_backend": "paddle_pp_doclayout_v3",
            "ocr_backend": "tesseract",
        }
    )

    builder.build_document(provider)

    assert provider.image_calls == [([0], 144), ([0], 300)]
    assert builder.actual_lowres_dpi == 144
    assert builder.actual_highres_dpi == 300


def test_document_builder_uses_surya_and_paddle_ocr_low_defaults():
    provider = _Provider()
    builder = DocumentBuilder(
        {
            "layout_backend": "surya",
            "surya_layout_quality": "high",
            "ocr_backend": "paddle_ocr_v5",
        }
    )

    builder.build_document(provider)

    assert provider.image_calls == [([0], 192), ([0], 192)]


def test_document_builder_honors_explicit_legacy_dpi_values():
    provider = _Provider()
    builder = DocumentBuilder(
        {
            "layout_backend": "mineru_pp_doclayout_v2_direct",
            "ocr_backend": "calamari",
            "lowres_image_dpi": 111,
            "highres_image_dpi": 444,
        }
    )

    builder.build_document(provider)

    assert provider.image_calls == [([0], 111), ([0], 444)]


def test_document_builder_honors_new_dpi_overrides():
    provider = _Provider()
    builder = DocumentBuilder(
        {
            "layout_backend": "surya",
            "surya_layout_quality": "fast",
            "layout_dpi_override": 150,
            "ocr_backend": "surya",
            "ocr_quality": "high",
            "ocr_dpi_override": 500,
        }
    )

    builder.build_document(provider)

    assert provider.image_calls == [([0], 150), ([0], 500)]


def test_layout_coordinates_normalize_from_layout_pixels_to_pdf_points():
    page = PageGroup(
        page_id=0,
        polygon=PolygonBox.from_bbox([0, 0, 72, 144]),
        children=[],
        structure=[],
    )
    layout_result = LayoutResult(
        image_bbox=[0, 0, 400, 800],
        bboxes=[
            LayoutBox(
                label=BlockTypes.Text.name,
                position=0,
                top_k={BlockTypes.Text.name: 1.0},
                polygon=[[0, 0], [200, 0], [200, 400], [0, 400]],
            )
        ],
        sliced=False,
    )

    LayoutBuilder(layout_model=None).add_blocks_to_pages([page], [layout_result])

    block = page.get_block(page.structure[0])
    assert block.polygon.bbox == [0.0, 0.0, 36.0, 72.0]
