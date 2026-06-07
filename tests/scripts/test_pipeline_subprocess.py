import json
import os
import subprocess
from pathlib import Path

from aih_contexture.scripts.ui.pipeline_subprocess import (
    _pipeline_worker_env,
    pipeline_python_executable,
    run_pipeline_file_subprocess,
)


def test_pipeline_python_executable_prefers_local_venv(tmp_path):
    venv_python = tmp_path / ".venv" / "Scripts" / "python.exe"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("", encoding="utf-8")

    assert pipeline_python_executable(tmp_path, fallback="fallback-python") == str(venv_python)


def test_pipeline_python_executable_prefers_posix_local_venv(monkeypatch, tmp_path):
    venv_python = tmp_path / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "aih_contexture.scripts.ui.pipeline_subprocess.venv_executable",
        lambda venv_dir, executable: Path(venv_dir) / "bin" / executable,
    )

    assert pipeline_python_executable(tmp_path, fallback="fallback-python") == str(venv_python)


def test_pipeline_python_executable_uses_fallback_without_venv(tmp_path):
    assert pipeline_python_executable(tmp_path, fallback="fallback-python") == "fallback-python"


def test_pipeline_worker_env_forces_utf8(monkeypatch):
    monkeypatch.delenv("PYTHONIOENCODING", raising=False)
    monkeypatch.delenv("PYTHONUTF8", raising=False)

    env = _pipeline_worker_env()

    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["PYTHONUTF8"] == "1"


def test_run_pipeline_file_subprocess_reads_result_and_cleans_temp_files(tmp_path):
    seen = {}

    def fake_runner(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs
        job_path = Path(cmd[cmd.index("--pipeline_job_json") + 1])
        result_path = Path(cmd[cmd.index("--pipeline_result_json") + 1])
        seen["job_path"] = job_path
        seen["result_path"] = result_path
        with open(job_path, "r", encoding="utf-8") as f:
            seen["job"] = json.load(f)
        result_path.write_text(
            json.dumps({"success": True, "file_name": "sample.pdf", "file_outputs": []}, ensure_ascii=False),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0)

    result = run_pipeline_file_subprocess(
        {"file_name": "sample.pdf", "batch_jobs": []},
        repo_root=tmp_path,
        runner=fake_runner,
    )

    assert result["success"] is True
    assert result["file_name"] == "sample.pdf"
    assert result["returncode"] == 0
    assert result["stdout"] is None
    assert result["stderr"] is None
    assert seen["job"]["file_name"] == "sample.pdf"
    assert seen["kwargs"]["cwd"] == os.fspath(tmp_path)
    assert seen["kwargs"]["capture_output"] is True
    assert seen["kwargs"]["text"] is True
    assert "-m" in seen["cmd"]
    assert "aih_contexture.scripts.convert_single" in seen["cmd"]
    assert not os.path.exists(seen["job_path"])
    assert not os.path.exists(seen["result_path"])


def test_run_pipeline_file_subprocess_reports_empty_result_file(tmp_path):
    def fake_runner(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0)

    result = run_pipeline_file_subprocess(
        {"file_name": "sample.pdf", "batch_jobs": []},
        repo_root=tmp_path,
        runner=fake_runner,
    )

    assert result["success"] is False
    assert result["file_name"] == "sample.pdf"
    assert result["returncode"] == 0
    assert "子进程未执行处理逻辑" in result["error"]


def test_run_pipeline_file_subprocess_reports_nonzero_without_result(tmp_path):
    def fake_runner(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 7)

    result = run_pipeline_file_subprocess(
        {"file_name": "bad.pdf", "batch_jobs": []},
        repo_root=tmp_path,
        runner=fake_runner,
    )

    assert result["success"] is False
    assert result["file_name"] == "bad.pdf"
    assert result["returncode"] == 7
    assert "返回码 7" in result["error"]
