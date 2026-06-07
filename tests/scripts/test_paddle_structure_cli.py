import json

from click.testing import CliRunner

from aih_contexture.scripts import paddle_structure as paddle_structure_script
from aih_contexture.scripts.paddle_structure import paddle_structure_cli


class FakeRuntime:
    def __init__(self, config):
        self.config = config

    def run(self, input_path):
        return [
            {
                "res": {
                    "input_path": str(input_path),
                    "page_index": 0,
                    "width": 100,
                    "height": 120,
                    "parsing_res_list": [
                        {
                            "block_label": "text",
                            "block_bbox": [0, 0, 80, 40],
                            "block_content": "Hello PP Structure",
                            "block_order": 0,
                        }
                    ],
                    "overall_ocr_res": {
                        "rec_texts": ["Hello PP Structure"],
                        "rec_boxes": [[2, 4, 70, 18]],
                        "rec_scores": [0.98],
                    },
                }
            }
        ]


def test_paddle_structure_cli_writes_raw_and_middle_outputs(tmp_path, monkeypatch):
    input_path = tmp_path / "sample.pdf"
    raw_path = tmp_path / "raw_structure.json"
    middle_path = tmp_path / "middle.json"
    report_path = tmp_path / "report.json"
    debug_path = tmp_path / "debug.md"
    scholarly_path = tmp_path / "scholarly.md"
    input_path.write_bytes(b"fake")
    monkeypatch.setattr(paddle_structure_script, "PaddleStructureV3Runtime", FakeRuntime)

    result = CliRunner().invoke(
        paddle_structure_cli,
        [
            str(input_path),
            "--output-json",
            str(raw_path),
            "--middle-output",
            str(middle_path),
            "--report",
            str(report_path),
            "--debug-markdown",
            str(debug_path),
            "--scholarly-markdown",
            str(scholarly_path),
            "--lang",
            "en",
            "--ocr-version",
            "PP-OCRv5",
        ],
    )

    assert result.exit_code == 0
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    middle = json.loads(middle_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert raw[0]["res"]["parsing_res_list"][0]["block_content"] == "Hello PP Structure"
    assert middle["backends"]["layout"] == "paddle_pp_structure_v3"
    assert middle["backends"]["ocr"] == "paddle_ocr_v5"
    assert middle["pages"][0]["blocks"][0]["spans"][0]["text"] == "Hello PP Structure"
    assert report["ok"] is True
    assert "### Text" in debug_path.read_text(encoding="utf-8")
    assert "Hello PP Structure" in scholarly_path.read_text(encoding="utf-8")
