import json

from click.testing import CliRunner
from PIL import Image

from aih_contexture.scripts import paddle_ocr as paddle_ocr_script
from aih_contexture.scripts.paddle_ocr import paddle_ocr_cli


class FakeRuntime:
    def __init__(self, config):
        self.config = config

    def run(self, image_paths, *, page_sizes=None):
        return [
            {
                "res": {
                    "page_index": 0,
                    "page_size": [100.0, 100.0],
                    "ocr_version": self.config["paddle_ocr_version"],
                    "lang": self.config["paddle_ocr_lang"],
                    "rec_texts": ["Hello"],
                    "rec_boxes": [[2, 4, 20, 14]],
                    "rec_scores": [0.98],
                }
            }
        ]


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


def test_paddle_ocr_cli_writes_raw_and_merged_middle(tmp_path, monkeypatch):
    image_path = tmp_path / "page.png"
    Image.new("RGB", (100, 100), "white").save(image_path)
    middle_path = tmp_path / "middle.json"
    raw_path = tmp_path / "raw_ocr.json"
    merged_path = tmp_path / "merged.json"
    report_path = tmp_path / "report.json"
    middle_path.write_text(json.dumps(_middle_payload()), encoding="utf-8")
    monkeypatch.setattr(paddle_ocr_script, "PaddleOcrRuntime", FakeRuntime)

    result = CliRunner().invoke(
        paddle_ocr_cli,
        [
            str(image_path),
            "--output-json",
            str(raw_path),
            "--middle-json",
            str(middle_path),
            "--merged-output",
            str(merged_path),
            "--report",
            str(report_path),
            "--lang",
            "en",
            "--ocr-version",
            "PP-OCRv5",
        ],
    )

    assert result.exit_code == 0
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    merged = json.loads(merged_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert raw[0]["res"]["rec_texts"] == ["Hello"]
    assert merged["pages"][0]["blocks"][0]["spans"][0]["text"] == "Hello"
    assert merged["backends"]["ocr"] == "paddle_ocr_v5"
    assert report["ocr_import"]["imported_spans"] == 1
