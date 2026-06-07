from pathlib import Path
from uuid import uuid4

from aih_contexture.scripts.ui.vlm_generalized_runner import run_vlm_generalized_batch


class FakeUploadedFile:
    def __init__(self, name: str, content: bytes):
        self.name = name
        self._content = content

    def getvalue(self) -> bytes:
        return self._content


class FakeStreamlit:
    def __init__(self):
        self.events: list[tuple[str, str]] = []

    def info(self, message):
        self.events.append(("info", str(message)))

    def write(self, message):
        self.events.append(("write", str(message)))

    def warning(self, message):
        self.events.append(("warning", str(message)))

    def error(self, message):
        self.events.append(("error", str(message)))

    def success(self, message):
        self.events.append(("success", str(message)))


class FakeVlmConverter:
    instances: list["FakeVlmConverter"] = []

    def __init__(self, config, progress_callback=None):
        self.config = config
        self.progress_callback = progress_callback
        self._last_json_pages = ['{"page": 1}']
        self._last_clean_html_pages = ["<h1>page</h1>"]
        FakeVlmConverter.instances.append(self)

    async def convert_async(self, file_path, semaphore):
        assert Path(file_path).exists()
        if self.progress_callback is not None:
            self.progress_callback({"event": "pages_loaded", "total_pages": 1})
            self.progress_callback({"event": "page_done", "page_num": 1, "ok": True})
        return "{0}\n# Page\n{1}"


def _base_config():
    return {
        "selected_template_id": None,
        "selected_preset": "高准确性（默认）",
        "vlm_api_provider": "openai",
        "vlm_direct_base_url": "http://localhost:1234/v1",
        "vlm_direct_model": "demo",
        "vlm_direct_api_key": "test-key",
        "vlm_direct_max_concurrent": 1,
        "vlm_direct_image_format": "JPEG",
        "vlm_direct_max_image_dimension": 1024,
        "vlm_direct_jpeg_quality": 60,
        "vlm_direct_timeout": 30,
        "vlm_direct_max_retries": 1,
        "vlm_auto_repair_failed_pages": False,
        "vlm_repair_max_concurrent": 1,
        "vlm_repair_rounds": 1,
        "vlm_direct_enable_page_anchors": True,
        "vlm_direct_page_anchor_position": "before",
        "vlm_direct_extract_printed_pages": True,
        "vlm_direct_printed_page_patterns": None,
        "vlm_direct_custom_id_source": "none",
        "vlm_direct_custom_id_data": None,
        "emit_middle_json": False,
        "emit_middle_report": False,
        "emit_middle_debug": False,
        "emit_middle_scholarly": False,
        "emit_middle_scholarly_report": False,
        "emit_layout_overlay": False,
        "emit_span_overlay": False,
    }


def _make_output_dir(name: str) -> Path:
    output_dir = Path(".tmp") / "vlm_generalized_runner" / name / uuid4().hex
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def test_run_vlm_generalized_batch_writes_outputs_and_zip(monkeypatch):
    monkeypatch.setattr(
        "aih_contexture.scripts.ui.vlm_generalized_runner.VlmDirectAsyncConverter",
        FakeVlmConverter,
    )

    st = FakeStreamlit()
    ctx = {"status": "running"}
    output_dir = _make_output_dir("success")
    output_paths = run_vlm_generalized_batch(
        st=st,
        uploaded_files=[FakeUploadedFile("doc.pdf", b"fake pdf bytes")],
        upload_mode="上传文件",
        output_dir=output_dir,
        config_values=_base_config(),
        output_formats=["markdown", "json"],
        vlm_use_page_range=False,
        vlm_start_page=None,
        vlm_end_page=None,
        vlm_concurrency_mode="serial_file",
        vlm_direct_total_concurrent=1,
        vlm_direct_max_concurrent_files=1,
        vlm_batch_rest=0,
        emit_middle_json=False,
        emit_middle_report=False,
        emit_middle_debug=False,
        emit_middle_scholarly=False,
        emit_middle_scholarly_report=False,
        emit_layout_overlay=False,
        emit_span_overlay=False,
        ctx=ctx,
    )

    assert ctx["status"] == "done"
    assert (output_dir / "vlm_direct_results.zip").exists()
    assert any(path.endswith(".md") for path in output_paths)
    assert any(path.endswith(".json") for path in output_paths)
    assert any(kind == "success" for kind, _ in st.events)


def test_run_vlm_generalized_batch_rejects_invalid_single_page_inputs():
    st = FakeStreamlit()
    ctx = {}
    output_dir = _make_output_dir("invalid")
    output_paths = run_vlm_generalized_batch(
        st=st,
        uploaded_files=[FakeUploadedFile("doc.pdf", b"not a pdf")],
        upload_mode="上传文件",
        output_dir=output_dir,
        config_values=_base_config(),
        output_formats=["markdown"],
        vlm_use_page_range=False,
        vlm_start_page=None,
        vlm_end_page=None,
        vlm_concurrency_mode="batch_single_page",
        vlm_direct_total_concurrent=1,
        vlm_direct_max_concurrent_files=1,
        vlm_batch_rest=0,
        emit_middle_json=False,
        emit_middle_report=False,
        emit_middle_debug=False,
        emit_middle_scholarly=False,
        emit_middle_scholarly_report=False,
        emit_layout_overlay=False,
        emit_span_overlay=False,
        ctx=ctx,
    )

    assert output_paths == []
    assert ctx["status"] == "failed"
    assert any("必须是 1 页 PDF" in message for kind, message in st.events if kind == "error")
