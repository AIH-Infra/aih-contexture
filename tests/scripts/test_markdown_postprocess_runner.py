import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from aih_contexture.scripts.ui.markdown_postprocess_runner import (
    run_markdown_postprocess_batch,
    process_mineru_json_file,
    process_middle_json_file,
    process_markdown_file,
    read_json_input,
    read_markdown_input,
    validate_markdown_llm_result,
)


class Upload:
    name = "note.md"

    def getvalue(self):
        return b"# Title\n"


class JsonUpload:
    name = "doc_middle.json"

    def getvalue(self):
        return json.dumps(
            {
                "schema_version": "contexture-middle-json/0.1",
                "source_name": "doc.pdf",
                "pages": [
                    {
                        "index": 0,
                        "anchor_start": 0,
                        "anchor_end": 1,
                        "printed_page": "7",
                        "blocks": [
                            {
                                "id": "b0",
                                "type": "Text",
                                "page_index": 0,
                                "anchor_start": 0,
                                "anchor_end": 1,
                                "order": 0,
                                "text": "Hello middle",
                                "provenance": [{"backend": "test", "stage": "layout"}],
                            },
                            {
                                "id": "m0",
                                "type": "MarginalNote",
                                "page_index": 0,
                                "anchor_start": 0,
                                "anchor_end": 1,
                                "order": 1,
                                "text": "Side note",
                                "attrs": {"side": "left"},
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ).encode("utf-8")


class MinerUJsonUpload:
    name = "paper_content_list.json"

    def getvalue(self):
        return json.dumps(
            [
                {"type": "text", "text": "Imported Title", "text_level": 1, "bbox": [10, 20, 900, 80], "page_idx": 0},
                {"type": "text", "text": "Imported body", "bbox": [10, 100, 900, 180], "page_idx": 0},
            ],
            ensure_ascii=False,
        ).encode("utf-8")


@dataclass
class Result:
    markdown: str
    metadata: dict

    def summary(self):
        return {"ok": True, "metadata": self.metadata}


class Engine:
    def __init__(self, result):
        self.result = result
        self.seen = None

    def process(self, markdown):
        self.seen = markdown
        return self.result


class FakeSt:
    def __init__(self):
        self.calls = []

    def warning(self, message):
        self.calls.append(("warning", message))

    def success(self, message):
        self.calls.append(("success", message))

    def caption(self, message):
        self.calls.append(("caption", message))


def test_read_markdown_input_supports_upload_and_folder_file(tmp_path: Path):
    folder_file = tmp_path / "folder.md"
    folder_file.write_text("folder text", encoding="utf-8")

    assert read_markdown_input(Upload(), "上传文件") == ("note.md", "# Title\n")
    assert read_markdown_input(folder_file, "选择文件夹") == ("folder.md", "folder text")


def test_read_json_input_supports_upload_and_folder_file(tmp_path: Path):
    folder_file = tmp_path / "folder_middle.json"
    folder_file.write_text('{"schema_version":"contexture-middle-json/0.1","pages":[]}', encoding="utf-8")

    assert read_json_input(JsonUpload(), "上传文件")[0] == "doc_middle.json"
    file_name, data = read_json_input(folder_file, "选择文件夹")
    assert file_name == "folder_middle.json"
    assert data["schema_version"] == "contexture-middle-json/0.1"


def test_process_markdown_file_writes_report_and_review_output(tmp_path: Path):
    engine = Engine(Result(markdown="changed", metadata={"llm": {"status": "no_review_needed"}}))

    result = process_markdown_file(
        Upload(),
        upload_mode="上传文件",
        engine=engine,
        output_dir=tmp_path,
        review_only=True,
        enable_llm=False,
    )

    assert engine.seen == "# Title\n"
    assert Path(result["report_path"]).name == "note.postprocess_report.json"
    assert Path(result["output_path"]).name == "note.page_repaired.review.md"
    assert Path(result["output_path"]).read_text(encoding="utf-8") == "# Title\n"
    assert json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))["ok"] is True
    assert result["output_paths"] == [result["report_path"], result["output_path"]]


def test_process_markdown_file_writes_repaired_output_when_not_review_only(tmp_path: Path):
    engine = Engine(Result(markdown="changed", metadata={}))

    result = process_markdown_file(
        Upload(),
        upload_mode="上传文件",
        engine=engine,
        output_dir=tmp_path,
        review_only=False,
        enable_llm=False,
    )

    assert Path(result["output_path"]).name == "note.page_repaired.md"
    assert Path(result["output_path"]).read_text(encoding="utf-8") == "changed"


def test_process_middle_json_file_rerenders_without_markdown_engine(tmp_path: Path):
    result = process_middle_json_file(
        JsonUpload(),
        upload_mode="上传文件",
        output_dir=tmp_path,
        apply_markdown_postprocess=False,
    )

    assert Path(result["output_path"]).name == "doc_middle.middle_rerendered.md"
    assert "<!-- Page: 7 -->" in Path(result["output_path"]).read_text(encoding="utf-8")
    assert "Hello middle" in Path(result["output_path"]).read_text(encoding="utf-8")
    assert Path(tmp_path / "doc_middle.middle_rerendered_middle.json").exists()
    assert not Path(tmp_path / "doc_middle.middle_rerendered_middle_report.json").exists()
    assert not Path(tmp_path / "doc_middle.middle_rerendered_middle_debug.md").exists()
    assert not Path(tmp_path / "doc_middle.middle_rerendered_middle_scholarly_report.json").exists()
    assert result["middle_validation"]["ok"] is True


def test_process_middle_json_file_honors_render_comment_options(tmp_path: Path):
    result = process_middle_json_file(
        JsonUpload(),
        upload_mode="上传文件",
        output_dir=tmp_path,
        include_printed_page_comments=False,
        include_margin_comments=False,
    )

    markdown = Path(result["output_path"]).read_text(encoding="utf-8")
    assert "<!-- Page: 7 -->" not in markdown
    assert "<!-- Margin:" not in markdown
    assert "> Side note" not in markdown
    assert "Side note" in markdown
    assert "Hello middle" in markdown


def test_process_middle_json_file_can_run_optional_markdown_postprocess(tmp_path: Path):
    engine = Engine(Result(markdown="changed after repair", metadata={}))

    result = process_middle_json_file(
        JsonUpload(),
        upload_mode="上传文件",
        output_dir=tmp_path,
        engine=engine,
        apply_markdown_postprocess=True,
        review_only=False,
        enable_llm=False,
    )

    assert "Hello middle" in engine.seen
    assert Path(result["output_path"]).name == "doc_middle.middle_rerendered.page_repaired.md"
    assert Path(result["output_path"]).read_text(encoding="utf-8") == "changed after repair"
    assert Path(result["report_path"]).name == "doc_middle.middle_rerendered.postprocess_report.json"


def test_process_mineru_json_file_imports_then_renders_contexture_middle(tmp_path: Path):
    result = process_mineru_json_file(
        MinerUJsonUpload(),
        upload_mode="上传文件",
        output_dir=tmp_path,
        apply_markdown_postprocess=False,
    )

    assert Path(result["output_path"]).name == "paper_content_list.mineru_imported.md"
    markdown = Path(result["output_path"]).read_text(encoding="utf-8")
    assert "# Imported Title" in markdown
    assert "Imported body" in markdown
    middle_path = tmp_path / "paper_content_list.mineru_imported_middle.json"
    assert middle_path.exists()
    imported_middle = json.loads(middle_path.read_text(encoding="utf-8"))
    assert imported_middle["metadata"]["import_source"] == "mineru_official_json"
    assert result["middle_validation"]["ok"] is True
    assert result["output_paths"] == [str(middle_path), result["output_path"]]


def test_run_markdown_postprocess_batch_routes_markdown_inputs(tmp_path: Path, monkeypatch):
    engine = Engine(Result(markdown="changed", metadata={"llm": {"status": "no_review_needed"}}))
    fake_st = FakeSt()
    monkeypatch.setattr(
        "aih_contexture.scripts.ui.markdown_postprocess_runner.build_markdown_postprocess_engine",
        lambda **kwargs: engine,
    )

    output_paths = run_markdown_postprocess_batch(
        st=fake_st,
        uploaded_files=[Upload()],
        upload_mode="上传文件",
        output_dir=tmp_path,
        input_kind="markdown",
        review_only=True,
        enable_llm=False,
        enable_cleanup=True,
        enable_printed_page_repair=False,
        llm_provider="openai",
        llm_base_url=None,
        llm_model=None,
        llm_api_key=None,
        llm_timeout=60,
        llm_max_retries=1,
    )

    assert Path(tmp_path / "note.page_repaired.review.md").exists()
    assert output_paths[0].endswith("note.postprocess_report.json")
    assert any(call[0] == "success" for call in fake_st.calls)


def test_run_markdown_postprocess_batch_routes_mineru_json_inputs(tmp_path: Path, monkeypatch):
    engine = Engine(Result(markdown="unused", metadata={}))
    fake_st = FakeSt()
    monkeypatch.setattr(
        "aih_contexture.scripts.ui.markdown_postprocess_runner.build_markdown_postprocess_engine",
        lambda **kwargs: engine,
    )

    output_paths = run_markdown_postprocess_batch(
        st=fake_st,
        uploaded_files=[MinerUJsonUpload()],
        upload_mode="上传文件",
        output_dir=tmp_path,
        input_kind="mineru_json",
        review_only=True,
        enable_llm=False,
        enable_cleanup=True,
        enable_printed_page_repair=False,
        llm_provider="openai",
        llm_base_url=None,
        llm_model=None,
        llm_api_key=None,
        llm_timeout=60,
        llm_max_retries=1,
    )

    assert any(path.endswith("paper_content_list.mineru_imported_middle.json") for path in output_paths)
    assert any(call == ("success", "✅ 已导入 MinerU 官方 JSON 并生成 Contexture Middle：paper_content_list.json") for call in fake_st.calls)


def test_validate_markdown_llm_result_rejects_uninvoked_llm():
    result = Result(
        markdown="",
        metadata={"llm": {"invoked": False, "status": "skipped", "provider": "openai"}},
    )

    with pytest.raises(RuntimeError, match="未真正调用模型"):
        validate_markdown_llm_result(result, enable_llm=True)


def test_validate_markdown_llm_result_rejects_unusable_invoked_response():
    result = Result(
        markdown="",
        metadata={
            "llm": {
                "invoked": True,
                "status": "invalid",
                "skipped_reason": "bad_json",
                "accepted_decision_count": 0,
            }
        },
    )

    with pytest.raises(RuntimeError, match="结果被跳过"):
        validate_markdown_llm_result(result, enable_llm=True)


def test_validate_markdown_llm_result_allows_no_review_needed_without_invocation():
    result = Result(markdown="", metadata={"llm": {"invoked": False, "status": "no_review_needed"}})

    assert validate_markdown_llm_result(result, enable_llm=True)["status"] == "no_review_needed"
