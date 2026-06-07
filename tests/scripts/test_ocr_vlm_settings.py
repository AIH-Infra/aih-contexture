from aih_contexture.scripts.ui.ocr_vlm_settings import (
    IMAGE_FORMAT_OPTIONS,
    PADDLEOCR_VL_IMAGE_FORMAT_OPTIONS,
    VLM_MODE_OPTIONS,
    count_api_keys,
    option_index,
    render_paddleocr_vl_ocr_settings,
    render_vlm_ocr_settings,
    vlm_mode_label,
)


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeStreamlit:
    def __init__(self, mode="tile", response_mode="text", api_style=None, paddle_version=None):
        self.mode = mode
        self.response_mode = response_mode
        self.api_style = api_style
        self.paddle_version = paddle_version
        self.calls = []
        self.session_state = {}

    def success(self, *args, **kwargs):
        self.calls.append(("success", args, kwargs))

    def info(self, *args, **kwargs):
        self.calls.append(("info", args, kwargs))

    def warning(self, *args, **kwargs):
        self.calls.append(("warning", args, kwargs))

    def caption(self, *args, **kwargs):
        self.calls.append(("caption", args, kwargs))

    def markdown(self, *args, **kwargs):
        self.calls.append(("markdown", args, kwargs))

    def expander(self, *args, **kwargs):
        self.calls.append(("expander", args, kwargs))
        return _Context()

    def text_input(self, label, value="", **kwargs):
        self.calls.append(("text_input", (label,), kwargs))
        key = kwargs.get("key")
        if key and key in self.session_state:
            return self.session_state[key]
        return value

    def text_area(self, label, value="", **kwargs):
        self.calls.append(("text_area", (label,), kwargs))
        return value

    def slider(self, label, *args, **kwargs):
        self.calls.append(("slider", (label,), kwargs))
        if "value" in kwargs:
            return kwargs["value"]
        return args[2]

    def number_input(self, label, **kwargs):
        self.calls.append(("number_input", (label,), kwargs))
        return kwargs["value"]

    def selectbox(self, label, options, index=0, **kwargs):
        self.calls.append(("selectbox", (label,), kwargs))
        if label == "协议风格" and self.api_style in options:
            return self.api_style
        if label == "PaddleOCR-VL 版本" and self.paddle_version in options:
            return self.paddle_version
        return options[index]

    def radio(self, label, options, index=0, **kwargs):
        self.calls.append(("radio", (label,), kwargs))
        if label == "处理模式":
            return self.mode
        if label == "返回格式":
            return self.response_mode
        return options[index]

    def checkbox(self, label, value=False, **kwargs):
        self.calls.append(("checkbox", (label,), kwargs))
        return value


def test_option_index_and_key_count_helpers():
    assert option_index(IMAGE_FORMAT_OPTIONS, "webp") == 2
    assert option_index(IMAGE_FORMAT_OPTIONS, "bad", default=1) == 1
    assert count_api_keys("a,b\nc") == 3
    assert vlm_mode_label("merge") == "区域合并"


def test_render_vlm_ocr_settings_returns_stable_keys_for_tile_mode():
    st = FakeStreamlit(mode="tile", response_mode="json")

    settings = render_vlm_ocr_settings(
        st,
        description="desc",
        layout_backend="surya",
        base_url="http://localhost:1234/v1",
        model="qwen-vl",
        api_key="a,b",
        max_concurrent=2,
        image_format="bad",
        mode="bad",
        response_mode="json",
        prompt="prompt",
        use_stop=False,
        merge_y_threshold=120,
        merge_max_blocks=20,
        full_page_max_tokens=4096,
    )

    assert settings["openai_base_url"] == "http://localhost:1234/v1"
    assert settings["openai_model"] == "qwen-vl"
    assert settings["openai_api_key"] == "a,b"
    assert settings["openai_max_concurrent"] == 2
    assert settings["openai_image_format"] == IMAGE_FORMAT_OPTIONS[0]
    assert settings["vlm_mode"] == "tile"
    assert settings["vlm_response_mode"] == "json"
    assert settings["vlm_merge_y_threshold"] == 80
    assert settings["vlm_merge_max_blocks"] == 15
    assert settings["vlm_full_page_max_tokens"] == 2048
    assert settings["use_llm"] is False
    assert settings["ocr_batch_size"] == 32
    assert any(call[0] == "caption" for call in st.calls)


def test_render_vlm_ocr_settings_keeps_merge_parameters():
    st = FakeStreamlit(mode="merge")

    settings = render_vlm_ocr_settings(
        st,
        description="desc",
        layout_backend="surya",
        base_url="url",
        model="model",
        api_key="",
        max_concurrent=1,
        image_format="png",
        mode="merge",
        response_mode="text",
        prompt="prompt",
        use_stop=True,
        merge_y_threshold=120,
        merge_max_blocks=20,
        full_page_max_tokens=4096,
    )

    assert settings["vlm_mode"] == "merge"
    assert settings["vlm_merge_y_threshold"] == 120
    assert settings["vlm_merge_max_blocks"] == 20
    assert settings["openai_use_stop"] is True


def test_render_vlm_ocr_settings_warns_for_full_page_without_layout():
    st = FakeStreamlit(mode="full_page")

    settings = render_vlm_ocr_settings(
        st,
        description="desc",
        layout_backend="none",
        base_url="url",
        model="model",
        api_key="",
        max_concurrent=1,
        image_format="png",
        mode="full_page",
        response_mode="text",
        prompt="prompt",
        use_stop=False,
        merge_y_threshold=80,
        merge_max_blocks=15,
        full_page_max_tokens=4096,
    )

    assert settings["vlm_mode"] == VLM_MODE_OPTIONS[2]
    assert settings["vlm_full_page_max_tokens"] == 4096
    assert any(call[0] == "warning" for call in st.calls)


def test_render_paddleocr_vl_ocr_settings_uses_direct_endpoint_and_paddle_keys():
    st = FakeStreamlit()

    settings = render_paddleocr_vl_ocr_settings(
        st,
        description="desc",
        endpoint="http://localhost:1234/v1",
        model="paddleocr-vl-1.5",
        api_key="lm-studio",
        api_style="openai",
        block_concurrency=4,
        image_format="JPEG",
        image_quality=90,
        crop_padding_px=4,
        crop_padding_frac=0.02,
    )

    assert settings["paddleocr_vl_endpoint"] == "http://localhost:1234/v1/chat/completions"
    assert settings["paddleocr_vl_model"] == "paddleocr-vl-1.5"
    assert settings["paddleocr_vl_api_key"] == "lm-studio"
    assert settings["paddleocr_vl_api_style"] == "openai"
    assert settings["paddleocr_vl_block_concurrency"] == 4
    assert settings["paddleocr_vl_prompt_label"] == "ocr"
    assert settings["paddleocr_vl_image_format"] == PADDLEOCR_VL_IMAGE_FORMAT_OPTIONS[0]
    assert settings["force_ocr"] is True
    assert not any(call[0] == "radio" and call[1] == ("处理模式",) for call in st.calls)
    assert not any(call[0] == "radio" and call[1] == ("返回格式",) for call in st.calls)
    assert not any(call[0] == "text_area" and call[1] == ("自定义 Prompt",) for call in st.calls)
    assert not any(call[0] == "expander" for call in st.calls)


def test_render_paddleocr_vl_ocr_settings_syncs_endpoint_and_model_from_selectors():
    st = FakeStreamlit(api_style="lmstudio-native", paddle_version="1.6")

    settings = render_paddleocr_vl_ocr_settings(
        st,
        description="desc",
        endpoint="http://localhost:1234/v1/chat/completions",
        model="paddleocr-vl-1.5",
        api_key="lm-studio",
        api_style="openai",
        block_concurrency=4,
        image_format="JPEG",
        image_quality=90,
        crop_padding_px=4,
        crop_padding_frac=0.02,
    )

    assert settings["paddleocr_vl_endpoint"] == "http://localhost:1234/api/v1/chat"
    assert settings["paddleocr_vl_version"] == "1.6"
    assert settings["paddleocr_vl_model"] == "paddleocr-vl-1.6"
    assert st.session_state["_last_paddleocr_vl_api_style"] == "lmstudio-native"
    assert st.session_state["_last_paddleocr_vl_version"] == "1.6"
