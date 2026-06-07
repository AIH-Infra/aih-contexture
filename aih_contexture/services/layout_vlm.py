"""
VLM 版面识别服务

使用 OpenAI 兼容 API 进行版面识别，支持 LM Studio、OpenAI、Claude 等后端。
"""

import base64
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from typing import Annotated, Any, Dict, List, Optional

import openai
from openai import APITimeoutError, RateLimitError
from PIL import Image

from aih_contexture.logger import get_logger
from aih_contexture.utils.api_key_rotator import APIKeyRotator
from aih_contexture.services.layout_base import (
    BaseLayoutService,
    LayoutBox,
    LayoutResult,
    SUPPORTED_LAYOUT_LABELS,
)

logger = get_logger()


# 默认版面识别提示词
DEFAULT_LAYOUT_PROMPT = """Analyze this document page and identify all layout regions.

For each region you detect, provide:
- label: The type of content. Must be one of: Text, SectionHeader, ListItem, Figure, Picture, Table, Equation, Code, Caption, Footnote, PageHeader, PageFooter, Form, Handwriting, TableOfContents, ComplexRegion
- polygon: Bounding box coordinates as [[x1,y1], [x2,y2], [x3,y3], [x4,y4]] in pixel coordinates (top-left, top-right, bottom-right, bottom-left)
- confidence: Confidence score between 0.0 and 1.0

Return your response as JSON in this exact format:
{"regions": [{"label": "Text", "polygon": [[0,0], [100,0], [100,50], [0,50]], "confidence": 0.95}, ...]}

Important:
- Detect ALL visible regions on the page
- Use precise bounding boxes that tightly fit each region
- Order regions by reading order (top-to-bottom, left-to-right for LTR documents)
- Do not overlap regions unless necessary
"""


class VlmLayoutService(BaseLayoutService):
    """
    使用 VLM (Vision Language Model) 进行版面识别。

    通过 OpenAI 兼容 API 发送页面图像，让 VLM 识别版面结构。
    """

    # VLM Layout 专用 API 配置（独立于 OCR）
    vlm_layout_base_url: Annotated[
        str,
        "VLM Layout 专用 API 的 Base URL（若未设置则使用 openai_base_url）"
    ] = ""

    vlm_layout_model: Annotated[
        str,
        "VLM Layout 专用模型名称（若未设置则使用 openai_model）"
    ] = ""

    vlm_layout_api_key: Annotated[
        str,
        "VLM Layout 专用 API 密钥（若未设置则使用 openai_api_key）"
    ] = ""

    # 图像处理配置
    vlm_layout_image_format: Annotated[
        str,
        "发送给 VLM 的图像格式: jpeg, png, webp"
    ] = "jpeg"

    vlm_layout_max_image_dimension: Annotated[
        int,
        "图像最大边长（像素），超过会缩放"
    ] = 1536

    vlm_layout_jpeg_quality: Annotated[
        int,
        "JPEG 压缩质量 (1-100)"
    ] = 85

    # 版面识别配置
    vlm_layout_prompt: Annotated[
        str,
        "版面识别提示词（直接指定，优先级最高）"
    ] = ""

    vlm_layout_prompt_template: Annotated[
        str,
        "版面识别提示词模板名称: modern, chinese_ancient, gothic_german, archive, table_form, scientific"
    ] = "modern"

    vlm_layout_timeout: Annotated[
        int,
        "版面识别超时时间（秒）"
    ] = 120

    vlm_layout_max_tokens: Annotated[
        int,
        "VLM 最大输出 token 数"
    ] = 4096

    vlm_layout_max_concurrent: Annotated[
        int,
        "VLM Layout 最大并发请求数"
    ] = 1

    def __init__(self, config: Optional[dict] = None):
        """
        初始化 VLM 版面识别服务。

        配置优先级：
        1. vlm_layout_* 专用配置（最高优先级）
        2. openai_* 配置（回退，保持向后兼容）
        3. 默认值

        提示词优先级：
        1. vlm_layout_prompt（直接指定的自定义提示词）
        2. vlm_layout_prompt_template（使用预制模板）
        3. 默认 modern 模板
        """
        super().__init__(config)

        config = config or {}

        # === API 配置：优先使用 vlm_layout_* ，回退到 openai_* ===
        self.base_url = (
            config.get("vlm_layout_base_url")
            or config.get("openai_base_url")
            or "http://127.0.0.1:1234/v1"
        )

        self.model = (
            config.get("vlm_layout_model")
            or config.get("openai_model")
            or "gpt-4o"
        )

        self.api_key = (
            config.get("vlm_layout_api_key")
            or config.get("openai_api_key")
            or "lm-studio"
        )

        # 初始化Key轮换器(支持多Key,逗号分隔)
        self.key_rotator = APIKeyRotator(self.api_key)
        if self.key_rotator.get_key_count() > 1:
            logger.info(f"[VlmLayoutService] Using {self.key_rotator.get_key_count()} API keys with rotation")

        # === 图像处理配置 ===
        self.image_format = config.get(
            "vlm_layout_image_format",
            config.get("openai_image_format", "jpeg")
        )

        self.max_image_dimension = int(config.get(
            "vlm_layout_max_image_dimension",
            config.get("max_image_dimension", 1536)
        ))

        self.jpeg_quality = int(config.get(
            "vlm_layout_jpeg_quality",
            config.get("jpeg_quality", 85)
        ))

        # === 版面识别特定配置 ===
        self.vlm_layout_timeout = int(config.get("vlm_layout_timeout", 120))
        self.vlm_layout_max_tokens = int(config.get("vlm_layout_max_tokens", 4096))
        self.vlm_layout_max_concurrent = max(1, int(
            config.get("vlm_layout_max_concurrent")
            or config.get("vlm_layout_batch_size")
            or 1
        ))

        if config.get("confidence_threshold") is not None:
            self.confidence_threshold = float(config["confidence_threshold"])

        # === 提示词：优先直接指定，否则使用模板 ===
        if config.get("vlm_layout_prompt"):
            # 用户直接指定了提示词
            self.prompt = str(config["vlm_layout_prompt"])
            logger.info("[VlmLayoutService] Using custom prompt")
        else:
            # 使用模板
            template_name = config.get("vlm_layout_prompt_template", "modern")
            try:
                from aih_contexture.templates.vlm_layout_prompts import get_layout_prompt
                self.prompt = get_layout_prompt(template_name)
                logger.info(f"[VlmLayoutService] Using template: {template_name}")
            except Exception as e:
                logger.warning(f"[VlmLayoutService] Failed to load template, using default: {e}")
                self.prompt = DEFAULT_LAYOUT_PROMPT

        logger.info(f"[VlmLayoutService] Init: base_url={self.base_url}, model={self.model}")
        logger.info(f"[VlmLayoutService] Image: format={self.image_format}, max_dim={self.max_image_dimension}")

    def get_client(self, api_key: Optional[str] = None) -> openai.OpenAI:
        """
        获取 OpenAI 客户端

        Args:
            api_key: 可选的API Key,如果不提供则使用当前轮换的Key
        """
        key_to_use = api_key or self.key_rotator.get_current_key() or "lm-studio"
        return openai.OpenAI(
            base_url=self.base_url,
            api_key=key_to_use
        )

    def _resize_if_needed(self, img: Image.Image) -> Image.Image:
        """如果图像超过最大尺寸则缩放"""
        w, h = img.size
        if w <= self.max_image_dimension and h <= self.max_image_dimension:
            return img
        scale = min(self.max_image_dimension / w, self.max_image_dimension / h)
        new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
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

    def _get_scale_factor(self, original_size: tuple, resized_img: Image.Image) -> tuple:
        """计算缩放因子，用于将坐标映射回原图"""
        orig_w, orig_h = original_size
        new_w, new_h = resized_img.size
        return orig_w / new_w, orig_h / new_h

    def _extract_json(self, text: str) -> Optional[Dict]:
        """从 VLM 响应中提取 JSON"""
        if not text:
            return None

        s = text.strip()

        # 直接尝试解析
        try:
            return json.loads(s)
        except Exception:
            pass

        # 尝试提取 fenced code block
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", s)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except Exception:
                pass

        # 尝试提取第一个 JSON 对象
        m = re.search(r"\{[\s\S]*\}", s)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass

        return None

    def _parse_regions(
        self,
        data: Dict,
        image_size: tuple,
        scale_factor: tuple = (1.0, 1.0)
    ) -> List[LayoutBox]:
        """解析 VLM 返回的区域信息"""
        regions = data.get("regions", [])
        if not isinstance(regions, list):
            return []

        layout_boxes = []
        scale_x, scale_y = scale_factor

        for idx, region in enumerate(regions):
            if not isinstance(region, dict):
                continue

            label = region.get("label", "Text")
            polygon = region.get("polygon", region.get("bbox", []))
            confidence = region.get("confidence", 0.9)

            # 规范化标签
            normalized_label = self.normalize_label(label)
            if normalized_label not in SUPPORTED_LAYOUT_LABELS:
                normalized_label = "Text"

            # 处理 polygon 格式
            if isinstance(polygon, list):
                if len(polygon) == 4 and all(isinstance(p, list) and len(p) == 2 for p in polygon):
                    # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]] 格式
                    scaled_polygon = [
                        [p[0] * scale_x, p[1] * scale_y]
                        for p in polygon
                    ]
                elif len(polygon) == 4 and all(isinstance(p, (int, float)) for p in polygon):
                    # [x1, y1, x2, y2] bbox 格式，转换为 polygon
                    x1, y1, x2, y2 = polygon
                    scaled_polygon = [
                        [x1 * scale_x, y1 * scale_y],
                        [x2 * scale_x, y1 * scale_y],
                        [x2 * scale_x, y2 * scale_y],
                        [x1 * scale_x, y2 * scale_y],
                    ]
                else:
                    continue
            else:
                continue

            # 确保坐标在图像范围内
            img_w, img_h = image_size
            scaled_polygon = [
                [max(0, min(img_w, p[0])), max(0, min(img_h, p[1]))]
                for p in scaled_polygon
            ]

            layout_boxes.append(LayoutBox(
                label=normalized_label,
                position=idx,
                top_k={normalized_label: float(confidence)},
                polygon=scaled_polygon
            ))

        return layout_boxes

    def detect_layout(
        self,
        images: List[Image.Image],
        batch_size: int = 1
    ) -> List[LayoutResult]:
        """
        对一批图像进行版面识别。

        Args:
            images: PIL Image 列表
            batch_size: 批处理大小（当前每次处理一张图像）

        Returns:
            LayoutResult 列表，与输入图像一一对应
        """
        if self.vlm_layout_max_concurrent <= 1 or len(images) <= 1:
            client = self.get_client()
            return [self._detect_single_image_safely(client, img) for img in images]

        max_workers = min(self.vlm_layout_max_concurrent, len(images))
        logger.info(f"[VlmLayoutService] Using concurrent layout requests: {max_workers}")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            return list(executor.map(
                lambda img: self._detect_single_image_safely(self.get_client(), img),
                images,
            ))

    def _detect_single_image_safely(
        self,
        client: openai.OpenAI,
        img: Image.Image
    ) -> LayoutResult:
        try:
            return self._detect_single_image(client, img)
        except Exception as e:
            logger.error(f"[VlmLayoutService] Layout detection failed: {e}")
            w, h = img.size
            return LayoutResult(
                image_bbox=[0, 0, w, h],
                bboxes=[],
                sliced=False
            )

    def _detect_single_image(
        self,
        client: openai.OpenAI,
        img: Image.Image
    ) -> LayoutResult:
        """对单张图像进行版面识别"""
        original_size = img.size
        resized_img = self._resize_if_needed(img)
        scale_factor = self._get_scale_factor(original_size, resized_img)

        # 构建请求
        b64_img = self._img_to_base64(resized_img)
        fmt = (self.image_format or "jpeg").lower()
        mime = "jpeg" if fmt in ("jpg", "jpeg") else ("png" if fmt == "png" else "webp")

        content = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/{mime};base64,{b64_img}"}
            },
            {
                "type": "text",
                "text": self.prompt  # 使用初始化时确定的 prompt
            }
        ]

        # API 调用（带重试和Key轮换）
        max_retries = int(self.layout_max_retries or 2)
        # 如果有多个Key,增加重试次数
        if self.key_rotator.get_key_count() > 1:
            max_retries = max(max_retries, self.key_rotator.get_key_count())

        last_error = None

        for attempt in range(max_retries + 1):
            try:
                # 每次重试使用当前的Key创建新client
                current_key = self.key_rotator.get_current_key()
                client_for_attempt = self.get_client(current_key)

                resp = client_for_attempt.chat.completions.create(
                    model=self.model,  # 使用初始化时确定的 model
                    messages=[{"role": "user", "content": content}],
                    timeout=self.vlm_layout_timeout,
                    max_tokens=self.vlm_layout_max_tokens,
                )

                raw_text = (resp.choices[0].message.content or "").strip()
                data = self._extract_json(raw_text)

                if data is None:
                    logger.warning("[VlmLayoutService] Failed to parse JSON from VLM response")
                    data = {"regions": []}

                # 解析区域
                layout_boxes = self._parse_regions(data, original_size, scale_factor)

                # 构建结果
                w, h = original_size
                result = LayoutResult(
                    image_bbox=[0, 0, w, h],
                    bboxes=layout_boxes,
                    sliced=False
                )

                # 验证标签并过滤低置信度
                result = self.validate_labels(result)
                result = self.filter_by_confidence(result)

                # 成功,标记成功
                self.key_rotator.mark_success()
                return result

            except (APITimeoutError, RateLimitError) as e:
                last_error = e
                logger.warning(f"[VlmLayoutService] Retryable error (attempt {attempt + 1}): {e}")
                if attempt < max_retries:
                    # 切换到下一个Key
                    next_key = self.key_rotator.mark_failure_and_rotate()
                    logger.info(f"[VlmLayoutService] Rotating to next API key (attempt {attempt + 2})")
                    time.sleep(2 * (attempt + 1))
                    continue

            except Exception as e:
                last_error = e
                logger.error(f"[VlmLayoutService] Error: {e}")
                # 非重试错误也切换Key
                if attempt < max_retries:
                    self.key_rotator.mark_failure_and_rotate()
                break

        # 所有重试失败，返回空结果
        logger.error(f"[VlmLayoutService] All retries failed: {last_error}")
        w, h = original_size
        return LayoutResult(
            image_bbox=[0, 0, w, h],
            bboxes=[],
            sliced=False
        )

    def health_check(self) -> bool:
        """检查 VLM 服务是否可用"""
        try:
            client = self.get_client()
            # 发送一个简单的文本请求来测试连接
            resp = client.chat.completions.create(
                model=self.model,  # 使用初始化时确定的 model
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5,
                timeout=10,
            )
            return True
        except Exception as e:
            logger.warning(f"[VlmLayoutService] Health check failed: {e}")
            return False
