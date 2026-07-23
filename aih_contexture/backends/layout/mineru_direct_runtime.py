from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from aih_contexture.backends.external_config import default_mineru_python, mineru_project_root_from_python
from aih_contexture.backends.sidecar_pool import SidecarProcessSpec, SidecarRuntimePool


class MineruDirectLayoutRuntime:
    """Run MinerU PP-DocLayoutV2 directly and return raw layout boxes."""

    def __init__(self, config: dict[str, Any] | None = None, *, sidecar_pool: SidecarRuntimePool | None = None):
        self.config = config or {}
        self.sidecar_pool = sidecar_pool
        self._selected_python: str | None = None

    @property
    def python(self) -> str:
        if self._selected_python:
            return self._selected_python
        configured = self.config.get("mineru_layout_python") or self.config.get("mineru_python")
        value = configured or self._default_python_with_fallback()
        if not value:
            raise RuntimeError(
                "MinerU direct layout requires a MinerU Python interpreter. "
                "Set 'mineru_layout_python' or CONTEXTURE_MINERU_PYTHON."
            )
        self._selected_python = str(value)
        return self._selected_python

    def _default_python_with_fallback(self) -> str | None:
        primary = default_mineru_python()
        candidates = []
        if primary:
            candidates.append(str(primary))
        current = str(sys.executable)
        if current not in candidates:
            candidates.append(current)

        for candidate in candidates:
            if self._python_can_import_layout(candidate):
                return candidate
        return primary

    def _python_can_import_layout(self, python: str) -> bool:
        try:
            completed = subprocess.run(
                [
                    str(python),
                    "-c",
                    "import torch; from mineru.model.layout.pp_doclayoutv2 import PPDocLayoutV2LayoutModel",
                ],
                cwd=Path(__file__).resolve().parents[3],
                env=self._env_for_python(str(python)),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=int(self.config.get("mineru_layout_import_timeout", 120)),
                check=False,
            )
        except Exception:
            return False
        return completed.returncode == 0

    def run(self, image_paths: list[str | Path], *, page_sizes: list[tuple[int, int]] | None = None) -> list[dict[str, Any]]:
        if not image_paths:
            return []
        runtime_mode = str(
            self.config.get("mineru_layout_runtime_mode")
            or self.config.get("sidecar_runtime_mode")
            or "oneshot"
        ).strip().lower()
        if runtime_mode in {"persistent", "auto"} and self.sidecar_pool is not None:
            try:
                return self._run_persistent(image_paths, page_sizes=page_sizes)
            except Exception:
                if runtime_mode == "persistent":
                    raise

        return self._run_oneshot(image_paths, page_sizes=page_sizes)

    def _run_oneshot(
        self,
        image_paths: list[str | Path],
        *,
        page_sizes: list[tuple[int, int]] | None = None,
    ) -> list[dict[str, Any]]:
        with tempfile.TemporaryDirectory(prefix="contexture-mineru-layout-direct-") as temp_dir:
            temp_path = Path(temp_dir)
            job_path = temp_path / "job.json"
            result_path = temp_path / "result.json"
            job_path.write_text(
                json.dumps(
                    {
                        "task": "mineru_layout_direct",
                        "image_paths": [str(path) for path in image_paths],
                        "page_sizes": page_sizes,
                        "config": self._sidecar_config(),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            command = [
                self.python,
                "-m",
                "aih_contexture.scripts.mineru_layout_direct_sidecar",
                "--job-json",
                str(job_path),
                "--result-json",
                str(result_path),
            ]
            completed = subprocess.run(
                command,
                cwd=Path(__file__).resolve().parents[3],
                env=self._env(),
                capture_output=True,
                text=True,
                timeout=int(self.config.get("mineru_layout_timeout", self.config.get("mineru_timeout", 3600))),
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    "MinerU direct layout sidecar failed with exit code "
                    f"{completed.returncode}.\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
                )
            return json.loads(result_path.read_text(encoding="utf-8"))

    def _run_persistent(
        self,
        image_paths: list[str | Path],
        *,
        page_sizes: list[tuple[int, int]] | None = None,
    ) -> list[dict[str, Any]]:
        if self.sidecar_pool is None:
            raise RuntimeError("Persistent MinerU layout requires a SidecarRuntimePool.")
        command = [
            self.python,
            "-m",
            "aih_contexture.scripts.mineru_layout_direct_sidecar",
            "--persistent",
        ]
        timeout = int(self.config.get("mineru_layout_timeout", self.config.get("mineru_timeout", 3600)))
        spec = SidecarProcessSpec.from_parts(
            backend="mineru_pp_doclayout_v2_direct",
            task="layout",
            command=command,
            cwd=Path(__file__).resolve().parents[3],
            env=self._env(),
            timeout=timeout,
        )
        result = self.sidecar_pool.request(
            spec,
            "layout",
            {
                "image_paths": [str(path) for path in image_paths],
                "page_sizes": page_sizes,
                "config": self._sidecar_config(),
            },
        )
        return list(result or [])

    def _sidecar_config(self) -> dict[str, Any]:
        return {
            str(key): value
            for key, value in self.config.items()
            if not str(key).startswith("_")
        }

    def _env(self) -> dict[str, str]:
        return self._env_for_python(self.python)

    def _env_for_python(self, python: str) -> dict[str, str]:
        env = os.environ.copy()
        repo_root = str(Path(__file__).resolve().parents[3])
        existing = env.get("PYTHONPATH")
        python_paths = [repo_root]
        external_root = mineru_project_root_from_python(python)
        if external_root:
            python_paths.append(str(external_root))
        if existing:
            python_paths.append(existing)
        env["PYTHONPATH"] = os.pathsep.join(python_paths)
        configured = self.config.get("mineru_env") or {}
        env.update({str(key): str(value) for key, value in configured.items()})
        env.setdefault("MINERU_MODEL_SOURCE", "modelscope")
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        return env
