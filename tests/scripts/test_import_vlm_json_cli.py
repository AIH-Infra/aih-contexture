import json

from click.testing import CliRunner

from aih_contexture.scripts.import_vlm_json import import_vlm_json_cli


def test_import_vlm_json_cli_writes_middle_report_and_markdown_outputs(tmp_path):
    input_path = tmp_path / "vlm_pages.json"
    output_path = tmp_path / "middle.json"
    report_path = tmp_path / "report.json"
    debug_path = tmp_path / "debug.md"
    scholarly_path = tmp_path / "scholarly.md"
    input_path.write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "printed_page_number": "12",
                        "page_width": 100,
                        "page_height": 200,
                        "regions": [
                            {"label": "Page-Header", "bbox": [0, 0, 100, 10], "text": "Header"},
                            {"label": "Text", "bbox": [0, 20, 100, 50], "text": "Hello VLM"},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        import_vlm_json_cli,
        [
            str(input_path),
            "--backend",
            "vlm_specialized",
            "--model",
            "qwen2vl-contexture",
            "--output",
            str(output_path),
            "--report",
            str(report_path),
            "--debug-markdown",
            str(debug_path),
            "--scholarly-markdown",
            str(scholarly_path),
            "--strict",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(output_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    debug_text = debug_path.read_text(encoding="utf-8")
    scholarly_text = scholarly_path.read_text(encoding="utf-8")

    assert data["backends"]["vlm"] == "vlm_specialized"
    assert data["pages"][0]["printed_page"] == "12"
    assert data["pages"][0]["blocks"][0]["type"] == "PageHeader"
    assert report["ok"] is True
    assert report["vlm_import"]["model"] == "qwen2vl-contexture"
    assert "### Text" in debug_text
    assert "<!-- PageHeader: Header -->" in scholarly_text
    assert "Hello VLM" in scholarly_text
