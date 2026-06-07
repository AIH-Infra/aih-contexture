from aih_contexture.scripts.ui.ocr_calamari_settings import (
    DEFAULT_CALAMARI_MODELS,
    default_model_index,
    render_calamari_ocr_settings,
)


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeStreamlit:
    def __init__(self, checkbox_values=None):
        self.checkbox_values = checkbox_values or {}
        self.calls = []

    def success(self, *args, **kwargs):
        self.calls.append(("success", args, kwargs))

    def info(self, *args, **kwargs):
        self.calls.append(("info", args, kwargs))

    def error(self, *args, **kwargs):
        self.calls.append(("error", args, kwargs))

    def caption(self, *args, **kwargs):
        self.calls.append(("caption", args, kwargs))

    def markdown(self, *args, **kwargs):
        self.calls.append(("markdown", args, kwargs))

    def columns(self, spec):
        self.calls.append(("columns", (spec,), {}))
        return [_Context(), _Context()]

    def button(self, *args, **kwargs):
        self.calls.append(("button", args, kwargs))
        return False

    def expander(self, *args, **kwargs):
        self.calls.append(("expander", args, kwargs))
        return _Context()

    def text_input(self, label, value="", **kwargs):
        self.calls.append(("text_input", (label,), kwargs))
        return value

    def selectbox(self, label, options, index=0, **kwargs):
        self.calls.append(("selectbox", (label,), kwargs))
        return options[index]

    def number_input(self, label, **kwargs):
        self.calls.append(("number_input", (label,), kwargs))
        return kwargs["value"]

    def checkbox(self, label, value=False, **kwargs):
        self.calls.append(("checkbox", (label,), kwargs))
        return self.checkbox_values.get(label, value)

    def slider(self, label, **kwargs):
        self.calls.append(("slider", (label,), kwargs))
        return kwargs["value"]


def test_default_model_index_uses_preferred_when_available():
    assert default_model_index(["x", "gt4histocr"]) == 1
    assert default_model_index(["x", "y"]) == 0


def test_render_calamari_settings_uses_online_models_and_stable_keys():
    st = FakeStreamlit()

    settings = render_calamari_ocr_settings(
        st,
        description="desc",
        base_url="http://localhost:11800",
        model="gt4histocr",
        batch_size=100,
        timeout=120,
        sequential_mode=False,
        trust_batch_order=False,
        require_ordering_info=True,
        fallback_to_sequential_on_ordering_failure=True,
        footnote_y_frac=0.83,
        binarize_lines=True,
        check_health=lambda url: (True, ["gt4histocr"]),
        get_models=lambda url: ["fraktur", "gt4histocr"],
    )

    assert settings["calamari_base_url"] == "http://localhost:11800"
    assert settings["calamari_model"] == "gt4histocr"
    assert settings["calamari_batch_size"] == 100
    assert settings["calamari_timeout"] == 120
    assert settings["calamari_require_ordering_info"] is True
    assert settings["calamari_fallback_to_sequential_on_ordering_failure"] is True
    assert settings["force_ocr"] is True
    assert settings["ocr_line_source"] == "tesseract"
    assert settings["use_llm"] is False
    assert settings["ocr_batch_size"] == 32
    assert any(call[0] == "caption" and "已预热模型" in call[1][0] for call in st.calls)


def test_render_calamari_settings_falls_back_when_service_is_offline():
    st = FakeStreamlit()

    settings = render_calamari_ocr_settings(
        st,
        description="desc",
        base_url="url",
        model="antiqua_historical",
        batch_size=50,
        timeout=60,
        sequential_mode=False,
        trust_batch_order=False,
        require_ordering_info=True,
        fallback_to_sequential_on_ordering_failure=True,
        footnote_y_frac=0.9,
        binarize_lines=False,
        check_health=lambda url: (False, []),
        get_models=lambda url: ["should-not-be-used"],
    )

    assert settings["calamari_model"] == DEFAULT_CALAMARI_MODELS[0]
    assert settings["calamari_binarize_lines"] is False
    assert settings["calamari_footnote_y_frac"] == 0.9
    assert settings["force_ocr"] is True
    assert any(call[0] == "error" for call in st.calls)


def test_render_calamari_settings_disables_batch_order_options_in_sequential_mode():
    st = FakeStreamlit({"使用串行模式": True})

    settings = render_calamari_ocr_settings(
        st,
        description="desc",
        base_url="url",
        model=DEFAULT_CALAMARI_MODELS[0],
        batch_size=50,
        timeout=60,
        sequential_mode=False,
        trust_batch_order=True,
        require_ordering_info=True,
        fallback_to_sequential_on_ordering_failure=True,
        footnote_y_frac=0.83,
        binarize_lines=True,
        check_health=lambda url: (False, []),
        get_models=lambda url: [],
    )

    assert settings["calamari_sequential_mode"] is True
    assert settings["calamari_trust_batch_order"] is False
    assert settings["calamari_require_ordering_info"] is False
    assert settings["calamari_fallback_to_sequential_on_ordering_failure"] is False
