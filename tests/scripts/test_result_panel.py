from pathlib import Path

from aih_contexture.scripts.ui.result_panel import (
    render_process_controls,
    render_result_history,
)


class FakeColumn:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeExpander(FakeColumn):
    pass


class FakeStreamlit:
    def __init__(self, *, buttons=None, session_state=None):
        self.buttons = list(buttons or [])
        self.session_state = session_state or {}
        self.calls = []

    def columns(self, spec):
        self.calls.append(("columns", spec))
        return FakeColumn(), FakeColumn()

    def button(self, *args, **kwargs):
        self.calls.append(("button", args, kwargs))
        return self.buttons.pop(0) if self.buttons else False

    def success(self, message):
        self.calls.append(("success", message))

    def subheader(self, message):
        self.calls.append(("subheader", message))

    def download_button(self, *args, **kwargs):
        self.calls.append(("download_button", args, kwargs))

    def expander(self, *args, **kwargs):
        self.calls.append(("expander", args, kwargs))
        return FakeExpander()

    def write(self, message):
        self.calls.append(("write", message))

    def caption(self, message):
        self.calls.append(("caption", message))


def test_render_process_controls_returns_start_button_and_uses_stable_labels():
    fake_st = FakeStreamlit(buttons=[True, False])

    start_button = render_process_controls(fake_st, "pipeline", "out")

    assert start_button is True
    assert fake_st.calls[1][1][0] == "🚀 开始转换"
    assert fake_st.calls[2][1][0] == "🔄 恢复历史"


def test_render_process_controls_restores_processed_files():
    restored = {"doc": [{"format": "middle_json", "name": "doc_middle.json", "path": "x"}]}
    fake_st = FakeStreamlit(buttons=[False, True], session_state={})

    render_process_controls(fake_st, "markdown_postprocess", "out", restore_outputs=lambda _: restored)

    assert fake_st.session_state["processed_files"] == restored
    assert ("success", "已恢复 1 组文件") in fake_st.calls
    assert fake_st.calls[1][1][0] == "🚀 开始后处理"


def test_render_result_history_shows_zip_and_processed_records(tmp_path: Path):
    zip_path = tmp_path / "results.zip"
    zip_path.write_bytes(b"zip")
    fake_st = FakeStreamlit(
        session_state={
            "last_zip_path": str(zip_path),
            "last_zip_name": "custom.zip",
            "processed_files": {
                "doc": [
                    {"format": "middle_debug", "name": "doc_middle_debug.md", "path": "x"},
                    {"name": "doc.unknown", "path": "y"},
                ]
            },
        }
    )

    render_result_history(fake_st)

    download_call = next(call for call in fake_st.calls if call[0] == "download_button")
    assert download_call[2]["file_name"] == "custom.zip"
    assert download_call[2]["key"] == "download_all_persist"
    assert ("write", "**doc**") in fake_st.calls
    assert ("caption", "  └─ [middle_debug] doc_middle_debug.md") in fake_st.calls
    assert ("caption", "  └─ [file] doc.unknown") in fake_st.calls
