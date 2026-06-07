from aih_contexture.scripts.ui.mineru_layout_settings import (
    render_mineru_direct_layout_settings,
    render_mineru_layout_settings,
)


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeStreamlit:
    def __init__(self, session_state=None):
        self.session_state = session_state or {}
        self.calls = []

    def markdown(self, *args, **kwargs):
        self.calls.append(("markdown", args, kwargs))

    def caption(self, *args, **kwargs):
        self.calls.append(("caption", args, kwargs))

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
        return value

    def expander(self, *args, **kwargs):
        self.calls.append(("expander", args, kwargs))
        return _Context()


def test_render_mineru_layout_settings_keeps_full_pipeline_options_collapsed():
    st = FakeStreamlit()

    settings = render_mineru_layout_settings(st, description="desc")

    assert settings["mineru_backend"] == "pipeline"
    assert settings["mineru_method"] == "txt"
    assert settings["mineru_api_url"] is None
    assert settings["mineru_server_url"] is None
    assert settings["mineru_extra_args"] is None
    assert any(
        call[0] == "caption" and "这是 MinerU pipeline，不是纯版面检测" in call[1][0]
        for call in st.calls
    )
    assert any(
        call[0] == "expander"
        and call[1][0] == "MinerU CLI 实验选项"
        and call[2].get("expanded") is False
        for call in st.calls
    )
    labels = [call[1][0] for call in st.calls if call[0] in {"text_input", "selectbox"}]
    assert labels[:4] == ["MinerU CLI 命令", "CLI 解析方法", "CLI 语言", "CLI 输出目录"]


def test_render_mineru_direct_layout_settings_is_layout_only_and_restores_defaults():
    st = FakeStreamlit()

    settings = render_mineru_direct_layout_settings(st, description="desc")

    assert settings["mineru_layout_device"] is None
    assert settings["mineru_layout_batch_size"] == 1
    assert settings["mineru_layout_timeout"] == 3600
    assert settings["mineru_layout_use_paddlex_filter_boxes"] is False
    assert any(
        call[0] == "caption" and "这个后端只做 layout" in call[1][0]
        for call in st.calls
    )
    labels = [call[1][0] for call in st.calls if call[0] in {"text_input", "selectbox"}]
    assert labels[:3] == ["MinerU 外部 Python", "运行设备", "PP-DocLayoutV2 模型目录"]
