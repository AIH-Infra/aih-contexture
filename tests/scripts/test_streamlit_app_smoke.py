from pathlib import Path

from streamlit.testing.v1 import AppTest


APP_PATH = Path("aih_contexture/scripts/streamlit_app.py")


def _mode_radio(app: AppTest):
    for radio in app.radio:
        if radio.label == "选择转换模式":
            return radio
    raise AssertionError("conversion mode radio not found")


def _assert_no_app_exceptions(app: AppTest):
    assert list(app.exception) == []


def test_streamlit_app_initial_pipeline_mode_loads_without_yolo():
    app = AppTest.from_file(str(APP_PATH))
    app.run(timeout=90)

    _assert_no_app_exceptions(app)
    assert any(header.value == "⚙️ 配置面板" for header in app.header)
    assert _mode_radio(app).value == "pipeline"
    assert any(uploader.label == "上传 PDF 文件" for uploader in app.file_uploader)
    layout_select = next(select for select in app.selectbox if select.label == "选择版面识别引擎")
    assert layout_select.value == "surya"
    assert "yolo" not in [str(option).lower() for option in layout_select.options]


def test_streamlit_app_switches_all_product_modes_without_exceptions():
    app = AppTest.from_file(str(APP_PATH))
    app.run(timeout=90)
    _assert_no_app_exceptions(app)

    expectations = [
        ("🌐 VLM 泛化模式", "上传 PDF 文件", "🚀 开始转换"),
        ("🎯 VLM 特化模式", "上传 PDF 文件", "🚀 开始转换"),
        ("📝 Markdown 后处理", "上传 Markdown 文件", "🚀 开始后处理"),
        ("🔧 Pipeline模式", "上传 PDF 文件", "🚀 开始转换"),
    ]
    for mode_label, uploader_label, button_label in expectations:
        _mode_radio(app).set_value(mode_label)
        app.run(timeout=90)
        _assert_no_app_exceptions(app)
        assert any(uploader.label == uploader_label for uploader in app.file_uploader)
        assert any(button.label == button_label for button in app.button)


def test_streamlit_app_vlm_specialized_defaults_to_churro_backend():
    app = AppTest.from_file(str(APP_PATH))
    app.run(timeout=90)
    _assert_no_app_exceptions(app)

    _mode_radio(app).set_value("🎯 VLM 特化模式")
    app.run(timeout=90)
    _assert_no_app_exceptions(app)

    ocr_backend_select = next(select for select in app.selectbox if select.label == "OCR 后端")
    assert ocr_backend_select.value == "churro"

    model_input = next(text for text in app.text_input if text.label == "模型名称")
    assert model_input.value == "churro-3b@q8_0"
