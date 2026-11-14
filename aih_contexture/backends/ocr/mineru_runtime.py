from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

class MineruPytorchPaddleOcrRuntime:
    """Run the vendored Paddle OCR Torch core in Contexture's own environment."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    @property
    def python(self) -> str:
        # Keep explicit interpreter overrides for saved configurations, but do
        # not discover an external MinerU installation for an internal model.
        value = (
            self.config.get("mineru_ocr_python")
            or self.config.get("mineru_python")
            or os.environ.get("CONTEXTURE_MINERU_OCR_PYTHON")
            or sys.executable
        )
        if not value:
            raise RuntimeError(
                "Paddle OCR Torch requires the Python interpreter running Contexture."
            )
        return str(value)

    def run(self, image_paths: list[str | Path], *, page_sizes: list[tuple[int, int]] | None = None) -> list[dict[str, Any]]:
        if not image_paths:
            return []

        with tempfile.TemporaryDirectory(prefix="contexture-mineru-ocr-") as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "job.json"
            result_path = temp_path / "result.json"
            job_path.write_text(
                json.dumps(
                    {
                        "task": "mineru_pytorch_paddle_ocr",
                        "image_paths": [str(path) for path in image_paths],
                        "page_sizes": page_sizes,
                        "config": {key: value for key, value in self.config.items() if not str(key).startswith("_")},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    self.python,
                    "-m",
                    "aih_contexture.scripts.mineru_ocr_sidecar",
                    "--job-json",
                    str(job_path),
                    "--result-json",
                    str(result_path),
                ],
                cwd=Path(__file__).resolve().parents[3],
                env=self._env(),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=int(self.config.get("mineru_ocr_timeout", self.config.get("mineru_timeout", 3600))),
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    "MinerU OCR sidecar failed with exit code "
                    f"{completed.returncode}.\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
                )
            return json.loads(result_path.read_text(encoding="utf-8"))

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        repo_root = str(Path(__file__).resolve().parents[3])
        existing = env.get("PYTHONPATH")
        python_paths = [repo_root]
        if existing:
            python_paths.append(existing)
        env["PYTHONPATH"] = os.pathsep.join(python_paths)
        configured = self.config.get("mineru_env") or {}
        env.update({str(key): str(value) for key, value in configured.items()})
        if self.config.get("mineru_ocr_device"):
            env["MINERU_DEVICE_MODE"] = str(self.config["mineru_ocr_device"])
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        return env
