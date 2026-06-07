from aih_contexture.middle.adapters import layout_result_to_middle_page
from aih_contexture.middle.labels import normalize_block_type
from aih_contexture.services.layout_base import LayoutBox, LayoutResult


def test_layout_result_to_middle_page_preserves_geometry_and_provenance():
    layout = LayoutResult(
        image_bbox=[0, 0, 1000, 1500],
        bboxes=[
            LayoutBox(
                label="header",
                position=1,
                top_k={"header": 0.92},
                polygon=[[0, 0], [1000, 0], [1000, 80], [0, 80]],
            ),
            LayoutBox(
                label="aside_text",
                position=0,
                top_k={"aside_text": 0.8},
                polygon=[[0, 200], [120, 200], [120, 500], [0, 500]],
            ),
        ],
        sliced=True,
    )

    page = layout_result_to_middle_page(
        layout,
        page_index=2,
        backend="mineru_pp_doclayout_v2",
        model="PP-DocLayoutV2",
    )

    assert page.width == 1000
    assert page.height == 1500
    assert page.anchor_start == 2
    assert page.anchor_end == 3
    assert page.attrs["sliced"] is True
    assert [block.type for block in page.blocks] == ["MarginalNote", "PageHeader"]
    assert page.blocks[0].bbox == [0.0, 200.0, 120.0, 500.0]
    assert page.blocks[0].provenance[0].backend == "mineru_pp_doclayout_v2"
    assert page.blocks[0].provenance[0].raw_label == "aside_text"


def test_normalize_block_type_covers_mineru_and_paddle_labels():
    assert normalize_block_type("doc_title") == "SectionHeader"
    assert normalize_block_type("paragraph_title") == "SectionHeader"
    assert normalize_block_type("page_footnote") == "Footnote"
    assert normalize_block_type("page_number") == "PageNumber"
    assert normalize_block_type("footer") == "PageFooter"
    assert normalize_block_type("header") == "PageHeader"
    assert normalize_block_type("isolate_formula") == "Equation"
    assert normalize_block_type("chart_body") == "Figure"
    assert normalize_block_type("algorithm_caption") == "Caption"
    assert normalize_block_type("code_caption") == "Caption"
    assert normalize_block_type("simple_table") == "Table"
    assert normalize_block_type("complex_table") == "Table"
    assert normalize_block_type("equation_interline") == "Equation"
    assert normalize_block_type("equation_inline") == "Equation"
    assert normalize_block_type("text_list") == "ListItem"
    assert normalize_block_type("reference_list") == "Reference"
    assert normalize_block_type("md") == "Text"
    assert normalize_block_type("discarded") == "ComplexRegion"
    assert normalize_block_type("unknown_vendor_label") == "ComplexRegion"


def test_vertical_text_keeps_orientation_hint():
    layout = LayoutResult(
        image_bbox=[0, 0, 100, 100],
        bboxes=[
            LayoutBox(
                label="vertical_text",
                position=0,
                top_k={"vertical_text": 0.7},
                polygon=[[10, 10], [20, 10], [20, 90], [10, 90]],
            )
        ],
    )

    page = layout_result_to_middle_page(layout, page_index=0, backend="paddle_pp_doclayout_v3")

    assert page.blocks[0].type == "Text"
    assert page.blocks[0].attrs["orientation"] == "vertical"
