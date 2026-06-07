from aih_contexture.scripts.ui.paddle_ocr_settings import render_paddle_ocr_settings


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeStreamlit:
    def __init__(self, session_state=None, checkbox_values=None):
        self.session_state = session_state or {}
        self.checkbox_values = checkbox_values or {}
        self.calls = []

    def markdown(self, *args, **kwargs):
        self.calls.append(("markdown", args, kwargs))

    def info(self, *args, **kwargs):
        self.calls.append(("info", args, kwargs))

    def caption(self, *args, **kwargs):
        self.calls.append(("caption", args, kwargs))

    def text_input(self, label, value="", **kwargs):
        self.calls.append(("text_input", (label,), kwargs))
        return value

    def selectbox(self, label, options, index=0, **kwargs):
        self.calls.append(("selectbox", (label,), kwargs))
        return options[index]

    def checkbox(self, label, value=False, **kwargs):
        self.calls.append(("checkbox", (label,), kwargs))
        key = kwargs.get("key")
        return self.checkbox_values.get(key, value)

    def number_input(self, label, value=0, **kwargs):
        self.calls.append(("number_input", (label,), kwargs))
        return value

    def expander(self, *args, **kwargs):
        self.calls.append(("expander", args, kwargs))
        return _Context()


def test_render_paddle_ocr_settings_returns_stable_defaults():
    st = FakeStreamlit()

    settings = render_paddle_ocr_settings(st, description="desc")

    assert settings["paddle_ocr_lang"] == "ch"
    assert settings["paddle_ocr_version"] == "PP-OCRv5"
    assert settings["paddle_ocr_enable_mkldnn"] is False
    assert settings["paddle_ocr_use_doc_orientation_classify"] is False
    assert settings["paddle_ocr_use_doc_unwarping"] is False
    assert settings["paddle_ocr_use_textline_orientation"] is False
    assert settings["force_ocr"] is True
    assert settings["use_llm"] is False
    assert any(call[0] == "checkbox" and call[2].get("key") == "paddle_ocr_enable_mkldnn" for call in st.calls)


def test_render_paddle_ocr_settings_reads_session_overrides():
    st = FakeStreamlit(
        session_state={
            "paddle_ocr_lang": "en",
            "paddle_ocr_version": "PP-OCRv5",
            "paddle_ocr_device": "cpu",
            "paddle_ocr_cpu_threads": 4,
        },
        checkbox_values={"paddle_ocr_use_textline_orientation": True},
    )

    settings = render_paddle_ocr_settings(st, description="desc")

    assert settings["paddle_ocr_lang"] == "en"
    assert settings["paddle_ocr_device"] == "cpu"
    assert settings["paddle_ocr_cpu_threads"] == 4
    assert settings["paddle_ocr_use_textline_orientation"] is True
