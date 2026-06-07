import json

from aih_contexture.evaluation.layout_compare import (
    compare_layout_eval_reports,
    render_layout_comparison_markdown,
    write_layout_comparison_review_crops,
)


def _write_report(
    path,
    backend="surya",
    case_id="case-1",
    source_pdf="sample.pdf",
    page_range=None,
    empty_complex_regions=0,
    small_empty_complex_regions=0,
    source_path=None,
):
    path.write_text(
        json.dumps(
            {
                "ok": True,
                "case_count": 1,
                "results": [
                    {
                        "source_path": source_path,
                        "ok": True,
                        "validation_ok": True,
                        "warnings": [],
                        "errors": [],
                        "summary": {
                            "page_count": 1,
                            "block_count": 2,
                            "block_types": {"Text": 2},
                            "backends": {"layout": backend},
                        },
                        "metrics": {
                            "page_count": 1,
                            "block_count": 2,
                            "block_types": {"Text": 2},
                            "blocks_missing_bbox": 0,
                            "blocks_missing_provenance": 0,
                            "unmapped_complex_regions": 0,
                            "empty_complex_regions": empty_complex_regions,
                            "small_empty_complex_regions": small_empty_complex_regions,
                            "span_count": 3,
                            "blocks_with_spans": 2,
                            "spans_missing_bbox": 1,
                            "spans_missing_provenance": 0,
                            "span_provenance_completeness": 1.0,
                        },
                        "case": {
                            "id": case_id,
                            "backend": backend,
                            "source_pdf": source_pdf,
                            "page_range": [0] if page_range is None else page_range,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_compare_layout_eval_reports_flattens_rows(tmp_path):
    report_path = tmp_path / "surya_eval.json"
    _write_report(report_path)

    payload = compare_layout_eval_reports([report_path])

    assert payload["ok"] is True
    assert payload["case_count"] == 1
    assert payload["group_count"] == 1
    assert payload["rows"][0]["backend"] == "surya"
    assert payload["rows"][0]["source_name"] == "sample.pdf"
    assert payload["rows"][0]["page_range"] == [0]
    assert payload["rows"][0]["block_types"] == {"Text": 2}
    assert payload["rows"][0]["small_empty_complex_regions"] == 0
    assert payload["rows"][0]["span_count"] == 3
    assert payload["rows"][0]["span_provenance_completeness"] == 1.0
    assert payload["quality_summary"]["by_backend"][0]["backend"] == "surya"
    assert payload["quality_summary"]["by_backend"][0]["case_count"] == 1


def test_render_layout_comparison_markdown_contains_summary_table(tmp_path):
    report_path = tmp_path / "surya_eval.json"
    _write_report(report_path)
    payload = compare_layout_eval_reports([report_path])

    markdown = render_layout_comparison_markdown(payload)

    assert "# Contexture Layout Comparison" in markdown
    assert "## Quality Summary" in markdown
    assert "| surya | case-1 | yes | 1 | 2 | 3 | 2 | 0 | 1 | 0 | 0 | 1.00 | Text:2 |" in markdown


def test_render_layout_comparison_markdown_groups_same_source_and_pages(tmp_path):
    report_a = tmp_path / "a_eval.json"
    report_b = tmp_path / "b_eval.json"
    _write_report(report_a, backend="surya", case_id="surya-sample", source_pdf="sample.pdf", page_range=[0])
    _write_report(report_b, backend="paddle_pp_doclayout_v3", case_id="paddle-sample", source_pdf="sample.pdf", page_range=[0])
    payload = compare_layout_eval_reports([report_a, report_b])

    markdown = render_layout_comparison_markdown(payload)

    assert payload["group_count"] == 1
    assert len(payload["groups"][0]["rows"]) == 2
    assert "## Grouped By Source/Page" in markdown
    assert "### sample.pdf pages 0" in markdown
    assert "| paddle_pp_doclayout_v3 | paddle-sample | yes | 2 | 3 | 1 | 0 |  | Text:2 |" in markdown


def test_quality_summary_lists_review_items(tmp_path):
    report_path = tmp_path / "eval.json"
    _write_report(
        report_path,
        backend="paddle_pp_doclayout_v3",
        case_id="paddle-sample",
        empty_complex_regions=1,
        small_empty_complex_regions=1,
    )
    payload = compare_layout_eval_reports([report_path])
    markdown = render_layout_comparison_markdown(payload)

    backend_summary = payload["quality_summary"]["by_backend"][0]
    assert backend_summary["review_flag_count"] == 1
    assert backend_summary["small_empty_complex_regions"] == 1
    assert payload["quality_summary"]["review_items"][0]["flags"] == "empty_complex:1, small_empty_complex:1"
    assert "### Review Items" in markdown
    assert "| paddle_pp_doclayout_v3 | paddle-sample | sample.pdf | 0 | empty_complex:1, small_empty_complex:1 |" in markdown


def test_write_layout_comparison_review_crops_uses_flagged_middle_json(tmp_path):
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
    report_path = tmp_path / "eval.json"
    _write_report(
        report_path,
        backend="paddle_pp_doclayout_v3",
        case_id="paddle-sample",
        empty_complex_regions=1,
        small_empty_complex_regions=1,
        source_path=str(middle_path),
    )
    payload = compare_layout_eval_reports([report_path])

    report = write_layout_comparison_review_crops(payload, tmp_path / "review")

    assert report["ok"] is True
    assert report["case_count"] == 1
    assert report["crop_count"] == 1
    assert (tmp_path / "review" / "layout_review_crops.json").exists()
    assert (tmp_path / "review" / "paddle_pp_doclayout_v3" / "paddle-sample" / "review_crops.json").exists()
