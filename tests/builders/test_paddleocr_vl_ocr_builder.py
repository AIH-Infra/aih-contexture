from PIL import Image

from aih_contexture.builders.paddleocr_vl_ocr import PaddleOCRVLOcrBuilder
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document
from aih_contexture.schema.groups.page import PageGroup
from aih_contexture.schema.polygon import PolygonBox
from aih_contexture.schema.registry import get_block_class


class FakeProvider:
    def get_page_bbox(self, _page_id):
        return PolygonBox.from_bbox([0, 0, 100, 100])


class FakePaddleVLService:
    def __init__(self):
        self.calls = []

    async def recognize_image_async(self, session, img, *, api_key=None, prompt_label=None):
        self.calls.append({"size": img.size, "prompt_label": prompt_label, "api_key": api_key})
        return {
            "backend": "paddleocr_vl_ocr",
            "official_protocol": "paddleocr_vl_prompt",
            "markdown": "Detected title",
            "blocks": [
                {
                    "label": "section_header",
                    "text": "Detected title",
                    "bbox": [0, 0, img.size[0], max(1, img.size[1] // 2)],
                }
            ],
        }


def _document_with_text_block():
    page = PageGroup(
        page_id=0,
        lowres_image=Image.new("RGB", (100, 100), "white"),
        highres_image=Image.new("RGB", (100, 100), "white"),
        polygon=PolygonBox.from_bbox([0, 0, 100, 100]),
        refs=[],
    )
    page.text_extraction_method = "surya"
    TextClass = get_block_class(BlockTypes.Text)
    text = TextClass(polygon=PolygonBox.from_bbox([0, 0, 100, 50]), page_id=0)
    page.add_full_block(text)
    page.structure = [text.id]
    return Document(filepath="sample.pdf", pages=[page]), text


def test_paddleocr_vl_ocr_builder_runs_block_crops_and_writes_spans():
    document, text = _document_with_text_block()
    service = FakePaddleVLService()
    builder = PaddleOCRVLOcrBuilder(
        {
            "ocr_backend": "paddleocr_vl_ocr",
            "paddleocr_vl_crop_padding_px": 0,
            "paddleocr_vl_crop_padding_frac": 0,
            "paddleocr_vl_api_key": "key",
        },
        service=service,
    )

    builder(document, FakeProvider())

    lines = text.contained_blocks(document, [BlockTypes.Line])
    assert len(lines) == 1
    spans = lines[0].contained_blocks(document, [BlockTypes.Span])
    assert spans[0].text == "Detected title "
    assert spans[0].polygon.bbox == [0.0, 0.0, 100.0, 25.0]
    assert service.calls == [{"size": (100, 50), "prompt_label": "ocr", "api_key": "key"}]
    assert text.get_internal_metadata("ocr_backend") == "paddleocr_vl_ocr"
