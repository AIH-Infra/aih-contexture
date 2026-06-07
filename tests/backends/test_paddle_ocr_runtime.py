import sys
import types
import json
import subprocess
from pathlib import Path

from aih_contexture.backends.ocr.paddle_runtime import PaddleOcrRuntime


class FakeResult:
    def __init__(self, payload):
        self.json = payload


class FakePredictor:
    def predict(self, input_paths):
        return [
            FakeResult(
                {
                    "res": {
                        "input_path": input_paths[0],
                        "page_index": None,
                        "rec_texts": ["Hello"],
                        "rec_boxes": [[1, 2, 30, 12]],
                        "rec_scores": [0.98],
                    }
                }
            )
        ]


def test_paddle_ocr_runtime_normalizes_result_payload(tmp_path):
    image_path = tmp_path / "page.png"
    image_path.write_bytes(b"fake")
    runtime = PaddleOcrRuntime(
        {"paddle_ocr_version": "PP-OCRv5", "paddle_ocr_lang": "en"},
        predictor=FakePredictor(),
    )

    payload = runtime.run([image_path], page_sizes=[(100, 200)])

    assert payload[0]["res"]["page_index"] == 0
    assert payload[0]["res"]["page_size"] == [100.0, 200.0]
    assert payload[0]["res"]["ocr_version"] == "PP-OCRv5"
    assert payload[0]["res"]["lang"] == "en"
    assert payload[0]["res"]["rec_texts"] == ["Hello"]


def test_paddle_ocr_runtime_disables_mkldnn_by_default(monkeypatch):
    captured = {}
    module = types.ModuleType("paddleocr")

    class FakePaddleOCR:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    module.PaddleOCR = FakePaddleOCR
    monkeypatch.setitem(sys.modules, "paddleocr", module)
    runtime = PaddleOcrRuntime({"paddle_ocr_device": "cpu"})
    monkeypatch.setattr(runtime, "is_available", lambda: True)

    runtime._create_predictor()

    assert captured["ocr_version"] == "PP-OCRv5"
    assert captured["lang"] == "ch"
    assert captured["device"] == "cpu"
    assert captured["enable_mkldnn"] is False
    assert captured["use_doc_orientation_classify"] is False
    assert captured["use_doc_unwarping"] is False
    assert captured["use_textline_orientation"] is False


def test_paddle_ocr_runtime_clamps_out_of_range_gpu_device(monkeypatch):
    captured = {}
    module = types.ModuleType("paddleocr")
    paddle_module = types.ModuleType("paddle")
    paddle_module.device = types.SimpleNamespace(
        cuda=types.SimpleNamespace(device_count=lambda: 1)
    )

    class FakePaddleOCR:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    module.PaddleOCR = FakePaddleOCR
    monkeypatch.setitem(sys.modules, "paddleocr", module)
    monkeypatch.setitem(sys.modules, "paddle", paddle_module)
    runtime = PaddleOcrRuntime({"paddle_ocr_device": "gpu:1"})
    monkeypatch.setattr(runtime, "is_available", lambda: True)

    runtime._create_predictor()

    assert captured["device"] == "gpu:0"


def test_paddle_ocr_runtime_passes_advanced_options(monkeypatch):
    captured = {}
    module = types.ModuleType("paddleocr")

    class FakePaddleOCR:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    module.PaddleOCR = FakePaddleOCR
    monkeypatch.setitem(sys.modules, "paddleocr", module)
    runtime = PaddleOcrRuntime(
        {
            "paddle_ocr_lang": "en",
            "paddle_ocr_enable_mkldnn": "true",
            "paddle_ocr_cpu_threads": 4,
            "paddle_ocr_use_textline_orientation": "false",
            "paddle_ocr_text_rec_score_thresh": 0.7,
        }
    )
    monkeypatch.setattr(runtime, "is_available", lambda: True)

    runtime._create_predictor()

    assert captured["lang"] == "en"
    assert captured["enable_mkldnn"] is True
    assert captured["cpu_threads"] == 4
    assert captured["use_textline_orientation"] is False
    assert captured["text_rec_score_thresh"] == 0.7


def test_paddle_ocr_runtime_can_delegate_to_external_python(tmp_path, monkeypatch):
    image_path = tmp_path / "page.png"
    image_path.write_bytes(b"fake")
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        result_path = Path(command[command.index("--result-json") + 1])
        result_path.write_text(
            json.dumps([{"res": {"page_index": 0, "rec_texts": ["Hello"], "ocr_version": "PP-OCRv5"}}]),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runtime = PaddleOcrRuntime(
        {
            "paddle_ocr_python": r"C:\Paddle\.venv\Scripts\python.exe",
            "paddle_ocr_version": "PP-OCRv5",
        }
    )

    payload = runtime.run([image_path], page_sizes=[(10, 20)])

    assert payload[0]["res"]["rec_texts"] == ["Hello"]
    assert seen["command"][:3] == [r"C:\Paddle\.venv\Scripts\python.exe", "-m", "aih_contexture.scripts.paddle_sidecar"]
