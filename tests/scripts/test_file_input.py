from pathlib import Path

from aih_contexture.scripts.ui.file_input import (
    collect_folder_files,
    file_input_spec,
    render_file_input_selector,
)


class FakeStreamlit:
    def __init__(self, *, upload_mode="上传文件", folder_path="", uploaded=None):
        self.upload_mode = upload_mode
        self.folder_path = folder_path
        self.uploaded = uploaded or []
        self.calls = []

    def radio(self, *args, **kwargs):
        self.calls.append(("radio", args, kwargs))
        return self.upload_mode

    def file_uploader(self, *args, **kwargs):
        self.calls.append(("file_uploader", args, kwargs))
        return self.uploaded

    def text_input(self, *args, **kwargs):
        self.calls.append(("text_input", args, kwargs))
        return self.folder_path

    def success(self, message):
        self.calls.append(("success", message))

    def error(self, message):
        self.calls.append(("error", message))


def test_file_input_spec_separates_markdown_and_pdf_modes():
    assert file_input_spec("markdown_postprocess")["types"] == ["md", "markdown"]
    assert file_input_spec("markdown_postprocess", "mineru_json")["success_name"] == "MinerU 官方 JSON"
    assert file_input_spec("markdown_postprocess", "middle_json")["success_name"] == "Contexture Middle JSON"
    assert file_input_spec("pipeline")["types"] == ["pdf"]
    assert file_input_spec("vlm_generalized")["suffixes"] == (".pdf",)


def test_collect_folder_files_filters_case_insensitive_suffixes(tmp_path: Path):
    (tmp_path / "a.PDF").write_text("", encoding="utf-8")
    (tmp_path / "b.md").write_text("", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "c.pdf").write_text("", encoding="utf-8")

    found = collect_folder_files(str(tmp_path), (".pdf",))

    assert {Path(path).name for path in found} == {"a.PDF", "c.pdf"}


def test_render_file_input_selector_uses_stable_streamlit_keys_for_upload_mode():
    fake_st = FakeStreamlit(uploaded=["doc.pdf"])

    upload_mode, uploaded_files = render_file_input_selector(fake_st, "pipeline")

    assert upload_mode == "上传文件"
    assert uploaded_files == ["doc.pdf"]
    assert fake_st.calls[0][2]["key"] == "upload_mode_global"
    assert fake_st.calls[1][1][0] == "上传 PDF 文件"
    assert fake_st.calls[1][2]["key"] == "file_uploader_global"


def test_render_file_input_selector_reports_missing_folder():
    fake_st = FakeStreamlit(upload_mode="选择文件夹", folder_path="Z:/missing/contexture")

    upload_mode, uploaded_files = render_file_input_selector(fake_st, "markdown_postprocess")

    assert upload_mode == "选择文件夹"
    assert uploaded_files == []
    assert ("error", "文件夹路径不存在") in fake_st.calls
