import zipfile
from pathlib import Path

from aih_contexture.scripts.ui.task_outputs import (
    build_zip,
    finalize_zip_outputs,
    get_output_basename,
    output_paths_from_records,
    record_processed_outputs,
    record_worker_file_outputs,
    worker_elapsed_seconds,
    worker_error_details,
)


def test_get_output_basename_includes_timestamp_and_optional_page_range(monkeypatch):
    class FakeDateTime:
        @classmethod
        def now(cls):
            class _Now:
                def strftime(self, fmt):
                    return "20260509_120000"
            return _Now()

    monkeypatch.setattr("aih_contexture.scripts.ui.task_outputs.datetime", FakeDateTime)

    assert get_output_basename("sample.pdf") == "sample_20260509_120000"
    assert get_output_basename("sample.pdf", 2, 5) == "sample_p2-5_20260509_120000"


def test_build_zip_includes_existing_files_only(tmp_path: Path):
    existing = tmp_path / "doc.md"
    missing = tmp_path / "missing.md"
    existing.write_text("hello", encoding="utf-8")
    zip_path = tmp_path / "out" / "results.zip"

    result = build_zip([existing, missing], zip_path)

    assert result == str(zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        assert zf.namelist() == ["doc.md"]
        assert zf.read("doc.md") == b"hello"


def test_build_zip_falls_back_to_timestamped_path_on_permission_error(monkeypatch, tmp_path: Path):
    existing = tmp_path / "doc.md"
    existing.write_text("hello", encoding="utf-8")
    zip_path = tmp_path / "out" / "results.zip"
    calls: list[str] = []

    def fake_write_zip(paths, current_zip_path):
        calls.append(current_zip_path)
        if len(calls) == 1:
            raise PermissionError("locked")
        return current_zip_path

    monkeypatch.setattr("aih_contexture.scripts.ui.task_outputs._write_zip", fake_write_zip)
    monkeypatch.setattr(
        "aih_contexture.scripts.ui.task_outputs.datetime",
        type(
            "FakeDateTime",
            (),
            {
                "now": classmethod(
                    lambda cls: type("FakeNow", (), {"strftime": lambda self, fmt: "20260530_120000"})()
                )
            },
        ),
    )

    result = build_zip([existing], zip_path)

    assert result == str(tmp_path / "out" / "results_20260530_120000.zip")
    assert calls == [str(zip_path), str(tmp_path / "out" / "results_20260530_120000.zip")]


def test_record_processed_outputs_writes_structured_records(tmp_path: Path):
    middle_path = tmp_path / "doc_middle.json"
    middle_path.write_text("{}", encoding="utf-8")
    ctx = {}

    records = record_processed_outputs(ctx, "doc_result", [middle_path])

    assert records == [
        {
            "format": "middle_json",
            "path": str(middle_path),
            "name": "doc_middle.json",
        }
    ]
    assert ctx["processed_files"]["doc_result"] == records


def test_output_paths_from_records_filters_missing_paths():
    records = [
        {"format": "markdown", "path": "doc.md"},
        {"format": "html"},
        {"format": "json", "path": ""},
    ]

    assert output_paths_from_records(records) == ["doc.md"]


def test_record_worker_file_outputs_preserves_worker_records():
    ctx = {}
    result = {
        "result_key": "worker-key",
        "file_outputs": [
            {"format": "markdown", "path": "doc.md", "name": "doc.md"},
        ],
    }

    result_key, records = record_worker_file_outputs(ctx, result, "fallback")

    assert result_key == "worker-key"
    assert records == [{"format": "markdown", "path": "doc.md", "name": "doc.md"}]
    assert ctx["processed_files"]["worker-key"] == records


def test_record_worker_file_outputs_uses_fallback_key():
    ctx = {}

    result_key, records = record_worker_file_outputs(ctx, {"file_outputs": []}, "fallback")

    assert result_key == "fallback"
    assert records == []
    assert ctx["processed_files"]["fallback"] == []


def test_worker_elapsed_seconds_uses_worker_value_or_clock_delta():
    assert worker_elapsed_seconds({"elapsed_seconds": 2.5}, started_at=10.0, now=20.0) == 2.5
    assert worker_elapsed_seconds({}, started_at=10.0, now=20.0) == 10.0


def test_worker_error_details_prefers_error_and_traceback():
    assert worker_error_details({"error": "bad", "traceback": "tb"}) == ("bad", "tb")
    assert worker_error_details({"stderr": "stderr"}) == ("子进程处理失败", "stderr")


def test_finalize_zip_outputs_updates_context(tmp_path: Path):
    output_path = tmp_path / "doc.md"
    output_path.write_text("markdown", encoding="utf-8")
    ctx = {}

    zip_path = finalize_zip_outputs(ctx, [output_path], tmp_path, "bundle.zip")

    assert zip_path == str(tmp_path / "bundle.zip")
    assert ctx["last_zip_path"] == zip_path
    assert ctx["last_zip_name"] == "bundle.zip"


def test_finalize_zip_outputs_ignores_empty_outputs(tmp_path: Path):
    ctx = {}

    zip_path = finalize_zip_outputs(ctx, [tmp_path / "missing.md"], tmp_path, "bundle.zip")

    assert zip_path is None
    assert ctx == {}
