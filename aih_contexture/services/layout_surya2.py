from __future__ import annotations

import asyncio

import aiohttp
from PIL import Image

from aih_contexture.config.vlm_model_presets import default_version, normalize_version, resolve_vlm_model
from aih_contexture.logger import get_logger
from aih_contexture.services.layout_base import BaseLayoutService, LayoutBox, LayoutResult, SUPPORTED_LAYOUT_LABELS
from aih_contexture.services.ocr_vlm_specialized import OpenAICompatibleVlmMixin
from aih_contexture.vendor.surya2_compat import (
    SURYA2_PROMPTS,
    parse_surya2_layout_json,
    surya2_label_for_contexture,
)

logger = get_logger()


class Surya2LayoutService(OpenAICompatibleVlmMixin, BaseLayoutService):
    """Surya 2 official VLM layout prompt as a Pipeline layout backend."""

    ocr_api_style: str = "openai"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        config = config or {}
        self.ocr_api_style = str(config.get("surya2_api_style") or config.get("ocr_api_style") or "openai").strip().lower()
        if self.ocr_api_style == "openai-compatible":
            self.ocr_api_style = "openai"
        self.ocr_endpoint = self._normalize_endpoint(
            config.get("surya2_endpoint")
            or config.get("ocr_endpoint")
            or config.get("openai_base_url"),
            api_style=self.ocr_api_style,
        )
        self.ocr_api_key = str(config.get("surya2_api_key") or config.get("ocr_api_key") or config.get("openai_api_key") or "").strip()
        self.ocr_timeout = int(config.get("surya2_layout_timeout", config.get("ocr_timeout", 120)))
        self.ocr_max_tokens = int(config.get("surya2_layout_max_tokens", config.get("ocr_max_tokens", 4096)))
        self.layout_retry_max_tokens = int(config.get("surya2_layout_retry_max_tokens", max(self.ocr_max_tokens, 4096)))
        self.ocr_temperature = float(config.get("ocr_temperature", 0.0))
        self.image_quality = int(config.get("surya2_image_quality", config.get("ocr_image_quality", 90)))
        self.image_format = str(config.get("surya2_image_format") or "PNG").strip().upper() or "PNG"
        self.vlm_request_concurrency = int(config.get("surya2_request_concurrency", config.get("surya2_layout_concurrency", 6)) or 6)
        self.layout_window_size = max(1, int(config.get("surya2_layout_batch_size") or config.get("surya2_layout_concurrency") or self.vlm_request_concurrency or 6))
        self.surya2_version = normalize_version("surya2", str(config.get("surya2_version") or default_version("surya2")).strip())
        self.ocr_model = str(config.get("surya2_model") or config.get("ocr_model") or "").strip()
        if not self.ocr_model:
            self.ocr_model = resolve_vlm_model("surya2", version=self.surya2_version)

    def get_backend_name(self) -> str:
        return "surya2_layout"

    def detect_layout(self, images: list[Image.Image], batch_size: int = 1) -> list[LayoutResult]:
        del batch_size
        return asyncio.run(self._detect_layout_async(images))

    async def _detect_layout_async(self, images: list[Image.Image]) -> list[LayoutResult]:
        results: list[LayoutResult] = []
        async with aiohttp.ClientSession() as session:
            for start in range(0, len(images), self.layout_window_size):
                window = images[start:start + self.layout_window_size]
                tasks = [self._detect_single_image(session, image) for image in window]
                results.extend(await asyncio.gather(*tasks))
        return results

    async def _detect_single_image(self, session: aiohttp.ClientSession, img: Image.Image) -> LayoutResult:
        original_size = img.size
        try:
            layout_text, raw = await self._post_layout_request(session, img, max_tokens=self.ocr_max_tokens)
            boxes = self._parse_layout(layout_text, original_size)
            if not boxes and self.layout_retry_max_tokens > self.ocr_max_tokens and self._should_retry_layout(layout_text, raw):
                logger.warning(
                    "[Surya2LayoutService] Layout parse returned no boxes; retrying with max_tokens=%s",
                    self.layout_retry_max_tokens,
                )
                layout_text, raw = await self._post_layout_request(session, img, max_tokens=self.layout_retry_max_tokens)
                boxes = self._parse_layout(layout_text, original_size)
            result = LayoutResult(
                image_bbox=[0, 0, original_size[0], original_size[1]],
                bboxes=boxes,
                sliced=False,
            )
            return self.validate_labels(result)
        except Exception as exc:
            logger.error("[Surya2LayoutService] Layout detection failed: %s", exc)
            return LayoutResult(image_bbox=[0, 0, original_size[0], original_size[1]], bboxes=[], sliced=False)

    async def _post_layout_request(
        self,
        session: aiohttp.ClientSession,
        img: Image.Image,
        *,
        max_tokens: int,
    ) -> tuple[str, dict]:
        return await self._post_vlm(
                session,
                img=img.convert("RGB"),
                prompt=SURYA2_PROMPTS["layout"],
                api_key=self.ocr_api_key,
                image_format=self.image_format,
                image_quality=self.image_quality,
                max_tokens=max_tokens,
                temperature=0.0,
                top_p=0.01,
                include_system=False,
            )

    @staticmethod
    def _should_retry_layout(text: str, raw: dict) -> bool:
        stripped = str(text or "").strip()
        if not stripped:
            return True
        if stripped.count("[") > stripped.count("]") or stripped.count("{") > stripped.count("}"):
            return True
        choices = raw.get("choices") if isinstance(raw, dict) else None
        if isinstance(choices, list) and choices:
            reason = choices[0].get("finish_reason") if isinstance(choices[0], dict) else None
            if reason in {"length", "max_tokens"}:
                return True
        return False

    def _parse_layout(self, text: str, page_size: tuple[int, int]) -> list[LayoutBox]:
        boxes: list[LayoutBox] = []
        for block in parse_surya2_layout_json(text, page_size=page_size):
            raw_label = str(block.get("raw_label") or block.get("label") or "")
            label = surya2_label_for_contexture(raw_label)
            if label not in SUPPORTED_LAYOUT_LABELS:
                label = "Text"
            x0, y0, x1, y1 = [float(value) for value in block["bbox"]]
            boxes.append(
                LayoutBox(
                    label=label,
                    position=int(block.get("order", len(boxes))),
                    top_k={label: 1.0},
                    polygon=[[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
                    metadata={
                        "raw_label": raw_label,
                        "backend_label": raw_label,
                        "label_source": "backend_native",
                        "native_layout_backend": self.get_backend_name(),
                        "normalized_bbox": block.get("normalized_bbox"),
                        "loc_bbox_1000": block.get("loc_bbox_1000"),
                    },
                )
            )
        return boxes

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
