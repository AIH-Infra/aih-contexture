from __future__ import annotations

import asyncio
import base64
import json
from io import BytesIO
from typing import Any
from urllib.parse import urlparse

import aiohttp
from PIL import Image

from aih_contexture.config.vlm_model_presets import (
    default_quant,
    default_version,
    model_family_label,
    normalize_quant,
    normalize_version,
    resolve_vlm_model,
)
from aih_contexture.logger import get_logger
from aih_contexture.services.ocr_base import BaseOcrService
from aih_contexture.vendor.mineru_vl_compat import (
    MINERU_VL_PROMPTS,
    convert_mineru_vl_bbox,
    mineru_vl_type_for_label,
    normalize_mineru_block,
    parse_mineru_vl_layout_tokens,
)
from aih_contexture.vendor.paddleocr_vl_compat import (
    PADDLE_VL_PROMPTS,
    extract_paddle_pruned_blocks,
    find_paddle_layout_results,
    paddle_prompt_label_to_block_label,
    parse_paddle_vl_loc_blocks,
    segment_paddle_vl_loc_blocks,
)
from aih_contexture.vendor.surya2_compat import (
    SURYA2_PROMPTS,
    html_to_plain_text,
    normalize_surya2_ocr_block,
    parse_surya2_layout_json,
)

logger = get_logger()


PADDLE_PROMPTS = PADDLE_VL_PROMPTS

MINERU_PROMPTS = MINERU_VL_PROMPTS


def _looks_like_layout_parsing_url(value: str | None) -> bool:
    if not value:
        return False
    try:
        path = urlparse(str(value)).path.rstrip("/")
    except Exception:
        return False
    return path.endswith("/layout-parsing")


class OpenAICompatibleVlmMixin:
    ocr_api_style: str = "openai"
    ocr_endpoint: str = ""
    ocr_model: str = ""
    ocr_api_key: str = ""
    ocr_timeout: int = 120
    ocr_max_tokens: int = 4096
    ocr_temperature: float = 0.0

    def _image_to_base64(self, img: Image.Image, *, image_format: str = "PNG", quality: int = 90) -> str:
        if img.mode != "RGB":
            img = img.convert("RGB")
        buffered = BytesIO()
        save_kwargs: dict[str, Any] = {}
        if image_format.upper() in {"JPEG", "WEBP"}:
            save_kwargs["quality"] = quality
        img.save(buffered, format=image_format.upper(), **save_kwargs)
        return base64.b64encode(buffered.getvalue()).decode("ascii")

    def _headers(self, api_key: str | None = None) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        key = api_key or self.ocr_api_key
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def _build_payload(
        self,
        *,
        image_b64: str,
        prompt: str,
        image_format: str = "png",
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        include_system: bool = True,
        max_tokens_field: str = "max_tokens",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        style = self.ocr_api_style
        data_url = f"data:image/{image_format.lower()};base64,{image_b64}"
        if style == "lmstudio-native":
            payload = {
                "model": self.ocr_model,
                "input": [
                    {"type": "image", "data_url": data_url},
                    {"type": "text", "content": prompt},
                ],
                "store": False,
                "temperature": self.ocr_temperature if temperature is None else temperature,
                "max_output_tokens": max_tokens or self.ocr_max_tokens,
            }
            if top_p is not None:
                payload["top_p"] = top_p
        else:
            messages: list[dict[str, Any]] = []
            if include_system:
                messages.append({"role": "system", "content": "You are a helpful assistant."})
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": prompt},
                    ],
                }
            )
            payload = {
                "model": self.ocr_model,
                "messages": messages,
                max_tokens_field: max_tokens or self.ocr_max_tokens,
                "temperature": self.ocr_temperature if temperature is None else temperature,
            }
            if top_p is not None:
                payload["top_p"] = top_p
        if extra:
            payload.update(extra)
        return payload

    def _extract_response_text(self, body: dict[str, Any]) -> str:
        if self.ocr_api_style == "lmstudio-native":
            for key in ("content", "output_text", "text", "response"):
                value = body.get(key)
                if isinstance(value, str) and value.strip():
                    return value
            output_text = self._extract_output_list_text(body.get("output"))
            if output_text:
                return output_text
            return ""

        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            for key in ("output_text", "content", "text", "response"):
                value = body.get(key)
                if isinstance(value, str) and value.strip():
                    return value
            return self._extract_output_list_text(body.get("output"))
        choice = choices[0]
        if not isinstance(choice, dict):
            return ""
        for key in ("text", "content"):
            value = choice.get(key)
            if isinstance(value, str) and value.strip():
                return value
        message = choice.get("message") or choice.get("delta") or {}
        if isinstance(message, dict):
            content = message.get("content")
            content_text = self._extract_content_text(content)
            if content_text:
                return content_text
        return ""

    @staticmethod
    def _extract_content_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return ""
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                value = part.get("text") or part.get("content")
                if isinstance(value, str):
                    parts.append(value)
        return "".join(parts)

    @classmethod
    def _extract_output_list_text(cls, output: Any) -> str:
        if not isinstance(output, list):
            return ""
        parts: list[str] = []
        for item in output:
            if isinstance(item, str):
                parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            for key in ("text", "content", "output_text"):
                value = item.get(key)
                text = cls._extract_content_text(value)
                if text:
                    parts.append(text)
                    break
        return "".join(parts)

    async def _post_vlm(
        self,
        session: aiohttp.ClientSession,
        *,
        img: Image.Image,
        prompt: str,
        api_key: str | None = None,
        image_format: str = "PNG",
        image_quality: int = 90,
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        include_system: bool = True,
        max_tokens_field: str = "max_tokens",
        extra: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        image_b64 = self._image_to_base64(img, image_format=image_format, quality=image_quality)
        payload = self._build_payload(
            image_b64=image_b64,
            prompt=prompt,
            image_format=image_format,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            include_system=include_system,
            max_tokens_field=max_tokens_field,
            extra=extra,
        )
        request_semaphore = self._vlm_request_semaphore()
        if request_semaphore is None:
            body = await self._send_payload_with_probe(session, payload=payload, api_key=api_key, prompt=prompt)
        else:
            async with request_semaphore:
                body = await self._send_payload_with_probe(session, payload=payload, api_key=api_key, prompt=prompt)
        return self._extract_response_text(body).strip(), body

    async def _send_payload_with_probe(
        self,
        session: aiohttp.ClientSession,
        *,
        payload: dict[str, Any],
        api_key: str | None = None,
        prompt: str = "",
    ) -> dict[str, Any]:
        active = int(getattr(self, "_vlm_active_requests", 0) or 0) + 1
        self._vlm_active_requests = active
        limit = getattr(self, "vlm_request_concurrency", None)
        backend = self._probe_backend_name()
        prompt_label = str(prompt or "").strip().splitlines()[0] if prompt else ""
        logger.info(
            "[VLM request start] backend=%s active=%s limit=%s prompt=%s",
            backend,
            active,
            limit,
            prompt_label,
        )
        try:
            return await self._send_payload(session, payload=payload, api_key=api_key)
        finally:
            self._vlm_active_requests = max(0, int(getattr(self, "_vlm_active_requests", 1) or 1) - 1)
            logger.info(
                "[VLM request done] backend=%s active=%s limit=%s prompt=%s",
                backend,
                self._vlm_active_requests,
                limit,
                prompt_label,
            )

    def _probe_backend_name(self) -> str:
        getter = getattr(self, "get_backend_name", None)
        if callable(getter):
            try:
                return str(getter())
            except Exception:
                pass
        return type(self).__name__

    def _vlm_request_semaphore(self) -> asyncio.Semaphore | None:
        limit = int(getattr(self, "vlm_request_concurrency", 0) or 0)
        if limit <= 0:
            return None
        loop = asyncio.get_running_loop()
        cached_loop = getattr(self, "_vlm_request_semaphore_loop", None)
        semaphore = getattr(self, "_vlm_request_semaphore_instance", None)
        if semaphore is None or cached_loop is not loop:
            semaphore = asyncio.Semaphore(limit)
            self._vlm_request_semaphore_instance = semaphore
            self._vlm_request_semaphore_loop = loop
        return semaphore

    async def _send_payload(
        self,
        session: aiohttp.ClientSession,
        *,
        payload: dict[str, Any],
        api_key: str | None = None,
    ) -> dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=self.ocr_timeout)
        async with session.post(
            self.ocr_endpoint,
            json=payload,
            headers=self._headers(api_key),
            timeout=timeout,
        ) as response:
            text = await response.text()
            if response.status != 200:
                raise RuntimeError(self._format_vlm_api_error(response.status, text))
            try:
                return json.loads(text)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"VLM API returned invalid JSON: {text[:1000]}") from exc

    def _format_vlm_api_error(self, status: int, text: str) -> str:
        snippet = text[:1000]
        lower = snippet.lower()
        if "does not support image" in lower or "contains images" in lower:
            backend_name = self.get_backend_name() if hasattr(self, "get_backend_name") else "vlm"
            if backend_name == "paddleocr_vl":
                return (
                    f"VLM API error {status}: PaddleOCR-VL model {self.ocr_model!r} rejected image input. "
                    "LM Studio currently reports this mounted model as text-only, so the PaddleOCR-VL "
                    "specialized path cannot run through that model ID. Use a vision-capable PaddleOCR-VL "
                    "runtime/service or switch to a VLM backend that LM Studio exposes with image support. "
                    f"Raw response: {snippet}"
                )
            return (
                f"VLM API error {status}: model {self.ocr_model!r} rejected image input. "
                "Use a vision-capable model/runtime for this VLM OCR backend. "
                f"Raw response: {snippet}"
            )
        return f"VLM API error {status}: {snippet}"


class OcrPaddleOCRVLService(OpenAICompatibleVlmMixin, BaseOcrService):
    """PaddleOCR-VL specialized VLM adapter.

    The OpenAI-compatible path mirrors PaddleOCR-VL's upstream single-prompt
    task protocol. A direct Paddle service can be added later for the official
    /layout-parsing response shape.
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.ocr_endpoint = config.get("paddleocr_vl_endpoint") or self.ocr_endpoint
        self.ocr_model = config.get("paddleocr_vl_model") or self.ocr_model
        self.ocr_api_key = config.get("paddleocr_vl_api_key") or self.ocr_api_key
        self.ocr_api_style = str(config.get("paddleocr_vl_api_style") or config.get("ocr_api_style", "openai")).strip().lower()
        if self.ocr_api_style == "openai-compatible":
            self.ocr_api_style = "openai"
        self.backend_name = str(config.get("paddleocr_vl_backend_name") or "paddleocr_vl").strip()
        self.paddleocr_vl_mode = str(config.get("paddleocr_vl_mode") or "auto").strip().lower()
        self.paddleocr_vl_layout_parsing_url = str(config.get("paddleocr_vl_layout_parsing_url") or "").strip()
        self.prompt_label = str(config.get("paddleocr_vl_prompt_label") or "layout_detection").strip().lower()
        if self.prompt_label not in PADDLE_PROMPTS:
            self.prompt_label = "layout_detection"
        self.paddleocr_vl_version = normalize_version(
            "paddleocr_vl",
            str(config.get("paddleocr_vl_version") or default_version("paddleocr_vl")).strip(),
        )
        if not self.ocr_model:
            self.ocr_model = resolve_vlm_model("paddleocr_vl", version=self.paddleocr_vl_version)
        self.image_quality = int(config.get("paddleocr_vl_image_quality", config.get("ocr_image_quality", 90)))
        self.image_format = str(config.get("paddleocr_vl_image_format") or config.get("ocr_image_format") or "JPEG").strip() or "JPEG"
        request_concurrency_value = config.get("paddleocr_vl_request_concurrency")
        if request_concurrency_value is None or str(request_concurrency_value).strip() == "":
            request_concurrency_value = config.get("ocr_concurrency")
        if request_concurrency_value is None or str(request_concurrency_value).strip() == "":
            request_concurrency_value = 1 if self.ocr_api_style == "lmstudio-native" else 0
        self.request_concurrency = max(0, int(request_concurrency_value or 0))
        self.vlm_request_concurrency = self.request_concurrency

    def get_backend_name(self) -> str:
        return self.backend_name

    def get_runtime_profile(self) -> dict[str, Any]:
        layout_url = self._layout_parsing_url()
        return {
            "backend": self.backend_name,
            "model_family": model_family_label("paddleocr_vl", self.paddleocr_vl_version),
            "paddleocr_vl_version": self.paddleocr_vl_version,
            "paddleocr_vl_mode": self.paddleocr_vl_mode,
            "paddleocr_vl_layout_parsing_url": layout_url or None,
            "api_style": self.ocr_api_style,
            "prompt_label": self.prompt_label,
            "official_protocol": "paddleocr_vl_layout_parsing" if layout_url and self.paddleocr_vl_mode != "vl_prompt" else "paddleocr_vl_prompt",
            "image_transport": self.image_format.upper(),
            "request_concurrency": self.request_concurrency or None,
        }

    async def process_page_async(
        self,
        session: aiohttp.ClientSession,
        img: Image.Image,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        if self._should_use_layout_parsing():
            return await self.layout_parse_image_async(session, img, api_key=api_key)
        return await self.recognize_image_async(
            session,
            img,
            api_key=api_key,
            prompt_label=self.prompt_label,
        )

    def _layout_parsing_url(self) -> str:
        if self.paddleocr_vl_layout_parsing_url:
            return self.paddleocr_vl_layout_parsing_url
        if _looks_like_layout_parsing_url(self.ocr_endpoint):
            return self.ocr_endpoint
        return ""

    def _should_use_layout_parsing(self) -> bool:
        mode = self.paddleocr_vl_mode.replace("-", "_")
        if mode in {"vl_prompt", "prompt", "vl_recognition", "recognition"}:
            return False
        layout_url = self._layout_parsing_url()
        if mode in {"layout_parsing", "official", "document_parsing"}:
            if not layout_url:
                raise RuntimeError(
                    "paddleocr_vl_mode=layout_parsing requires paddleocr_vl_layout_parsing_url "
                    "or a paddleocr_vl_endpoint/ocr_endpoint ending with /layout-parsing."
                )
            return True
        return bool(layout_url)

    async def layout_parse_image_async(
        self,
        session: aiohttp.ClientSession,
        img: Image.Image,
        *,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        body = await self._post_layout_parsing(session, img=img, api_key=api_key)
        layout_results = find_paddle_layout_results(body)
        markdown = self._layout_results_markdown(layout_results)
        blocks = extract_paddle_pruned_blocks(layout_results[0].get("prunedResult")) if layout_results else []
        return {
            "backend": self.backend_name,
            "official_protocol": "paddleocr_vl_layout_parsing",
            "markdown": markdown,
            "blocks": blocks,
            "img_size": list(img.size),
            "raw": {"response": body},
        }

    async def _post_layout_parsing(
        self,
        session: aiohttp.ClientSession,
        *,
        img: Image.Image,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        url = self._layout_parsing_url()
        if not url:
            raise RuntimeError("PaddleOCR-VL layout parsing URL is not configured.")
        image_b64 = self._image_to_base64(img, image_format=self.image_format, quality=self.image_quality)
        payload = {
            "file": image_b64,
            "fileType": 1,
            "visualize": False,
        }
        options = self.config.get("paddleocr_vl_layout_parsing_options")
        if isinstance(options, dict):
            payload.update(options)
        request_semaphore = self._vlm_request_semaphore()
        if request_semaphore is None:
            return await self._send_layout_parsing_payload(session, url=url, payload=payload, api_key=api_key)
        async with request_semaphore:
            return await self._send_layout_parsing_payload(session, url=url, payload=payload, api_key=api_key)

    async def _send_layout_parsing_payload(
        self,
        session: aiohttp.ClientSession,
        *,
        url: str,
        payload: dict[str, Any],
        api_key: str | None = None,
    ) -> dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=self.ocr_timeout)
        async with session.post(
            url,
            json=payload,
            headers=self._layout_parsing_headers(api_key),
            timeout=timeout,
        ) as response:
            text = await response.text()
            if response.status != 200:
                raise RuntimeError(self._format_layout_parsing_error(response.status, text))
            try:
                body = json.loads(text)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"PaddleOCR-VL layout parsing API returned invalid JSON: {text[:1000]}") from exc
        if isinstance(body, dict) and body.get("errorCode", 0) not in {0, "0", None}:
            raise RuntimeError(f"PaddleOCR-VL layout parsing API error: {body.get('errorMsg', 'Unknown error')}")
        if not isinstance(body, dict):
            raise RuntimeError("PaddleOCR-VL layout parsing API returned a non-object JSON response.")
        return body

    def _layout_parsing_headers(self, api_key: str | None = None) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Client-Platform": "aih-contexture"}
        key = api_key or self.ocr_api_key
        if key:
            token = str(key).strip()
            lowered = token.lower()
            if lowered.startswith("token ") or lowered.startswith("bearer "):
                headers["Authorization"] = token
            else:
                headers["Authorization"] = f"token {token}"
        return headers

    @staticmethod
    def _layout_results_markdown(layout_results: list[Any]) -> str:
        texts: list[str] = []
        for result in layout_results:
            if not isinstance(result, dict):
                continue
            markdown = result.get("markdown")
            if isinstance(markdown, dict):
                text = markdown.get("text") or markdown.get("markdown_texts")
                if isinstance(text, str) and text.strip():
                    texts.append(text.strip())
            elif isinstance(markdown, str) and markdown.strip():
                texts.append(markdown.strip())
        return "\n\n".join(texts)

    @staticmethod
    def _format_layout_parsing_error(status: int, text: str) -> str:
        snippet = text[:1000]
        try:
            body = json.loads(text)
            if isinstance(body, dict) and body.get("errorMsg"):
                snippet = str(body.get("errorMsg"))[:1000]
        except Exception:
            pass
        if status == 403:
            return f"PaddleOCR-VL layout parsing authentication failed (403): {snippet}"
        if status == 429:
            return f"PaddleOCR-VL layout parsing rate limit exceeded (429): {snippet}"
        return f"PaddleOCR-VL layout parsing API error {status}: {snippet}"

    async def recognize_image_async(
        self,
        session: aiohttp.ClientSession,
        img: Image.Image,
        *,
        api_key: str | None = None,
        prompt_label: str | None = None,
    ) -> dict[str, Any]:
        active_prompt_label = str(prompt_label or self.prompt_label or "layout_detection").strip().lower()
        if active_prompt_label not in PADDLE_PROMPTS:
            active_prompt_label = "layout_detection"
        prompt = PADDLE_PROMPTS[active_prompt_label]
        text, raw = await self._post_vlm(
            session,
            img=img,
            prompt=prompt,
            api_key=api_key,
            image_format=self.image_format,
            image_quality=self.image_quality,
            include_system=False,
            max_tokens_field="max_completion_tokens",
            top_p=0.1,
        )
        width, height = img.size
        loc_blocks = parse_paddle_vl_loc_blocks(
            text,
            width=width,
            height=height,
            prompt_label=active_prompt_label,
            prompt=prompt,
        )
        loc_blocks = segment_paddle_vl_loc_blocks(loc_blocks)
        clean_text = "\n".join(block["text"] for block in loc_blocks) if loc_blocks else text
        blocks = loc_blocks or [
            {
                "type": paddle_prompt_label_to_block_label(active_prompt_label),
                "label": paddle_prompt_label_to_block_label(active_prompt_label),
                "text": text,
                "bbox": [0, 0, width, height],
                "raw_prompt_label": active_prompt_label,
                "raw_query": prompt,
            }
        ]
        return {
            "backend": self.backend_name,
            "official_protocol": "paddleocr_vl_prompt",
            "markdown": clean_text,
            "blocks": blocks,
            "raw": {"response": raw},
        }


def _paddle_prompt_label_to_block_label(prompt_label: str) -> str:
    return paddle_prompt_label_to_block_label(prompt_label)


def _paddle_vl_loc_text_to_blocks(
    text: str,
    *,
    width: int,
    height: int,
    prompt_label: str,
    prompt: str,
) -> list[dict[str, Any]]:
    return segment_paddle_vl_loc_blocks(parse_paddle_vl_loc_blocks(
        text,
        width=width,
        height=height,
        prompt_label=prompt_label,
        prompt=prompt,
    ))


def _classify_paddle_loc_ocr_line(
    text: str,
    *,
    norm_bbox: list[int],
    in_footnotes: bool,
) -> tuple[str, bool]:
    from aih_contexture.vendor.paddleocr_vl_compat import classify_paddle_loc_ocr_line

    label, next_in_footnotes, _, _ = classify_paddle_loc_ocr_line(
        text,
        norm_bbox=norm_bbox,
        in_footnotes=in_footnotes,
    )
    return label, next_in_footnotes


class OcrMinerUVLService(OpenAICompatibleVlmMixin, BaseOcrService):
    """MinerU-VL specialized VLM adapter.

    Single product path: run the upstream layout/recognition protocol, normalize
    the raw MinerU protocol into official-compatible blocks, then let Contexture
    Middle render the final scholarly Markdown.
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.ocr_api_style = str(config.get("ocr_api_style", "openai")).strip().lower()
        if self.ocr_api_style == "openai-compatible":
            self.ocr_api_style = "openai"
        self.block_concurrency = int(config.get("mineru_vl_block_concurrency", 4))
        default_request_concurrency = 1 if self.ocr_api_style == "lmstudio-native" else self.block_concurrency
        request_concurrency_value = config.get("mineru_vl_request_concurrency")
        if request_concurrency_value is None or str(request_concurrency_value).strip() == "":
            request_concurrency_value = default_request_concurrency
        self.request_concurrency = max(
            1,
            int(request_concurrency_value),
        )
        self.vlm_request_concurrency = self.request_concurrency
        self.layout_image_size = tuple(config.get("mineru_vl_layout_image_size", (1036, 1036)))
        self.image_quality = int(config.get("ocr_image_quality", 90))
        self.mineru_vl_version = normalize_version(
            "mineru_vl",
            str(config.get("mineru_vl_version") or default_version("mineru_vl")).strip(),
        )
        self.mineru_vl_quant = normalize_quant(
            "mineru_vl",
            self.mineru_vl_version,
            str(config.get("mineru_vl_quant") or default_quant("mineru_vl")).strip(),
        )
        if not self.ocr_model:
            self.ocr_model = resolve_vlm_model(
                "mineru_vl",
                version=self.mineru_vl_version,
                quant=self.mineru_vl_quant,
            )

    def get_backend_name(self) -> str:
        return "mineru_vl"

    def get_runtime_profile(self) -> dict[str, Any]:
        return {
            "backend": "mineru_vl",
            "model_family": model_family_label("mineru_vl", self.mineru_vl_version),
            "mineru_vl_version": self.mineru_vl_version,
            "mineru_vl_quant": self.mineru_vl_quant,
            "api_style": self.ocr_api_style,
            "official_protocol": "mineru_vl_official",
            "bbox_scale": 1000,
            "layout_image_size": list(self.layout_image_size),
            "image_transport": "PNG",
            "request_concurrency": self.request_concurrency,
        }

    async def process_page_async(
        self,
        session: aiohttp.ClientSession,
        img: Image.Image,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        layout_img = img.convert("RGB").resize(self.layout_image_size, Image.Resampling.BICUBIC)
        layout_text, layout_raw = await self._post_vlm(
            session,
            img=layout_img,
            prompt=MINERU_PROMPTS["layout"],
            api_key=api_key,
            image_format="PNG",
            image_quality=self.image_quality,
            temperature=0.0,
            top_p=0.01,
            extra={"skip_special_tokens": False} if self.ocr_api_style != "lmstudio-native" else None,
        )
        blocks = self._parse_layout(layout_text, img.size)
        if not blocks:
            return {
                "backend": "mineru_vl",
                "official_protocol": "mineru_vl_official",
                "markdown": "",
                "blocks": [],
                "raw": {"layout_text": layout_text, "layout_response": layout_raw},
            }

        sem = asyncio.Semaphore(max(1, self.block_concurrency))

        async def extract(block: dict[str, Any]) -> dict[str, Any]:
            async with sem:
                crop = self._crop_block(img, block["bbox"])
                prompt = self._prompt_for_type(str(block["label"]))
                text, raw = await self._post_vlm(
                    session,
                    img=crop,
                    prompt=prompt,
                    api_key=api_key,
                    image_format="PNG",
                    image_quality=self.image_quality,
                    temperature=0.0,
                    top_p=0.01,
                    extra={"skip_special_tokens": False} if self.ocr_api_style != "lmstudio-native" else None,
                )
                block["text"] = text
                block["raw_prompt"] = prompt
                block["raw_response"] = raw
                return normalize_mineru_block(block)

        extracted = await asyncio.gather(*(extract(block) for block in blocks))
        markdown = self._blocks_to_markdown(extracted)
        return {
            "backend": "mineru_vl",
            "official_protocol": "mineru_vl_official",
            "markdown": markdown,
            "blocks": extracted,
            "raw": {"layout_text": layout_text, "layout_response": layout_raw},
        }

    def _parse_layout(self, text: str, page_size: tuple[int, int]) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        for block in parse_mineru_vl_layout_tokens(text, page_size):
            normalized = dict(block)
            normalized["type"] = self._type_for_label(str(normalized.get("label") or ""))
            normalized["text"] = ""
            blocks.append(normalized)
        return blocks

    @staticmethod
    def _convert_bbox(values: tuple[str, str, str, str]) -> list[float] | None:
        return convert_mineru_vl_bbox(values)

    @staticmethod
    def _crop_block(img: Image.Image, bbox: list[int]) -> Image.Image:
        width, height = img.size
        x1, y1, x2, y2 = bbox
        pad = 4
        box = (
            max(0, x1 - pad),
            max(0, y1 - pad),
            min(width, x2 + pad),
            min(height, y2 + pad),
        )
        if box[2] <= box[0] or box[3] <= box[1]:
            return img
        return img.crop(box)

    @staticmethod
    def _prompt_for_type(label: str) -> str:
        return MINERU_PROMPTS.get(label, MINERU_PROMPTS["default"])

    @staticmethod
    def _type_for_label(label: str) -> str:
        return mineru_vl_type_for_label(label)

    @staticmethod
    def _blocks_to_markdown(blocks: list[dict[str, Any]]) -> str:
        parts = []
        for block in sorted(blocks, key=lambda item: int(item.get("order", 0))):
            text = str(block.get("text") or "").strip()
            if not text:
                continue
            label = str(block.get("label") or "")
            if label in {"title", "section_header"}:
                parts.append(f"## {text}")
            elif label == "table":
                parts.append(text)
            elif label == "equation":
                parts.append(f"$$\n{text}\n$$")
            else:
                parts.append(text)
        return "\n\n".join(parts)


class OcrSurya2Service(OpenAICompatibleVlmMixin, BaseOcrService):
    """Surya 2 specialized VLM adapter.

    Surya 2's upstream protocol is service-style: layout returns JSON boxes
    with 0..1000 coordinates, and block OCR returns HTML. Contexture preserves
    that protocol and adapts the normalized blocks into Middle downstream.
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.ocr_api_style = str(config.get("surya2_api_style") or config.get("ocr_api_style", "openai")).strip().lower()
        if self.ocr_api_style == "openai-compatible":
            self.ocr_api_style = "openai"
        self.ocr_endpoint = self._normalize_endpoint(
            config.get("surya2_endpoint") or config.get("ocr_endpoint") or self.ocr_endpoint,
            api_style=self.ocr_api_style,
        )
        self.ocr_model = str(config.get("surya2_model") or config.get("ocr_model") or "").strip()
        self.ocr_api_key = str(config.get("surya2_api_key") or config.get("ocr_api_key") or self.ocr_api_key or "").strip()
        self.ocr_timeout = int(config.get("surya2_timeout", config.get("ocr_timeout", self.ocr_timeout)))
        self.ocr_max_tokens = int(config.get("surya2_max_tokens", config.get("ocr_max_tokens", self.ocr_max_tokens)))
        self.image_format = str(config.get("surya2_image_format") or config.get("ocr_image_format") or "PNG").strip().upper() or "PNG"
        self.image_quality = int(config.get("surya2_image_quality", config.get("ocr_image_quality", 90)))
        self.block_concurrency = max(1, int(config.get("surya2_block_concurrency", 4) or 4))
        request_concurrency_value = config.get("surya2_request_concurrency")
        if request_concurrency_value is None or str(request_concurrency_value).strip() == "":
            request_concurrency_value = 6
        self.request_concurrency = max(1, int(request_concurrency_value))
        self.vlm_request_concurrency = self.request_concurrency
        self.surya2_version = normalize_version(
            "surya2",
            str(config.get("surya2_version") or default_version("surya2")).strip(),
        )
        if not self.ocr_model:
            self.ocr_model = resolve_vlm_model("surya2", version=self.surya2_version)

    def get_backend_name(self) -> str:
        return "surya2"

    def get_runtime_profile(self) -> dict[str, Any]:
        return {
            "backend": "surya2",
            "model_family": model_family_label("surya2", self.surya2_version),
            "surya2_version": self.surya2_version,
            "api_style": self.ocr_api_style,
            "official_protocol": "surya2_layout_block_html",
            "bbox_scale": 1000,
            "image_transport": self.image_format.upper(),
            "request_concurrency": self.request_concurrency,
            "block_concurrency": self.block_concurrency,
        }

    async def process_page_async(
        self,
        session: aiohttp.ClientSession,
        img: Image.Image,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        layout_text, layout_raw = await self._post_vlm(
            session,
            img=img.convert("RGB"),
            prompt=SURYA2_PROMPTS["layout"],
            api_key=api_key,
            image_format=self.image_format,
            image_quality=self.image_quality,
            temperature=0.0,
            top_p=0.01,
            include_system=False,
            max_tokens=min(self.ocr_max_tokens, 4096),
        )
        blocks = parse_surya2_layout_json(layout_text, page_size=img.size)
        if not blocks:
            html_text, raw = await self._ocr_block_async(session, img, api_key=api_key)
            text = html_to_plain_text(html_text)
            return {
                "backend": "surya2",
                "official_protocol": "surya2_page_html_fallback",
                "markdown": text,
                "blocks": [
                    {
                        "label": "text",
                        "type": "text",
                        "text": text,
                        "html": html_text,
                        "bbox": [0, 0, img.size[0], img.size[1]],
                        "raw_prompt": SURYA2_PROMPTS["ocr"],
                        "raw_response": raw,
                    }
                ] if text else [],
                "img_size": list(img.size),
                "raw": {"layout_text": layout_text, "layout_response": layout_raw},
            }

        sem = asyncio.Semaphore(self.block_concurrency)

        async def extract(block: dict[str, Any]) -> dict[str, Any]:
            async with sem:
                crop = self._crop_block(img, block["bbox"])
                prompt = self._prompt_for_block(block)
                html_text, raw = await self._post_vlm(
                    session,
                    img=crop,
                    prompt=prompt,
                    api_key=api_key,
                    image_format=self.image_format,
                    image_quality=self.image_quality,
                    temperature=0.0,
                    top_p=0.01,
                    include_system=False,
                )
                return normalize_surya2_ocr_block(block, html_text=html_text, raw_response=raw, raw_prompt=prompt)

        extracted = await asyncio.gather(*(extract(block) for block in blocks))
        markdown = self._blocks_to_markdown(extracted)
        return {
            "backend": "surya2",
            "official_protocol": "surya2_layout_block_html",
            "markdown": markdown,
            "blocks": extracted,
            "img_size": list(img.size),
            "raw": {"layout_text": layout_text, "layout_response": layout_raw},
        }

    async def recognize_image_async(
        self,
        session: aiohttp.ClientSession,
        img: Image.Image,
        *,
        api_key: str | None = None,
        prompt_label: str | None = None,
    ) -> dict[str, Any]:
        del prompt_label
        html_text, raw = await self._ocr_block_async(session, img, api_key=api_key)
        text = html_to_plain_text(html_text)
        return {
            "backend": "surya2",
            "official_protocol": "surya2_block_html",
            "markdown": text,
            "html": html_text,
            "blocks": [
                {
                    "label": "text",
                    "type": "text",
                    "text": text,
                    "html": html_text,
                    "bbox": [0, 0, img.size[0], img.size[1]],
                    "raw_prompt": SURYA2_PROMPTS["ocr"],
                }
            ] if text else [],
            "raw": {"response": raw},
        }

    async def _ocr_block_async(
        self,
        session: aiohttp.ClientSession,
        img: Image.Image,
        *,
        api_key: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        return await self._post_vlm(
            session,
            img=img.convert("RGB"),
            prompt=SURYA2_PROMPTS["ocr"],
            api_key=api_key,
            image_format=self.image_format,
            image_quality=self.image_quality,
            temperature=0.0,
            top_p=0.01,
            include_system=False,
        )

    @staticmethod
    def _crop_block(img: Image.Image, bbox: list[int]) -> Image.Image:
        width, height = img.size
        x0, y0, x1, y1 = [int(value) for value in bbox]
        pad = 4
        box = (
            max(0, x0 - pad),
            max(0, y0 - pad),
            min(width, x1 + pad),
            min(height, y1 + pad),
        )
        if box[2] <= box[0] or box[3] <= box[1]:
            return img
        return img.crop(box)

    @staticmethod
    def _prompt_for_block(block: dict[str, Any]) -> str:
        label = str(block.get("label") or block.get("type") or "").strip().lower()
        if label == "table":
            return SURYA2_PROMPTS["table"]
        return SURYA2_PROMPTS["ocr"]

    @staticmethod
    def _blocks_to_markdown(blocks: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for block in sorted(blocks, key=lambda item: int(item.get("order", 0))):
            text = str(block.get("text") or "").strip()
            if not text:
                continue
            label = str(block.get("label") or block.get("type") or "").strip().lower()
            if label == "section_header":
                parts.append(f"## {text}")
            elif label == "equation":
                parts.append(f"$$\n{text}\n$$")
            else:
                parts.append(text)
        return "\n\n".join(parts)

    @staticmethod
    def _normalize_endpoint(value: object, *, api_style: str) -> str:
        if not value:
            if api_style == "lmstudio-native":
                return "http://localhost:1234/api/v1/chat"
            return "http://127.0.0.1:1234/v1/chat/completions"
        text = str(value).strip()
        stripped = text.rstrip("/")
        if api_style == "lmstudio-native":
            if stripped.endswith("/api/v1/chat"):
                return stripped
            if stripped.endswith("/v1/chat/completions"):
                return f"{stripped.removesuffix('/v1/chat/completions')}/api/v1/chat"
            if stripped.endswith("/v1"):
                return f"{stripped.removesuffix('/v1')}/api/v1/chat"
            return text
        if api_style == "openai" and stripped.endswith("/v1"):
            return f"{stripped}/chat/completions"
        return text
