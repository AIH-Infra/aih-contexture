from __future__ import annotations

import gc
from collections.abc import Callable, Iterable, Iterator, MutableMapping
from typing import Any


DEFAULT_MODEL_CACHE_POLICY = "release_before_non_pipeline"
NON_PIPELINE_MODES = {"vlm_generalized", "vlm_specialized", "markdown_postprocess"}


class LazyModelDict(MutableMapping[str, Any]):
    """Mutable artifact mapping that loads heavyweight models on first access."""

    def __init__(self, factories: dict[str, Callable[[], Any]] | None = None):
        self._factories = dict(factories or {})
        self._loaded: dict[str, Any] = {}
        self._extras: dict[str, Any] = {}

    def __getitem__(self, key: str) -> Any:
        if key in self._loaded:
            return self._loaded[key]
        if key in self._extras:
            return self._extras[key]
        if key in self._factories:
            value = self._factories[key]()
            self._loaded[key] = value
            return value
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        if key in self._factories:
            self._loaded[key] = value
        else:
            self._extras[key] = value

    def __contains__(self, key: object) -> bool:
        return key in self._factories or key in self._loaded or key in self._extras

    def __delitem__(self, key: str) -> None:
        if key in self._loaded:
            del self._loaded[key]
            return
        if key in self._extras:
            del self._extras[key]
            return
        if key in self._factories:
            return
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        yield from dict.fromkeys([*self._factories, *self._extras])

    def __len__(self) -> int:
        return len(set(self._factories) | set(self._extras))

    def loaded_keys(self) -> set[str]:
        return set(self._loaded)

    def materialize_all(self) -> dict[str, Any]:
        return {key: self[key] for key in self}

    def release(self, keys: Iterable[str] | None = None) -> None:
        target_keys = list(self._loaded if keys is None else keys)
        released = False
        for key in target_keys:
            if key not in self._loaded:
                continue
            _close_resource(self._loaded.pop(key))
            released = True
        if released:
            _collect_model_memory()

    def release_all(self) -> None:
        self.release()


def prepare_for_run(job_or_mode: Any, artifact_dict: Any, *, cache_policy: str | None = None) -> None:
    """Release stale in-process models only at an actual run boundary."""

    policy = cache_policy or DEFAULT_MODEL_CACHE_POLICY
    if policy not in {"release_before_non_pipeline", "job"}:
        return
    mode = _mode_from_job_or_mode(job_or_mode)
    if mode in NON_PIPELINE_MODES:
        _release_all_if_supported(artifact_dict)


def finish_run(job_or_mode: Any, artifact_dict: Any, *, cache_policy: str | None = None) -> None:
    policy = cache_policy or DEFAULT_MODEL_CACHE_POLICY
    if policy == "job":
        _release_all_if_supported(artifact_dict)


def _mode_from_job_or_mode(job_or_mode: Any) -> str:
    if isinstance(job_or_mode, str):
        return job_or_mode
    return str(getattr(job_or_mode, "mode", "") or "")


def _release_all_if_supported(value: Any) -> None:
    release_all = getattr(value, "release_all", None)
    if callable(release_all):
        release_all()


def _close_resource(value: Any) -> None:
    close = getattr(value, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def _collect_model_memory() -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        mps = getattr(torch, "mps", None)
        empty_cache = getattr(mps, "empty_cache", None)
        if callable(empty_cache):
            empty_cache()
    except Exception:
        pass
