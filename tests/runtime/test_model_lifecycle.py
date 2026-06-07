from __future__ import annotations

from aih_contexture.models import create_model_dict
from aih_contexture.runtime.model_lifecycle import LazyModelDict, finish_run, prepare_for_run


class Closeable:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class Job:
    def __init__(self, mode: str):
        self.mode = mode


def test_lazy_model_dict_does_not_load_until_access():
    calls = []
    models = LazyModelDict({"layout_model": lambda: calls.append("layout") or object()})

    assert calls == []
    assert "layout_model" in models
    assert calls == []


def test_create_model_dict_returns_unloaded_lazy_mapping():
    models = create_model_dict()

    assert isinstance(models, LazyModelDict)
    assert models.loaded_keys() == set()
    assert "layout_model" in models


def test_lazy_model_dict_loads_only_requested_key():
    calls = []
    models = LazyModelDict(
        {
            "layout_model": lambda: calls.append("layout") or "layout",
            "recognition_model": lambda: calls.append("recognition") or "recognition",
        }
    )

    assert models["recognition_model"] == "recognition"
    assert calls == ["recognition"]
    assert models.loaded_keys() == {"recognition_model"}


def test_lazy_model_dict_allows_extra_mutable_keys():
    models = LazyModelDict({"layout_model": lambda: "layout"})

    models["llm_service"] = "service"

    assert models["llm_service"] == "service"
    assert models["layout_model"] == "layout"


def test_release_all_closes_loaded_factory_resources(monkeypatch):
    monkeypatch.setattr("aih_contexture.runtime.model_lifecycle._collect_model_memory", lambda: None)
    resource = Closeable()
    models = LazyModelDict({"layout_model": lambda: resource})

    assert models["layout_model"] is resource
    models.release_all()

    assert resource.closed is True
    assert models.loaded_keys() == set()


def test_prepare_for_run_releases_only_for_actual_non_pipeline_run(monkeypatch):
    monkeypatch.setattr("aih_contexture.runtime.model_lifecycle._collect_model_memory", lambda: None)
    resource = Closeable()
    models = LazyModelDict({"layout_model": lambda: resource})
    models["layout_model"]

    prepare_for_run(Job("pipeline"), models)

    assert models.loaded_keys() == {"layout_model"}
    assert resource.closed is False

    prepare_for_run(Job("vlm_generalized"), models)

    assert models.loaded_keys() == set()
    assert resource.closed is True


def test_finish_run_job_policy_releases_after_any_mode(monkeypatch):
    monkeypatch.setattr("aih_contexture.runtime.model_lifecycle._collect_model_memory", lambda: None)
    resource = Closeable()
    models = LazyModelDict({"layout_model": lambda: resource})
    models["layout_model"]

    finish_run(Job("pipeline"), models, cache_policy="job")

    assert models.loaded_keys() == set()
    assert resource.closed is True
