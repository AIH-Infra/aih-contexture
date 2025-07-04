import pytest

from marker.renderers.chunk import ChunkRenderer


@pytest.mark.config({"page_range": [0]})
def test_markdown_renderer_pagination(pdf_document):
    renderer = ChunkRenderer()
    chunk_output = renderer(pdf_document)
    blocks = chunk_output.blocks
    page_info = chunk_output.page_info

    assert len(blocks) == 15
    assert blocks[0].block_type == "SectionHeader"
    assert page_info[0]["bbox"] is not None
    assert page_info[0]["polygon"] is not None
