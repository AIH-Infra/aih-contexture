from aih_contexture.scripts.ui.ocr_surya_settings import render_surya_ocr_settings


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeStreamlit:
    def __init__(self):
        self.calls = []

    def success(self, *args, **kwargs):
        self.calls.append(("success", args, kwargs))

    def info(self, *args, **kwargs):
        self.calls.append(("info", args, kwargs))

    def caption(self, *args, **kwargs):
        self.calls.append(("caption", args, kwargs))

    def expander(self, *args, **kwargs):
        self.calls.append(("expander", args, kwargs))
        return _Context()

    def slider(self, label, *args, **kwargs):
        self.calls.append(("slider", (label,), kwargs))
        return args[2]


def test_render_surya_ocr_settings_returns_batch_and_force_flag():
    st = FakeStreamlit()

    settings = render_surya_ocr_settings(
        st,
        description="desc",
        batch_size=16,
        force_ocr=False,
    )

    assert settings["ocr_batch_size"] == 16
    assert settings["force_ocr"] is True
    assert any(call[0] == "caption" for call in st.calls)
    assert any(call[0] == "slider" and call[2]["key"] == "ocr_batch_size" for call in st.calls)
    assert not any(call[0] == "checkbox" for call in st.calls)
