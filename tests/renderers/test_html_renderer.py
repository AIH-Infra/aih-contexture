import pytest

from marker.renderers.html import HTMLRenderer


@pytest.mark.config(
    {
        "page_range": [0],
        "disable_ocr": True,
        "add_block_ids": True,
        "paginate_output": True,
    }
)
def test_html_renderer_block_ids(pdf_document, config):
    renderer = HTMLRenderer(config)
    html = renderer(pdf_document).html

    # Verify some block IDs are present
    assert "/page/0/Text/1" in html
