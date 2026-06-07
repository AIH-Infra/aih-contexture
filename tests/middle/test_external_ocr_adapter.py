import json

from click.testing import CliRunner

from aih_contexture.middle.adapters.external_ocr import merge_external_ocr_into_middle_document
from aih_contexture.scripts.import_external_ocr import import_external_ocr_cli


def _middle_payload():
    return {
        "schema_version": "contexture-middle-json/0.1",
        "source_name": "sample.pdf",
        "page_count": 1,
        "pages": [
            {
                "index": 0,
                "width": 100,
                "height": 100,
                "anchor_start": 0,
                "anchor_end": 1,
                "blocks": [
                    {
                        "id": "p0-b0",
                        "type": "Text",
                        "page_index": 0,
                        "order": 0,
                        "text": "",
                        "anchor_start": 0,
                        "anchor_end": 1,
                        "bbox": [0, 0, 80, 40],
                        "spans": [],
                        "children": [],
                        "attrs": {},
                        "provenance": [{"backend": "surya", "stage": "layout"}],
                    }
                ],
            }
        ],
        "backends": {"layout": "surya", "ocr": "none"},
    }


def test_merge_external_ocr_accepts_paddle_ocr_result_shape():
    data = merge_external_ocr_into_middle_document(
        _middle_payload(),
        {
            "res": {
                "page_index": 0,
                "rec_texts": ["Hello", "world"],
                "rec_boxes": [[2, 4, 20, 14], [25, 4, 50, 14]],
                "rec_scores": [0.98, 0.97],
            }
        },
        backend="paddle_ocr_v5",
        model="PP-OCRv5",
    )

    block = data["pages"][0]["blocks"][0]
    assert data["backends"]["ocr"] == "paddle_ocr_v5"
    assert data["metadata"]["ocr_import"]["imported_spans"] == 2
    assert block["text"] == "Hello world"
    assert [span["text"] for span in block["spans"]] == ["Hello", "world"]
    assert block["spans"][0]["provenance"][0]["model"] == "PP-OCRv5"


def test_merge_external_ocr_accepts_mineru_nested_span_shape():
    data = merge_external_ocr_into_middle_document(
        _middle_payload(),
        {
            "pdf_info": [
                {
                    "page_idx": 0,
                    "para_blocks": [
                        {
                            "type": "text",
                            "lines": [
                                {"spans": [{"content": "MinerU text", "bbox": [2, 4, 50, 14], "score": 0.91}]}
                            ],
                        }
                    ],
                }
            ]
        },
        backend="mineru_pytorch_paddle_ocr",
        model="mineru-ocr",
    )

    block = data["pages"][0]["blocks"][0]
    assert block["text"] == "MinerU text"
    assert block["spans"][0]["confidence"] == 0.91


def test_merge_external_ocr_can_append_unmatched_text_block():
    data = merge_external_ocr_into_middle_document(
        _middle_payload(),
        {"pages": [{"page_index": 0, "lines": [{"text": "outside", "bbox": [90, 90, 99, 99]}]}]},
        backend="external_ocr",
    )

    assert data["metadata"]["ocr_import"]["unmatched_items"] == 1
    assert len(data["pages"][0]["blocks"]) == 2
    assert data["pages"][0]["blocks"][1]["attrs"]["source"] == "external_ocr_unmatched"


def test_import_external_ocr_cli_writes_middle_json_and_report(tmp_path):
    middle_path = tmp_path / "middle.json"
    ocr_path = tmp_path / "ocr.json"
    output_path = tmp_path / "middle_with_ocr.json"
    report_path = tmp_path / "report.json"
    debug_path = tmp_path / "debug.md"
    middle_path.write_text(json.dumps(_middle_payload()), encoding="utf-8")
    ocr_path.write_text(
        json.dumps({"res": {"page_index": 0, "rec_texts": ["Hello"], "rec_boxes": [[2, 4, 20, 14]]}}),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        import_external_ocr_cli,
        [
            str(middle_path),
            str(ocr_path),
            "--backend",
            "paddle_ocr_v5",
            "--model",
            "PP-OCRv5",
            "--output",
            str(output_path),
            "--report",
            str(report_path),
            "--debug-markdown",
            str(debug_path),
            "--strict",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(output_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["pages"][0]["blocks"][0]["spans"][0]["text"] == "Hello"
    assert report["ocr_import"]["imported_spans"] == 1
    assert "### Text" in debug_path.read_text(encoding="utf-8")
