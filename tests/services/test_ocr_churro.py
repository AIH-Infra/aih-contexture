from aih_contexture.services.ocr_churro import CHURRO_OFFICIAL_SYSTEM_PROMPT, OcrChurroService


def test_churro_service_defaults_to_openai_compatible_protocol():
    service = OcrChurroService({"ocr_model": "churro-3b@q8_0"})

    assert service.ocr_api_style == "openai"


def test_churro_service_uses_official_system_prompt_and_image_only_openai_user_message():
    service = OcrChurroService(
        {
            "ocr_model": "churro-3b@q8_0",
            "ocr_api_style": "openai",
            "ocr_image_format": "PNG",
        }
    )

    payload = service._build_payload("abc", service._build_prompt())

    assert service._build_prompt() == CHURRO_OFFICIAL_SYSTEM_PROMPT
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][0]["content"][0]["text"] == CHURRO_OFFICIAL_SYSTEM_PROMPT
    assert payload["messages"][1]["role"] == "user"
    assert payload["messages"][1]["content"] == [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}}
    ]


def test_churro_lmstudio_native_payload_does_not_send_openai_roles():
    service = OcrChurroService(
        {
            "ocr_model": "churro-3b@q8_0",
            "ocr_api_style": "lmstudio-native",
            "ocr_image_format": "PNG",
            "ocr_max_tokens": 4096,
        }
    )

    payload = service._build_payload("abc", service._build_prompt())

    assert payload["model"] == "churro-3b@q8_0"
    assert payload["input"] == [
        {"type": "text", "content": CHURRO_OFFICIAL_SYSTEM_PROMPT},
        {"type": "image", "data_url": "data:image/png;base64,abc"},
    ]
    assert all("role" not in item for item in payload["input"])
    assert payload["max_output_tokens"] == 4096


def test_churro_lmstudio_native_extracts_output_message_content():
    service = OcrChurroService(
        {
            "ocr_model": "churro-3b@q8_0",
            "ocr_api_style": "lmstudio-native",
        }
    )

    body = {
        "output": [
            {
                "type": "message",
                "content": "<HistoricalDocument><Body /></HistoricalDocument>",
            }
        ]
    }

    assert service._extract_response_text(body) == "<HistoricalDocument><Body /></HistoricalDocument>"
