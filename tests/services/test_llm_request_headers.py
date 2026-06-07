from pydantic import BaseModel

from aih_contexture.services.lmstudio_native import LMStudioNativeService
from aih_contexture.services.openai import OpenAIService


class TinyResponse(BaseModel):
    value: str


class FakeResponse:
    status_code = 200

    def json(self):
        return {"content": '{"value":"ok"}', "usage": {"total_tokens": 3}}

    def raise_for_status(self):
        raise AssertionError("raise_for_status should not be called")


def test_lmstudio_native_requests_no_cache_headers(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs["headers"]
        return FakeResponse()

    monkeypatch.setattr("requests.post", fake_post)
    service = LMStudioNativeService({"max_retries": 0})

    result = service("prompt", None, None, TinyResponse)

    assert result == {"value": "ok"}
    assert captured["headers"]["Cache-Control"] == "no-cache, no-store"
    assert captured["headers"]["Pragma"] == "no-cache"
    assert captured["headers"]["X-Accel-Buffering"] == "no"


def test_openai_service_uses_no_cache_default_headers(monkeypatch):
    captured = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("aih_contexture.services.openai.openai.OpenAI", FakeOpenAI)
    service = OpenAIService(
        {
            "openai_base_url": "http://localhost:1234/v1",
            "openai_api_key": "key",
        }
    )

    service.get_client()

    assert captured["base_url"] == "http://localhost:1234/v1"
    assert captured["api_key"] == "key"
    assert captured["default_headers"]["Cache-Control"] == "no-cache, no-store"
    assert captured["default_headers"]["Pragma"] == "no-cache"
