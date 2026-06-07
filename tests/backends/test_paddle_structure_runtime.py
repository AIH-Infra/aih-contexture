import sys
import types

from aih_contexture.backends.document.paddle_structure_runtime import PaddleStructureV3Runtime


class FakeResult:
    def __init__(self, payload):
        self.json = payload


class FakePipeline:
    def predict(self, input):
        return [
            FakeResult(
                {
                    "input_path": input,
                    "page_index": None,
                    "width": 100,
                    "height": 120,
                    "parsing_res_list": [
                        {
                            "block_label": "text",
                            "block_bbox": [0, 0, 80, 40],
                            "block_content": "Hello",
                        }
                    ],
                }
            )
        ]


def test_paddle_structure_runtime_normalizes_result_payload(tmp_path):
    input_path = tmp_path / "sample.pdf"
    input_path.write_bytes(b"fake")
    runtime = PaddleStructureV3Runtime(
        {"paddle_structure_lang": "en", "paddle_structure_ocr_version": "PP-OCRv5"},
        pipeline=FakePipeline(),
    )

    payload = runtime.run(input_path)

    assert payload[0]["res"]["page_index"] == 0
    assert payload[0]["res"]["pipeline"] == "PP-StructureV3"
    assert payload[0]["res"]["lang"] == "en"
    assert payload[0]["res"]["ocr_version"] == "PP-OCRv5"
    assert payload[0]["res"]["parsing_res_list"][0]["block_content"] == "Hello"


def test_paddle_structure_runtime_disables_preprocessors_by_default(monkeypatch):
    captured = {}
    module = types.ModuleType("paddleocr")

    class FakePPStructureV3:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    module.PPStructureV3 = FakePPStructureV3
    monkeypatch.setitem(sys.modules, "paddleocr", module)
    runtime = PaddleStructureV3Runtime({"paddle_structure_device": "cpu"})
    monkeypatch.setattr(runtime, "is_available", lambda: True)

    runtime._create_pipeline()

    assert captured["lang"] == "ch"
    assert captured["ocr_version"] == "PP-OCRv5"
    assert captured["device"] == "cpu"
    assert captured["use_doc_orientation_classify"] is False
    assert captured["use_doc_unwarping"] is False
    assert captured["use_textline_orientation"] is False


def test_paddle_structure_runtime_passes_advanced_options(monkeypatch):
    captured = {}
    module = types.ModuleType("paddleocr")

    class FakePPStructureV3:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    module.PPStructureV3 = FakePPStructureV3
    monkeypatch.setitem(sys.modules, "paddleocr", module)
    runtime = PaddleStructureV3Runtime(
        {
            "paddle_structure_engine": "paddle_static",
            "paddle_structure_use_table_recognition": "false",
            "paddle_structure_use_formula_recognition": "true",
            "paddle_structure_layout_threshold": 0.4,
        }
    )
    monkeypatch.setattr(runtime, "is_available", lambda: True)

    runtime._create_pipeline()

    assert captured["engine"] == "paddle_static"
    assert captured["use_table_recognition"] is False
    assert captured["use_formula_recognition"] is True
    assert captured["layout_threshold"] == 0.4


def test_paddle_structure_runtime_rewrites_missing_extra_error(monkeypatch):
    module = types.ModuleType("paddleocr")

    class FakePPStructureV3:
        def __init__(self, **kwargs):
            raise RuntimeError("A dependency error occurred during pipeline creation")

    module.PPStructureV3 = FakePPStructureV3
    monkeypatch.setitem(sys.modules, "paddleocr", module)
    runtime = PaddleStructureV3Runtime({})
    monkeypatch.setattr(runtime, "is_available", lambda: True)

    try:
        runtime._create_pipeline()
    except RuntimeError as exc:
        assert "paddlex[ocr]" in str(exc)
    else:
        raise AssertionError("missing PP-StructureV3 extra dependency should be reported")
