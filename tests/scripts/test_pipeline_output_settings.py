from aih_contexture.scripts.ui.pipeline_output_settings import (
    PIPELINE_DEFAULT_OUTPUT_FORMATS,
    PIPELINE_OUTPUT_FORMATS,
    default_pipeline_output_formats,
    render_pipeline_output_settings,
)


def test_default_pipeline_output_formats_are_stable_copy():
    formats = default_pipeline_output_formats()

    assert formats == ["markdown", "json", "html"]
    assert formats is not PIPELINE_DEFAULT_OUTPUT_FORMATS


def test_default_pipeline_output_formats_can_be_mutated_without_global_side_effect():
    formats = default_pipeline_output_formats()
    formats.append("middle_json")

    assert default_pipeline_output_formats() == ["markdown", "json", "html"]


class FakeStreamlit:
    def __init__(self, checkbox_values):
        self.checkbox_values = list(checkbox_values)

    def markdown(self, *args, **kwargs):
        pass

    def multiselect(self, *args, **kwargs):
        return ["markdown"]

    def checkbox(self, *args, **kwargs):
        return self.checkbox_values.pop(0)


def test_render_pipeline_output_settings_layout_overlay_implies_middle_json():
    formats, settings = render_pipeline_output_settings(
        FakeStreamlit([False, False, False, False, False, True, False])
    )

    assert formats == ["markdown"]
    assert settings.emit_middle_json is True
    assert settings.emit_layout_overlay is True
    assert settings.emit_span_overlay is False


def test_render_pipeline_output_settings_span_overlay_implies_middle_json():
    formats, settings = render_pipeline_output_settings(
        FakeStreamlit([False, False, False, False, False, False, True])
    )

    assert formats == ["markdown"]
    assert settings.emit_middle_json is True
    assert settings.emit_layout_overlay is False
    assert settings.emit_span_overlay is True
