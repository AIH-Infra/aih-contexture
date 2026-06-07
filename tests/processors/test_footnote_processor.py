import pytest

from aih_contexture.processors.footnote import FootnoteProcessor
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.blocks import ComplexRegion, Footnote, Picture, Text
from aih_contexture.schema.document import Document
from aih_contexture.schema.groups.page import PageGroup
from aih_contexture.schema.polygon import PolygonBox


@pytest.mark.filename("population_stats.pdf")
@pytest.mark.config({"page_range": [4]})
def test_footnote_processor(pdf_document):
    processor = FootnoteProcessor()
    processor(pdf_document)

    page0_footnotes = pdf_document.pages[0].contained_blocks(pdf_document, [BlockTypes.Footnote])
    assert len(page0_footnotes) >= 2

    assert page0_footnotes[-1].raw_text(pdf_document).strip().startswith("5")


def _polygon(x0, y0, x1, y1):
    return PolygonBox.from_bbox([x0, y0, x1, y1])


def test_footnote_processor_lifts_nested_footnotes_and_sorts_by_position():
    page = PageGroup(
        page_id=0,
        polygon=_polygon(0, 0, 100, 300),
        children=[],
        structure=[],
    )
    body = page.add_full_block(Text(polygon=_polygon(0, 0, 100, 50), page_id=0))
    complex_region = page.add_full_block(ComplexRegion(polygon=_polygon(0, 150, 100, 260), page_id=0))
    nested_footnote = page.add_full_block(Footnote(polygon=_polygon(0, 220, 100, 240), page_id=0))
    picture = page.add_full_block(Picture(polygon=_polygon(0, 180, 100, 210), page_id=0))
    top_footnote = page.add_full_block(Footnote(polygon=_polygon(0, 120, 100, 140), page_id=0))

    page.add_structure(body)
    page.add_structure(complex_region)
    page.add_structure(top_footnote)
    complex_region.add_structure(nested_footnote)
    complex_region.add_structure(picture)
    document = Document(filepath="sample.pdf", pages=[page])

    FootnoteProcessor()(document)

    assert nested_footnote.id not in complex_region.structure
    assert picture.id in complex_region.structure
    assert page.structure[-2:] == [top_footnote.id, nested_footnote.id]
