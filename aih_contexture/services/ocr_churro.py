"""
OCR Churro Service

提供 Churro OCR 模型的 API 封装，支持：
- OpenAI 兼容的 API 调用
- XML 输出格式
- 异步处理
- 重试机制
"""

import json
import base64
from io import BytesIO
from typing import Optional
from lxml import etree

import PIL
from PIL import Image
import aiohttp

from aih_contexture.config.vlm_model_presets import (
    default_quant,
    default_version,
    normalize_quant,
    normalize_version,
    resolve_vlm_model,
)
from aih_contexture.logger import get_logger
from aih_contexture.services.ocr_base import BaseOcrService

logger = get_logger()


CHURRO_OFFICIAL_SYSTEM_PROMPT = "Transcribe the entiretly of this historical documents to XML format."


class OcrChurroService(BaseOcrService):
    """
    Churro OCR 服务

    专为历史文档设计的 3B 参数 VLM 模型
    """

    def __init__(self, config: dict):
        """初始化服务"""
        super().__init__(config)
        self.max_retries = config.get("max_retries", 3)
        self.churro_version = normalize_version("churro", str(config.get("churro_version") or default_version("churro")).strip())
        self.churro_quant = normalize_quant(
            "churro",
            self.churro_version,
            str(config.get("churro_quant") or default_quant("churro")).strip(),
        )
        if not self.ocr_model:
            self.ocr_model = resolve_vlm_model("churro", version=self.churro_version, quant=self.churro_quant)
        self.ocr_api_style = str(config.get("ocr_api_style", "openai")).strip().lower()
        if self.ocr_api_style == "openai-compatible":
            self.ocr_api_style = "openai"
        elif self.ocr_api_style == "lmstudio_native":
            self.ocr_api_style = "lmstudio-native"
        if self.ocr_api_style not in ("openai", "lmstudio-native"):
            logger.warning(f"Unknown ocr_api_style={self.ocr_api_style}, fallback to openai")
            self.ocr_api_style = "openai"
        self.image_format = str(config.get("ocr_image_format") or "PNG").strip().upper()
        if self.image_format == "JPG":
            self.image_format = "JPEG"
        if self.image_format not in {"PNG", "JPEG", "WEBP"}:
            self.image_format = "PNG"
        self.image_quality = int(config.get("ocr_image_quality") or 95)

    def get_backend_name(self) -> str:
        """获取后端名称"""
        return "churro"

    def get_runtime_profile(self) -> dict:
        """返回当前 service 的运行时 profile 元数据。"""
        return {
            "backend": "churro",
            "churro_version": self.churro_version,
            "churro_quant": self.churro_quant,
            "api_style": self.ocr_api_style,
            "bbox_scale": None,
            "preprocess_profile": "official_churro_max_2500",
            "sampling_profile": None,
            "official_protocol": "churro_historical_document_xml",
            "model_family": "Churro 3B HistoricalDocument XML",
            "image_transport": self.image_format,
        }

    def _img_to_base64(self, img: PIL.Image.Image) -> str:
        """将图像转换为 base64 编码"""
        buffered = BytesIO()
        if self.image_format == "JPEG" and img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        save_kwargs = {"format": self.image_format}
        if self.image_format == "JPEG":
            save_kwargs.update({"quality": self.image_quality, "optimize": True})
        img.save(buffered, **save_kwargs)
        return base64.b64encode(buffered.getvalue()).decode()

    def _build_prompt(self) -> str:
        """构建 Churro OCR prompt"""
        return CHURRO_OFFICIAL_SYSTEM_PROMPT

    def _build_payload(self, img_base64: str, prompt: str) -> dict:
        mime = f"image/{self.image_format.lower()}"
        if self.ocr_api_style == "lmstudio-native":
            payload = {
                "model": self.ocr_model,
                "input": [
                    {"type": "text", "content": prompt},
                    {"type": "image", "data_url": f"data:{mime};base64,{img_base64}"},
                ],
                "store": False,
                "temperature": self.ocr_temperature,
                "max_output_tokens": self.ocr_max_tokens,
            }
        else:
            payload = {
                "model": self.ocr_model,
                "messages": [
                    {
                        "role": "system",
                        "content": [
                            {"type": "text", "text": prompt},
                        ],
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime};base64,{img_base64}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": self.ocr_max_tokens,
                "temperature": self.ocr_temperature
            }
        return payload

    def _extract_openai_text(self, body: dict) -> str:
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        message = choices[0].get("message", {})
        content = message.get("content")
        return content if isinstance(content, str) else ""

    def _extract_lmstudio_native_text(self, body: dict) -> str:
        candidates = [
            body.get("content"),
            body.get("output_text"),
            body.get("text"),
            body.get("response"),
        ]
        for item in candidates:
            if isinstance(item, str) and item.strip():
                return item

        output = body.get("output")
        if isinstance(output, list):
            parts = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                for key in ("text", "content"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        parts.append(value)
                content = item.get("content")
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict):
                            value = part.get("text")
                            if isinstance(value, str) and value.strip():
                                parts.append(value)
            if parts:
                return "".join(parts)

        prediction = body.get("prediction")
        if isinstance(prediction, dict):
            for key in ("text", "content"):
                value = prediction.get(key)
                if isinstance(value, str) and value.strip():
                    return value

        return ""

    def _extract_response_text(self, body: dict) -> str:
        if self.ocr_api_style == "lmstudio-native":
            return self._extract_lmstudio_native_text(body)
        return self._extract_openai_text(body)

    async def process_page_async(
        self,
        session: aiohttp.ClientSession,
        img: Image.Image,
        api_key: Optional[str] = None
    ) -> str:
        """
        异步处理单页图像

        Args:
            session: aiohttp ClientSession
            img: PIL Image 对象
            api_key: API 密钥（可选）

        Returns:
            XML 字符串
        """
        img_base64 = self._img_to_base64(img)
        prompt = self._build_prompt()

        # 构建请求
        headers = {
            "Content-Type": "application/json"
        }
        if api_key or self.ocr_api_key:
            headers["Authorization"] = f"Bearer {api_key or self.ocr_api_key}"

        payload = self._build_payload(img_base64, prompt)

        # 重试逻辑
        for attempt in range(self.max_retries):
            try:
                timeout = aiohttp.ClientTimeout(total=self.ocr_timeout)
                async with session.post(
                    self.ocr_endpoint,
                    json=payload,
                    headers=headers,
                    timeout=timeout
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        from aih_contexture.utils.churro_output import normalize_churro_xml_output

                        xml_output = normalize_churro_xml_output(self._extract_response_text(result))

                        if not xml_output.strip():
                            logger.warning(f"Empty XML output, attempt {attempt + 1}")
                            if attempt < self.max_retries - 1:
                                continue
                            raise ValueError("Churro returned empty XML output")

                        try:
                            etree.fromstring(xml_output.encode())
                        except etree.XMLSyntaxError as e:
                            logger.warning(f"Invalid XML output, attempt {attempt + 1}: {e}")
                            if attempt < self.max_retries - 1:
                                continue
                            raise ValueError(f"Churro returned invalid XML output: {e}") from e

                        return xml_output
                    else:
                        error_text = await response.text()
                        logger.error(f"API error {response.status}: {error_text}")
                        if attempt < self.max_retries - 1:
                            continue
                        raise Exception(f"API error: {response.status}")

            except Exception as e:
                logger.error(f"Request failed (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    continue
                raise

        raise Exception("Max retries exceeded")
