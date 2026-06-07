from PIL import Image

from aih_contexture.builders.paddle_ocr import PaddleOcrBuilder
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document
from aih_contexture.schema.groups.page import PageGroup
from aih_contexture.schema.polygon import PolygonBox
from aih_contexture.schema.registry import get_block_class


class FakeRuntime:
    ocr_version = "PP-OCRv5"

    def run(self, image_paths, *, page_sizes=None):
        assert len(image_paths) == 1
        return [
            {
                "res": {
                    "page_index": 0,
                    "rec_texts": ["Paddle text"],
                    "rec_boxes": [[10, 10, 90, 30]],
                    "rec_scores": [0.98],
                }
            }
        ]


class FakeProvider:
    def get_page_bbox(self, _page_id):
        return PolygonBox.from_bbox([0, 0, 100, 100])


def _document_with_line():
    page = PageGroup(
        page_id=0,
        lowres_image=Image.new("RGB", (100, 100), "white"),
        highres_image=Image.new("RGB", (100, 100), "white"),
        polygon=PolygonBox.from_bbox([0, 0, 100, 100]),
        refs=[],
    )
    page.text_extraction_method = "surya"
    TextClass = get_block_class(BlockTypes.Text)
    LineClass = get_block_class(BlockTypes.Line)
    text = TextClass(polygon=PolygonBox.from_bbox([0, 0, 100, 50]), page_id=0)
    page.add_full_block(text)
    page.structure = [text.id]
    line = LineClass(
        polygon=PolygonBox.from_bbox([5, 5, 95, 35]),
        page_id=0,
        text_extraction_method="surya",
    )
    page.add_full_block(line)
    text.structure = [line.id]
    return Document(filepath="sample.pdf", pages=[page]), line


def test_paddle_ocr_builder_writes_spans_into_existing_lines():
    document, line = _document_with_line()
    builder = PaddleOcrBuilder({"ocr_backend": "paddle_ocr_v5"}, runtime=FakeRuntime())

    builder(document, FakeProvider())

    spans = line.contained_blocks(document, [BlockTypes.Span])
    assert len(spans) == 1
    assert spans[0].text == "Paddle text "
    assert spans[0].polygon.bbox == [10.0, 10.0, 90.0, 30.0]
    assert line.get_internal_metadata("ocr_backend") == "paddle_ocr_v5"
    assert line.get_internal_metadata("ocr_confidence") == 0.98
    assert builder.last_runtime_payload[0]["res"]["rec_texts"] == ["Paddle text"]
