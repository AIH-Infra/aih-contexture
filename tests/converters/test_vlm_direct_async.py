import asyncio
import json

import pytest
from PIL import Image

from aih_contexture.converters.vlm_direct_async import VlmDirectAsyncConverter


class FakeResponse:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._payload

    async def text(self):
        return json.dumps(self._payload)


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({
            "url": url,
            "json": json,
            "headers": headers,
            "timeout": timeout,
        })
        return self.response


def make_converter(**overrides):
    config = {
        "vlm_api_provider": "openai_compatible",
        "vlm_direct_base_url": "https://chat.cloudapi.vip/v1",
        "vlm_direct_model": "gemini-3-flash",
        "vlm_direct_api_key": "test-key",
        "vlm_direct_output_mode": "json",
    }
    config.update(overrides)
    return VlmDirectAsyncConverter(config)


def test_finish_reason_length_marks_truncated_in_json_mode():
    converter = make_converter()

    assert converter._log_and_validate_finish_reason("openai", "length", 1, 4096) is True


def test_extract_json_from_prefixed_output():
    converter = make_converter()
    raw = 'Here is the JSON you requested:\n{"printed_page_number": null, "page_width": 1, "page_height": 1, "regions": []}\nThank you.'

    extracted = converter._extract_json_from_output(raw)
    parsed = json.loads(extracted)

    assert parsed["regions"] == []
    assert parsed["page_width"] == 1


def test_extract_json_skips_anchor_like_prefix_object():
    converter = make_converter()
    raw = '{0}\n\njson\n{"printed_page_number": "3", "page_width": 1, "page_height": 1, "regions": []}'

    extracted = converter._extract_json_from_output(raw)
    parsed = json.loads(extracted)

    assert parsed["printed_page_number"] == "3"
    assert parsed["regions"] == []


def test_validate_json_page_output_rejects_non_json_text():
    converter = make_converter()
    with pytest.raises(ValueError):
        converter._validate_json_page_output("openai", 3, "plain markdown without json object")


def test_validate_json_page_output_accepts_anchor_prefixed_json():
    converter = make_converter()
    raw = '{0}\n\njson\n{"printed_page_number": "7", "page_width": 1, "page_height": 1, "regions": []}'
    converter._validate_json_page_output("openai", 7, raw)


def test_process_json_outputs_marks_invalid_page_explicitly():
    converter = make_converter()
    raw_outputs = [
        '{"printed_page_number": "5", "page_width": 1, "page_height": 1, "regions": []}',
        "not valid json",
    ]

    markdown_pages, printed_pages, json_pages = converter._process_json_outputs(raw_outputs)

    assert printed_pages == ["5", None]
    assert markdown_pages[1].startswith("<!-- Error parsing page 2:")

    error_page = json.loads(json_pages[1])
    assert error_page["page_number"] == 2
    assert "error" in error_page


def test_gemini_native_json_constraints_only_for_official_endpoint():
    relay_converter = make_converter(
        vlm_api_provider="gemini",
        vlm_direct_base_url="https://code.newcli.com/gemini",
    )
    official_converter = make_converter(
        vlm_api_provider="gemini",
        vlm_direct_base_url="https://generativelanguage.googleapis.com",
    )

    assert relay_converter._supports_gemini_native_json_constraints() is False
    assert official_converter._supports_gemini_native_json_constraints() is True


def test_zero_max_tokens_keeps_preset_or_json_safe_default():
    converter = make_converter(
        vlm_direct_max_tokens=0,
        vlm_direct_api_preset="high_accuracy",
    )
    assert converter._effective_max_tokens() == 4096


def test_image_transport_defaults_to_png_without_resize():
    converter = make_converter()

    assert converter.image_format == "png"
    assert converter.max_image_dimension == 0


def test_resize_skips_when_max_dimension_is_zero():
    converter = make_converter(vlm_direct_max_image_dimension=0)
    img = Image.new("RGB", (5000, 3200), color="white")

    resized = converter._resize_if_needed(img)

    assert resized.size == (5000, 3200)


def test_resize_still_applies_for_positive_limit():
    converter = make_converter(vlm_direct_max_image_dimension=1000)
    img = Image.new("RGB", (5000, 3000), color="white")

    resized = converter._resize_if_needed(img)

    assert resized.size == (1000, 600)


def test_gemini_payload_uses_matching_png_mime():
    converter = make_converter(
        vlm_api_provider="gemini",
        vlm_direct_base_url="https://generativelanguage.googleapis.com",
        vlm_direct_image_format="png",
    )
    converter._img_to_base64 = lambda img: "ZmFrZQ=="
    session = FakeSession(
        FakeResponse(
            200,
            {
                "candidates": [
                    {
                        "content": {"parts": [{"text": '{"printed_page_number": null, "page_width": 1, "page_height": 1, "regions": []}'}]},
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"candidatesTokenCount": 1},
            },
        )
    )

    asyncio.run(converter._convert_page_gemini(session, Image.new("RGB", (10, 10)), 1))

    payload = session.calls[0]["json"]
    assert payload["contents"][0]["parts"][0]["inline_data"]["mime_type"] == "image/png"


def test_anthropic_payload_uses_matching_png_media_type():
    converter = make_converter(
        vlm_api_provider="anthropic",
        vlm_direct_base_url="https://api.anthropic.com",
        vlm_direct_image_format="png",
    )
    converter._img_to_base64 = lambda img: "ZmFrZQ=="
    session = FakeSession(
        FakeResponse(
            200,
            {
                "content": [{"text": '{"printed_page_number": null, "page_width": 1, "page_height": 1, "regions": []}'}],
                "stop_reason": "end_turn",
                "usage": {"output_tokens": 1},
            },
        )
    )

    asyncio.run(converter._convert_page_anthropic(session, Image.new("RGB", (10, 10)), 1))

    payload = session.calls[0]["json"]
    assert payload["messages"][0]["content"][0]["source"]["media_type"] == "image/png"


def test_classify_page_output_http_error_uses_comment_placeholder():
    converter = make_converter(vlm_direct_output_mode="markdown")
    raw = "<!DOCTYPE html><html><body><h1>502 Bad Gateway</h1></body></html>"

    result = converter._classify_page_output(1, raw, "openai", http_status=502)

    assert result.cleaned_text == "<!-- Error converting page 1: upstream_http (502) -->"
    assert result.raw_text == raw


def test_classify_page_output_rejects_html_gateway_page_even_with_200():
    converter = make_converter()
    raw = "<!DOCTYPE html><html><body><script>var data = {\"regions\": []}</script><h1>Bad Gateway</h1></body></html>"

    result = converter._classify_page_output(2, raw, "openai", http_status=200)

    assert result.ok is False
    assert result.content_kind == "html_error"
    assert result.error_kind == "parse_error"


def test_classify_page_output_marks_truncated_json_as_failed_page():
    converter = make_converter()
    raw = '{"printed_page_number": "1", "page_width": 100, "page_height": 200, "regions": ['

    result = converter._classify_page_output(
        3,
        raw,
        "openai",
        finish_reason="length",
        truncated=True,
    )

    assert result.ok is False
    assert result.truncated is True
    assert result.error_kind == "truncated"


def test_process_json_outputs_accepts_page_result_and_marks_error_pages():
    converter = make_converter()
    raw_outputs = [
        converter._classify_page_output(
            1,
            '{"printed_page_number": "5", "page_width": 1, "page_height": 1, "regions": []}',
            "openai",
        ),
        converter._error_page_result(
            2,
            "openai",
            "API error 502",
            http_status=502,
            raw_text="<!DOCTYPE html><html><body>502 Bad Gateway</body></html>",
            error_kind="upstream_http",
        ),
    ]

    markdown_pages, printed_pages, json_pages = converter._process_json_outputs(raw_outputs)

    assert printed_pages == ["5", None]
    assert markdown_pages[1].startswith("<!-- Error parsing page 2: upstream_http")
    error_page = json.loads(json_pages[1])
    assert error_page["page_number"] == 2
    assert error_page["error"] == "upstream_http"


def test_convert_all_pages_async_keeps_page_order_and_error_pages(monkeypatch):
    converter = make_converter(vlm_direct_output_mode="markdown")
    images = [Image.new("RGB", (10, 10), color="white") for _ in range(3)]

    async def fake_convert(_session, _img, page_num):
        if page_num == 1:
            return converter._classify_page_output(page_num, "page-1", "openai")
        if page_num == 2:
            return converter._error_page_result(page_num, "openai", "API error 502", http_status=502, error_kind="upstream_http")
        return converter._classify_page_output(page_num, "page-3", "openai")

    monkeypatch.setattr(converter, "_convert_page_async_no_semaphore", fake_convert)

    results = asyncio.run(converter._convert_all_pages_async(images))

    assert [result.page_num for result in results] == [1, 2, 3]
    assert [result.ok for result in results] == [True, False, True]
    assert results[1].error_kind == "upstream_http"
    assert [result.cleaned_text for result in results] == ["page-1", "<!-- Error converting page 2: API error 502 -->", "page-3"]
