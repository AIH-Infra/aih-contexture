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
import aiohttp

from aih_contexture.logger import get_logger
from aih_contexture.config.vlm_model_presets import (
    default_quant,
    default_version,
    normalize_quant,
    normalize_version,
    resolve_vlm_model,
)
from aih_contexture.services.ocr_base import BaseOcrService

logger = get_logger()


V1_LAYOUT_PROMPT = """OCR this image to HTML, arranged as layout blocks. Each layout block should be a div with the data-bbox attribute representing the bounding box of the block in [x0, y0, x1, y1] format. Bboxes are normalized 0-1024. The data-label attribute is the label for the block.

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

Only use these tags ['math', 'br', 'i', 'b', 'u', 'del', 'sup', 'sub', 'table', 'tr', 'td', 'p', 'th', 'div', 'pre', 'h1', 'h2', 'h3', 'h4', 'h5', 'ul', 'ol', 'li', 'input', 'a', 'span', 'img', 'hr', 'tbody', 'small', 'caption', 'strong', 'thead', 'big', 'code'], and these attributes ['class', 'colspan', 'rowspan', 'display', 'checked', 'type', 'border', 'value', 'style', 'href', 'alt', 'align'].

Guidelines:
* Inline math: Surround math with <math>...</math> tags. Math expressions should be rendered in KaTeX-compatible LaTeX. Use display for block math.
* Tables: Use colspan and rowspan attributes to match table structure.
* Formatting: Maintain consistent formatting with the image, including spacing, indentation, subscripts/superscripts, and special characters.
* Images: Include a description of any images in the alt attribute of an <img> tag. Do not fill out the src property.
* Forms: Mark checkboxes and radio buttons properly.
* Text: join lines together properly into paragraphs using <p>...</p> tags. Use <br> tags for line breaks within paragraphs, but only when absolutely necessary to maintain meaning.
* Use the simplest possible HTML structure that accurately represents the content of the block.
* Make sure the text is accurate and easy for a human to read and interpret. Reading order should be correct and natural."""


V2_LAYOUT_PROMPT = """OCR this image to HTML, arranged as layout blocks. Each layout block should be a div with the data-bbox attribute representing the bounding box of the block in x0 y0 x1 y1 format. Bboxes are normalized 0-1000. The data-label attribute is the label for the block.

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
- Chemical-Block
- Diagram
- Bibliography
- Blank-Page

Only use these tags ['math', 'br', 'i', 'b', 'u', 'del', 'sup', 'sub', 'table', 'tr', 'td', 'p', 'th', 'div', 'pre', 'h1', 'h2', 'h3', 'h4', 'h5', 'ul', 'ol', 'li', 'input', 'a', 'span', 'img', 'hr', 'tbody', 'small', 'caption', 'strong', 'thead', 'big', 'code', 'chem'], and these attributes ['class', 'colspan', 'rowspan', 'display', 'checked', 'type', 'border', 'value', 'style', 'href', 'alt', 'align', 'data-bbox', 'data-label'].

Guidelines:
* Inline math: Surround math with <math>...</math> tags. Math expressions should be rendered in KaTeX-compatible LaTeX. Use display for block math.
* Tables: Use colspan and rowspan attributes to match table structure.
* Formatting: Maintain consistent formatting with the image, including spacing, indentation, subscripts/superscripts, and special characters.
* Images: Include a description of any images in the alt attribute of an <img> tag. Do not fill out the src property. Describe in detail inside the div tag. Also convert charts to high fidelity data, and convert diagrams to mermaid.
* Forms: Mark checkboxes and radio buttons properly.
* Text: join lines together properly into paragraphs using <p>...</p> tags. Use <br> tags for line breaks within paragraphs, but only when absolutely necessary to maintain meaning.
* Chemistry: Use <chem>...</chem> tags for chemical formulas with reactive SMILES.
* Lists: Preserve indents and proper list markers.
* Use the simplest possible HTML structure that accurately represents the content of the block.
* Make sure the text is accurate and easy for a human to read and interpret. Reading order should be correct and natural."""


class OcrChandraService(BaseOcrService):
    """
    Chandra OCR 服务

    支持通过 OpenAI 兼容的 API 调用 Chandra 模型
    """

    ocr_endpoint: Annotated[
        str, "OCR API endpoint (OpenAI Chat Completions format)"
    ] = "http://localhost:1234/v1/chat/completions"

    ocr_model: Annotated[
        str, "OCR model name"
    ] = "chandra-ocr-2@q8_0"

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

    ocr_api_style: Annotated[
        str, "Protocol style: 'openai' or 'lmstudio-native'"
    ] = "lmstudio-native"

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
        super().__init__(config or {})
        self._consecutive_failures = 0  # 连续异常计数器
        self.chandra_version = default_version("chandra")
        self.chandra_quant = default_quant("chandra")
        self.ocr_model = resolve_vlm_model(
            "chandra",
            version=self.chandra_version,
            quant=self.chandra_quant,
        )

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
            if "ocr_api_style" in config:
                self.ocr_api_style = str(config["ocr_api_style"]).strip().lower()
            if "chandra_version" in config:
                self.chandra_version = normalize_version("chandra", str(config["chandra_version"]).strip())
            if "chandra_quant" in config:
                self.chandra_quant = normalize_quant("chandra", self.chandra_version, str(config["chandra_quant"]).strip())
            if "max_retries" in config:
                self.max_retries = config["max_retries"]
            if "max_consecutive_failures" in config:
                self.max_consecutive_failures = config["max_consecutive_failures"]
            if "ocr_model" not in config:
                self.ocr_model = resolve_vlm_model(
                    "chandra",
                    version=self.chandra_version,
                    quant=self.chandra_quant,
                )

        if self.ocr_api_style not in ("openai", "lmstudio-native"):
            logger.warning(f"Unknown ocr_api_style={self.ocr_api_style}, fallback to lmstudio-native")
            self.ocr_api_style = "lmstudio-native"

    def get_backend_name(self) -> str:
        """获取后端名称"""
        return "chandra"

    def _get_profile(self) -> Dict[str, Any]:
        """获取当前 Chandra 版本 profile。"""
        if self.chandra_version == "2.0":
            return {
                "version": "2.0",
                "prompt_profile": "v2_ocr_layout",
                "prompt": V2_LAYOUT_PROMPT,
                "bbox_scale": 1000,
                "sampling_profile": "official_v2",
                "preprocess_profile": "official_v2",
                "image_transport": "PNG",
                "top_p": 0.1,
                "repeat_penalty": 1.05,
                "max_tokens": max(self.ocr_max_tokens, 12384),
            }

        return {
            "version": "1.0",
            "prompt_profile": "v1_layout",
            "prompt": V1_LAYOUT_PROMPT,
            "bbox_scale": 1024,
            "sampling_profile": "legacy",
            "preprocess_profile": "legacy",
            "image_transport": "PNG",
            "top_p": 0.1,
            "repeat_penalty": 1.1,
            "max_tokens": self.ocr_max_tokens,
        }

    def get_runtime_profile(self) -> Dict[str, Any]:
        """返回当前 service 的运行时 profile 元数据。"""
        profile = self._get_profile()
        return {
            "backend": "chandra",
            "api_style": self.ocr_api_style,
            "chandra_version": profile["version"],
            "chandra_quant": self.chandra_quant,
            "bbox_scale": profile["bbox_scale"],
            "preprocess_profile": profile["preprocess_profile"],
            "sampling_profile": profile["sampling_profile"],
            "image_transport": profile["image_transport"],
            "prompt_profile": profile["prompt_profile"],
        }

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
            logger.warning("[Service.Chandra] Suspicious output: excessive digit sequences")
            return True

        # 检测重复短语循环（如 "Therefore it would seem..."）
        if len(result) > 500:
            # 检查是否有重复的长短语
            chunk_size = 50
            chunks = [result[i:i+chunk_size] for i in range(0, min(len(result), 1000), chunk_size)]
            if len(chunks) > 5:
                unique_chunks = set(chunks)
                if len(unique_chunks) < len(chunks) * 0.3:  # 重复率超过70%
                    logger.warning("[Service.Chandra] Suspicious output: repeated phrase loops")
                    return True

        return False

    def _build_prompt(self) -> str:
        """
        构建 OCR prompt (使用 Chandra 官方推荐的 ocr_layout 模式)
        """
        prompt = self._get_profile()["prompt"]
        logger.debug("Using official ocr_layout prompt (length: %d chars)", len(prompt))
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
        logger.debug("Image dimensions: %dx%d pixels", img.size[0], img.size[1])

        # 保存为 PNG（与其他分支一致）
        img.save(buffered, format="PNG")

        base64_str = base64.b64encode(buffered.getvalue()).decode()
        logger.debug("Base64 length: %d chars", len(base64_str))

        return base64_str

    def _build_request_payload(
        self,
        img_base64: str,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
    ) -> Dict[str, Any]:
        """根据协议风格构建请求 payload。"""
        prompt = self._build_prompt()
        profile = self._get_profile()
        if temperature is None:
            temperature = self.ocr_temperature
        if top_p is None:
            top_p = profile["top_p"]

        if self.ocr_api_style == "lmstudio-native":
            payload = {
                "model": self.ocr_model,
                "input": [
                    {"type": "text", "content": prompt},
                    {"type": "image", "data_url": f"data:image/png;base64,{img_base64}"},
                ],
                "store": False,
                "temperature": temperature,
                "top_p": top_p,
                "max_output_tokens": profile["max_tokens"],
                "repeat_penalty": profile["repeat_penalty"],
            }
        else:
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
                "max_tokens": profile["max_tokens"],
                "temperature": temperature,
                "top_p": top_p,
                "repetition_penalty": profile["repeat_penalty"],
                "stop": ["</div></div></div>"],
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

    def _extract_openai_text(self, body: Dict[str, Any]) -> str:
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        message = choices[0].get("message", {})
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
        reasoning = message.get("reasoning_content")
        if isinstance(reasoning, str) and reasoning.strip():
            return reasoning
        return ""

    def _extract_lmstudio_native_text(self, body: Dict[str, Any]) -> str:
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
            preferred = []
            fallback = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                bucket = preferred if item.get("type") in {"text", "content", "message"} else fallback
                for key in ("text", "content"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        bucket.append(value)
                content = item.get("content")
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict):
                            value = part.get("text")
                            if isinstance(value, str) and value.strip():
                                bucket.append(value)
            if preferred:
                return "".join(preferred)
            if fallback:
                return "".join(fallback)

        prediction = body.get("prediction")
        if isinstance(prediction, dict):
            for key in ("text", "content"):
                value = prediction.get(key)
                if isinstance(value, str) and value.strip():
                    return value

        return ""

    def _extract_response_text(self, body: Dict[str, Any]) -> str:
        if self.ocr_api_style == "lmstudio-native":
            return self._extract_lmstudio_native_text(body)
        return self._extract_openai_text(body)

    def process_page(self, img: PIL.Image.Image) -> Dict[str, Any] | str:
        """
        同步处理单页图像（使用 OpenAI 客户端）

        Args:
            img: PIL Image 对象

        Returns:
            OCR 结果 (HTML string)
        """
        import urllib.request

        img_base64 = self._img_to_base64(img)
        headers = self._build_headers()

        logger.debug("Using sync HTTP request for OCR (api_style=%s)", self.ocr_api_style)

        for attempt in range(self.max_retries):
            try:
                profile = self._get_profile()
                attempt_temperature = self.ocr_temperature
                attempt_top_p = profile["top_p"]
                if profile["sampling_profile"] == "official_v2" and attempt > 0:
                    attempt_temperature = min(self.ocr_temperature + 0.2 * attempt, 0.8)
                    attempt_top_p = 0.95

                payload = self._build_request_payload(
                    img_base64,
                    temperature=attempt_temperature,
                    top_p=attempt_top_p,
                )
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    self.ocr_endpoint,
                    data=data,
                    headers=headers,
                )

                with urllib.request.urlopen(req, timeout=self.ocr_timeout) as resp:
                    body = json.load(resp)

                result = self._extract_response_text(body).strip()
                logger.debug("Response length: %d chars", len(result))
                logger.debug("Response preview: %s", result[:200])

                if self._is_abnormal_output(result):
                    self._consecutive_failures += 1
                    logger.warning(
                        "[Service.Chandra] Suspicious output detected (consecutive: %d)",
                        self._consecutive_failures
                    )
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

        img_base64 = self._img_to_base64(img)
        headers = self._build_headers()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        logger.debug("Using aiohttp for OCR (api_style=%s)", self.ocr_api_style)

        for attempt in range(self.max_retries):
            try:
                profile = self._get_profile()
                attempt_temperature = self.ocr_temperature
                attempt_top_p = profile["top_p"]
                if profile["sampling_profile"] == "official_v2" and attempt > 0:
                    attempt_temperature = min(self.ocr_temperature + 0.2 * attempt, 0.8)
                    attempt_top_p = 0.95

                payload = self._build_request_payload(
                    img_base64,
                    temperature=attempt_temperature,
                    top_p=attempt_top_p,
                )
                timeout = aiohttp.ClientTimeout(total=self.ocr_timeout)
                async with session.post(
                    self.ocr_endpoint,
                    json=payload,
                    headers=headers,
                    timeout=timeout,
                ) as response:
                    response.raise_for_status()
                    body = await response.json()

                result = self._extract_response_text(body).strip()
                logger.debug("Response length: %d chars", len(result))
                logger.debug("Response preview: %s", result[:200])

                # 异常输出检测
                if self._is_abnormal_output(result):
                    self._consecutive_failures += 1
                    logger.warning(
                        "[Service.Chandra] Suspicious output detected (consecutive: %d)",
                        self._consecutive_failures
                    )
                    logger.warning("[Service.Chandra] Suspicious content preview: %s...", result[:100])

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
