from aih_contexture.scripts.ui.pipeline_run_settings import render_pipeline_run_settings


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeStreamlit:
    def __init__(self, *, radio_value="自动", checkbox_values=None, number_values=None):
        self.radio_value = radio_value
        self.checkbox_values = checkbox_values or {}
        self.number_values = number_values or {}
        self.calls = []

    def expander(self, *args, **kwargs):
        self.calls.append(("expander", args, kwargs))
        return _Context()

    def markdown(self, *args, **kwargs):
        self.calls.append(("markdown", args, kwargs))

    def info(self, *args, **kwargs):
        self.calls.append(("info", args, kwargs))

    def divider(self, *args, **kwargs):
        self.calls.append(("divider", args, kwargs))

    def columns(self, spec):
        self.calls.append(("columns", (spec,), {}))
        return [_Context(), _Context()]

    def radio(self, label, options, index=0, **kwargs):
        self.calls.append(("radio", (label,), kwargs))
        return self.radio_value if self.radio_value in options else options[index]

    def checkbox(self, label, value=False, **kwargs):
        self.calls.append(("checkbox", (label,), kwargs))
        key = kwargs.get("key")
        if key in self.checkbox_values:
            return self.checkbox_values[key]
        return self.checkbox_values.get(label, value)

    def number_input(self, label, **kwargs):
        self.calls.append(("number_input", (label,), kwargs))
        key = kwargs.get("key")
        if key in self.number_values:
            return self.number_values[key]
        return self.number_values.get(label, kwargs.get("value"))


def test_render_pipeline_run_settings_auto_mode_defaults(monkeypatch):
    monkeypatch.setenv("USE_FP16", "true")
    st = FakeStreamlit(checkbox_values={"use_page_range": False, "使用 FP16": True})

    settings = render_pipeline_run_settings(st)

    assert settings["batch_mode"] == "自动"
    assert settings["process_mode"] == "自动"
    assert settings["batch_threshold"] == 50
    assert settings["pages_per_batch"] == 25
    assert settings["cooling_seconds"] == 3
    assert settings["use_page_range"] is False
    assert settings["start_page_1based"] is None
    assert settings["end_page_1based"] is None
    assert settings["use_fp16"] is True
    assert any(call[0] == "checkbox" and call[2].get("key") == "use_page_range" for call in st.calls)


def test_render_pipeline_run_settings_single_batch_skips_batch_inputs():
    st = FakeStreamlit(radio_value="单批处理", checkbox_values={"use_page_range": False})

    settings = render_pipeline_run_settings(st)

    assert settings["process_mode"] == "强制单批"
    assert settings["batch_threshold"] == 50
    assert settings["pages_per_batch"] == 25
    assert settings["cooling_seconds"] == 0
    assert not any(call[0] == "info" for call in st.calls)


def test_render_pipeline_run_settings_page_range_keeps_stable_keys():
    st = FakeStreamlit(
        radio_value="分批处理",
        checkbox_values={"use_page_range": True, "使用 FP16": False},
        number_values={
            "分批阈值（页）": 80,
            "每批页数": 20,
            "批次间冷却（秒）": 5,
            "start_page": 3,
            "end_page": 9,
        },
    )

    settings = render_pipeline_run_settings(st)

    assert settings["process_mode"] == "强制分批"
    assert settings["batch_threshold"] == 80
    assert settings["pages_per_batch"] == 20
    assert settings["cooling_seconds"] == 5
    assert settings["use_page_range"] is True
    assert settings["start_page_1based"] == 3
    assert settings["end_page_1based"] == 9
    assert any(call[0] == "number_input" and call[2].get("key") == "start_page" for call in st.calls)
    assert any(call[0] == "number_input" and call[2].get("key") == "end_page" for call in st.calls)
