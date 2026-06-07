from aih_contexture.middle.adapters.ocr_direct import ocr_direct_outputs_to_middle_document
from aih_contexture.middle.scholarly_markdown import render_middle_scholarly_markdown
from aih_contexture.middle.validation import validate_middle_json


def test_ocr_direct_adapter_maps_chandra_official_chunks_to_middle():
    data = ocr_direct_outputs_to_middle_document(
        [
            {
                "page_num": 0,
                "img_size": [100, 200],
                "chunks": [
                    {"label": "Page-Header", "bbox": [0, 0, 100, 10], "content": "Header"},
                    {"label": "Section-Header", "bbox": [0, 20, 100, 40], "content": "<h1>Intro</h1>"},
                    {"label": "Text", "bbox": [0, 50, 100, 80], "content": "<p>Hello <b>world</b></p>"},
                    {"label": "Table", "bbox": [0, 90, 100, 120], "content": "<table><tr><td>A</td></tr></table>"},
                    {"label": "Image", "bbox": [0, 130, 100, 180], "content": "<img alt='Seal impression'/>"},
                ],
            }
        ],
        backend="chandra",
        model="chandra-2",
        source_name="sample.pdf",
        printed_pages=["7"],
    ).to_dict()

    page = data["pages"][0]
    blocks = page["blocks"]

    assert validate_middle_json(data).ok is True
    assert data["backends"] == {"vlm_specialized": "chandra", "vlm_specialized_model": "chandra-2"}
    assert page["printed_page"] == "7"
    assert [block["type"] for block in blocks] == ["PageHeader", "SectionHeader", "Text", "Table", "Picture"]
    assert blocks[2]["text"] == "Hello world"
    assert blocks[3]["text"] == "<table><tr><td>A</td></tr></table>"
    assert blocks[4]["text"] == "Seal impression"
    assert blocks[2]["attrs"]["official_protocol"] == "chandra_chunks"


def test_ocr_direct_adapter_maps_churro_official_xml_json_to_middle():
    data = ocr_direct_outputs_to_middle_document(
        [
            {
                "metadata": {},
                "content": [
                    {
                        "type": "page",
                        "page_number": "xii",
                        "elements": [
                            {"type": "heading", "text": "Chapter"},
                            {"type": "paragraph", "text": "Body text"},
                            {"type": "marginal_note", "placement": "left_margin", "text": "Side"},
                            {"type": "blockquote", "text": "Quoted"},
                        ],
                    }
                ],
            }
        ],
        backend="churro",
        model="churro-3b",
        source_name="sample.pdf",
    ).to_dict()

    page = data["pages"][0]
    blocks = page["blocks"]

    assert validate_middle_json(data).ok is True
    assert page["printed_page"] == "xii"
    assert [block["type"] for block in blocks] == ["SectionHeader", "Text", "MarginalNote", "Text"]
    assert blocks[2]["attrs"]["placement"] == "left_margin"
    assert blocks[3]["attrs"]["style"] == "blockquote"
    assert blocks[0]["provenance"][0]["stage"] == "official_xml_json"


def test_ocr_direct_adapter_maps_churro_page_furniture_and_bottom_notes():
    data = ocr_direct_outputs_to_middle_document(
        [
            {
                "metadata": {},
                "content": [
                    {
                        "type": "page",
                        "page_number": "35",
                        "elements": [
                            {"type": "page_number", "text": "35", "region": "header"},
                            {"type": "page_header", "text": "G. Gorham", "region": "header"},
                            {"type": "paragraph", "text": "Body text¹."},
                            {"type": "footnote", "placement": "bottom_margin", "text": "1 Footnote body."},
                            {"type": "page_footer", "text": "Springer", "region": "footer"},
                        ],
                    }
                ],
            }
        ],
        backend="churro",
        model="churro-3b",
        source_name="sample.pdf",
    ).to_dict()

    assert validate_middle_json(data).ok is True
    page = data["pages"][0]
    assert [block["type"] for block in page["blocks"]] == [
        "PageNumber",
        "PageHeader",
        "Text",
        "Footnote",
        "PageFooter",
    ]

    markdown = render_middle_scholarly_markdown(data)
    assert "<!-- Page: 35 -->" in markdown
    assert "<!-- PageHeader: G. Gorham -->" in markdown
    assert "<!-- PageFooter: Springer -->" in markdown
    assert "Body text<sup>1</sup>." in markdown
    assert "<sup>1</sup> Footnote body." in markdown


def test_ocr_direct_adapter_maps_paddleocr_vl_official_blocks_to_middle():
    data = ocr_direct_outputs_to_middle_document(
        [
            {
                "page_num": 0,
                "img_size": [100, 200],
                "backend": "paddleocr_vl",
                "official_protocol": "paddleocr_vl_prompt",
                "blocks": [
                    {
                        "label": "text",
                        "type": "text",
                        "text": "Body text",
                        "bbox": [0, 0, 100, 200],
                        "raw_query": "OCR:",
                    }
                ],
            }
        ],
        backend="paddleocr_vl",
        model="PaddleOCR-VL-1.5",
        source_name="sample.pdf",
    ).to_dict()

    assert validate_middle_json(data).ok is True
    assert data["backends"] == {"vlm_specialized": "paddleocr_vl", "vlm_specialized_model": "PaddleOCR-VL-1.5"}
    block = data["pages"][0]["blocks"][0]
    assert block["type"] == "Text"
    assert block["text"] == "Body text"
    assert block["attrs"]["official_protocol"] == "paddleocr_vl_prompt"
    assert block["attrs"]["raw_query"] == "OCR:"


def test_ocr_direct_adapter_recovers_paddleocr_vl_page_furniture_from_plain_ocr():
    data = ocr_direct_outputs_to_middle_document(
        [
            {
                "page_num": 7,
                "img_size": [879, 1333],
                "backend": "paddleocr_vl",
                "official_protocol": "paddleocr_vl_prompt",
                "blocks": [
                    {
                        "label": "text",
                        "type": "text",
                        "text": (
                            "40     G. Gorham\n\n"
                            "Body text with a note.<sup>35</sup>\n\n"
                            "³⁵ De Corpore note body.\n\n"
                            "⁴² Another note body.\n\n"
                            "⁴³ Springer"
                        ),
                        "bbox": [0, 0, 879, 1333],
                        "raw_prompt_label": "ocr",
                    }
                ],
            }
        ],
        backend="paddleocr_vl",
        model="PaddleOCR-VL-1.5",
        source_name="sample.pdf",
    ).to_dict()

    assert validate_middle_json(data).ok is True
    page = data["pages"][0]
    assert [block["type"] for block in page["blocks"]] == [
        "PageNumber",
        "PageHeader",
        "PageFooter",
        "Text",
        "Footnote",
        "Footnote",
    ]

    markdown = render_middle_scholarly_markdown(data)
    assert "<!-- Page: 40 -->" in markdown
    assert "<!-- PageHeader: G. Gorham -->" in markdown
    assert "<!-- PageFooter: Springer -->" in markdown
    assert "<sup>43</sup> Springer" not in markdown
    assert "<sup>35</sup> De Corpore note body." in markdown
    assert "<sup>42</sup> Another note body." in markdown


def test_ocr_direct_adapter_falls_back_to_specialized_vlm_markdown_when_blocks_missing():
    data = ocr_direct_outputs_to_middle_document(
        [
            {
                "page_num": 0,
                "img_size": [100, 200],
                "backend": "paddleocr_vl",
                "official_protocol": "paddleocr_vl_service",
                "markdown": {"text": "Official page markdown"},
                "blocks": [],
            }
        ],
        backend="paddleocr_vl",
        model="PaddleOCR-VL-1.5",
        source_name="sample.pdf",
    ).to_dict()

    assert validate_middle_json(data).ok is True
    block = data["pages"][0]["blocks"][0]
    assert block["type"] == "Text"
    assert block["text"] == "Official page markdown"
    assert block["attrs"]["raw"]["official_markdown_fallback"] is True


def test_ocr_direct_adapter_maps_paddleocr_vl_layout_parsing_result_to_middle():
    data = ocr_direct_outputs_to_middle_document(
        [
            {
                "page_num": 0,
                "img_size": [600, 800],
                "backend": "paddleocr_vl",
                "raw": {
                    "result": {
                        "layoutParsingResults": [
                            {
                                "prunedResult": {
                                    "parsing_res_list": [
                                        {
                                            "block_label": "table",
                                            "block_content": "<table><tr><td>A</td></tr></table>",
                                            "block_bbox": [10, 20, 300, 160],
                                            "score": 0.91,
                                            "block_order": 2,
                                        },
                                        {
                                            "block_label": "figure_caption",
                                            "block_content": "A caption",
                                            "block_bbox": [10, 170, 300, 200],
                                            "block_order": 3,
                                        },
                                    ]
                                },
                                "markdown": {"text": "official markdown", "images": {"img/a.jpg": "base64"}},
                                "outputImages": {"img/a.jpg": "base64"},
                            }
                        ]
                    }
                },
            }
        ],
        backend="paddleocr_vl",
        model="PaddleOCR-VL-1.5",
        source_name="sample.pdf",
    ).to_dict()

    assert validate_middle_json(data).ok is True
    page = data["pages"][0]
    blocks = page["blocks"]
    assert page["attrs"]["official_protocol"] == "paddleocr_vl_layout_parsing"
    assert "layoutParsingResult" in page["attrs"]["raw"]
    assert page["attrs"]["markdown_images"] == {"img/a.jpg": "base64"}
    assert page["attrs"]["output_images"] == {"img/a.jpg": "base64"}
    assert [block["type"] for block in blocks] == ["Table", "Caption"]
    assert [block["order"] for block in blocks] == [2, 3]
    assert blocks[0]["confidence"] == 0.91
    assert blocks[0]["bbox"] == [10.0, 20.0, 300.0, 160.0]
    assert blocks[0]["text"] == "<table><tr><td>A</td></tr></table>"
    assert blocks[0]["attrs"]["raw"]["block_source"] == "parsing_res_list"
    assert blocks[1]["text"] == "A caption"


def test_ocr_direct_adapter_preserves_paddleocr_vl_heading_levels_from_official_labels():
    data = ocr_direct_outputs_to_middle_document(
        [
            {
                "page_num": 0,
                "img_size": [600, 800],
                "backend": "paddleocr_vl",
                "raw": {
                    "result": {
                        "layoutParsingResults": [
                            {
                                "prunedResult": {
                                    "parsing_res_list": [
                                        {
                                            "block_label": "DocTitle",
                                            "block_content": "Mixing Bodily Fluids",
                                            "block_bbox": [60, 40, 420, 72],
                                            "block_order": 0,
                                        },
                                        {
                                            "block_label": "paragraph_title",
                                            "block_content": "Introduction",
                                            "block_bbox": [80, 120, 220, 145],
                                            "block_order": 1,
                                        },
                                    ]
                                }
                            }
                        ]
                    }
                },
            }
        ],
        backend="paddleocr_vl",
        model="PaddleOCR-VL-1.6",
        source_name="sample.pdf",
    ).to_dict()

    blocks = data["pages"][0]["blocks"]
    assert [block["type"] for block in blocks] == ["SectionHeader", "SectionHeader"]
    assert blocks[0]["attrs"]["heading_level"] == 1
    assert blocks[0]["attrs"]["title_role"] == "doc_title"
    assert blocks[1]["attrs"]["heading_level"] == 2

    markdown = render_middle_scholarly_markdown(data)
    assert "# Mixing Bodily Fluids" in markdown
    assert "## Introduction" in markdown


def test_ocr_direct_adapter_maps_mineru_vl_page_blocks_to_middle():
    data = ocr_direct_outputs_to_middle_document(
        [
            {
                "page_num": 0,
                "img_size": [100, 200],
                "backend": "mineru_vl",
                "official_protocol": "mineru_vl_official",
                "blocks": [
                    {
                        "label": "title",
                        "type": "section_header",
                        "text": "Chapter",
                        "bbox": [0, 0, 100, 20],
                        "normalized_bbox": [0, 0, 1, 0.1],
                        "raw_prompt": "\nText Recognition:",
                    },
                    {
                        "label": "table",
                        "type": "table",
                        "text": "<table><tr><td>A</td></tr></table>",
                        "bbox": [0, 50, 100, 150],
                    },
                ],
            }
        ],
        backend="mineru_vl",
        model="MinerU2.5-Pro-2604-1.2B",
        source_name="sample.pdf",
    ).to_dict()

    assert validate_middle_json(data).ok is True
    blocks = data["pages"][0]["blocks"]
    assert [block["type"] for block in blocks] == ["SectionHeader", "Table"]
    assert blocks[0]["attrs"]["normalized_bbox"] == [0, 0, 1, 0.1]
    assert blocks[1]["text"] == "<table><tr><td>A</td></tr></table>"


def test_ocr_direct_adapter_maps_mineru_bottom_ref_text_to_footnote():
    data = ocr_direct_outputs_to_middle_document(
        [
            {
                "page_num": 0,
                "img_size": [100, 200],
                "backend": "mineru_vl",
                "official_protocol": "mineru_vl_official",
                "blocks": [
                    {
                        "label": "ref_text",
                        "type": "text",
                        "text": "\\( ^{35} \\) De Corpore 4.26.1.",
                        "bbox": [0, 150, 100, 170],
                    }
                ],
            }
        ],
        backend="mineru_vl",
        model="MinerU2.5-Pro-2605",
        source_name="sample.pdf",
    ).to_dict()

    block = data["pages"][0]["blocks"][0]
    assert block["type"] == "Footnote"
    assert block["attrs"]["raw_label"] == "ref_text"


def test_ocr_direct_adapter_promotes_official_page_number_to_printed_page():
    data = ocr_direct_outputs_to_middle_document(
        [
            {
                "page_num": 0,
                "img_size": [100, 200],
                "backend": "mineru_vl",
                "official_protocol": "mineru_vl_official",
                "blocks": [
                    {
                        "label": "page_number",
                        "type": "page_number",
                        "text": "35",
                        "bbox": [85, 5, 95, 12],
                    },
                    {
                        "label": "text",
                        "type": "text",
                        "text": "Body",
                        "bbox": [0, 30, 100, 80],
                    },
                ],
            }
        ],
        backend="mineru_vl",
        model="MinerU2.5-Pro-2605",
        source_name="sample.pdf",
    ).to_dict()

    assert data["pages"][0]["printed_page"] == "35"
    assert data["pages"][0]["blocks"][0]["type"] == "PageNumber"


def test_ocr_direct_adapter_promotes_page_number_when_printed_page_input_is_blank():
    data = ocr_direct_outputs_to_middle_document(
        [
            {
                "page_num": 0,
                "img_size": [100, 200],
                "backend": "mineru_vl",
                "official_protocol": "mineru_vl_official",
                "blocks": [
                    {
                        "label": "page_number",
                        "type": "page_number",
                        "text": "35",
                        "bbox": [85, 5, 95, 12],
                    }
                ],
            }
        ],
        backend="mineru_vl",
        model="MinerU2.5-Pro-2605",
        source_name="sample.pdf",
        printed_pages=[""],
    ).to_dict()

    assert data["pages"][0]["printed_page"] == "35"


def test_ocr_direct_adapter_maps_mineru_vl_document_page_text_to_text_block():
    data = ocr_direct_outputs_to_middle_document(
        [
            {
                "page_num": 0,
                "img_size": [879, 1333],
                "backend": "mineru_vl",
                "official_protocol": "mineru_vl_official",
                "blocks": [
                    {
                        "type": "text",
                        "label": "document",
                        "text": "SOPHIA\n\nMixing Bodily Fluids",
                        "bbox": [0, 0, 879, 1333],
                        "raw_prompt_label": "document",
                        "raw_query": "\nText Recognition:",
                    }
                ],
            }
        ],
        backend="mineru_vl",
        model="MinerU2.5-Pro-2604-1.2B",
        source_name="sample.pdf",
    ).to_dict()

    assert validate_middle_json(data).ok is True
    block = data["pages"][0]["blocks"][0]
    assert block["type"] == "Text"
    assert block["text"] == "SOPHIA\n\nMixing Bodily Fluids"
    assert block["attrs"]["raw_label"] == "text"
    assert block["attrs"]["raw"]["label"] == "document"
    assert block["attrs"]["raw_prompt_label"] == "document"


def test_ocr_direct_adapter_maps_mineru_middle_json_pdf_info_to_middle():
    data = ocr_direct_outputs_to_middle_document(
        [
            {
                "backend": "mineru_vl",
                "pdf_info": [
                    {
                        "page_idx": 0,
                        "page_size": [600, 800],
                        "para_blocks": [
                            {
                                "type": "title",
                                "bbox": [10, 20, 500, 60],
                                "lines": [
                                    {
                                        "spans": [
                                            {
                                                "type": "text",
                                                "content": "Chapter",
                                                "bbox": [10, 20, 500, 60],
                                                "score": 0.98,
                                            }
                                        ]
                                    }
                                ],
                                "raw_response": {"kept": True},
                            },
                            {
                                "type": "interline_equation",
                                "bbox": [10, 80, 300, 120],
                                "lines": [{"spans": [{"type": "equation", "content": "E=mc^2"}]}],
                            },
                        ],
                        "discarded_blocks": [
                            {
                                "type": "page_number",
                                "text": "12",
                                "bbox": [280, 760, 320, 790],
                            }
                        ],
                    }
                ],
            }
        ],
        backend="mineru_vl",
        model="MinerU2.5-Pro-2604-1.2B",
        source_name="sample.pdf",
    ).to_dict()

    assert validate_middle_json(data).ok is True
    page = data["pages"][0]
    blocks = page["blocks"]
    assert page["attrs"]["official_protocol"] == "mineru_middle_json"
    assert "page_info" in page["attrs"]["raw"]
    assert [block["type"] for block in blocks] == ["SectionHeader", "Equation", "PageNumber"]
    assert blocks[0]["text"] == "Chapter"
    assert blocks[0]["spans"][0]["confidence"] == 0.98
    assert blocks[0]["attrs"]["raw"]["raw_response"] == {"kept": True}
    assert blocks[2]["attrs"]["raw"]["block_source"] == "discarded_blocks"


def test_ocr_direct_adapter_preserves_mineru_visual_children_and_aggregates_text():
    data = ocr_direct_outputs_to_middle_document(
        [
            {
                "backend": "mineru_vl",
                "pdf_info": [
                    {
                        "page_idx": 0,
                        "page_size": [600, 800],
                        "para_blocks": [
                            {
                                "type": "table",
                                "bbox": [10, 20, 500, 260],
                                "blocks": [
                                    {
                                        "type": "table_caption",
                                        "index": 1,
                                        "lines": [{"spans": [{"type": "text", "content": "Table 1. Results"}]}],
                                    },
                                    {
                                        "type": "table_body",
                                        "index": 2,
                                        "lines": [{"spans": [{"type": "table", "html": "<table><tr><td>A</td></tr></table>"}]}],
                                    },
                                    {
                                        "type": "table_footnote",
                                        "index": 3,
                                        "lines": [{"spans": [{"type": "text", "content": "Source: archive"}]}],
                                    },
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
        backend="mineru_vl",
        model="MinerU2.5-Pro-2604-1.2B",
        source_name="sample.pdf",
    ).to_dict()

    assert validate_middle_json(data).ok is True
    block = data["pages"][0]["blocks"][0]
    assert block["type"] == "Table"
    assert block["text"] == "Table 1. Results\n<table><tr><td>A</td></tr></table>\nSource: archive"
    assert [child["type"] for child in block["children"]] == ["Caption", "Table", "Footnote"]
    assert block["children"][1]["text"] == "<table><tr><td>A</td></tr></table>"


def test_ocr_direct_adapter_promotes_edge_numeric_text_to_page_number():
    data = ocr_direct_outputs_to_middle_document(
        [
            {
                "page_num": 7,
                "img_size": [600, 800],
                "backend": "mineru_vl",
                "official_protocol": "mineru_vl_official",
                "blocks": [
                    {
                        "label": "text",
                        "text": "35",
                        "bbox": [290, 20, 310, 40],
                        "order": 0,
                    },
                    {
                        "label": "text",
                        "text": "Body text",
                        "bbox": [80, 160, 520, 220],
                        "order": 1,
                    },
                ],
            }
        ],
        backend="mineru_vl",
        model="MinerU2.5-Pro-2604-1.2B",
        source_name="sample.pdf",
    ).to_dict()

    assert validate_middle_json(data).ok is True
    page = data["pages"][0]
    assert page["printed_page"] == "35"
    assert [block["type"] for block in page["blocks"]] == ["PageNumber", "Text"]
    assert page["blocks"][0]["attrs"]["inferred_type"] == "PageNumber"
