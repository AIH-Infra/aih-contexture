import json

from click.testing import CliRunner

from aih_contexture.middle.adapters.external_document import external_document_to_middle_document
from aih_contexture.scripts.import_external_document import import_external_document_cli


def test_external_document_adapter_accepts_mineru_layout_and_nested_ocr():
    data = external_document_to_middle_document(
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
                                {"spans": [{"content": "Chapter One", "bbox": [12, 24, 300, 54], "score": 0.91}]}
                            ],
                        },
                        {
                            "type": "page_footnote",
                            "bbox": [10, 1000, 700, 1080],
                            "lines": [
                                {"spans": [{"content": "1. Archive note", "bbox": [12, 1010, 240, 1040]}]}
                            ],
                        },
                    ],
                }
            ]
        },
        layout_backend="mineru_pp_doclayout_v2",
        layout_model="PP-DocLayoutV2",
        ocr_backend="mineru_pytorch_paddle_ocr",
        ocr_model="mineru-ocr",
        source_name="sample.pdf",
        block_source="para_blocks",
    )

    page = data["pages"][0]

    assert data["metadata"]["import_source"] == "external_document_json"
    assert data["metadata"]["document_import"]["layout_backend"] == "mineru_pp_doclayout_v2"
    assert data["metadata"]["ocr_import"]["imported_spans"] == 2
    assert data["backends"]["layout"] == "mineru_pp_doclayout_v2"
    assert data["backends"]["ocr"] == "mineru_pytorch_paddle_ocr"
    assert [block["type"] for block in page["blocks"]] == ["SectionHeader", "Footnote"]
    assert page["blocks"][0]["spans"][0]["text"] == "Chapter One"
    assert page["blocks"][1]["spans"][0]["text"] == "1. Archive note"


def test_external_document_adapter_accepts_paddle_layout_and_ocr_result_shape():
    data = external_document_to_middle_document(
        {
            "res": {
                "page_index": 0,
                "page_size": [100, 100],
                "boxes": [
                    {"label": "text", "coordinate": [0, 0, 80, 40], "score": 0.92},
                    {"label": "figure", "coordinate": [0, 50, 80, 90], "score": 0.88},
                ],
                "rec_texts": ["Hello", "world"],
                "rec_boxes": [[2, 4, 20, 14], [25, 4, 50, 14]],
                "rec_scores": [0.98, 0.97],
            }
        },
        layout_backend="paddle_pp_doclayout_v3",
        layout_model="PP-DocLayoutV3",
        ocr_backend="paddle_ocr_v5",
        ocr_model="PP-OCRv5",
    )

    text_block = data["pages"][0]["blocks"][0]

    assert [block["type"] for block in data["pages"][0]["blocks"]] == ["Text", "Figure"]
    assert text_block["text"] == "Hello world"
    assert [span["text"] for span in text_block["spans"]] == ["Hello", "world"]
    assert data["metadata"]["ocr_import"]["unmatched_items"] == 0


def test_external_document_adapter_accepts_pp_structure_v3_result_shape():
    data = external_document_to_middle_document(
        {
            "res": {
                "input_path": "sample.pdf",
                "page_index": 0,
                "page_count": 1,
                "width": 100,
                "height": 120,
                "parsing_res_list": [
                    {
                        "block_label": "text",
                        "block_bbox": [0, 0, 80, 40],
                        "block_content": "PP structure text",
                        "block_order": 0,
                    },
                    {
                        "block_label": "table",
                        "block_bbox": [0, 50, 80, 100],
                        "block_content": "<table><tr><td>A</td></tr></table>",
                        "block_order": 1,
                    },
                ],
                "overall_ocr_res": {
                    "rec_texts": ["PP structure text"],
                    "rec_boxes": [[2, 4, 70, 18]],
                    "rec_scores": [0.93],
                },
            }
        },
        layout_backend="paddle_pp_structure_v3",
        layout_model="PP-StructureV3",
        ocr_backend="paddle_ocr_v5",
        ocr_model="PP-OCRv5",
        block_source="parsing_res_list",
    )

    page = data["pages"][0]

    assert [block["type"] for block in page["blocks"]] == ["Text", "Table"]
    assert page["blocks"][0]["text"] == "PP structure text"
    assert page["blocks"][0]["spans"][0]["text"] == "PP structure text"
    assert data["metadata"]["ocr_import"]["imported_spans"] == 1


def test_import_external_document_cli_writes_middle_report_and_debug_preview(tmp_path):
    input_path = tmp_path / "mineru_middle.json"
    output_path = tmp_path / "contexture_middle.json"
    report_path = tmp_path / "contexture_middle_report.json"
    debug_path = tmp_path / "contexture_middle_debug.md"
    scholarly_path = tmp_path / "contexture.md"
    input_path.write_text(
        json.dumps(
            {
                "pdf_info": [
                    {
                        "page_idx": 0,
                        "page_size": [100, 200],
                        "para_blocks": [
                            {
                                "type": "text",
                                "bbox": [0, 0, 80, 40],
                                "lines": [{"spans": [{"content": "hello", "bbox": [2, 4, 20, 14]}]}],
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        import_external_document_cli,
        [
            str(input_path),
            "--layout-backend",
            "mineru_pp_doclayout_v2",
            "--layout-model",
            "PP-DocLayoutV2",
            "--ocr-backend",
            "mineru_pytorch_paddle_ocr",
            "--ocr-model",
            "mineru-ocr",
            "--output",
            str(output_path),
            "--report",
            str(report_path),
            "--debug-markdown",
            str(debug_path),
            "--scholarly-markdown",
            str(scholarly_path),
            "--block-source",
            "para_blocks",
            "--strict",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(output_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    debug_text = debug_path.read_text(encoding="utf-8")
    scholarly_text = scholarly_path.read_text(encoding="utf-8")
    assert data["pages"][0]["blocks"][0]["spans"][0]["text"] == "hello"
    assert report["ok"] is True
    assert report["ocr_import"]["imported_spans"] == 1
    assert "### Text" in debug_text
    assert "hello" in scholarly_text
