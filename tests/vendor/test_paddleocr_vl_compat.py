from aih_contexture.vendor.paddleocr_vl_compat import (
    extract_paddle_pruned_blocks,
    parse_paddle_vl_loc_blocks,
    segment_paddle_vl_loc_blocks,
)


def test_parse_paddle_vl_loc_blocks_recovers_structure_without_content_specific_rules():
    text = "\n".join(
        [
            "35<|LOC_865|><|LOC_48|><|LOC_886|><|LOC_48|><|LOC_886|><|LOC_59|><|LOC_865|><|LOC_59|>",
            "Introduction<|LOC_116|><|LOC_87|><|LOC_239|><|LOC_87|><|LOC_239|><|LOC_100|><|LOC_116|><|LOC_100|>",
            "\\(^{1}\\) See the recent collection.<|LOC_116|><|LOC_582|><|LOC_529|><|LOC_582|><|LOC_529|><|LOC_595|><|LOC_116|><|LOC_595|>",
            "Springer<|LOC_793|><|LOC_947|><|LOC_884|><|LOC_947|><|LOC_884|><|LOC_965|><|LOC_793|><|LOC_965|>",
        ]
    )

    blocks = parse_paddle_vl_loc_blocks(
        text,
        width=1000,
        height=2000,
        prompt_label="ocr",
        prompt="OCR:",
    )

    assert [block["label"] for block in blocks] == [
        "page_number",
        "section_header",
        "footnote",
        "page_footer",
    ]
    assert blocks[0]["bbox"] == [865, 96, 886, 118]
    assert blocks[1]["heading_level"] == 2
    assert blocks[1]["heading_level_source"] == "paddle_loc_heuristic"
    assert blocks[3]["text"] == "Springer"


def test_parse_paddle_vl_loc_blocks_treats_top_running_title_as_header():
    text = "\n".join(
        [
            "35<|LOC_865|><|LOC_48|><|LOC_886|><|LOC_48|><|LOC_886|><|LOC_59|><|LOC_865|><|LOC_59|>",
            "Mixing Bodily Fluids: Hobbes's Stoic God<|LOC_115|><|LOC_49|><|LOC_431|><|LOC_49|><|LOC_431|><|LOC_61|><|LOC_115|><|LOC_61|>",
        ]
    )

    blocks = parse_paddle_vl_loc_blocks(
        text,
        width=1000,
        height=2000,
        prompt_label="ocr",
        prompt="OCR:",
    )

    assert [block["label"] for block in blocks] == ["page_number", "page_header"]


def test_extract_paddle_pruned_blocks_normalizes_official_layout_labels_and_heading_attrs():
    blocks = extract_paddle_pruned_blocks(
        {
            "parsing_res_list": [
                {
                    "block_label": "DocTitle",
                    "block_content": "Mixing Bodily Fluids",
                    "block_bbox": [10, 20, 500, 60],
                    "block_order": 0,
                },
                {
                    "block_label": "Footer",
                    "block_content": "Springer",
                    "block_bbox": [800, 940, 900, 960],
                    "block_order": 1,
                },
            ]
        }
    )

    assert blocks[0]["label"] == "doc_title"
    assert blocks[0]["heading_level"] == 1
    assert blocks[0]["title_role"] == "doc_title"
    assert blocks[1]["label"] == "page_footer"


def test_layout_detection_loc_blocks_are_segmented_for_modern_print():
    text = "\n".join(
        [
            "39<|LOC_860|><|LOC_47|><|LOC_882|><|LOC_47|><|LOC_882|><|LOC_61|><|LOC_860|><|LOC_61|>",
            "Mixing Bodily Fluids: Hobbes's Stoic God<|LOC_118|><|LOC_49|><|LOC_431|><|LOC_49|><|LOC_431|><|LOC_62|><|LOC_118|><|LOC_62|>",
            "A first body line continues the argument.<|LOC_118|><|LOC_85|><|LOC_878|><|LOC_85|><|LOC_878|><|LOC_101|><|LOC_118|><|LOC_101|>",
            "A second body line belongs to the same paragraph.<|LOC_117|><|LOC_102|><|LOC_880|><|LOC_102|><|LOC_880|><|LOC_119|><|LOC_117|><|LOC_119|>",
            "Cosmology<|LOC_116|><|LOC_353|><|LOC_307|><|LOC_353|><|LOC_307|><|LOC_367|><|LOC_116|><|LOC_367|>",
            "\\(^{27}\\) First note line.<|LOC_116|><|LOC_582|><|LOC_529|><|LOC_582|><|LOC_529|><|LOC_595|><|LOC_116|><|LOC_595|>",
            "Continuation of the same note.<|LOC_115|><|LOC_597|><|LOC_889|><|LOC_597|><|LOC_889|><|LOC_610|><|LOC_115|><|LOC_610|>",
            "\\( ^{28} \\) Second note starts here.<|LOC_115|><|LOC_612|><|LOC_887|><|LOC_612|><|LOC_887|><|LOC_624|><|LOC_115|><|LOC_624|>",
            "Springer<|LOC_793|><|LOC_947|><|LOC_884|><|LOC_947|><|LOC_884|><|LOC_965|><|LOC_793|><|LOC_965|>",
        ]
    )

    lines = parse_paddle_vl_loc_blocks(
        text,
        width=1000,
        height=2000,
        prompt_label="layout_detection",
        prompt="Layout Detection:",
    )
    blocks = segment_paddle_vl_loc_blocks(lines)

    assert [block["label"] for block in blocks] == [
        "page_number",
        "page_header",
        "text",
        "section_header",
        "footnote",
        "footnote",
        "page_footer",
    ]
    assert blocks[2]["text"] == "A first body line continues the argument. A second body line belongs to the same paragraph."
    assert len(blocks[2]["lines"]) == 2
    assert "Continuation of the same note." in blocks[4]["text"]
    assert blocks[4]["attrs"]["original_marker"] == "\\(^{27}\\)"
    assert blocks[5]["text"].startswith("\\( ^{28} \\)")


def test_segmenter_demotes_first_page_metadata_but_keeps_article_title():
    text = "\n".join(
        [
            "53:33-49<|LOC_239|><|LOC_49|><|LOC_310|><|LOC_49|><|LOC_310|><|LOC_60|><|LOC_239|><|LOC_60|>",
            "DOI 10.1007/s11841-013-0377-x<|LOC_118|><|LOC_61|><|LOC_362|><|LOC_62|><|LOC_362|><|LOC_75|><|LOC_118|><|LOC_74|>",
            "Mixing Bodily Fluids: Hobbes's Stoic God<|LOC_120|><|LOC_137|><|LOC_645|><|LOC_137|><|LOC_645|><|LOC_153|><|LOC_120|><|LOC_153|>",
            "Geoffrey Gorham<|LOC_118|><|LOC_180|><|LOC_292|><|LOC_181|><|LOC_291|><|LOC_198|><|LOC_118|><|LOC_197|>",
            "Published online: 20 July 2013<|LOC_118|><|LOC_295|><|LOC_345|><|LOC_295|><|LOC_345|><|LOC_308|><|LOC_118|><|LOC_308|>",
            "Abstract The pantheon begins here.<|LOC_120|><|LOC_355|><|LOC_880|><|LOC_356|><|LOC_880|><|LOC_371|><|LOC_120|><|LOC_370|>",
        ]
    )

    lines = parse_paddle_vl_loc_blocks(
        text,
        width=1000,
        height=2000,
        prompt_label="layout_detection",
        prompt="Layout Detection:",
    )
    blocks = segment_paddle_vl_loc_blocks(lines)

    assert [block["label"] for block in blocks] == ["text", "section_header", "text", "text", "text"]
    assert "DOI 10.1007" in blocks[0]["text"]
    assert blocks[1]["text"] == "Mixing Bodily Fluids: Hobbes's Stoic God"
    assert blocks[1]["heading_level"] == 1
    assert blocks[2]["text"] == "Geoffrey Gorham"
    assert blocks[3]["text"] == "Published online: 20 July 2013"
