import sys
import types
import json
import subprocess
from pathlib import Path

from aih_contexture.backends.layout.paddle_runtime import PaddleLayoutDetectionRuntime


class FakeResult:
    def __init__(self, payload):
        self.json = payload


class FakePredictor:
    def __init__(self):
        self.closed = False
        self.batch_size = None

    def predict(self, input_paths, batch_size=None):
        self.batch_size = batch_size
        return [
            FakeResult(
                {
                    "res": {
                        "input_path": input_paths[0],
                        "page_index": None,
                        "boxes": [
                            {
                                "label": "paragraph_title",
                                "score": 0.9,
                                "coordinate": [10, 20, 30, 40],
                            }
                        ],
                    }
                }
            )
        ]

    def close(self):
        self.closed = True


def test_paddle_layout_runtime_normalizes_result_payload(tmp_path):
    image_path = tmp_path / "page.png"
    image_path.write_bytes(b"fake")
    predictor = FakePredictor()
    runtime = PaddleLayoutDetectionRuntime(
        {"paddle_layout_model_name": "PP-DocLayout_plus-L"},
        predictor=predictor,
    )

    payload = runtime.run([image_path], page_sizes=[(100, 200)])

    assert payload[0]["res"]["page_index"] == 0
    assert payload[0]["res"]["page_size"] == [100.0, 200.0]
    assert payload[0]["res"]["model_name"] == "PP-DocLayout_plus-L"
    assert payload[0]["res"]["boxes"][0]["label"] == "paragraph_title"
    assert predictor.closed is False


def test_paddle_layout_runtime_passes_predict_batch_size(tmp_path):
    image_path = tmp_path / "page.png"
    image_path.write_bytes(b"fake")
    predictor = FakePredictor()
    runtime = PaddleLayoutDetectionRuntime(
        {
            "paddle_layout_model_name": "PP-DocLayout_plus-L",
            "paddle_layout_batch_size": 32,
        },
        predictor=predictor,
    )

    runtime.run([image_path], page_sizes=[(100, 200)])

    assert predictor.batch_size == 32


def test_paddle_layout_runtime_disables_mkldnn_by_default(monkeypatch):
    captured = {}
    module = types.ModuleType("paddleocr")

    class FakeLayoutDetection:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    module.LayoutDetection = FakeLayoutDetection
    monkeypatch.setitem(sys.modules, "paddleocr", module)
    runtime = PaddleLayoutDetectionRuntime({"paddle_layout_device": "cpu"})
    monkeypatch.setattr(runtime, "is_available", lambda: True)

    runtime._create_predictor()

    assert captured["device"] == "cpu"
    assert captured["enable_mkldnn"] is False


def test_paddle_layout_runtime_passes_advanced_options(monkeypatch):
    captured = {}
    module = types.ModuleType("paddleocr")

    class FakeLayoutDetection:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    module.LayoutDetection = FakeLayoutDetection
    monkeypatch.setitem(sys.modules, "paddleocr", module)
    runtime = PaddleLayoutDetectionRuntime(
        {
            "paddle_layout_enable_mkldnn": "true",
            "paddle_layout_enable_cinn": "false",
            "paddle_layout_cpu_threads": 4,
            "paddle_layout_engine": "paddle_static",
        }
    )
    monkeypatch.setattr(runtime, "is_available", lambda: True)

    runtime._create_predictor()

    assert captured["enable_mkldnn"] is True
    assert captured["enable_cinn"] is False
    assert captured["cpu_threads"] == 4
    assert captured["engine"] == "paddle_static"


def test_paddle_layout_runtime_can_delegate_to_external_python(tmp_path, monkeypatch):
    image_path = tmp_path / "page.png"
    image_path.write_bytes(b"fake")
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        result_path = Path(command[command.index("--result-json") + 1])
        result_path.write_text(
            json.dumps([{"res": {"page_index": 0, "boxes": [], "model_name": "PP-DocLayoutV3"}}]),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runtime = PaddleLayoutDetectionRuntime(
        {
            "paddle_layout_python": r"C:\Paddle\.venv\Scripts\python.exe",
            "paddle_layout_model_name": "PP-DocLayoutV3",
        }
    )

    payload = runtime.run([image_path], page_sizes=[(10, 20)])

    assert payload[0]["res"]["model_name"] == "PP-DocLayoutV3"
    assert seen["command"][:3] == [r"C:\Paddle\.venv\Scripts\python.exe", "-m", "aih_contexture.scripts.paddle_sidecar"]
