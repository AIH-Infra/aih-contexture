"""Runs Indra on a PDF through a long-lived sidecar and caches per-page results.

The layout and OCR sides of one conversion share a runtime, so a page is read once. Results are kept in memory
and, when ``indra_cache_dir`` is set, on disk under a key made of the PDF content, page, mode, dpi, math and model.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

import pymupdf

from aih_contexture.backends.ocr.indra.settings import WORKER_PATH, IndraSettings, check_ready
from aih_contexture.backends.sidecar_pool import SidecarProcessSpec, SidecarRuntimePool

CACHE_VERSION = 5
_MODEL_CONTENT_SUFFIXES = {".onnx", ".npz", ".json", ".safetensors"}
_LAYOUT_MODEL_NAMES = {"det.onnx", "meta.json", "order.onnx"}
_MATH_MODEL_PREFIXES = ("math",)
_IDENTITY_CACHE_ATTR = "_contexture_indra_identity_cache"


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_fingerprint(path: Path) -> tuple[int, int, int, int, int]:
    stat = path.stat()
    return (
        int(stat.st_dev),
        int(stat.st_ino),
        int(stat.st_size),
        int(stat.st_mtime_ns),
        int(stat.st_ctime_ns),
    )


class IndraIdentityCache:
    """Task-scoped content digests, invalidated when a file changes on disk."""

    def __init__(self) -> None:
        self._digests: dict[Path, tuple[tuple[int, int, int, int, int], str]] = {}
        self._lock = threading.RLock()

    def digest(self, path: str | Path) -> str:
        resolved = Path(path).expanduser().resolve()
        with self._lock:
            for _ in range(2):
                before = _file_fingerprint(resolved)
                cached = self._digests.get(resolved)
                if cached is not None and cached[0] == before:
                    return cached[1]

                digest = _file_digest(resolved)
                after = _file_fingerprint(resolved)
                if before == after:
                    self._digests[resolved] = (after, digest)
                    return digest

            raise RuntimeError(f"File changed while computing Indra identity: {resolved}")


def _identity_cache_for_pool(pool: SidecarRuntimePool | None) -> IndraIdentityCache:
    if pool is None:
        return IndraIdentityCache()
    cache = getattr(pool, _IDENTITY_CACHE_ATTR, None)
    if cache is None:
        cache = IndraIdentityCache()
        setattr(pool, _IDENTITY_CACHE_ATTR, cache)
    return cache


class IndraRuntime:
    def __init__(self, settings: IndraSettings, *, pool: SidecarRuntimePool | None = None):
        self.settings = settings
        self._owns_pool = pool is None
        self._pool = pool if pool is not None else SidecarRuntimePool()
        self._identity_cache = _identity_cache_for_pool(pool)
        self._memory: dict[str, dict[str, Any]] = {}
        self._model_identity: str | None = None
        self.version: str | None = None
        self.last_wall_seconds: float | None = None
        self.progress_stage = "ocr"

    def close(self) -> None:
        if self._owns_pool:
            self._pool.close_all()

    def __enter__(self) -> "IndraRuntime":
        return self

    def __exit__(self, *exc) -> bool:
        self.close()
        return False

    # -- public ---------------------------------------------------------------------------------------------

    def run(self, pdf_path: str | Path, page_indices: list[int] | None = None, *, cores: int | None = None) -> dict[int, dict]:
        """Indra page dicts keyed by the page's index in ``pdf_path`` (pixel boxes at ``settings.dpi``)."""
        pdf = Path(pdf_path)
        with pymupdf.open(str(pdf)) as document:
            wanted = list(range(len(document))) if page_indices is None else sorted(set(page_indices))
            bad = [index for index in wanted if not 0 <= index < len(document)]
            if bad:
                raise ValueError(f"pages out of range (document has {len(document)}): {bad}")
        # Refresh once per run, not once per page. This also detects model files
        # replaced in-place between calls on a long-lived runtime.
        self._model_identity = self._current_model_identity()
        # Without an explicit model directory the sidecar may resolve weights
        # from a managed/download cache that this process cannot fingerprint.
        # Keep the result cache off in that case instead of risking stale pages.
        cacheable = bool(self.settings.model_dir)
        digest = self._identity_cache.digest(pdf) if cacheable else None
        found: dict[int, dict] = {}
        missing = []
        for index in wanted:
            cached = self._cache_get(digest, index) if digest is not None else None
            if cached is not None:
                found[index] = cached
            else:
                missing.append(index)
        if missing:
            for index, page in self._convert(pdf, missing, cores).items():
                found[index] = page
                if digest is not None:
                    self._cache_put(digest, index, page)
        return {index: found[index] for index in wanted}

    def info(self) -> dict[str, Any]:
        problems = check_ready(self.settings)
        if problems:
            raise RuntimeError("; ".join(problems))
        return self._pool.request(self._spec(), "info", {})

    # -- sidecar ----------------------------------------------------------------------------------------------

    def _spec(self) -> SidecarProcessSpec:
        env = dict(os.environ)
        env.setdefault("PYTHONUTF8", "1")
        if not self.settings.allow_download:
            env["HF_HUB_OFFLINE"] = "1"  # the model folder is the user's; never fetch weights behind their back
        return SidecarProcessSpec.from_parts(
            backend="indra",
            task="convert",
            command=[self.settings.interpreter(), "-X", "utf8", str(WORKER_PATH)],
            env=env,
            timeout=self.settings.timeout,
        )

    def _convert(self, pdf: Path, indices: list[int], cores: int | None) -> dict[int, dict]:
        problems = check_ready(self.settings)
        if problems:
            raise RuntimeError("Indra OCR is not ready: " + "; ".join(problems))
        if self.settings.layout_only:
            result = self._pool.request(self._spec(), "convert", {
                "pdf": str(pdf), "page_indices": indices, "layout_only": True,
                "dpi": self.settings.dpi, "cores": cores or self.settings.cores,
                "model_dir": self.settings.model_dir, "model_identity": self._model_identity,
                "progress_stage": self.progress_stage,
            })
            self.version = result.get("version") or self.version
            self.last_wall_seconds = result.get("wall_seconds")
            if len(result["pages"]) != len(indices):
                raise RuntimeError("Indra returned an incomplete layout batch")
            return {indices[page["page_num"]]: page for page in result["pages"]}
        with pymupdf.open(str(pdf)) as document:
            whole = len(indices) == len(document)
        with tempfile.TemporaryDirectory(prefix="contexture-indra-") as temp_dir:
            target = pdf
            if not whole:  # Indra reads whole files: cut the wanted pages out, keeping their text layers
                target = Path(temp_dir) / "pages.pdf"
                with pymupdf.open(str(pdf)) as source, pymupdf.open() as subset:
                    for index in indices:
                        subset.insert_pdf(source, from_page=index, to_page=index)
                    subset.save(str(target))
            result = self._pool.request(self._spec(), "convert", {
                "pdf": str(target),
                "mode": self.settings.mode,
                "dpi": self.settings.dpi,
                "math": self.settings.math,
                "cores": cores or self.settings.cores,
                "model_dir": self.settings.model_dir,
                "model_identity": self._model_identity,
                "progress_stage": self.progress_stage,
            })
        self.version = result.get("version") or self.version
        self.last_wall_seconds = result.get("wall_seconds")
        pages = result["pages"]
        if len(pages) != len(indices):
            raise RuntimeError(f"Indra returned {len(pages)} pages for {len(indices)} requested")
        return {indices[page["page_num"]]: page for page in pages}

    # -- cache ------------------------------------------------------------------------------------------------

    def _key(self, digest: str, index: int) -> str:
        s = self.settings
        if self._model_identity is None:
            raise RuntimeError("Indra cache identity has not been initialized; call run() first")
        return f"v{CACHE_VERSION}-{digest[:32]}-p{index}-{s.mode}-{s.dpi}-{int(s.math)}-{int(s.layout_only)}-{self._model_identity[:24]}"

    def _current_model_identity(self) -> str:
        """Hash local inference assets and the worker protocol without starting Indra.

        The configured sidecar may use a different Python environment, so querying
        its installed package metadata would require launching that interpreter and
        would make cache reads depend on the sidecar. The worker source digest
        covers this repository's request/result protocol; local model contents
        cover OCR, layout ordering, and math assets.
        """
        identity = hashlib.sha256()
        identity.update(f"worker:{self._identity_cache.digest(WORKER_PATH)}\n".encode("utf-8"))
        package_version = self._local_indra_version()
        identity.update(f"indra_ocr:{package_version or '<external-or-unavailable>'}\n".encode("utf-8"))
        interpreter = Path(self.settings.python or sys.executable).expanduser()
        try:
            interpreter = interpreter.resolve()
            stat = interpreter.stat()
            interpreter_stamp = f"{interpreter}:{stat.st_size}:{stat.st_mtime_ns}"
        except OSError:
            interpreter_stamp = str(interpreter)
        identity.update(f"interpreter:{interpreter_stamp}\n".encode("utf-8"))
        model_dir = Path(self.settings.model_dir).expanduser() if self.settings.model_dir else None
        model_dir_stamp = str(model_dir.resolve()) if model_dir else "<indra-managed-models>"
        identity.update(f"model_dir:{model_dir_stamp}\n".encode("utf-8"))
        model_files = self._used_model_files(model_dir)
        for path in model_files:
            identity.update(f"{path.name}:".encode("utf-8"))
            identity.update(bytes.fromhex(self._identity_cache.digest(path)))
            identity.update(b"\n")
        return identity.hexdigest()

    def _used_model_files(self, model_dir: Path | None) -> list[Path]:
        if model_dir is None or not model_dir.is_dir():
            return []
        model_files = sorted(
            (
                path for path in model_dir.iterdir()
                if path.is_file() and path.suffix.lower() in _MODEL_CONTENT_SUFFIXES
            ),
            key=lambda path: path.name.lower(),
        )
        if self.settings.layout_only:
            return [path for path in model_files if path.name.lower() in _LAYOUT_MODEL_NAMES]
        if not self.settings.math:
            return [
                path for path in model_files
                if not path.name.lower().startswith(_MATH_MODEL_PREFIXES)
            ]
        return model_files

    def _local_indra_version(self) -> str | None:
        """Return package metadata only when it belongs to the selected interpreter."""
        if self.settings.python:
            try:
                if Path(self.settings.python).expanduser().resolve() != Path(sys.executable).resolve():
                    return None
            except OSError:
                return None
        try:
            return importlib.metadata.version("indra-ocr")
        except importlib.metadata.PackageNotFoundError:
            return None

    def _cache_path(self, key: str) -> Path | None:
        # Auto-downloaded model locations/version can change without a stable
        # user-supplied identity. Keep this case within-runtime only.
        if not self.settings.cache_dir or not self.settings.model_dir:
            return None
        return Path(self.settings.cache_dir) / f"{key}.json"

    def _cache_get(self, digest: str, index: int) -> dict | None:
        key = self._key(digest, index)
        if key in self._memory:
            return self._memory[key]
        path = self._cache_path(key)
        if path is not None and path.exists():
            try:
                page = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
            self._memory[key] = page
            return page
        return None

    def _cache_put(self, digest: str, index: int, page: dict) -> None:
        key = self._key(digest, index)
        self._memory[key] = page
        path = self._cache_path(key)
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(page, ensure_ascii=False), encoding="utf-8")
            temporary.replace(path)
