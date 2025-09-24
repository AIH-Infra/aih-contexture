import pytest

from marker.processors.ignoretext import IgnoreTextProcessor
from marker.schema import BlockTypes


@pytest.mark.filename("bio_pdf.pdf")
@pytest.mark.config({"page_range": list(range(10))})
@pytest.mark.skip(reason="New layout model correctly identifies the block as a PageHeader, so nothing to be done by the IgnoreTextProcessor")
def test_ignoretext_processor(pdf_document):
    processor = IgnoreTextProcessor()
    processor(pdf_document)

    page1_header = pdf_document.pages[1].contained_blocks(pdf_document, [BlockTypes.Text])[0]
    assert "bioRxiv" in page1_header.raw_text(pdf_document)

    assert page1_header.ignore_for_output is True
