"""
VLM Direct Converter - 直接使用 VLM 处理整页，返回 Markdown

跳过传统的 Layout Detection + OCR 流程，直接用超强视觉大模型处理整页图像。
适合使用 GPT-4o, Claude 3.5 Sonnet, Gemini 等强大的多模态模型。

优势：
- 最简单的流程：图像 → VLM → Markdown
- 最高的准确度：利用大模型的理解能力
- 最好的格式保持：大模型能理解复杂的文档结构

劣势：
- 速度较慢：每页需要调用一次 API
- 成本较高：大模型 API 按 token 计费
- 需要网络：依赖外部 API
"""

import base64
import time
from io import BytesIO
from typing import Annotated, List, Optional

import openai
from openai import APITimeoutError, RateLimitError
from PIL import Image

from aih_contexture.converters import BaseConverter
from aih_contexture.logger import get_logger
from aih_contexture.providers.registry import provider_from_filepath

logger = get_logger()


# 默认提示词
DEFAULT_PROMPT = """Convert this document page to Markdown format.

Requirements:
1. Preserve the exact structure and formatting
2. Use proper Markdown syntax for:
   - Headings (# ## ###)
   - Lists (- or 1. 2. 3.)
   - Tables (| col1 | col2 |)
   - Code blocks (```language```)
   - Math equations ($inline$ or $$block$$)
   - Bold (**text**) and italic (*text*)
3. Maintain reading order (top-to-bottom, left-to-right for LTR documents)
4. Do NOT add any explanations or comments
5. Output ONLY the Markdown content

Return the Markdown directly without any wrapper or code blocks."""


class VlmDirectConverter(BaseConverter):
    """
    VLM Direct Converter - 直接使用 VLM 处理整页返回 Markdown

    配置参数：
    - vlm_direct_base_url: API Base URL
    - vlm_direct_model: 模型名称
    - vlm_direct_api_key: API 密钥
    - vlm_direct_prompt: 自定义提示词
    - vlm_direct_max_image_dimension: 图像最大边长
    - vlm_direct_jpeg_quality: JPEG 质量
    - vlm_direct_timeout: 超时时间
    - vlm_direct_max_tokens: 最大输出 token 数
    """

    # API 配置
    vlm_direct_base_url: Annotated[
        str,
        "VLM API 的 Base URL"
    ] = "https://api.openai.com/v1"

    vlm_direct_model: Annotated[
        str,
        "VLM 模型名称"
    ] = "gpt-4o"

    vlm_direct_api_key: Annotated[
        str,
        "API 密钥"
    ] = ""

    # 提示词配置
    vlm_direct_prompt: Annotated[
        str,
        "转换提示词"
    ] = DEFAULT_PROMPT

    # 图像处理配置
    vlm_direct_image_format: Annotated[
        str,
        "图像格式: jpeg, png, webp"
    ] = "jpeg"

    vlm_direct_max_image_dimension: Annotated[
        int,
        "图像最大边长（像素）"
    ] = 2048

    vlm_direct_jpeg_quality: Annotated[
        int,
        "JPEG 压缩质量 (1-100)"
    ] = 90

    # API 调用配置
    vlm_direct_timeout: Annotated[
        int,
        "API 超时时间（秒）"
    ] = 180

    vlm_direct_max_tokens: Annotated[
        int,
        "最大输出 token 数"
    ] = 8192

    vlm_direct_max_retries: Annotated[
        int,
        "最大重试次数"
    ] = 3

    # 页面分隔符
    vlm_direct_page_separator: Annotated[
        str,
        "页面之间的分隔符"
    ] = "\n\n---\n\n"

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        config = config or {}

        # 加载配置
        self.base_url = config.get("vlm_direct_base_url", self.vlm_direct_base_url)
        self.model = config.get("vlm_direct_model", self.vlm_direct_model)
        self.api_key = config.get("vlm_direct_api_key", self.vlm_direct_api_key)

        self.prompt = config.get("vlm_direct_prompt", self.vlm_direct_prompt)

        self.image_format = config.get("vlm_direct_image_format", self.vlm_direct_image_format)
        self.max_image_dimension = int(config.get("vlm_direct_max_image_dimension", self.vlm_direct_max_image_dimension))
        self.jpeg_quality = int(config.get("vlm_direct_jpeg_quality", self.vlm_direct_jpeg_quality))

        self.timeout = int(config.get("vlm_direct_timeout", self.vlm_direct_timeout))
        self.max_tokens = int(config.get("vlm_direct_max_tokens", self.vlm_direct_max_tokens))
        self.max_retries = int(config.get("vlm_direct_max_retries", self.vlm_direct_max_retries))

        self.page_separator = config.get("vlm_direct_page_separator", self.vlm_direct_page_separator)

        logger.info(f"[VlmDirectConverter] Init: base_url={self.base_url}, model={self.model}")
        logger.info(f"[VlmDirectConverter] Image: format={self.image_format}, max_dim={self.max_image_dimension}")

    def get_client(self) -> openai.OpenAI:
        """获取 OpenAI 客户端"""
        return openai.OpenAI(
            base_url=self.base_url,
            api_key=self.api_key or "default-key"
        )

    def _resize_if_needed(self, img: Image.Image) -> Image.Image:
        """如果图像超过最大尺寸则缩放"""
        w, h = img.size
        if w <= self.max_image_dimension and h <= self.max_image_dimension:
            return img
        scale = min(self.max_image_dimension / w, self.max_image_dimension / h)
        new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
        logger.info(f"[VlmDirectConverter] Resizing image from {w}x{h} to {new_size[0]}x{new_size[1]}")
        return img.resize(new_size, Image.Resampling.LANCZOS)

    def _img_to_base64(self, img: Image.Image) -> str:
        """将图像转换为 base64 编码"""
        fmt = (self.image_format or "jpeg").lower()
        img = self._resize_if_needed(img)

        buf = BytesIO()
        if fmt in ("jpg", "jpeg"):
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            img.save(buf, format="JPEG", quality=int(self.jpeg_quality), optimize=True)
        elif fmt == "webp":
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            img.save(buf, format="WEBP", quality=int(self.jpeg_quality))
        else:
            img.save(buf, format="PNG", optimize=True)

        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def _convert_page(self, client: openai.OpenAI, img: Image.Image, page_num: int) -> str:
        """转换单个页面"""
        logger.info(f"[VlmDirectConverter] Converting page {page_num}...")

        # 构建请求
        b64_img = self._img_to_base64(img)
        fmt = (self.image_format or "jpeg").lower()
        mime = "jpeg" if fmt in ("jpg", "jpeg") else ("png" if fmt == "png" else "webp")

        content = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/{mime};base64,{b64_img}"}
            },
            {
                "type": "text",
                "text": self.prompt
            }
        ]

        # API 调用（带重试）
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": content}],
                    timeout=self.timeout,
                    max_tokens=self.max_tokens,
                )

                markdown = (resp.choices[0].message.content or "").strip()
                logger.info(f"[VlmDirectConverter] Page {page_num} converted successfully ({len(markdown)} chars)")
                return markdown

            except (APITimeoutError, RateLimitError) as e:
                last_error = e
                logger.warning(f"[VlmDirectConverter] Retryable error on page {page_num} (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries:
                    time.sleep(2 * (attempt + 1))
                    continue

            except Exception as e:
                last_error = e
                logger.error(f"[VlmDirectConverter] Error on page {page_num}: {e}")
                break

        # 所有重试失败
        logger.error(f"[VlmDirectConverter] Failed to convert page {page_num}: {last_error}")
        return f"<!-- Error converting page {page_num}: {last_error} -->"

    def __call__(self, filepath: str) -> str:
        """
        转换文档为 Markdown

        Args:
            filepath: 文档路径

        Returns:
            完整的 Markdown 文本
        """
        logger.info(f"[VlmDirectConverter] Starting conversion: {filepath}")

        # 1. 加载文档
        provider_cls = provider_from_filepath(filepath)
        provider = provider_cls(filepath, self.config)

        # 2. 获取所有页面图像
        images = []
        for page_idx in range(len(provider)):
            page = provider[page_idx]
            img = page.get_image()
            images.append(img)

        logger.info(f"[VlmDirectConverter] Loaded {len(images)} pages")

        # 3. 逐页转换
        client = self.get_client()
        markdown_pages = []

        for idx, img in enumerate(images):
            page_num = idx + 1
            markdown = self._convert_page(client, img, page_num)
            markdown_pages.append(markdown)

        # 4. 拼接所有页面
        full_markdown = self.page_separator.join(markdown_pages)

        logger.info(f"[VlmDirectConverter] Conversion complete: {len(full_markdown)} chars total")
        return full_markdown
