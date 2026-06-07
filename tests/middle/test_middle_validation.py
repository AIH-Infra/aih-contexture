from click.testing import CliRunner

from aih_contexture.middle.schema import MiddleBlock, MiddleDocument, MiddlePage, MiddleProvenance, MiddleSpan
from aih_contexture.middle.validation import summarize_middle_json, validate_middle_json
from aih_contexture.scripts.middle import middle_cli


def test_validate_middle_json_accepts_valid_interval_anchors():
    data = MiddleDocument(
        source_name="sample.pdf",
        pages=[
            MiddlePage(
                index=0,
                blocks=[
                    MiddleBlock(
                        id="p0-b0",
                        type="Text",
                        page_index=0,
                        order=0,
                        bbox=[0, 0, 10, 20],
                        polygon=[[0, 0], [10, 0], [10, 20], [0, 20]],
                        provenance=[MiddleProvenance(backend="surya", stage="layout")],
                    )
                ],
            )
        ],
    ).to_dict()

    report = validate_middle_json(data)

    assert report.ok is True
    assert report.summary["page_count"] == 1
    assert report.summary["block_types"] == {"Text": 1}


def test_validate_middle_json_rejects_bad_anchor_and_unknown_type():
    data = MiddleDocument(
        pages=[
            MiddlePage(
                index=2,
                blocks=[
                    MiddleBlock(
                        id="bad",
                        type="VendorRawType",
                        page_index=2,
                        order=0,
                    )
                ],
            )
        ],
    ).to_dict()
    data["pages"][0]["anchor_end"] = 2

    report = validate_middle_json(data)

    assert report.ok is False
    assert any("anchor_end" in issue.path for issue in report.errors)
    assert any("unknown canonical block type" in issue.message for issue in report.errors)


def test_summarize_middle_json_counts_pages_and_blocks():
    data = {
        "schema_version": "contexture-middle-json/0.1",
        "source_name": "sample.pdf",
        "backends": {"layout": "surya"},
        "pages": [
            {"index": 0, "blocks": [{"type": "Text", "spans": [{"text": "hello"}]}, {"type": "Footnote"}]},
            {"index": 1, "blocks": []},
        ],
    }

    summary = summarize_middle_json(data)

    assert summary["page_count"] == 2
    assert summary["pages_with_blocks"] == 1
    assert summary["block_count"] == 2
    assert summary["blocks_with_spans"] == 1
    assert summary["span_count"] == 1
    assert summary["block_types"] == {"Footnote": 1, "Text": 1}


def test_validate_middle_json_reports_traceability_and_geometry_warnings():
    data = MiddleDocument(
        pages=[
            MiddlePage(
                index=0,
                width=100,
                height=200,
                blocks=[
                    MiddleBlock(
                        id="dup",
                        type="Text",
                        page_index=0,
                        order=1,
                        bbox=[0, 0, 0, 10],
                        confidence=1.2,
                        provenance=[],
                    ),
                    MiddleBlock(
                        id="dup",
                        type="Footnote",
                        page_index=0,
                        order=1,
                        bbox=[-1, 10, 120, 220],
                        provenance=[MiddleProvenance(backend="", stage="", confidence=-0.5)],
                    ),
                ],
            )
        ],
    ).to_dict()

    report = validate_middle_json(data)

    assert report.ok is False
    assert any("duplicate block id" in issue.message for issue in report.errors)
    assert any("duplicate order" in issue.message for issue in report.warnings)
    assert any("zero width or height" in issue.message for issue in report.warnings)
    assert any("outside page width" in issue.message for issue in report.warnings)
    assert any("outside page height" in issue.message for issue in report.warnings)
    assert any("backend" in issue.path for issue in report.warnings)
    assert any("stage" in issue.path for issue in report.warnings)
    assert any("[0, 1]" in issue.message for issue in report.warnings)


def test_validate_middle_json_rejects_invalid_page_dimension_and_provenance_shape():
    data = {
        "schema_version": "contexture-middle-json/0.1",
        "pages": [
            {
                "index": 0,
                "anchor_start": 0,
                "anchor_end": 1,
                "width": -1,
                "height": "bad",
                "provenance": {"backend": "surya"},
                "blocks": [
                    {
                        "id": "b0",
                        "type": "Text",
                        "page_index": 0,
                        "order": 0,
                        "anchor_start": 0,
                        "anchor_end": 1,
                        "provenance": {"backend": "surya"},
                    }
                ],
            }
        ],
    }

    report = validate_middle_json(data)

    assert report.ok is False
    assert any(issue.path.endswith(".width") for issue in report.errors)
    assert any(issue.path.endswith(".height") for issue in report.errors)
    assert any(issue.path.endswith(".provenance") and "must be a list" in issue.message for issue in report.errors)


def test_validate_middle_json_checks_nested_spans():
    data = MiddleDocument(
        pages=[
            MiddlePage(
                index=0,
                width=100,
                height=100,
                blocks=[
                    MiddleBlock(
                        id="p0-b0",
                        type="Text",
                        page_index=0,
                        order=0,
                        provenance=[MiddleProvenance(backend="paddle_pp_doclayout_v3", stage="layout")],
                        spans=[
                            MiddleSpan(
                                text="",
                                bbox=[90, 90, 120, 120],
                                confidence=1.5,
                                provenance=[],
                            )
                        ],
                    )
                ],
            )
        ],
    ).to_dict()
    data["pages"][0]["blocks"][0]["spans"].append({"bbox": [1, 2, 3, 4]})

    report = validate_middle_json(data)

    assert report.ok is False
    assert report.summary["span_count"] == 2
    assert any(issue.path.endswith(".text") and "must be a string" in issue.message for issue in report.errors)
    assert any("outside page width" in issue.message for issue in report.warnings)
    assert any("outside page height" in issue.message for issue in report.warnings)
    assert any("[0, 1]" in issue.message for issue in report.warnings)
    assert any(issue.path.endswith(".provenance") for issue in report.warnings)


def test_middle_cli_reports_validation_success(tmp_path):
    data = MiddleDocument(pages=[MiddlePage(index=0)]).to_dict()
    path = tmp_path / "sample_middle.json"
    path.write_text(__import__("json").dumps(data), encoding="utf-8")

    result = CliRunner().invoke(middle_cli, [str(path), "--summary-only"])

    assert result.exit_code == 0
    assert '"page_count": 1' in result.output


def test_middle_cli_writes_scholarly_markdown(tmp_path):
    data = MiddleDocument(
        pages=[
            MiddlePage(
                index=0,
                blocks=[
                    MiddleBlock(
                        id="p0-b0",
                        type="Text",
                        page_index=0,
                        order=0,
                        text="hello",
                        provenance=[MiddleProvenance(backend="surya", stage="layout")],
                    )
                ],
            )
        ]
    ).to_dict()
    path = tmp_path / "sample_middle.json"
    markdown_path = tmp_path / "sample.md"
    path.write_text(__import__("json").dumps(data), encoding="utf-8")

    result = CliRunner().invoke(middle_cli, [str(path), "--scholarly-markdown", str(markdown_path)])

    assert result.exit_code == 0
    assert "Wrote scholarly Markdown" in result.output
    assert "hello" in markdown_path.read_text(encoding="utf-8")
