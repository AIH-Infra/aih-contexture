import asyncio

from PIL import Image

from aih_contexture.services.ocr_vlm_specialized import OcrMinerUVLService
from aih_contexture.services.ocr_vlm_specialized import OcrPaddleOCRVLService


def test_paddleocr_vl_payload_matches_upstream_vl_recognition_protocol():
    service = OcrPaddleOCRVLService(
        {
            "ocr_api_style": "openai",
            "ocr_endpoint": "http://example.test/v1/chat/completions",
            "ocr_model": "paddleocr-vl-1.5",
            "ocr_max_tokens": 4096,
            "ocr_temperature": 0.0,
        }
    )

    payload = service._build_payload(
        image_b64="ZmFrZQ==",
        image_format="JPEG",
        prompt="OCR:",
        include_system=False,
        max_tokens_field="max_completion_tokens",
        top_p=0.1,
    )

    assert payload["model"] == "paddleocr-vl-1.5"
    assert payload["max_completion_tokens"] == 4096
    assert "max_tokens" not in payload
    assert payload["top_p"] == 0.1
    assert payload["messages"] == [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/jpeg;base64,ZmFrZQ=="},
                },
                {"type": "text", "text": "OCR:"},
            ],
        }
    ]


def test_paddleocr_and_mineru_profiles_default_to_latest_model_versions():
    paddle = OcrPaddleOCRVLService({})
    mineru = OcrMinerUVLService({})
    mineru_with_blank_gate = OcrMinerUVLService(
        {"ocr_api_style": "lmstudio-native", "mineru_vl_request_concurrency": None}
    )

    assert paddle.ocr_model == "paddleocr-vl-1.5"
    assert paddle.get_runtime_profile()["paddleocr_vl_version"] == "1.5"
    assert mineru.ocr_model == "mineru2.5-pro-2605-1.2b@q8_0"
    assert mineru.get_runtime_profile()["mineru_vl_version"] == "2.5pro-2605"
    assert mineru.get_runtime_profile()["mineru_vl_quant"] == "q8_0"
    assert mineru_with_blank_gate.get_runtime_profile()["request_concurrency"] == 1


def test_paddleocr_vl_request_gate_inherits_page_concurrency_when_unset():
    service = OcrPaddleOCRVLService(
        {
            "ocr_api_style": "lmstudio-native",
            "ocr_concurrency": 2,
            "paddleocr_vl_request_concurrency": None,
        }
    )
    explicit = OcrPaddleOCRVLService(
        {
            "ocr_api_style": "lmstudio-native",
            "ocr_concurrency": 2,
            "paddleocr_vl_request_concurrency": 4,
        }
    )

    assert service.get_runtime_profile()["request_concurrency"] == 2
    assert explicit.get_runtime_profile()["request_concurrency"] == 4


def test_paddleocr_vl_image_rejection_error_is_actionable():
    service = OcrPaddleOCRVLService({"ocr_model": "paddleocr-vl-1.5"})

    message = service._format_vlm_api_error(
        400,
        '{"error":{"message":"The provided messages contains images, but paddleocr-vl-1.5 does not support image inputs."}}',
    )

    assert "PaddleOCR-VL model 'paddleocr-vl-1.5' rejected image input" in message
    assert "LM Studio currently reports this mounted model as text-only" in message


class _FakePaddleOCRVLWithLocService(OcrPaddleOCRVLService):
    async def _post_vlm(self, session, **kwargs):
        return (
            "35<|LOC_865|><|LOC_48|><|LOC_886|><|LOC_48|><|LOC_886|><|LOC_59|><|LOC_865|><|LOC_59|>\n"
            "Introduction<|LOC_116|><|LOC_87|><|LOC_239|><|LOC_87|><|LOC_239|><|LOC_100|><|LOC_116|><|LOC_100|>\n"
            "\\(^{1}\\) See the recent collection.<|LOC_116|><|LOC_582|><|LOC_529|><|LOC_582|><|LOC_529|><|LOC_595|><|LOC_116|><|LOC_595|>\n"
            "Springer<|LOC_793|><|LOC_947|><|LOC_884|><|LOC_947|><|LOC_884|><|LOC_965|><|LOC_793|><|LOC_965|>",
            {"ok": True},
        )


class _FakePaddleOCRVLLayoutParsingService(OcrPaddleOCRVLService):
    def __init__(self):
        super().__init__(
            {
                "paddleocr_vl_mode": "auto",
                "paddleocr_vl_layout_parsing_url": "https://example.test/layout-parsing",
                "paddleocr_vl_api_key": "secret",
            }
        )
        self.layout_calls = []
        self.prompt_calls = []

    async def _post_layout_parsing(self, session, *, img, api_key=None):
        self.layout_calls.append({"size": img.size, "api_key": api_key})
        return {
            "errorCode": 0,
            "result": {
                "layoutParsingResults": [
                    {
                        "markdown": {"text": "# Detected title"},
                        "prunedResult": {
                            "parsing_res_list": [
                                {
                                    "block_label": "DocTitle",
                                    "block_content": "Detected title",
                                    "block_bbox": [10, 20, 200, 60],
                                    "block_order": 0,
                                }
                            ]
                        },
                    }
                ]
            },
        }

    async def _post_vlm(self, session, **kwargs):
        self.prompt_calls.append(kwargs)
        return "Prompt text", {"ok": True}


def test_paddleocr_vl_prompt_loc_tokens_become_positioned_blocks():
    service = _FakePaddleOCRVLWithLocService({"ocr_model": "paddleocr-vl-1.5"})
    img = Image.new("RGB", (1000, 2000), "white")

    result = asyncio.run(service.process_page_async(session=object(), img=img))

    assert "<|LOC_" not in result["markdown"]
    assert [block["label"] for block in result["blocks"]] == [
        "page_number",
        "section_header",
        "footnote",
        "page_footer",
    ]
    assert result["blocks"][0]["bbox"] == [865, 96, 886, 118]
    assert result["blocks"][1]["heading_level"] == 2
    assert result["blocks"][2]["text"].startswith("\\(^{1}\\)")
    assert result["blocks"][3]["text"] == "Springer"


def test_paddleocr_vl_auto_uses_official_layout_parsing_when_configured():
    service = _FakePaddleOCRVLLayoutParsingService()
    img = Image.new("RGB", (320, 480), "white")

    result = asyncio.run(service.process_page_async(session=object(), img=img, api_key="override"))

    assert service.layout_calls == [{"size": (320, 480), "api_key": "override"}]
    assert service.prompt_calls == []
    assert result["official_protocol"] == "paddleocr_vl_layout_parsing"
    assert result["markdown"] == "# Detected title"
    assert result["blocks"][0]["label"] == "doc_title"
    assert result["blocks"][0]["heading_level"] == 1
    assert result["img_size"] == [320, 480]


def test_paddleocr_vl_recognize_image_stays_on_prompt_path_for_pipeline_ocr():
    service = _FakePaddleOCRVLLayoutParsingService()
    img = Image.new("RGB", (120, 80), "white")

    result = asyncio.run(service.recognize_image_async(session=object(), img=img, prompt_label="ocr"))

    assert service.layout_calls == []
    assert len(service.prompt_calls) == 1
    assert service.prompt_calls[0]["prompt"] == "OCR:"
    assert result["official_protocol"] == "paddleocr_vl_prompt"


def test_paddleocr_vl_layout_parsing_headers_use_official_token_scheme():
    service = OcrPaddleOCRVLService({"paddleocr_vl_api_key": "secret"})

    assert service._layout_parsing_headers()["Authorization"] == "token secret"
    assert service._layout_parsing_headers("Bearer ready")["Authorization"] == "Bearer ready"


class _FakeMinerUVLTwoStepService(OcrMinerUVLService):
    def __init__(self):
        super().__init__(
            {
                "ocr_api_style": "openai",
                "ocr_endpoint": "http://example.test/v1/chat/completions",
                "ocr_model": "mineru-vl",
                "ocr_max_tokens": 4096,
                "ocr_temperature": 0.0,
                "mineru_vl_block_concurrency": 1,
                "mineru_vl_layout_image_size": (100, 100),
            }
        )
        self.calls = []

    async def _post_vlm(self, session, **kwargs):
        self.calls.append(kwargs)
        if kwargs["prompt"] == "\nLayout Detection:":
            return (
                "<|box_start|>100 100 900 180<|box_end|><|ref_start|>title<|ref_end|>"
                "<|rotate_up|>",
                {"layout": True},
            )
        return "Detected title", {"ocr": True}


def test_mineru_vl_process_page_defaults_to_two_step_structured_blocks():
    service = _FakeMinerUVLTwoStepService()
    img = Image.new("RGB", (320, 480), "white")

    result = asyncio.run(service.process_page_async(session=object(), img=img))

    assert len(service.calls) == 2
    assert service.calls[0]["prompt"] == "\nLayout Detection:"
    assert service.calls[1]["prompt"] == "\nText Recognition:"
    assert service.get_runtime_profile()["official_protocol"] == "mineru_vl_official"
    assert "mineru_vl_mode" not in service.get_runtime_profile()
    assert result["official_protocol"] == "mineru_vl_official"
    assert result["markdown"] == "## Detected title"
    assert result["blocks"][0]["type"] == "section_header"
    assert result["blocks"][0]["label"] == "title"
    assert result["blocks"][0]["text"] == "Detected title"


class _FakeMinerUVLTableService(_FakeMinerUVLTwoStepService):
    async def _post_vlm(self, session, **kwargs):
        self.calls.append(kwargs)
        if kwargs["prompt"] == "\nLayout Detection:":
            return (
                "<|box_start|>100 100 900 800<|box_end|><|ref_start|>table<|ref_end|>"
                "<|rotate_up|>",
                {"layout": True},
            )
        return "<fcel>De Motu<fcel>Thomas Hobbes<nl><fcel>LS<fcel>Long and Sedley", {"ocr": True}


def test_mineru_vl_official_path_normalizes_table_protocol_tokens():
    service = _FakeMinerUVLTableService()
    img = Image.new("RGB", (320, 480), "white")

    result = asyncio.run(service.process_page_async(session=object(), img=img))

    block = result["blocks"][0]
    assert block["label"] == "table"
    assert block["text"].startswith("<table>")
    assert "<fcel>" not in block["text"]
    assert "<nl>" not in block["text"]
    assert block["raw_mineru_content"].startswith("<fcel>De Motu")


class _FakeMinerUVLRequestGateService(OcrMinerUVLService):
    def __init__(self):
        super().__init__(
            {
                "ocr_api_style": "lmstudio-native",
                "ocr_endpoint": "http://example.test/api/v1/chat",
                "ocr_model": "mineru-vl",
                "ocr_max_tokens": 4096,
                "ocr_temperature": 0.0,
                "mineru_vl_block_concurrency": 4,
                "mineru_vl_request_concurrency": 1,
                "mineru_vl_layout_image_size": (100, 100),
            }
        )
        self.active_requests = 0
        self.max_active_requests = 0

    async def _send_payload(self, session, *, payload, api_key=None):
        self.active_requests += 1
        self.max_active_requests = max(self.max_active_requests, self.active_requests)
        try:
            await asyncio.sleep(0)
            prompt = payload["input"][1]["content"]
            if prompt == "\nLayout Detection:":
                return {
                    "content": (
                        "<|box_start|>100 100 900 180<|box_end|><|ref_start|>title<|ref_end|>"
                        "<|rotate_up|>"
                        "<|box_start|>100 220 900 320<|box_end|><|ref_start|>text<|ref_end|>"
                        "<|rotate_up|>"
                    )
                }
            return {"content": "Detected text"}
        finally:
            self.active_requests -= 1


def test_mineru_vl_request_gate_caps_layout_and_block_requests():
    service = _FakeMinerUVLRequestGateService()
    img = Image.new("RGB", (320, 480), "white")

    result = asyncio.run(service.process_page_async(session=object(), img=img))

    assert len(result["blocks"]) == 2
    assert service.max_active_requests == 1
    assert service.get_runtime_profile()["request_concurrency"] == 1
