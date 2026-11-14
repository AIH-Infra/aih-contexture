from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


MINERU_COMMAND_ENV = "CONTEXTURE_MINERU_COMMAND"
MINERU_PYTHON_ENV = "CONTEXTURE_MINERU_PYTHON"
MINERU_SOURCE_ROOT_ENV = "CONTEXTURE_MINERU_SOURCE_ROOT"
PADDLE_PYTHON_ENV = "CONTEXTURE_PADDLE_PYTHON"
MINERU_LAYOUT_PYTHON_ENV = "CONTEXTURE_MINERU_LAYOUT_PYTHON"
MINERU_LAYOUT_MODEL_DIR_ENV = "CONTEXTURE_MINERU_MODEL_DIR"
SCREENAI_MODEL_DIR_ENV = "CONTEXTURE_SCREENAI_MODEL_DIR"
MINERU_TOOLS_CONFIG_JSON_ENV = "MINERU_TOOLS_CONFIG_JSON"
EXPECTED_BACKEND_ENV = "CONTEXTURE_EXPECT_BACKEND"
RUNTIME_ROOT_ENV = "CONTEXTURE_RUNTIME_ROOT"

DEFAULT_RUNTIME_ROOT = Path("D:\\Runtime")
MINERU_LAYOUT_MODEL_SUBPATH = ("models", "Layout", "PP-DocLayoutV2")
MINERU_LAYOUT_MODEL_REPO = "OpenDataLab/PDF-Extract-Kit-1.0"
# Measured on ROCm/CUDA PP-DocLayoutV2: batch 4 gives ~22 pages/s versus ~19 at
# batch 1, while batch 8 adds only ~1 page/s for double the peak memory.
DEFAULT_MINERU_LAYOUT_BATCH_SIZE = 4

# The layout sidecar only needs PP-DocLayoutV2, so it can run inside the
# instance's own GPU environment instead of the shared MinerU virtualenv.
_RUNTIME_ENV_BY_BACKEND = {
    "rocm": "conda_py3.12_rocm100_torch213_contexture",
    "amd": "conda_py3.12_rocm100_torch213_contexture",
    "cuda": "conda_py3.12_cu132_torch213_contexture",
    "nvidia": "conda_py3.12_cu132_torch213_contexture",
}


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


def default_runtime_root() -> Path:
    """Return the root that holds the per-instance GPU conda environments."""

    configured = os.environ.get(RUNTIME_ROOT_ENV)
    if configured:
        return Path(configured).expanduser()
    return DEFAULT_RUNTIME_ROOT


def default_mineru_layout_python() -> str | None:
    """Resolve the interpreter for the PP-DocLayoutV2 layout sidecar only.

    The layout driver is vendored in this package and needs nothing but the
    shared PyTorch environment, so the default is this instance's own GPU
    environment, else the interpreter already running Contexture. It never
    falls back to the external MinerU environment: that one is only needed by
    the MinerU OCR and CLI paths, which resolve it via :func:`default_mineru_python`.
    """

    configured = os.environ.get(MINERU_LAYOUT_PYTHON_ENV)
    if configured:
        return configured

    runtime_python = _instance_runtime_python()
    if runtime_python:
        return runtime_python

    return sys.executable or None


def default_mineru_layout_model_dir() -> str | None:
    """Resolve local PP-DocLayoutV2 weights without importing MinerU.

    The layout driver is vendored in this package, so weights are managed by
    us: an explicit environment override wins, then the shared managed cache
    under the runtime root, then the legacy downloader caches.
    """

    configured = os.environ.get(MINERU_LAYOUT_MODEL_DIR_ENV)
    if configured:
        return str(Path(configured).expanduser())

    managed = managed_mineru_layout_model_dir()
    if _is_layout_model_dir(managed):
        return str(managed)

    for root in _mineru_pipeline_model_roots():
        candidate = root.joinpath(*MINERU_LAYOUT_MODEL_SUBPATH)
        if _is_layout_model_dir(candidate):
            return str(candidate)
    return None


def managed_mineru_layout_model_dir() -> Path:
    """Shared, Contexture-managed cache location for PP-DocLayoutV2 weights."""

    return default_runtime_root() / "contexture" / "data" / "shared" / Path(*MINERU_LAYOUT_MODEL_SUBPATH)


def ensure_mineru_layout_model_dir() -> str:
    """Return local PP-DocLayoutV2 weights, downloading into the managed cache."""

    resolved = default_mineru_layout_model_dir()
    if resolved:
        return resolved

    try:
        from modelscope import snapshot_download
    except ImportError as exc:
        raise RuntimeError(
            "PP-DocLayoutV2 weights are not cached locally and modelscope is not "
            "installed. Run 'pip install modelscope' or set CONTEXTURE_MINERU_MODEL_DIR."
        ) from exc

    shared_root = managed_mineru_layout_model_dir().parents[2]
    pattern = "/".join(MINERU_LAYOUT_MODEL_SUBPATH) + "/*"
    snapshot_download(MINERU_LAYOUT_MODEL_REPO, allow_patterns=[pattern], local_dir=str(shared_root))

    managed = managed_mineru_layout_model_dir()
    if not _is_layout_model_dir(managed):
        raise RuntimeError(f"PP-DocLayoutV2 download finished but weights are missing under {managed}.")
    return str(managed)


def _is_layout_model_dir(candidate: Path) -> bool:
    return candidate.is_dir() and (candidate / "model.safetensors").is_file() and (candidate / "config.json").is_file()


def _screenai_lib_name() -> str:
    from aih_contexture.backends.ocr.screenai._platform import LIB_NAME

    return LIB_NAME


def _newest_component_version(base: Path) -> Path | None:
    """Newest ``<base>/<version>`` directory that actually holds the library."""

    if not base.is_dir():
        return None
    for version_dir in sorted(base.iterdir(), reverse=True):
        if version_dir.is_dir() and (version_dir / _screenai_lib_name()).is_file():
            return version_dir
    return None


def default_screenai_model_dir() -> str | None:
    """Resolve a local Screen AI component directory (holds the DLL and models).

    The wrapper is vendored in this package, but the component itself is
    proprietary Google material and never distributed with us: an explicit
    environment override wins, then the shared managed cache under the
    runtime root, then locro's own install, then Chrome's component store.
    """

    configured = os.environ.get(SCREENAI_MODEL_DIR_ENV)
    if configured:
        return str(Path(configured).expanduser())

    managed = _newest_component_version(managed_screenai_root())
    if managed:
        return str(managed)

    from aih_contexture.backends.ocr.screenai._platform import default_model_dir

    local = _newest_component_version(default_model_dir())
    if local:
        return str(local)

    from aih_contexture.backends.ocr.screenai._platform import chrome_component_bases

    for base in chrome_component_bases():
        chrome = _newest_component_version(base)
        if chrome:
            return str(chrome)
    return None


def managed_screenai_root() -> Path:
    """Shared, Contexture-managed cache root for Screen AI components."""

    return default_runtime_root() / "contexture" / "data" / "shared" / "models" / "ScreenAI"


def ensure_screenai_model_dir() -> str:
    """Return a usable Screen AI component dir, materializing the managed cache.

    Unlike the MinerU weights there is no public download: Google's component
    server only serves Chrome itself. An env override is used as-is; otherwise
    the managed cache must hold the component so everything lives under our
    runtime root. When the cache is empty we copy the newest available source
    into it -- the local Chrome installation (freshest) or locro's own install
    -- after which neither is needed anymore.
    """

    configured = os.environ.get(SCREENAI_MODEL_DIR_ENV)
    if configured:
        return str(Path(configured).expanduser())

    managed = _newest_component_version(managed_screenai_root())
    if managed:
        return str(managed)

    from aih_contexture.backends.ocr.screenai._platform import chrome_component_bases, default_model_dir

    source = None
    for base in [*chrome_component_bases(), default_model_dir()]:
        source = _newest_component_version(base)
        if source:
            break
    if source is None:
        raise RuntimeError(
            "No local Screen AI component found. Install Chrome, open "
            "chrome://components, update 'Screen AI', then retry (or set "
            "CONTEXTURE_SCREENAI_MODEL_DIR to an existing component directory)."
        )

    target = managed_screenai_root() / source.name
    shutil.copytree(source, target, dirs_exist_ok=True)
    managed = _newest_component_version(managed_screenai_root())
    if managed is None:
        raise RuntimeError(f"Screen AI copy finished but the library is missing under {target}.")
    return str(managed)


def _instance_runtime_python() -> str | None:
    backend = os.environ.get(EXPECTED_BACKEND_ENV, "").strip().lower()
    env_name = _RUNTIME_ENV_BY_BACKEND.get(backend)
    if not env_name:
        return None

    root = default_runtime_root() / env_name
    for candidate in (
        root / ("python.exe" if os.name == "nt" else "bin/python"),
        root / "Scripts" / "python.exe",
        root / "bin" / "python",
    ):
        if candidate.exists():
            return str(candidate)
    return None


def _mineru_pipeline_model_roots() -> list[Path]:
    roots: list[Path] = []
    config_root = _pipeline_models_dir_from_config()
    if config_root:
        roots.append(config_root)

    home = Path.home()
    for relative in (
        Path(".cache") / "modelscope" / "hub" / "models" / "OpenDataLab" / "PDF-Extract-Kit-1___0",
        Path(".cache") / "modelscope" / "hub" / "models" / "OpenDataLab" / "PDF-Extract-Kit-1.0",
        Path(".cache") / "huggingface" / "hub" / "models--opendatalab--PDF-Extract-Kit-1.0",
    ):
        candidate = home / relative
        if candidate.is_dir():
            roots.append(candidate)

    return roots


def _pipeline_models_dir_from_config() -> Path | None:
    configured = os.environ.get(MINERU_TOOLS_CONFIG_JSON_ENV)
    config_path = Path(configured).expanduser() if configured else Path.home() / "mineru.json"
    if not config_path.is_file():
        return None

    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    models_dir = payload.get("models-dir") if isinstance(payload, dict) else None
    if not isinstance(models_dir, dict):
        return None
    pipeline_dir = models_dir.get("pipeline")
    if not pipeline_dir:
        return None

    candidate = Path(str(pipeline_dir)).expanduser()
    return candidate if candidate.is_dir() else None


def default_mineru_source_root() -> str | None:
    """Return a MinerU source checkout for sidecar PYTHONPATH injection."""

    configured = os.environ.get(MINERU_SOURCE_ROOT_ENV)
    if configured:
        return configured

    for candidate in _mineru_source_root_candidates():
        if (candidate / "mineru").exists():
            return str(candidate)

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


def mineru_project_root_from_python(python: str | os.PathLike[str] | None) -> Path | None:
    """Infer a usable MinerU source root for a sidecar Python.

    Keep the source checkout aligned with the configured virtualenv by default.
    Only an explicit CONTEXTURE_MINERU_SOURCE_ROOT may override that pairing.
    """

    configured = os.environ.get(MINERU_SOURCE_ROOT_ENV)
    if configured:
        root = Path(configured)
        if (root / "mineru").exists():
            return root

    inferred = external_project_root_from_python(python)
    if inferred and (inferred / "mineru").exists():
        return inferred
    fallback = default_mineru_source_root()
    if fallback:
        root = Path(fallback)
        if (root / "mineru").exists():
            return root
    return None


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
        venv_executable(roots[0] / "MinerU-mineru-3.4.2-released" / ".venv-mineru", "mineru"),
        venv_executable(roots[0] / "MinerU-mineru-3.2.1-released" / ".venv-mineru", "mineru"),
        venv_executable(roots[0] / "MinerU-mineru-3.1.8-released" / ".venv-mineru", "mineru"),
        venv_executable(roots[1] / "MinerU-mineru-3.4.2-released" / ".venv-mineru", "mineru"),
        venv_executable(roots[1] / "MinerU-mineru-3.2.1-released" / ".venv-mineru", "mineru"),
        venv_executable(roots[1] / "MinerU-mineru-3.1.8-released" / ".venv-mineru", "mineru"),
        venv_executable(roots[2] / "MinerU-mineru-3.4.2-released" / ".venv-mineru", "mineru"),
        venv_executable(roots[2] / "MinerU-mineru-3.2.1-released" / ".venv-mineru", "mineru"),
        venv_executable(roots[2] / "MinerU-mineru-3.1.8-released" / ".venv-mineru", "mineru"),
    ]


def _mineru_python_candidates() -> list[Path]:
    roots = _external_roots()
    return [
        venv_executable(roots[0] / "MinerU-mineru-3.4.2-released" / ".venv-mineru", "python"),
        venv_executable(roots[0] / "MinerU-mineru-3.2.1-released" / ".venv-mineru", "python"),
        venv_executable(roots[0] / "MinerU-mineru-3.1.8-released" / ".venv-mineru", "python"),
        venv_executable(roots[1] / "MinerU-mineru-3.4.2-released" / ".venv-mineru", "python"),
        venv_executable(roots[1] / "MinerU-mineru-3.2.1-released" / ".venv-mineru", "python"),
        venv_executable(roots[1] / "MinerU-mineru-3.1.8-released" / ".venv-mineru", "python"),
        venv_executable(roots[2] / "MinerU-mineru-3.4.2-released" / ".venv-mineru", "python"),
        venv_executable(roots[2] / "MinerU-mineru-3.2.1-released" / ".venv-mineru", "python"),
        venv_executable(roots[2] / "MinerU-mineru-3.1.8-released" / ".venv-mineru", "python"),
    ]


def _mineru_source_root_candidates() -> list[Path]:
    roots = _external_roots()
    versions = ("3.4.2", "3.2.1", "3.1.8")
    candidates: list[Path] = []
    for root in roots:
        for version in versions:
            candidates.append(root / f"MinerU-mineru-{version}-released")
    return candidates


def _paddle_python_candidates() -> list[Path]:
    roots = _external_roots()
    versions = ("3.7.0", "3.6.0", "3.5.0")
    candidates: list[Path] = []
    for root in roots:
        for version in versions:
            candidates.append(venv_executable(root / f"PaddleOCR-{version}" / ".venv-paddle-gpu", "python"))
    return candidates
