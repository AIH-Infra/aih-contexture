"""
OCR Chandra Service

提供 Chandra OCR 模型的 API 封装，支持：
- OpenAI 兼容的 API 调用
- 异步和同步模式
- 重试机制
- 多种输出格式 (JSON/HTML/Markdown)
- 异常检测和暂停-恢复机制
"""

import json
import time
import base64
from io import BytesIO
from typing import List, Dict, Any, Optional, Annotated


class ModelCrashError(Exception):
    """模型崩溃异常，用于触发暂停-恢复机制"""
    def __init__(self, message: str, consecutive_failures: int = 0):
        super().__init__(message)
        self.consecutive_failures = consecutive_failures

import PIL
from PIL import Image
import openai

from aih_contexture.logger import get_logger
from aih_contexture.services import BaseService

logger = get_logger()


class OcrChandraService(BaseService):
    """
    Chandra OCR 服务

    支持通过 OpenAI 兼容的 API 调用 Chandra 模型
    """

    ocr_endpoint: Annotated[
        str, "OCR API endpoint (OpenAI Chat Completions format)"
    ] = "http://localhost:1234/v1/chat/completions"

    ocr_model: Annotated[
        str, "OCR model name"
    ] = "chandra"

    ocr_api_key: Annotated[
        Optional[str], "API key for authentication (optional)"
    ] = ""

    ocr_output_format: Annotated[
        str, "Output format: json, html, or markdown"
    ] = "json"

    ocr_max_tokens: Annotated[
        int, "Maximum tokens for OCR response"
    ] = 12384  # Chandra 官方示例使用 12384

    ocr_temperature: Annotated[
        float, "Temperature for OCR model (0.0 for strict OCR)"
    ] = 0.0  # 最低温度，确保输出稳定

    ocr_timeout: Annotated[
        int, "Timeout for OCR API calls (seconds)"
    ] = 120

    # 异常检测配置
    max_consecutive_failures: Annotated[
        int, "Maximum consecutive abnormal outputs before stopping"
    ] = 3

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化服务

        Args:
            config: 可选的配置字典，包含以下键：
                - ocr_endpoint: API endpoint
                - ocr_model: 模型名称
                - ocr_api_key: API 密钥
                - ocr_output_format: 输出格式
                - ocr_max_tokens: 最大 token 数
                - ocr_temperature: 温度参数
                - ocr_timeout: 超时时间
                - max_retries: 最大重试次数
        """
        super().__init__()
        self._consecutive_failures = 0  # 连续异常计数器

        # 从配置字典设置属性
        if config:
            if "ocr_endpoint" in config:
                self.ocr_endpoint = config["ocr_endpoint"]
            if "ocr_model" in config:
                self.ocr_model = config["ocr_model"]
            if "ocr_api_key" in config:
                self.ocr_api_key = config["ocr_api_key"]
            if "ocr_output_format" in config:
                self.ocr_output_format = config["ocr_output_format"]
            if "ocr_max_tokens" in config:
                self.ocr_max_tokens = config["ocr_max_tokens"]
            if "ocr_temperature" in config:
                self.ocr_temperature = config["ocr_temperature"]
            if "ocr_timeout" in config:
                self.ocr_timeout = config["ocr_timeout"]
            if "max_retries" in config:
                self.max_retries = config["max_retries"]
            if "max_consecutive_failures" in config:
                self.max_consecutive_failures = config["max_consecutive_failures"]

    def _is_abnormal_output(self, result: str) -> bool:
        """
        检测输出是否异常（如全是问号、空白、重复循环等）

        Args:
            result: OCR 输出结果

        Returns:
            True 如果输出异常
        """
        if not result or len(result.strip()) < 10:
            return True

        # 检测全是问号或乱码
        question_marks = result.count('?') + result.count('？')
        if question_marks > len(result) * 0.5:  # 超过50%是问号
            return True

        # 检测重复字符（如 "????????..." 或 "000000..."）
        if len(set(result.strip())) < 5 and len(result) > 20:
            return True

        # 检测重复数字序列（如 "14600000000..."）
        digit_count = sum(1 for c in result if c.isdigit())
        if digit_count > len(result) * 0.7 and len(result) > 100:
            logger.warning(f"[异常检测] 检测到大量数字序列")
            return True

        # 检测重复短语循环（如 "Therefore it would seem..."）
        if len(result) > 500:
            # 检查是否有重复的长短语
            chunk_size = 50
            chunks = [result[i:i+chunk_size] for i in range(0, min(len(result), 1000), chunk_size)]
            if len(chunks) > 5:
                unique_chunks = set(chunks)
                if len(unique_chunks) < len(chunks) * 0.3:  # 重复率超过70%
                    logger.warning(f"[异常检测] 检测到重复短语循环")
                    return True

        return False

    def _build_prompt(self) -> str:
        """
        构建 OCR prompt (使用 Chandra 官方推荐的 ocr_layout 模式)
        """
        prompt = """OCR this image to HTML, arranged as layout blocks. Each layout block should be a div with the data-bbox attribute representing the bounding box of the block in [x0, y0, x1, y1] format. Bboxes are normalized 0-1024. The data-label attribute is the label for the block.

Use the following labels:
- Caption
- Footnote
- Equation-Block
- List-Group
- Page-Header
- Page-Footer
- Image
- Section-Header
- Table
- Text
- Complex-Block
- Code-Block
- Form
- Table-Of-Contents
- Figure

Only use these tags [math, br, i, b, u, del, sup, sub, table, tr, td, p, th, div, pre, h1, h2, h3, h4, h5, ul, ol, li, input, a, span, img, hr, tbody, small, caption, strong, thead, big, code], and these attributes [class, colspan, rowspan, display, checked, type, border, value, style, href, alt, align].

Guidelines:
* Tables: Use <table>, <tr>, <td>, <th> tags with colspan and rowspan attributes to match table structure.
* Inline math: Surround math with <math>...</math> tags in KaTeX-compatible LaTeX.
* Text: Join lines into paragraphs using <p>...</p> tags.
* Use the simplest possible HTML structure that accurately represents the content."""

        logger.info(f"[DEBUG] 使用官方 ocr_layout 提示词 (长度: {len(prompt)} 字符)")
        return prompt

    def _img_to_base64(self, img: PIL.Image.Image) -> str:
        """
        将图像转换为 base64 编码

        Args:
            img: PIL Image 对象

        Returns:
            base64 编码的字符串
        """
        buffered = BytesIO()

        # 确保是 RGB 模式
        if img.mode != "RGB":
            img = img.convert("RGB")

        # 记录图像尺寸
        logger.info(f"[DEBUG] 图像尺寸: {img.size[0]}x{img.size[1]} 像素")

        # 保存为 PNG（与其他分支一致）
        img.save(buffered, format="PNG")

        base64_str = base64.b64encode(buffered.getvalue()).decode()
        logger.info(f"[DEBUG] Base64 长度: {len(base64_str)} 字符")

        return base64_str

    def _build_request_payload(self, img_base64: str) -> Dict[str, Any]:
        """
        构建 API 请求 payload (OpenAI Chat Completions 格式)

        Args:
            img_base64: base64 编码的图像

        Returns:
            请求 payload 字典
        """
        prompt = self._build_prompt()

        # OpenAI Chat Completions 格式（按照 Chandra 官方示例）
        # 重要：图片在前，文本在后！
        payload = {
            "model": self.ocr_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{img_base64}"
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ],
            "max_tokens": self.ocr_max_tokens,
            "temperature": self.ocr_temperature,
            "top_p": 0.1
        }

        return payload

    def _build_headers(self) -> Dict[str, str]:
        """
        构建 API 请求 headers

        Returns:
            headers 字典
        """
        headers = {
            "Content-Type": "application/json"
        }

        if self.ocr_api_key:
            headers["Authorization"] = f"Bearer {self.ocr_api_key}"

        return headers

    def _parse_response(self, content: str) -> str:
        """
        解析 API 响应内容

        Chandra 返回 HTML 格式，直接返回字符串

        Args:
            content: API 返回的 HTML 内容

        Returns:
            HTML 字符串
        """
        return content.strip()

    def process_page(self, img: PIL.Image.Image) -> Dict[str, Any] | str:
        """
        同步处理单页图像（使用 OpenAI 客户端）

        Args:
            img: PIL Image 对象

        Returns:
            OCR 结果 (HTML string)
        """
        # 1. 图像转 base64
        img_base64 = self._img_to_base64(img)
        prompt = self._build_prompt()

        # 2. 创建 OpenAI 客户端
        client = openai.OpenAI(
            base_url=self.ocr_endpoint.replace("/chat/completions", ""),
            api_key=self.ocr_api_key or "default-key"
        )

        # 3. 构建消息内容（与 VLM Direct 一致）
        content = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img_base64}"}
            },
            {
                "type": "text",
                "text": prompt
            }
        ]

        logger.info(f"[DEBUG] 使用 OpenAI 客户端发送请求")

        # 4. 发送请求（带重试）
        for attempt in range(self.max_retries):
            try:
                resp = client.chat.completions.create(
                    model=self.ocr_model,
                    messages=[{"role": "user", "content": content}],
                    timeout=self.ocr_timeout,
                    max_tokens=self.ocr_max_tokens,
                    temperature=self.ocr_temperature,
                    top_p=0.1,
                    extra_body={
                        "repetition_penalty": 1.1,  # 防止重复生成
                        "stop": ["</div></div></div>"]  # 防止无限嵌套
                    }
                )

                # 检测 token 数为 0（模型崩溃的早期信号）
                if hasattr(resp, 'usage') and resp.usage:
                    total_tokens = getattr(resp.usage, 'total_tokens', -1)
                    if total_tokens == 0:
                        logger.warning(f"[异常检测] usage.total_tokens = 0，模型可能已崩溃")

                result = (resp.choices[0].message.content or "").strip()
                logger.info(f"[DEBUG] 返回内容长度: {len(result)} 字符")
                logger.info(f"[DEBUG] 返回内容前200字符: {result[:200]}")

                # 异常输出检测
                if self._is_abnormal_output(result):
                    self._consecutive_failures += 1
                    logger.warning(f"[异常检测] 检测到异常输出（连续第 {self._consecutive_failures} 次）")

                    if self._consecutive_failures >= self.max_consecutive_failures:
                        error_msg = (
                            f"⚠️ 检测到连续 {self._consecutive_failures} 次异常输出！\n"
                            f"模型可能已崩溃，请重启 LM Studio"
                        )
                        logger.error(error_msg)
                        raise ModelCrashError(error_msg, self._consecutive_failures)
                else:
                    self._consecutive_failures = 0

                return self._parse_response(result)

            except Exception as e:
                logger.warning(f"OCR request failed (attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 * (attempt + 1))
                else:
                    raise

    async def process_page_async(
        self,
        session,  # 不再使用 aiohttp session
        img: PIL.Image.Image,
        api_key: Optional[str] = None
    ) -> Dict[str, Any] | str:
        """
        异步处理单页图像（使用 OpenAI 异步客户端）

        Args:
            session: 保留参数兼容性（不再使用）
            img: PIL Image 对象
            api_key: 可选的 API 密钥

        Returns:
            OCR 结果 (HTML string)
        """
        import asyncio

        # 1. 图像转 base64
        img_base64 = self._img_to_base64(img)
        prompt = self._build_prompt()

        # 2. 创建 OpenAI 异步客户端
        client = openai.AsyncOpenAI(
            base_url=self.ocr_endpoint.replace("/chat/completions", ""),
            api_key=api_key or self.ocr_api_key or "default-key"
        )

        # 3. 构建消息内容
        content = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img_base64}"}
            },
            {
                "type": "text",
                "text": prompt
            }
        ]

        logger.info(f"[DEBUG] 使用 OpenAI 异步客户端发送请求")

        # 4. 发送请求（带重试）
        for attempt in range(self.max_retries):
            try:
                resp = await client.chat.completions.create(
                    model=self.ocr_model,
                    messages=[{"role": "user", "content": content}],
                    timeout=self.ocr_timeout,
                    max_tokens=self.ocr_max_tokens,
                    temperature=self.ocr_temperature,
                    top_p=0.1,
                    extra_body={
                        "repetition_penalty": 1.1,  # 防止重复生成
                        "stop": ["</div></div></div>"]  # 防止无限嵌套
                    }
                )

                # 检测 token 数为 0（模型崩溃的早期信号）
                if hasattr(resp, 'usage') and resp.usage:
                    total_tokens = getattr(resp.usage, 'total_tokens', -1)
                    if total_tokens == 0:
                        logger.warning(f"[异常检测] usage.total_tokens = 0，模型可能已崩溃")

                result = (resp.choices[0].message.content or "").strip()
                logger.info(f"[DEBUG] 返回内容长度: {len(result)} 字符")
                logger.info(f"[DEBUG] 返回内容前200字符: {result[:200]}")

                # 异常输出检测
                if self._is_abnormal_output(result):
                    self._consecutive_failures += 1
                    logger.warning(f"[异常检测] 检测到异常输出（连续第 {self._consecutive_failures} 次）")
                    logger.warning(f"[异常检测] 异常内容: {result[:100]}...")

                    if self._consecutive_failures >= self.max_consecutive_failures:
                        error_msg = (
                            f"⚠️ 检测到连续 {self._consecutive_failures} 次异常输出！\n"
                            f"模型可能已崩溃，请：\n"
                            f"1. 重启 LM Studio\n"
                            f"2. 减少并发数\n"
                            f"3. 增加批次休息时间"
                        )
                        logger.error(error_msg)
                        raise ModelCrashError(error_msg, self._consecutive_failures)
                else:
                    # 正常输出，重置计数器
                    self._consecutive_failures = 0

                return self._parse_response(result)

            except Exception as e:
                logger.warning(f"OCR async request failed (attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 * (attempt + 1))
                else:
                    raise
