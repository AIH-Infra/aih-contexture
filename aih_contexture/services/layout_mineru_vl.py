from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
from PIL import Image

from aih_contexture.config.vlm_model_presets import default_quant, default_version, normalize_quant, normalize_version, resolve_vlm_model
from aih_contexture.logger import get_logger
from aih_contexture.services.layout_base import BaseLayoutService, LayoutBox, LayoutResult, SUPPORTED_LAYOUT_LABELS
from aih_contexture.services.ocr_vlm_specialized import OpenAICompatibleVlmMixin
from aih_contexture.vendor.mineru_vl_compat import (
    MINERU_VL_PROMPTS,
    convert_mineru_vl_bbox,
    mineru_vl_layout_label_for_ref,
    parse_mineru_vl_layout_tokens,
)

logger = get_logger()


class MineruVLLayoutService(OpenAICompatibleVlmMixin, BaseLayoutService):
    """MinerU-VL official Layout Detection protocol as a Pipeline layout backend."""

    ocr_api_style: str = "lmstudio-native"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        config = config or {}
        self.ocr_api_style = str(config.get("mineru_vl_api_style") or config.get("ocr_api_style") or "lmstudio-native").strip().lower()
        if self.ocr_api_style == "openai-compatible":
            self.ocr_api_style = "openai"
        self.ocr_endpoint = self._normalize_endpoint(
            config.get("mineru_vl_endpoint")
            or config.get("ocr_endpoint")
            or config.get("openai_base_url"),
            api_style=self.ocr_api_style,
        )
        self.ocr_api_key = str(config.get("mineru_vl_api_key") or config.get("ocr_api_key") or config.get("openai_api_key") or "").strip()
        self.ocr_timeout = int(config.get("mineru_vl_layout_timeout", config.get("ocr_timeout", 120)))
        self.ocr_max_tokens = int(config.get("mineru_vl_layout_max_tokens", config.get("ocr_max_tokens", 4096)))
        self.ocr_temperature = float(config.get("ocr_temperature", 0.0))
        self.layout_image_size = tuple(config.get("mineru_vl_layout_image_size", (1036, 1036)))
        self.image_quality = int(config.get("mineru_vl_image_quality", config.get("ocr_image_quality", 90)))
        self.vlm_request_concurrency = int(config.get("mineru_vl_request_concurrency", config.get("mineru_vl_layout_concurrency", 1)) or 1)
        self.layout_window_size = max(
            1,
            int(
                config.get("mineru_vl_layout_batch_size")
                or config.get("mineru_vl_layout_concurrency")
                or self.vlm_request_concurrency
                or 1
            ),
        )
        self.mineru_vl_version = normalize_version(
            "mineru_vl",
            str(config.get("mineru_vl_version") or default_version("mineru_vl")).strip(),
        )
        self.mineru_vl_quant = normalize_quant(
            "mineru_vl",
            self.mineru_vl_version,
            str(config.get("mineru_vl_quant") or default_quant("mineru_vl")).strip(),
        )
        self.ocr_model = str(config.get("mineru_vl_model") or config.get("ocr_model") or "").strip()
        if not self.ocr_model:
            self.ocr_model = resolve_vlm_model(
                "mineru_vl",
                version=self.mineru_vl_version,
                quant=self.mineru_vl_quant,
            )

    def get_backend_name(self) -> str:
        return "mineru_vl_layout"

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
        layout_img = img.convert("RGB").resize(self.layout_image_size, Image.Resampling.BICUBIC)
        try:
            layout_text, _raw = await self._post_vlm(
                session,
                img=layout_img,
                prompt=MINERU_VL_PROMPTS["layout"],
                api_key=self.ocr_api_key,
                image_format="PNG",
                image_quality=self.image_quality,
                temperature=0.0,
                top_p=0.01,
                extra={"skip_special_tokens": False} if self.ocr_api_style != "lmstudio-native" else None,
            )
            boxes = self._parse_layout(layout_text, original_size)
            result = LayoutResult(image_bbox=[0, 0, original_size[0], original_size[1]], bboxes=boxes, sliced=False)
            return self.validate_labels(result)
        except Exception as exc:
            logger.error("[MineruVLLayoutService] Layout detection failed: %s", exc)
            return LayoutResult(image_bbox=[0, 0, original_size[0], original_size[1]], bboxes=[], sliced=False)

    def _parse_layout(self, text: str, page_size: tuple[int, int]) -> list[LayoutBox]:
        boxes: list[LayoutBox] = []
        for block in parse_mineru_vl_layout_tokens(text, page_size):
            px_bbox = [float(value) for value in block["bbox"]]
            normalized_label = self._label_for_mineru_ref(str(block.get("label") or ""))
            if normalized_label not in SUPPORTED_LAYOUT_LABELS:
                normalized_label = "Text"
            raw_label = str(block.get("label") or "").strip().lower()
            x0, y0, x3, y3 = px_bbox
            boxes.append(
                LayoutBox(
                    label=normalized_label,
                    position=int(block.get("order", len(boxes))),
                    top_k={normalized_label: 1.0},
                    polygon=[[x0, y0], [x3, y0], [x3, y3], [x0, y3]],
                    metadata={
                        "raw_label": raw_label,
                        "backend_label": raw_label,
                        "label_source": "backend_native",
                        "native_layout_backend": self.get_backend_name(),
                        "normalized_bbox": block.get("normalized_bbox"),
                        "rotate": block.get("rotate"),
                        "token_tail": block.get("tail"),
                    },
                )
            )
        return boxes

    @staticmethod
    def _convert_bbox(values: tuple[str, str, str, str]) -> list[float] | None:
        return convert_mineru_vl_bbox(values)

    def _label_for_mineru_ref(self, label: str) -> str:
        mapped = mineru_vl_layout_label_for_ref(label)
        if mapped:
            return mapped
        return self.normalize_label(label)

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
        if api_style == "openai":
            if stripped.endswith("/v1"):
                return f"{stripped}/chat/completions"
        return text
