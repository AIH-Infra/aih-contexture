from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from aih_contexture.runtime.subprocess_stream import run_streaming_subprocess
from aih_contexture.backends.external_config import default_mineru_command


CommandRunner = Callable[..., subprocess.CompletedProcess]


@dataclass(frozen=True, slots=True)
class MineruRuntimeResult:
    command: list[str]
    output_dir: Path
    middle_json_path: Path
    stdout: str
    stderr: str


class MineruCliLayoutRuntime:
    """Run MinerU CLI and return the generated middle JSON path.

    This runtime deliberately treats MinerU as an external producer of raw JSON.
    Contexture still owns label normalization, Middle JSON validation, and final
    Markdown rendering.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        runner: CommandRunner | None = None,
    ):
        self.config = config or {}
        self.runner = runner or subprocess.run

    @property
    def command_name(self) -> str:
        return str(self.config.get("mineru_command") or default_mineru_command())

    def is_available(self) -> bool:
        command = self.command_name
        if any(separator in command for separator in ("/", "\\")):
            return Path(command).exists()
        return shutil.which(command) is not None

    def run(self, input_path: str | Path) -> MineruRuntimeResult:
        input_path = Path(input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"MinerU input file not found: {input_path}")
        if not self.is_available():
            raise RuntimeError(
                "MinerU CLI is not available. Install MinerU or set "
                "'mineru_command' to the mineru executable path before selecting "
                "the legacy full-pipeline import path."
            )

        output_dir = self._output_dir(input_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        command = self.build_command(input_path, output_dir)
        completed = self._run_command(command)
        if completed.returncode != 0:
            raise RuntimeError(
                "MinerU CLI failed with exit code "
                f"{completed.returncode}.\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
            )

        middle_json_path = self.find_middle_json(output_dir, input_path)
        return MineruRuntimeResult(
            command=command,
            output_dir=output_dir,
            middle_json_path=middle_json_path,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )

    def _run_command(self, command: list[str]) -> subprocess.CompletedProcess:
        timeout = int(self.config.get("mineru_timeout", 3600))
        if self.runner is subprocess.run and bool(self.config.get("mineru_stream_logs", True)):
            return run_streaming_subprocess(
                command,
                cwd=self.config.get("mineru_workdir") or None,
                env=self._subprocess_env(),
                timeout=timeout,
                prefix="[MinerU CLI]",
            )

        return self.runner(
            command,
            cwd=self.config.get("mineru_workdir") or None,
            env=self._subprocess_env(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def _subprocess_env(self) -> dict[str, str]:
        env = os.environ.copy()
        configured = self.config.get("mineru_env") or {}
        env.update({str(key): str(value) for key, value in configured.items()})
        env.setdefault("MINERU_MODEL_SOURCE", "modelscope")
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        return env

    def build_command(self, input_path: Path, output_dir: Path) -> list[str]:
        backend = str(self.config.get("mineru_backend") or "pipeline")
        method = str(self.config.get("mineru_method") or "txt")
        lang = str(self.config.get("mineru_lang") or "ch")
        command = [
            self.command_name,
            "-p",
            str(input_path),
            "-o",
            str(output_dir),
            "-b",
            backend,
            "-m",
            method,
            "-l",
            lang,
        ]
        if self.config.get("mineru_api_url"):
            command.extend(["--api-url", str(self.config["mineru_api_url"])])
        if self.config.get("mineru_server_url"):
            command.extend(["-u", str(self.config["mineru_server_url"])])
        start_page, end_page = self._page_window()
        if start_page is not None:
            command.extend(["-s", str(start_page)])
        if end_page is not None:
            command.extend(["-e", str(end_page)])
        if self.config.get("mineru_formula_enable") is not None:
            command.extend(["-f", _bool_arg(self.config["mineru_formula_enable"])])
        if self.config.get("mineru_table_enable") is not None:
            command.extend(["-t", _bool_arg(self.config["mineru_table_enable"])])
        if self.config.get("mineru_image_analysis") is not None:
            command.extend(["--image-analysis", _bool_arg(self.config["mineru_image_analysis"])])
        command.extend(_extra_args(self.config.get("mineru_extra_args")))
        return command

    def find_middle_json(self, output_dir: Path, input_path: Path) -> Path:
        stem = input_path.stem
        method = str(self.config.get("mineru_method") or "txt")
        backend = str(self.config.get("mineru_backend") or "pipeline")
        candidate_dirs = [output_dir / stem / method]
        if backend.startswith("hybrid"):
            candidate_dirs.insert(0, output_dir / stem / f"hybrid_{method}")
        if backend.startswith("vlm"):
            candidate_dirs.insert(0, output_dir / stem / "vlm")

        for directory in candidate_dirs:
            candidate = directory / f"{stem}_middle.json"
            if candidate.exists():
                return candidate

        matches = sorted(
            output_dir.rglob(f"{stem}_middle.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if matches:
            return matches[0]
        raise FileNotFoundError(
            f"MinerU completed but no {stem}_middle.json was found under {output_dir}."
        )

    def _output_dir(self, input_path: Path) -> Path:
        configured = self.config.get("mineru_output_dir")
        if configured:
            return Path(configured).expanduser()
        return Path(tempfile.mkdtemp(prefix=f"contexture-mineru-{input_path.stem}-"))

    def _page_window(self) -> tuple[int | None, int | None]:
        if self.config.get("mineru_start_page") is not None or self.config.get("mineru_end_page") is not None:
            start = self.config.get("mineru_start_page")
            end = self.config.get("mineru_end_page")
            return (
                int(start) if start is not None else None,
                int(end) if end is not None else None,
            )

        page_range = self.config.get("page_range")
        if page_range is None:
            return None, None
        if isinstance(page_range, range):
            pages = list(page_range)
        elif isinstance(page_range, (list, tuple)):
            pages = [int(page) for page in page_range]
        elif isinstance(page_range, str):
            pages = _parse_range(page_range)
        else:
            return None, None
        if not pages:
            return None, None
        pages = sorted(set(pages))
        if pages != list(range(pages[0], pages[-1] + 1)):
            return None, None
        return pages[0], pages[-1]


def _bool_arg(value: Any) -> str:
    return "true" if bool(value) else "false"


def _extra_args(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return shlex.split(str(value), posix=False)


def _parse_range(value: str) -> list[int]:
    pages: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        if "-" in item:
            start, end = item.split("-", 1)
            pages.extend(range(int(start), int(end) + 1))
        else:
            pages.append(int(item))
    return pages
