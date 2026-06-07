import json

from click.testing import CliRunner

from aih_contexture.middle.adapters import (
    external_layout_document_to_middle_document,
    external_layout_page_to_middle_page,
)
from aih_contexture.builders.external_layout_sidecar import _layout_label
from aih_contexture.scripts.import_external_layout import import_external_layout_cli


def test_external_layout_adapter_accepts_mineru_style_layout_blocks():
    page = external_layout_page_to_middle_page(
        {
            "page_idx": 5,
            "page_bbox": [0, 0, 1000, 1500],
            "layout_bboxes": [
                {
                    "layout_label": "aside_text",
                    "layout_bbox": [10, 200, 120, 500],
                    "score": 0.86,
                    "text": "side note",
                },
                {
                    "layout_label": "page_footnote",
                    "layout_bbox": [100, 1300, 900, 1450],
                    "score": 0.91,
                },
            ],
        },
        backend="mineru_pp_doclayout_v2",
        model="PP-DocLayoutV2",
    )

    assert page.index == 5
    assert page.width == 1000
    assert page.height == 1500
    assert [block.type for block in page.blocks] == ["MarginalNote", "Footnote"]
    assert page.blocks[0].text == "side note"
    assert page.blocks[0].confidence == 0.86
    assert page.blocks[0].provenance[0].backend == "mineru_pp_doclayout_v2"


def test_external_layout_adapter_accepts_polygon_only_blocks():
    page = external_layout_page_to_middle_page(
        {
            "page_index": 0,
            "width": 100,
            "height": 200,
            "blocks": [
                {
                    "type": "vertical_text",
                    "points": [[10, 10], [20, 10], [20, 100], [10, 100]],
                }
            ],
        },
        backend="paddle_pp_doclayout_v3",
    )

    block = page.blocks[0]
    assert block.type == "Text"
    assert block.attrs["orientation"] == "vertical"
    assert block.bbox == [10.0, 10.0, 20.0, 100.0]


def test_external_layout_document_adapter_accepts_mineru_middle_json_shape():
    doc = external_layout_document_to_middle_document(
        {
            "pdf_info": [
                {
                    "page_idx": 0,
                    "page_size": [800, 1200],
                    "para_blocks": [
                        {
                            "type": "title",
                            "bbox": [10, 20, 700, 80],
                            "lines": [
                                {"spans": [{"content": "Chapter One"}]},
                            ],
                        },
                        {
                            "type": "ref_text",
                            "bbox": [10, 900, 700, 980],
                            "text": "Reference item",
                        },
                    ],
                }
            ],
            "_backend": "pipeline",
        },
        backend="mineru_pp_doclayout_v2",
        model="PP-DocLayoutV2",
        source_name="sample.pdf",
        block_source="para_blocks",
    )

    data = doc.to_dict()

    assert data["source_name"] == "sample.pdf"
    assert data["page_count"] == 1
    assert data["pages"][0]["width"] == 800
    assert data["pages"][0]["height"] == 1200
    assert [block["type"] for block in data["pages"][0]["blocks"]] == ["SectionHeader", "Reference"]
    assert data["pages"][0]["blocks"][0]["text"] == "Chapter One"


def test_external_layout_document_adapter_can_select_block_source():
    doc = external_layout_document_to_middle_document(
        {
            "pdf_info": [
                {
                    "page_idx": 0,
                    "page_size": [800, 1200],
                    "para_blocks": [{"type": "text", "bbox": [0, 0, 10, 10], "text": "para"}],
                    "preproc_blocks": [{"type": "title", "bbox": [0, 20, 10, 30], "text": "preproc"}],
                }
            ],
        },
        backend="mineru_pp_doclayout_v2",
        block_source="preproc_blocks",
    )

    data = doc.to_dict()

    assert data["metadata"]["block_source"] == "preproc_blocks"
    assert len(data["pages"][0]["blocks"]) == 1
    assert data["pages"][0]["blocks"][0]["type"] == "SectionHeader"
    assert data["pages"][0]["blocks"][0]["text"] == "preproc"


def test_external_layout_document_adapter_can_merge_all_block_sources():
    doc = external_layout_document_to_middle_document(
        {
            "pdf_info": [
                {
                    "page_idx": 0,
                    "blocks": [{"type": "text", "bbox": [0, 0, 10, 10], "text": "block"}],
                    "para_blocks": [{"type": "ref_text", "bbox": [0, 20, 10, 30], "text": "ref"}],
                }
            ],
        },
        backend="generic_layout",
        block_source="all",
    )

    blocks = doc.to_dict()["pages"][0]["blocks"]

    assert [block["type"] for block in blocks] == ["Text", "Reference"]
    assert blocks[0]["attrs"]["raw"]["block_source"] == "blocks"
    assert blocks[1]["attrs"]["raw"]["block_source"] == "para_blocks"


def test_sidecar_layout_label_maps_reference_to_constructible_text_block():
    assert _layout_label("Reference") == "Text"


def test_external_layout_document_adapter_accepts_paddle_layout_detection_result():
    doc = external_layout_document_to_middle_document(
        {
            "res": {
                "input_path": "layout.jpg",
                "page_index": None,
                "boxes": [
                    {
                        "label": "paragraph_title",
                        "score": 0.9,
                        "coordinate": [10, 20, 300, 60],
                    },
                    {
                        "label": "figure_title",
                        "score": 0.8,
                        "coordinate": [10, 400, 300, 430],
                    },
                ],
            }
        },
        backend="paddle_pp_doclayout_plus_l",
        model="PP-DocLayout_plus-L",
    )

    data = doc.to_dict()

    assert data["pages"][0]["index"] == 0
    assert [block["type"] for block in data["pages"][0]["blocks"]] == ["SectionHeader", "Caption"]
    assert data["pages"][0]["blocks"][0]["confidence"] == 0.9
    assert data["pages"][0]["blocks"][0]["bbox"] == [10.0, 20.0, 300.0, 60.0]


def test_external_layout_adapter_falls_back_when_order_is_none():
    page = external_layout_page_to_middle_page(
        {
            "page_index": 0,
            "boxes": [
                {"label": "text", "coordinate": [0, 0, 10, 10], "order": None},
                {"label": "text", "coordinate": [0, 20, 10, 30], "position": None},
            ],
        },
        backend="paddle_pp_doclayout_v3",
    )

    assert [block.order for block in page.blocks] == [0, 1]


def test_import_external_layout_cli_writes_middle_json_and_report(tmp_path):
    input_path = tmp_path / "mineru_middle.json"
    output_path = tmp_path / "contexture_middle.json"
    report_path = tmp_path / "contexture_middle_report.json"
    debug_path = tmp_path / "contexture_middle_debug.md"
    input_path.write_text(
        json.dumps(
            {
                "pdf_info": [
                    {
                        "page_idx": 0,
                        "page_size": [100, 200],
                        "para_blocks": [{"type": "text", "bbox": [0, 0, 10, 20], "text": "hello"}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        import_external_layout_cli,
        [
            str(input_path),
            "--backend",
            "mineru_pp_doclayout_v2",
            "--model",
            "PP-DocLayoutV2",
            "--output",
            str(output_path),
            "--report",
            str(report_path),
            "--debug-markdown",
            str(debug_path),
            "--block-source",
            "para_blocks",
        ],
    )

    assert result.exit_code == 0
    assert output_path.exists()
    assert report_path.exists()
    assert debug_path.exists()
    output_data = json.loads(output_path.read_text(encoding="utf-8"))
    report_data = json.loads(report_path.read_text(encoding="utf-8"))
    debug_text = debug_path.read_text(encoding="utf-8")
    assert output_data["pages"][0]["blocks"][0]["type"] == "Text"
    assert output_data["metadata"]["block_source"] == "para_blocks"
    assert report_data["ok"] is True
    assert "### Text" in debug_text
