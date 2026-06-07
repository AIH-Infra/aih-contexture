from __future__ import annotations

import os
import shutil
from pathlib import Path


MINERU_COMMAND_ENV = "CONTEXTURE_MINERU_COMMAND"
MINERU_PYTHON_ENV = "CONTEXTURE_MINERU_PYTHON"
PADDLE_PYTHON_ENV = "CONTEXTURE_PADDLE_PYTHON"


def default_mineru_command() -> str:
    """Resolve the MinerU command without baking a local path into releases."""

    configured = os.environ.get(MINERU_COMMAND_ENV)
    if configured:
        return configured

    on_path = shutil.which("mineru")
    if on_path:
        return on_path

    for sibling in _mineru_command_candidates():
        if sibling.exists():
            return str(sibling)

    return "mineru"


def default_paddle_python() -> str | None:
    """Return an optional external Paddle Python for future sidecar use."""

    configured = os.environ.get(PADDLE_PYTHON_ENV)
    if configured:
        return configured

    for sibling in _paddle_python_candidates():
        if sibling.exists():
            return str(sibling)

    return None


def default_mineru_python() -> str | None:
    """Return an optional external MinerU Python for direct model sidecars."""

    configured = os.environ.get(MINERU_PYTHON_ENV)
    if configured:
        return configured

    command = default_mineru_command()
    command_path = Path(command)
    if command_path.name.lower() in {"mineru.exe", "mineru"}:
        executable = "python.exe" if os.name == "nt" else "python"
        sibling = command_path.with_name(executable)
        if sibling.exists():
            return str(sibling)

    for sibling in _mineru_python_candidates():
        if sibling.exists():
            return str(sibling)

    return None


def venv_executable(venv_dir: str | os.PathLike[str], executable: str, *, os_name: str | None = None) -> Path:
    """Return the platform-native executable path inside a virtualenv."""

    platform_name = os_name or os.name
    scripts_dir = "Scripts" if platform_name == "nt" else "bin"
    suffix = ".exe" if platform_name == "nt" and not executable.lower().endswith(".exe") else ""
    return Path(venv_dir) / scripts_dir / f"{executable}{suffix}"


def external_project_root_from_python(python: str | os.PathLike[str] | None) -> Path | None:
    """Infer the source checkout that owns a configured sidecar virtualenv."""

    if not python:
        return None
    python_path = Path(python)
    parts = python_path.parts
    for marker in (".venv-mineru", ".venv-paddle-gpu", ".venv", "venv"):
        if marker in parts:
            marker_index = parts.index(marker)
            if marker_index > 0:
                root = Path(*parts[:marker_index])
                if root.exists():
                    return root
    try:
        candidate = python_path.parents[2]
    except IndexError:
        return None
    return candidate if candidate.exists() else None


def _infra_root() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root.parent


def _external_roots() -> list[Path]:
    root = _infra_root()
    return [
        root / "aih-contexture-reference",
        root / "reference",
        root,
    ]


def _mineru_command_candidates() -> list[Path]:
    roots = _external_roots()
    return [
        venv_executable(roots[0] / "MinerU-mineru-3.2.1-released" / ".venv-mineru", "mineru"),
        venv_executable(roots[0] / "MinerU-mineru-3.1.8-released" / ".venv-mineru", "mineru"),
        venv_executable(roots[1] / "MinerU-mineru-3.2.1-released" / ".venv-mineru", "mineru"),
        venv_executable(roots[1] / "MinerU-mineru-3.1.8-released" / ".venv-mineru", "mineru"),
        venv_executable(roots[2] / "MinerU-mineru-3.2.1-released" / ".venv-mineru", "mineru"),
        venv_executable(roots[2] / "MinerU-mineru-3.1.8-released" / ".venv-mineru", "mineru"),
    ]


def _mineru_python_candidates() -> list[Path]:
    roots = _external_roots()
    return [
        venv_executable(roots[0] / "MinerU-mineru-3.2.1-released" / ".venv-mineru", "python"),
        venv_executable(roots[0] / "MinerU-mineru-3.1.8-released" / ".venv-mineru", "python"),
        venv_executable(roots[1] / "MinerU-mineru-3.2.1-released" / ".venv-mineru", "python"),
        venv_executable(roots[1] / "MinerU-mineru-3.1.8-released" / ".venv-mineru", "python"),
        venv_executable(roots[2] / "MinerU-mineru-3.2.1-released" / ".venv-mineru", "python"),
        venv_executable(roots[2] / "MinerU-mineru-3.1.8-released" / ".venv-mineru", "python"),
    ]


def _paddle_python_candidates() -> list[Path]:
    roots = _external_roots()
    return [
        venv_executable(roots[0] / "PaddleOCR-3.6.0" / ".venv-paddle-gpu", "python"),
        venv_executable(roots[0] / "PaddleOCR-3.5.0" / ".venv-paddle-gpu", "python"),
        venv_executable(roots[1] / "PaddleOCR-3.6.0" / ".venv-paddle-gpu", "python"),
        venv_executable(roots[1] / "PaddleOCR-3.5.0" / ".venv-paddle-gpu", "python"),
        venv_executable(roots[2] / "PaddleOCR-3.6.0" / ".venv-paddle-gpu", "python"),
        venv_executable(roots[2] / "PaddleOCR-3.5.0" / ".venv-paddle-gpu", "python"),
    ]
