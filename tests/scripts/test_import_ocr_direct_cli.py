import json

from click.testing import CliRunner

from aih_contexture.scripts.import_ocr_direct import import_ocr_direct_cli


def test_import_ocr_direct_cli_writes_chandra_middle_outputs(tmp_path):
    input_path = tmp_path / "chandra_chunks.json"
    output_path = tmp_path / "middle.json"
    report_path = tmp_path / "report.json"
    debug_path = tmp_path / "debug.md"
    scholarly_path = tmp_path / "scholarly.md"
    input_path.write_text(
        json.dumps(
            [
                {
                    "page_num": 0,
                    "img_size": [100, 200],
                    "chunks": [
                        {"label": "Page-Header", "bbox": [0, 0, 100, 10], "content": "Header"},
                        {"label": "Text", "bbox": [0, 20, 100, 60], "content": "<p>Hello Chandra</p>"},
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        import_ocr_direct_cli,
        [
            str(input_path),
            "--backend",
            "chandra",
            "--model",
            "chandra-2",
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
    assert data["backends"]["vlm_specialized"] == "chandra"
    assert data["pages"][0]["blocks"][1]["text"] == "Hello Chandra"
    assert report["ok"] is True
    assert "### Text" in debug_path.read_text(encoding="utf-8")
    assert "Hello Chandra" in scholarly_path.read_text(encoding="utf-8")


def test_import_ocr_direct_cli_accepts_churro_parse_xml_pages_shape(tmp_path):
    input_path = tmp_path / "churro_pages.json"
    output_path = tmp_path / "middle.json"
    input_path.write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "page_num": 0,
                        "xml": "<Page/>",
                        "json": {
                            "metadata": {},
                            "content": [
                                {
                                    "type": "page",
                                    "page_number": "ix",
                                    "elements": [
                                        {"type": "heading", "text": "Churro heading"},
                                        {"type": "marginal_note", "placement": "right_margin", "text": "Side"},
                                    ],
                                }
                            ],
                        },
                        "markdown": "",
                        "html": "",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        import_ocr_direct_cli,
        [
            str(input_path),
            "--backend",
            "churro",
            "--output",
            str(output_path),
            "--strict",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["backends"]["vlm_specialized"] == "churro"
    assert data["pages"][0]["printed_page"] == "ix"
    assert [block["type"] for block in data["pages"][0]["blocks"]] == ["SectionHeader", "MarginalNote"]
