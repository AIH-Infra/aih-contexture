from aih_contexture.scripts.ui.surya_layout_settings import render_surya_layout_settings


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeStreamlit:
    def __init__(self, checkbox_values=None, session_state=None):
        self.checkbox_values = checkbox_values or {}
        self.session_state = session_state or {}
        self.calls = []

    def success(self, *args, **kwargs):
        self.calls.append(("success", args, kwargs))

    def caption(self, *args, **kwargs):
        self.calls.append(("caption", args, kwargs))

    def markdown(self, *args, **kwargs):
        self.calls.append(("markdown", args, kwargs))

    def subheader(self, *args, **kwargs):
        self.calls.append(("subheader", args, kwargs))

    def expander(self, *args, **kwargs):
        self.calls.append(("expander", args, kwargs))
        return _Context()

    def columns(self, spec):
        self.calls.append(("columns", (spec,), {}))
        return [_Context(), _Context()]

    def checkbox(self, label, value=False, **kwargs):
        self.calls.append(("checkbox", (label,), kwargs))
        key = kwargs.get("key")
        if key in self.checkbox_values:
            return self.checkbox_values[key]
        return self.checkbox_values.get(label, value)

    def radio(self, label, options, index=0, **kwargs):
        self.calls.append(("radio", (label,), kwargs))
        return options[index]

    def text_input(self, label, value="", **kwargs):
        self.calls.append(("text_input", (label,), kwargs))
        return value

    def multiselect(self, label, options, default=None, **kwargs):
        self.calls.append(("multiselect", (label,), kwargs))
        return default or []

    def slider(self, label, *args, **kwargs):
        self.calls.append(("slider", (label,), kwargs))
        return args[2]


def test_render_surya_layout_settings_returns_default_processor_config():
    st = FakeStreamlit()

    settings = render_surya_layout_settings(
        st,
        description="desc",
        extract_printed_pages=True,
    )

    assert settings["markdown_noise_removal_enabled"] is True
    assert settings["markdown_noise_cleaning_level"] == "basic"
    assert settings["line_merge_enabled"] is True
    assert settings["blockquote_enabled"] is True
    assert settings["code_enabled"] is True
    assert settings["section_header_enabled"] is True
    assert settings["equation_enabled"] is True
    assert settings["footnote_enabled"] is True
    assert settings["table_enabled"] is True
    assert settings["printed_page_zones"] == ["footer", "header"]
    assert settings["printed_page_header_end"] == 0.15
    assert settings["printed_page_footer_start"] == 0.83
    assert any(call[0] == "checkbox" and call[2].get("key") == "markdown_noise_removal_enabled_pipeline" for call in st.calls)
    assert any(call[0] == "multiselect" and call[2].get("key") == "printed_page_zones_pipeline" for call in st.calls)


def test_render_surya_layout_settings_uses_safe_noise_defaults_when_disabled():
    st = FakeStreamlit({"markdown_noise_removal_enabled_pipeline": False})

    settings = render_surya_layout_settings(
        st,
        description="desc",
        extract_printed_pages=False,
    )

    assert settings["markdown_noise_removal_enabled"] is False
    assert settings["markdown_noise_cleaning_level"] == "basic"
    assert settings["markdown_noise_custom_symbols"] == ""
    assert settings["markdown_noise_line_start_only"] is True


def test_render_surya_layout_settings_reads_page_header_footer_session_defaults():
    st = FakeStreamlit(
        session_state={
            "emit_page_header_comment_global": True,
            "keep_pagefooter_in_output_global": True,
        }
    )

    settings = render_surya_layout_settings(
        st,
        description="desc",
        extract_printed_pages=False,
    )

    assert settings["emit_page_header_comment"] is True
    assert settings["keep_pagefooter_in_output"] is True
    assert any(call[0] == "multiselect" for call in st.calls)
