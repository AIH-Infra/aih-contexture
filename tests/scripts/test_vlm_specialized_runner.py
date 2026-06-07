from pathlib import Path
from uuid import uuid4

from aih_contexture.scripts.ui.vlm_specialized_runner import run_vlm_specialized_batch


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


class FakeCrashError(Exception):
    pass


class FakeOcrConverter:
    instances: list["FakeOcrConverter"] = []

    def __init__(self, config, progress_callback=None):
        self.config = config
        self.progress_callback = progress_callback
        self.index = len(FakeOcrConverter.instances)
        self._last_chunks = [[{"label": "Text", "content": "A"}]]
        self._last_clean_html_pages = ["<p>A</p>"]
        self._last_xml_pages = ["<page>A</page>"]
        FakeOcrConverter.instances.append(self)

    async def __call__(self, file_path, semaphore):
        if self.index == 1:
            raise FakeCrashError("boom")
        if self.progress_callback is not None:
            self.progress_callback({"event": "pages_loaded", "total_pages": 1})
            self.progress_callback({"event": "page_done", "page_num": 1, "ok": True})
        return "{0}\nA\n{1}"


def _make_output_dir(name: str) -> Path:
    output_dir = Path(".tmp") / "vlm_specialized_runner" / name / uuid4().hex
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _base_config():
    return {
        "ocr_backend": "churro",
        "ocr_endpoint": "http://localhost:1234/api/v1/chat",
        "ocr_model": "churro-3b",
        "ocr_api_key": "test-key",
        "ocr_api_style": "lmstudio-native",
        "ocr_concurrency": 1,
        "ocr_batch_size": 1,
        "ocr_batch_rest": 0,
        "ocr_max_retries": 1,
        "ocr_resize_max": 1024,
        "ocr_image_format": "JPEG",
        "ocr_image_quality": 60,
        "ocr_timeout": 30,
        "ocr_max_tokens": 4096,
        "enable_page_anchors": True,
        "page_anchor_position": "before",
        "extract_printed_pages": True,
        "custom_id_source": "none",
        "custom_id_data": None,
        "ocr_noise_removal": True,
        "ocr_noise_patterns": "",
        "ocr_footnote_fix": True,
        "ocr_hyphenation_fix": True,
        "ocr_filter_page_header": False,
        "ocr_filter_page_footer": False,
        "emit_middle_json": False,
        "emit_middle_report": False,
        "emit_middle_debug": False,
        "emit_middle_scholarly": False,
        "emit_middle_scholarly_report": False,
        "emit_layout_overlay": False,
        "emit_span_overlay": False,
    }


def test_run_vlm_specialized_batch_writes_outputs_and_zip(monkeypatch):
    FakeOcrConverter.instances = []
    monkeypatch.setattr(
        "aih_contexture.scripts.ui.vlm_specialized_runner.build_vlm_specialized_config",
        lambda values, output_formats: {
            "ocr_backend": values.get("ocr_backend", "churro"),
            "ocr_endpoint": values.get("ocr_endpoint"),
            "ocr_model": values.get("ocr_model"),
            "ocr_api_key": values.get("ocr_api_key"),
            "ocr_output_format": "xml",
            "final_output_formats": list(output_formats),
        },
    )
    monkeypatch.setattr(
        "aih_contexture.scripts.ui.vlm_specialized_runner.OcrDirectAsyncConverter",
        FakeOcrConverter,
    )

    st = FakeStreamlit()
    ctx = {"status": "running"}
    output_dir = _make_output_dir("success")
    result = run_vlm_specialized_batch(
        st=st,
        uploaded_files=[FakeUploadedFile("doc.pdf", b"fake pdf bytes")],
        upload_mode="上传文件",
        output_dir=output_dir,
        config_values=_base_config(),
        output_formats=["markdown", "json", "xml"],
        vlm_use_page_range=False,
        vlm_start_page=None,
        vlm_end_page=None,
        vlm_concurrency_mode="serial_file",
        ocr_total_concurrent=1,
        ocr_max_concurrent_files=1,
        ocr_batch_rest=0,
        emit_middle_json=False,
        emit_middle_report=False,
        emit_middle_debug=False,
        emit_middle_scholarly=False,
        emit_middle_scholarly_report=False,
        emit_layout_overlay=False,
        emit_span_overlay=False,
        ctx=ctx,
    )

    assert result == {"crashed": False, "paused": False}
    assert ctx["status"] == "done"
    assert (output_dir / "ocr_direct_results.zip").exists()
    records = next(iter(ctx["processed_files"].values()))
    assert any(record["name"].endswith(".md") for record in records)
    assert any(kind == "success" for kind, _ in st.events)


def test_run_vlm_specialized_batch_records_pause_state_on_model_crash(monkeypatch):
    FakeOcrConverter.instances = []
    monkeypatch.setattr(
        "aih_contexture.scripts.ui.vlm_specialized_runner.build_vlm_specialized_config",
        lambda values, output_formats: {
            "ocr_backend": values.get("ocr_backend", "churro"),
            "ocr_endpoint": values.get("ocr_endpoint"),
            "ocr_model": values.get("ocr_model"),
            "ocr_api_key": values.get("ocr_api_key"),
            "ocr_output_format": "xml",
            "final_output_formats": list(output_formats),
        },
    )
    monkeypatch.setattr(
        "aih_contexture.scripts.ui.vlm_specialized_runner.OcrDirectAsyncConverter",
        FakeOcrConverter,
    )
    monkeypatch.setattr(
        "aih_contexture.services.ocr_chandra.ModelCrashError",
        FakeCrashError,
    )

    st = FakeStreamlit()
    ctx = {"status": "running"}
    output_dir = _make_output_dir("crash")
    result = run_vlm_specialized_batch(
        st=st,
        uploaded_files=[
            FakeUploadedFile("doc-a.pdf", b"fake pdf bytes"),
            FakeUploadedFile("doc-b.pdf", b"fake pdf bytes"),
        ],
        upload_mode="上传文件",
        output_dir=output_dir,
        config_values=_base_config(),
        output_formats=["markdown", "json", "xml"],
        vlm_use_page_range=False,
        vlm_start_page=None,
        vlm_end_page=None,
        vlm_concurrency_mode="serial_file",
        ocr_total_concurrent=1,
        ocr_max_concurrent_files=1,
        ocr_batch_rest=0,
        emit_middle_json=False,
        emit_middle_report=False,
        emit_middle_debug=False,
        emit_middle_scholarly=False,
        emit_middle_scholarly_report=False,
        emit_layout_overlay=False,
        emit_span_overlay=False,
        ctx=ctx,
    )

    assert result == {"crashed": True, "paused": True}
    assert ctx["status"] == "error"
    assert ctx["ocr_paused"] is True
    assert ctx["ocr_pause_info"]["all_output_paths_for_zip"]
    assert any(kind == "error" for kind, _ in st.events)
