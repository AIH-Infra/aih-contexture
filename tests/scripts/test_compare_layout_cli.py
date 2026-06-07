import json

from click.testing import CliRunner

from aih_contexture.scripts.compare_layout import compare_layout_cli


def test_compare_layout_cli_writes_json_and_markdown(tmp_path):
    report_path = tmp_path / "eval.json"
    output_json = tmp_path / "compare.json"
    output_md = tmp_path / "compare.md"
    middle_path = tmp_path / "sample_middle.json"
    middle_path.write_text(
        json.dumps(
            {
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
                                "type": "ComplexRegion",
                                "page_index": 0,
                                "order": 0,
                                "text": "",
                                "anchor_start": 0,
                                "anchor_end": 1,
                                "bbox": [5, 5, 12, 12],
                                "spans": [],
                                "children": [],
                                "attrs": {},
                                "provenance": [{"backend": "paddle", "stage": "layout"}],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(
            {
                "ok": True,
                "results": [
                    {
                        "source_path": str(middle_path),
                        "ok": True,
                        "validation_ok": True,
                        "summary": {"page_count": 1, "block_count": 1, "block_types": {"Text": 1}},
                        "metrics": {
                            "page_count": 1,
                            "block_count": 1,
                            "block_types": {"Text": 1},
                            "blocks_missing_bbox": 0,
                            "blocks_missing_provenance": 0,
                            "empty_complex_regions": 1,
                            "small_empty_complex_regions": 1,
                            "span_count": 1,
                            "blocks_with_spans": 1,
                            "spans_missing_bbox": 0,
                            "spans_missing_provenance": 0,
                            "span_provenance_completeness": 1.0,
                        },
                        "case": {"id": "case-1", "backend": "surya"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        compare_layout_cli,
        [
            str(report_path),
            "--output-json",
            str(output_json),
            "--output-markdown",
            str(output_md),
            "--review-crop-dir",
            str(tmp_path / "review"),
        ],
    )

    assert result.exit_code == 0
    assert json.loads(output_json.read_text(encoding="utf-8"))["case_count"] == 1
    assert "# Contexture Layout Comparison" in output_md.read_text(encoding="utf-8")
    assert (tmp_path / "review" / "layout_review_crops.json").exists()
