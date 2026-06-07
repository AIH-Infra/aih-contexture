from aih_contexture.scripts.ui.middle_debug_settings import (
    render_layout_overlay_debug_settings,
    render_middle_artifact_settings,
    render_middle_debug_markdown_settings,
    render_middle_debug_settings,
    render_middle_report_settings,
    render_middle_scholarly_report_settings,
    render_middle_scholarly_settings,
    render_span_overlay_debug_settings,
)


class FakeStreamlit:
    def __init__(self, value):
        self.value = value
        self.calls = []

    def checkbox(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.value


def test_render_middle_debug_settings_uses_stable_key_and_returns_value():
    st = FakeStreamlit(True)

    result = render_middle_debug_settings(st)

    assert result is True
    assert st.calls[0][0] == ("保存 Middle JSON 核心文件",)
    assert st.calls[0][1]["key"] == "pipeline_emit_middle_json"
    assert st.calls[0][1]["value"] is True
    assert "*_middle.json" in st.calls[0][1]["help"]


def test_middle_derived_settings_use_stable_keys():
    for render, expected_key in (
        (render_middle_report_settings, "pipeline_emit_middle_report"),
        (render_middle_debug_markdown_settings, "pipeline_emit_middle_debug"),
        (render_middle_scholarly_settings, "pipeline_emit_middle_scholarly"),
        (render_middle_scholarly_report_settings, "pipeline_emit_middle_scholarly_report"),
    ):
        st = FakeStreamlit(True)

        result = render(st)

        assert result is True
        assert st.calls[0][1]["key"] == expected_key


def test_render_layout_overlay_debug_settings_uses_stable_key_and_returns_value():
    st = FakeStreamlit(True)

    result = render_layout_overlay_debug_settings(st)

    assert result is True
    assert st.calls[0][0] == ("导出版面 Overlay",)
    assert st.calls[0][1]["key"] == "pipeline_emit_layout_overlay"
    assert "*_layout_overlay.pdf" in st.calls[0][1]["help"]


def test_render_span_overlay_debug_settings_uses_stable_key_and_returns_value():
    st = FakeStreamlit(True)

    result = render_span_overlay_debug_settings(st)

    assert result is True
    assert st.calls[0][0] == ("导出 Span Overlay",)
    assert st.calls[0][1]["key"] == "pipeline_emit_span_overlay"
    assert "*_span_overlay.pdf" in st.calls[0][1]["help"]


def test_render_middle_artifact_settings_supports_mode_specific_keys():
    st = FakeStreamlit(True)

    result = render_middle_artifact_settings(st, key_prefix="vlm_generalized", overlays=False)

    assert result.emit_middle_json is True
    assert result.emit_middle_report is True
    assert result.emit_layout_overlay is False
    assert result.emit_span_overlay is False
    assert st.calls[0][1]["key"] == "vlm_generalized_emit_middle_json"


def test_render_middle_artifact_settings_enables_middle_when_overlay_selected():
    class SequenceStreamlit:
        def __init__(self, values):
            self.values = list(values)
            self.calls = []

        def checkbox(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return self.values.pop(0)

    st = SequenceStreamlit([False, False, False, False, False, True, False])

    result = render_middle_artifact_settings(st, key_prefix="vlm_specialized", overlays=True)

    assert result.emit_middle_json is True
    assert result.emit_layout_overlay is True
    assert result.emit_span_overlay is False
    assert [call[1]["key"] for call in st.calls] == [
        "vlm_specialized_emit_middle_json",
        "vlm_specialized_emit_middle_report",
        "vlm_specialized_emit_middle_debug",
        "vlm_specialized_emit_middle_scholarly",
        "vlm_specialized_emit_middle_scholarly_report",
        "vlm_specialized_emit_layout_overlay",
        "vlm_specialized_emit_span_overlay",
    ]


def test_render_middle_artifact_settings_can_force_middle_json_on():
    class SequenceStreamlit:
        def __init__(self, values):
            self.values = list(values)
            self.calls = []

        def checkbox(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return self.values.pop(0)

    st = SequenceStreamlit([False, False, False, False, False, False, False])

    result = render_middle_artifact_settings(st, key_prefix="pipeline", force_middle_json=True)

    assert result.emit_middle_json is True
    assert result.emit_layout_overlay is False
    assert result.emit_span_overlay is False
    assert st.calls[0][1]["key"] == "pipeline_emit_middle_json"
    assert st.calls[0][1]["value"] is True
    assert st.calls[0][1]["disabled"] is True
    assert "全局偏好" in st.calls[0][1]["help"]
