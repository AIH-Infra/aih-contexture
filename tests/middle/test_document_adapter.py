from aih_contexture.middle.adapters import document_to_middle
from aih_contexture.schema.blocks import Text
from aih_contexture.schema.document import Document
from aih_contexture.schema.groups.page import PageGroup
from aih_contexture.schema.polygon import PolygonBox
from aih_contexture.schema.text.line import Line
from aih_contexture.schema.text.span import Span


def test_document_to_middle_exports_page_blocks_and_provenance():
    page = PageGroup(
        page_id=3,
        polygon=PolygonBox.from_bbox([0, 0, 100, 200]),
        children=[],
    )
    block = Text(
        polygon=PolygonBox.from_bbox([10, 20, 90, 60]),
        block_id=0,
        page_id=3,
    )
    page.add_child(block)
    page.add_structure(block)
    document = Document(filepath="sample.pdf", pages=[page])

    middle = document_to_middle(
        document,
        layout_backend="surya",
        layout_model="surya-layout-test",
        ocr_backend="calamari",
    ).to_dict()

    assert middle["source_name"] == "sample.pdf"
    assert middle["backends"] == {"layout": "surya", "ocr": "calamari", "layout_model": "surya-layout-test"}
    assert middle["pages"][0]["index"] == 3
    assert middle["pages"][0]["anchor_start"] == 3
    assert middle["pages"][0]["anchor_end"] == 4
    assert middle["pages"][0]["blocks"][0]["type"] == "Text"
    assert middle["pages"][0]["blocks"][0]["bbox"] == [10.0, 20.0, 90.0, 60.0]
    assert middle["pages"][0]["blocks"][0]["provenance"][0]["backend"] == "surya"
    assert middle["pages"][0]["blocks"][0]["provenance"][0]["model"] == "surya-layout-test"
    assert middle["pages"][0]["blocks"][0]["provenance"][1]["backend"] == "calamari"


def test_document_to_middle_exports_pipeline_page_number_metadata():
    page = PageGroup(
        page_id=0,
        polygon=PolygonBox.from_bbox([0, 0, 100, 200]),
        children=[],
    )
    page._internal_metadata = {
        "machine_page_number": 1,
        "printed_page_number": "217",
        "page_header_text": "Is there any Philosophy of History? 217",
        "page_footer_text": "Footer",
    }
    document = Document(filepath="sample.pdf", pages=[page])

    middle = document_to_middle(document, layout_backend="paddle_pp_doclayout_v3", ocr_backend="none").to_dict()

    assert middle["pages"][0]["printed_page"] == "217"
    assert middle["pages"][0]["attrs"]["machine_page_number"] == 1
    assert middle["pages"][0]["attrs"]["page_header_text"] == "Is there any Philosophy of History? 217"
    assert middle["pages"][0]["attrs"]["page_footer_text"] == "Footer"


def test_document_to_middle_exports_nested_spans():
    page = PageGroup(
        page_id=0,
        polygon=PolygonBox.from_bbox([0, 0, 100, 200]),
        children=[],
    )
    block = Text(
        polygon=PolygonBox.from_bbox([10, 20, 90, 80]),
        page_id=0,
    )
    page.add_full_block(block)
    page.add_structure(block)
    line = Line(
        polygon=PolygonBox.from_bbox([10, 20, 90, 40]),
        page_id=0,
    )
    page.add_full_block(line)
    block.add_structure(line)
    span = Span(
        polygon=PolygonBox.from_bbox([12, 22, 40, 36]),
        text="hello",
        font="TestFont",
        font_weight=400,
        font_size=10,
        minimum_position=0,
        maximum_position=5,
        formats=["plain"],
        page_id=0,
        text_extraction_method="pdftext",
    )
    page.add_full_block(span)
    line.add_structure(span)
    document = Document(filepath="sample.pdf", pages=[page])

    middle = document_to_middle(document, layout_backend="surya", ocr_backend="none").to_dict()

    spans = middle["pages"][0]["blocks"][0]["spans"]
    assert len(spans) == 1
    assert spans[0]["text"] == "hello"
    assert spans[0]["bbox"] == [12.0, 22.0, 40.0, 36.0]
    assert spans[0]["attrs"]["font"] == "TestFont"
    assert spans[0]["provenance"][0]["stage"] == "span"
