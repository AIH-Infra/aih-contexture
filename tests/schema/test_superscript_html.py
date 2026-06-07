from aih_contexture.schema.polygon import PolygonBox
from aih_contexture.schema.text.span import Span


def _polygon():
    return PolygonBox.from_bbox([0, 0, 10, 10])


def test_span_preserves_existing_sup_tag_when_marked_superscript():
    span = Span(
        polygon=_polygon(),
        text="<sup>26</sup> Alexander, on Mixture.",
        font="TestFont",
        font_weight=400,
        font_size=10,
        minimum_position=0,
        maximum_position=10,
        formats=["plain"],
        has_superscript=True,
        page_id=0,
    )

    html = span.assemble_html(None, [], None, {"superscript_policy": "preserve_all"})

    assert html == "<sup>26</sup> Alexander, on Mixture."
    assert "<sup>&</sup>lt;sup" not in html
