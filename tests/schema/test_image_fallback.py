from PIL import Image

from aih_contexture.schema.blocks.picture import Picture
from aih_contexture.schema.document import Document
from aih_contexture.schema.groups.page import PageGroup
from aih_contexture.schema.polygon import PolygonBox


def _polygon(x0, y0, x1, y1):
    return PolygonBox(polygon=[[x0, y0], [x1, y0], [x1, y1], [x0, y1]])


def test_block_image_falls_back_to_lowres_when_highres_page_image_is_missing():
    page = PageGroup(
        page_id=0,
        polygon=_polygon(0, 0, 100, 100),
        lowres_image=Image.new("RGB", (100, 100), "white"),
        highres_image=None,
        children=[],
        structure=[],
    )
    block = Picture(polygon=_polygon(10, 20, 50, 60), page_id=0)
    page.add_full_block(block)
    document = Document(filepath="synthetic.pdf", pages=[page])

    cropped = block.get_image(document, highres=True)

    assert cropped is not None
    assert cropped.size == (40, 40)


def test_block_image_returns_none_when_no_page_image_is_available():
    page = PageGroup(
        page_id=0,
        polygon=_polygon(0, 0, 100, 100),
        lowres_image=None,
        highres_image=None,
        children=[],
        structure=[],
    )
    block = Picture(polygon=_polygon(10, 20, 50, 60), page_id=0)
    page.add_full_block(block)
    document = Document(filepath="synthetic.pdf", pages=[page])

    assert block.get_image(document, highres=True) is None
