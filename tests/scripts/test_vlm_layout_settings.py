from aih_contexture.scripts.ui.vlm_layout_settings import (
    IMAGE_FORMAT_OPTIONS,
    PROMPT_TEMPLATE_OPTIONS,
    count_api_keys,
    option_index,
    render_vlm_layout_settings,
)


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeStreamlit:
    def __init__(self, prompt_mode="使用预制模板"):
        self.prompt_mode = prompt_mode
        self.calls = []

    def success(self, *args, **kwargs):
        self.calls.append(("success", args, kwargs))

    def info(self, *args, **kwargs):
        self.calls.append(("info", args, kwargs))

    def caption(self, *args, **kwargs):
        self.calls.append(("caption", args, kwargs))

    def divider(self):
        self.calls.append(("divider", (), {}))

    def expander(self, *args, **kwargs):
        self.calls.append(("expander", args, kwargs))
        return _Context()

    def columns(self, count):
        return [_Context() for _ in range(count)]

    def text_input(self, label, value="", **kwargs):
        self.calls.append(("text_input", (label,), kwargs))
        return value

    def text_area(self, label, value="", **kwargs):
        self.calls.append(("text_area", (label,), kwargs))
        return value

    def slider(self, label, **kwargs):
        self.calls.append(("slider", (label,), kwargs))
        return kwargs["value"]

    def number_input(self, label, **kwargs):
        self.calls.append(("number_input", (label,), kwargs))
        return kwargs["value"]

    def selectbox(self, label, options, index=0, **kwargs):
        self.calls.append(("selectbox", (label,), kwargs))
        return options[index]

    def radio(self, label, options, index=0, **kwargs):
        self.calls.append(("radio", (label,), kwargs))
        return self.prompt_mode


def test_option_index_uses_default_for_unknown_value():
    assert option_index(IMAGE_FORMAT_OPTIONS, "png") == 1
    assert option_index(IMAGE_FORMAT_OPTIONS, "bad", default=2) == 2


def test_count_api_keys_accepts_commas_and_newlines():
    assert count_api_keys("") == 0
    assert count_api_keys("a,b\nc") == 3


def test_render_vlm_layout_settings_returns_stable_keys_for_template_mode():
    st = FakeStreamlit()

    settings = render_vlm_layout_settings(
        st,
        description="desc",
        base_url="http://localhost:1234/v1",
        model="qwen-vl",
        api_key="a,b",
        max_concurrent=2,
        image_format="bad",
        max_image_dimension=2048,
        jpeg_quality=85,
        timeout=120,
        prompt_template="modern",
        prompt="custom",
    )

    assert settings["vlm_layout_base_url"] == "http://localhost:1234/v1"
    assert settings["vlm_layout_model"] == "qwen-vl"
    assert settings["vlm_layout_api_key"] == "a,b"
    assert settings["vlm_layout_max_concurrent"] == 2
    assert settings["vlm_layout_image_format"] == IMAGE_FORMAT_OPTIONS[0]
    assert settings["vlm_layout_prompt_template"] == "modern"
    assert settings["vlm_layout_prompt"] == ""
    assert any(call[0] == "info" for call in st.calls)


def test_render_vlm_layout_settings_custom_prompt_mode_clears_template():
    st = FakeStreamlit(prompt_mode="自定义提示词")

    settings = render_vlm_layout_settings(
        st,
        description="desc",
        base_url="url",
        model="model",
        api_key="",
        max_concurrent=1,
        image_format="png",
        max_image_dimension=1024,
        jpeg_quality=80,
        timeout=60,
        prompt_template="modern",
        prompt="custom prompt",
    )

    assert settings["vlm_layout_prompt_template"] == ""
    assert settings["vlm_layout_prompt"] == "custom prompt"
