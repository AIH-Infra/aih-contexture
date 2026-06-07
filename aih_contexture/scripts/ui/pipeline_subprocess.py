from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

from aih_contexture.backends.external_config import venv_executable
from aih_contexture.runtime.subprocess_stream import run_streaming_subprocess


def pipeline_python_executable(repo_root: str | os.PathLike[str], fallback: str | None = None) -> str:
    venv_python = venv_executable(Path(repo_root) / ".venv", "python")
    if venv_python.exists():
        return str(venv_python)
    return fallback or sys.executable


def run_pipeline_file_subprocess(
    job_spec: dict[str, Any],
    *,
    repo_root: str | os.PathLike[str],
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pipeline_job.json", mode="w", encoding="utf-8") as job_file:
        json.dump(job_spec, job_file, ensure_ascii=False, indent=2)
        job_path = job_file.name

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pipeline_result.json") as result_file:
        result_path = result_file.name

    cmd = [
        pipeline_python_executable(repo_root),
        "-m",
        "aih_contexture.scripts.convert_single",
        "--pipeline_job_json",
        job_path,
        "--pipeline_result_json",
        result_path,
    ]

    if runner is None:
        proc = run_streaming_subprocess(
            cmd,
            cwd=os.fspath(repo_root),
            env=_pipeline_worker_env(),
            prefix="[Contexture Pipeline Worker]",
        )
    else:
        proc = runner(
            cmd,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=os.fspath(repo_root),
            capture_output=True,
        )

    result = None
    result_read_error = None
    try:
        if os.path.exists(result_path) and os.path.getsize(result_path) > 0:
            try:
                with open(result_path, "r", encoding="utf-8") as f:
                    result = json.load(f)
            except json.JSONDecodeError as e:
                result_read_error = f"子进程结果文件不是合法 JSON: {e}"
        else:
            result_read_error = "子进程未写入结果文件内容"
    finally:
        for temp_path in (job_path, result_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    returncode = getattr(proc, "returncode", 0)
    if result is None:
        if returncode == 0 and result_read_error:
            error_message = f"子进程未执行处理逻辑；{result_read_error}"
        elif returncode != 0 and result_read_error:
            error_message = f"子进程异常退出（返回码 {returncode}）；{result_read_error}"
        elif returncode != 0:
            error_message = f"子进程异常退出（返回码 {returncode}）"
        else:
            error_message = "子进程未生成结果文件"

        result = {
            "success": False,
            "file_name": job_spec.get("file_name"),
            "result_key": None,
            "file_outputs": [],
            "elapsed_seconds": None,
            "error": error_message,
            "traceback": "",
        }

    result["returncode"] = returncode
    result["stdout"] = getattr(proc, "stdout", None)
    result["stderr"] = getattr(proc, "stderr", None)
    return result


def _pipeline_worker_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    return env
