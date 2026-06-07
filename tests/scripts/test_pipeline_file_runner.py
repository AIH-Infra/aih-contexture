from pathlib import Path

from aih_contexture.scripts.ui import pipeline_file_runner as runner


class DummyCancel:
    def __init__(self, value=False):
        self.value = value

    def is_set(self):
        return self.value


def test_run_pipeline_file_builds_job_records_outputs_and_cleans_temp(monkeypatch, tmp_path: Path):
    messages = {"write": [], "info": [], "warning": [], "error": []}
    cleaned = []
    seen = {}
    input_pdf = tmp_path / "input.pdf"
    input_pdf.write_bytes(b"%PDF")

    monkeypatch.setattr(
        runner,
        "materialize_pdf_batch",
        lambda file_objects, upload_mode: ([(str(input_pdf), "input.pdf")], ["temp.pdf"]),
    )
    monkeypatch.setattr(runner, "pdf_page_count", lambda path: 3)
    monkeypatch.setattr(runner, "safe_cleanup_temp_files", lambda paths, **kwargs: cleaned.extend(paths))

    def fake_subprocess(job_spec, *, repo_root):
        seen["job_spec"] = job_spec
        seen["repo_root"] = repo_root
        return {
            "success": True,
            "file_name": "input.pdf",
            "file_outputs": [{"path": str(tmp_path / "input.md"), "format": "markdown"}],
            "elapsed_seconds": 1.25,
            "backend_summary": {
                "layout_backends": ["surya"],
                "layout_models": [],
                "ocr_backends": ["none"],
                "disable_ocr": [True],
            },
        }

    monkeypatch.setattr(runner, "run_pipeline_file_subprocess", fake_subprocess)

    result = runner.run_pipeline_file(
        object(),
        file_idx=0,
        total_files=1,
        upload_mode="上传文件",
        ctx={"processed_files": {}},
        cancel=DummyCancel(False),
        values={
            "process_mode": "强制分批",
            "batch_threshold": 1,
            "pages_per_batch": 2,
            "use_page_range": False,
            "layout_backend": "surya",
            "ocr_backend": "none",
            "use_llm": False,
        },
        output_dir=str(tmp_path),
        output_formats=["markdown"],
        repo_root="repo-root",
        config_builder=lambda params: {"page_range": params["page_range"]},
        write=messages["write"].append,
        info=messages["info"].append,
        warning=messages["warning"].append,
        error=messages["error"].append,
    )

    assert result["status"] == "success"
    assert result["output_paths"] == [str(tmp_path / "input.md")]
    assert seen["repo_root"] == "repo-root"
    assert seen["job_spec"]["file_name"] == "input.pdf"
    assert seen["job_spec"]["batch_jobs"] == [
        {"label": "1-2", "config_dict": {"page_range": "0-1"}},
        {"label": "3-3", "config_dict": {"page_range": "2-2"}},
    ]
    assert cleaned == ["temp.pdf"]
    assert any("本次实际后端计划" in item for item in messages["write"])
    assert any("子进程实际后端" in item for item in messages["info"])
    assert any("处理耗时" in item for item in messages["info"])
    assert messages["error"] == []


def test_run_pipeline_file_returns_cancelled_before_materializing(monkeypatch):
    called = {"materialize": False}

    def fail_materialize(*args, **kwargs):
        called["materialize"] = True
        raise AssertionError("should not materialize after cancellation")

    monkeypatch.setattr(runner, "materialize_pdf_batch", fail_materialize)
    warnings = []
    ctx = {}

    result = runner.run_pipeline_file(
        object(),
        file_idx=0,
        total_files=1,
        upload_mode="上传文件",
        ctx=ctx,
        cancel=DummyCancel(True),
        values={},
        output_dir="out",
        output_formats=["markdown"],
        repo_root="repo-root",
        config_builder=lambda params: params,
        warning=warnings.append,
    )

    assert result == {"status": "cancelled", "output_paths": []}
    assert ctx["status"] == "cancelled"
    assert called["materialize"] is False
    assert warnings == ["⏹ 任务已取消"]


def test_run_pipeline_file_reports_worker_failure(monkeypatch, tmp_path: Path):
    input_pdf = tmp_path / "bad.pdf"
    input_pdf.write_bytes(b"%PDF")
    errors = []

    monkeypatch.setattr(
        runner,
        "materialize_pdf_batch",
        lambda file_objects, upload_mode: ([(str(input_pdf), "bad.pdf")], []),
    )
    monkeypatch.setattr(runner, "pdf_page_count", lambda path: 1)
    monkeypatch.setattr(runner, "safe_cleanup_temp_files", lambda paths, **kwargs: None)
    monkeypatch.setattr(
        runner,
        "run_pipeline_file_subprocess",
        lambda job_spec, *, repo_root: {
            "success": False,
            "error": "worker failed",
            "stderr": "details",
            "file_outputs": [],
        },
    )

    result = runner.run_pipeline_file(
        object(),
        file_idx=0,
        total_files=1,
        upload_mode="上传文件",
        ctx={},
        cancel=DummyCancel(False),
        values={"layout_backend": "surya", "ocr_backend": "none", "use_llm": False},
        output_dir=str(tmp_path),
        output_formats=["markdown"],
        repo_root="repo-root",
        config_builder=lambda params: {"page_range": params["page_range"]},
        error=errors.append,
    )

    assert result["status"] == "failed"
    assert result["error"] == "worker failed"
    assert errors == ["处理《bad.pdf》失败: worker failed", "details"]
