from aih_contexture.scripts.ui.dpi_settings import (
    render_pipeline_layout_dpi_settings,
    render_pipeline_ocr_dpi_settings,
)


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeStreamlit:
    def __init__(self, *, selectbox_values=None, number_input_values=None, session_state=None):
        self.selectbox_values = selectbox_values or {}
        self.number_input_values = number_input_values or {}
        self.session_state = session_state or {}
        self.calls = []

    def expander(self, *args, **kwargs):
        self.calls.append(("expander", args, kwargs))
        return _Context()

    def selectbox(self, label, options, index=0, **kwargs):
        self.calls.append(("selectbox", (label, options), kwargs))
        key = kwargs.get("key")
        if key in self.selectbox_values:
            return self.selectbox_values[key]
        return options[index]

    def number_input(self, label, value=0, **kwargs):
        self.calls.append(("number_input", (label,), kwargs))
        key = kwargs.get("key")
        if key in self.number_input_values:
            return self.number_input_values[key]
        return value

    def caption(self, *args, **kwargs):
        self.calls.append(("caption", args, kwargs))


def test_layout_dpi_settings_surya_uses_fast_default():
    st = FakeStreamlit()

    settings = render_pipeline_layout_dpi_settings(
        st,
        layout_backend="surya",
    )

    assert settings == {
        "surya_layout_quality": "fast",
        "layout_dpi_override": None,
    }
    assert any(call[0] == "selectbox" and call[2].get("key") == "surya_layout_quality" for call in st.calls)
    assert any("实际版面渲染 DPI：96" in call[1][0] for call in st.calls if call[0] == "caption")


def test_layout_dpi_settings_surya_accepts_high_quality():
    st = FakeStreamlit(selectbox_values={"surya_layout_quality": "high"})

    settings = render_pipeline_layout_dpi_settings(
        st,
        layout_backend="surya",
        surya_layout_quality="standard",
    )

    assert settings["surya_layout_quality"] == "high"
    assert settings["layout_dpi_override"] is None
    assert any("实际版面渲染 DPI：192" in call[1][0] for call in st.calls if call[0] == "caption")


def test_layout_dpi_settings_non_surya_keeps_quality_and_allows_override():
    st = FakeStreamlit(number_input_values={"layout_dpi_override": 288})

    settings = render_pipeline_layout_dpi_settings(
        st,
        layout_backend="paddle_pp_doclayout_v3",
        surya_layout_quality="standard",
    )

    assert settings == {
        "surya_layout_quality": "standard",
        "layout_dpi_override": 288,
    }
    assert not any(call[0] == "selectbox" for call in st.calls)
    assert any("默认使用 144 DPI" in call[1][0] for call in st.calls if call[0] == "caption")
    assert any("实际版面渲染 DPI：288" in call[1][0] for call in st.calls if call[0] == "caption")


def test_ocr_dpi_settings_auto_uses_backend_default():
    st = FakeStreamlit()

    settings = render_pipeline_ocr_dpi_settings(
        st,
        ocr_backend="paddle_ocr_v5",
    )

    assert settings == {
        "ocr_quality": "auto",
        "ocr_dpi_override": None,
    }
    assert any(call[0] == "selectbox" and call[2].get("key") == "ocr_quality" for call in st.calls)
    assert any("实际 OCR 渲染 DPI：192" in call[1][0] for call in st.calls if call[0] == "caption")


def test_ocr_dpi_settings_tesseract_auto_uses_medium_default():
    st = FakeStreamlit()

    render_pipeline_ocr_dpi_settings(st, ocr_backend="tesseract")

    assert any("实际 OCR 渲染 DPI：300" in call[1][0] for call in st.calls if call[0] == "caption")


def test_ocr_dpi_settings_vlm_legacy_alias_uses_medium_default():
    st = FakeStreamlit()

    render_pipeline_ocr_dpi_settings(st, ocr_backend="vlm")

    assert any("实际 OCR 渲染 DPI：300" in call[1][0] for call in st.calls if call[0] == "caption")


def test_ocr_dpi_settings_accepts_quality_and_override():
    st = FakeStreamlit(
        selectbox_values={"ocr_quality": "high"},
        number_input_values={"ocr_dpi_override": 450},
    )

    settings = render_pipeline_ocr_dpi_settings(
        st,
        ocr_backend="calamari",
        ocr_quality="medium",
    )

    assert settings == {
        "ocr_quality": "high",
        "ocr_dpi_override": 450,
    }
    assert any("实际 OCR 渲染 DPI：450" in call[1][0] for call in st.calls if call[0] == "caption")


def test_ocr_dpi_settings_none_backend_skips_widgets():
    st = FakeStreamlit()

    settings = render_pipeline_ocr_dpi_settings(
        st,
        ocr_backend="none",
        ocr_quality="high",
        ocr_dpi_override=600,
    )

    assert settings == {
        "ocr_quality": "auto",
        "ocr_dpi_override": None,
    }
    assert st.calls == []
