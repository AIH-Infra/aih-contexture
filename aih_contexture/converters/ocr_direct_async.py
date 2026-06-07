"""
OCR Direct Async Converter

直接使用 OCR 模型处理文档的异步转换器

特点：
- 异步并发处理
- 批处理与休息间隔
- API 密钥池管理
- 图像预处理
- 重试机制
- 页码锚点集成
"""

import asyncio
import base64
import re
import time
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, List, Optional, Annotated, Tuple, Union

import aiohttp
from PIL import Image
import fitz  # PyMuPDF
from bs4 import BeautifulSoup

from aih_contexture.converters import BaseConverter
from aih_contexture.schema.document import Document
from aih_contexture.services.ocr_factory import OcrServiceFactory
from aih_contexture.config.vlm_model_presets import default_version
from aih_contexture.builders.ocr_parser import OcrParser
from aih_contexture.formatters import PageAnchorPlugin, PrintedPageExtractor, join_markdown_pages
from aih_contexture.utils.api_key_pool import APIKeyPool
from aih_contexture.utils.chandra_output import parse_markdown, parse_html, parse_chunks
from aih_contexture.logger import get_logger
from aih_contexture.utils.markdown_filters import strip_margin_comment_markers

logger = get_logger()


def _coalesce_config_value(value, default):
    if value is None:
        return default
    if isinstance(value, str) and value.strip().lower() in {"", "none"}:
        return default
    return value


def _empty_page_result(page_num: int, img: Image.Image, raw_output: str = ""):
    from aih_contexture.schema.groups.page import PageGroup
    from aih_contexture.schema.polygon import PolygonBox

    page_polygon = PolygonBox.from_bbox([0, 0, img.width, img.height])
    empty_page = PageGroup(
        page_id=page_num,
        polygon=page_polygon,
        structure=[]
    )
    return (page_num, empty_page, raw_output, img.size, img)


def _specialized_vlm_error_page(backend: str, page_num: int, exc: Exception) -> dict[str, Any]:
    return {
        "backend": backend,
        "official_protocol": "error",
        "markdown": "",
        "blocks": [],
        "raw": "",
        "error": {
            "page": page_num,
            "stage": "process_page_async",
            "message": str(exc),
        },
    }


def _page_result_ok(result: Any) -> bool:
    if isinstance(result, Exception):
        return False
    if not isinstance(result, tuple) or len(result) < 3:
        return False
    raw_output = result[2]
    if isinstance(raw_output, dict) and raw_output.get("error"):
        return False
    return True


class OcrDirectAsyncConverter(BaseConverter):
    """
    OCR Direct 异步转换器

    完全吸收现有成功的工程实践：
    - 并发控制 (asyncio.Semaphore)
    - 批处理与休息间隔
    - API 密钥池管理
    - 图像预处理
    - 重试机制
    - 页码锚点系统
    """

    # API 配置
    ocr_endpoint: Annotated[
        str, "OCR API endpoint"
    ] = "http://localhost:1234/v1"

    ocr_model: Annotated[
        str, "OCR model name"
    ] = "chandra"

    ocr_api_key: Annotated[
        Optional[str], "API key for authentication"
    ] = None

    ocr_output_format: Annotated[
        str, "Output format (json/html/markdown)"
    ] = "json"

    ocr_max_tokens: Annotated[
        int, "Maximum tokens in response"
    ] = 4096

    ocr_temperature: Annotated[
        float, "Temperature for generation (0.0 for strict OCR)"
    ] = 0.0  # 最低温度，确保输出稳定

    ocr_timeout: Annotated[
        int, "API timeout in seconds"
    ] = 120

    ocr_max_retries: Annotated[
        int, "Maximum retry attempts"
    ] = 3

    # 并发控制
    ocr_concurrency: Annotated[
        int, "Maximum concurrent OCR requests"
    ] = 5

    ocr_batch_size: Annotated[
        int, "Batch size for processing pages"
    ] = 10

    ocr_batch_rest: Annotated[
        float, "Rest interval between batches (seconds)"
    ] = 2.0

    # 图像预处理
    ocr_resize_max: Annotated[
        int, "Maximum image dimension for OCR"
    ] = 1024  # 降低到 1024 以适应 LM Studio 上下文窗口

    ocr_image_format: Annotated[
        str, "Image format for OCR (PNG or JPEG)"
    ] = "JPEG"  # 默认使用 JPEG

    ocr_image_quality: Annotated[
        int, "JPEG quality (1-100)"
    ] = 60  # 降低质量以减小大小（LM Studio 上下文窗口限制）

    # 页码锚点
    ocr_page_anchor_enabled: Annotated[
        bool, "Enable page anchor system"
    ] = True

    def __init__(self, config, *, progress_callback: Callable[[dict[str, Any]], None] | None = None):
        super().__init__(config)
        config = config or {}
        self.progress_callback = progress_callback

        # 🆕 接收后端类型和输出格式
        self.backend = config.get("ocr_backend", "chandra")
        self.chandra_version = str(config.get("chandra_version", default_version("chandra")))
        self.final_output_formats = config.get("final_output_formats", ["markdown"])
        self.specialized_vlm_markdown_mode = self._normalize_specialized_vlm_markdown_mode(
            config.get(
                "vlm_specialized_markdown_mode",
                config.get("ocr_specialized_markdown_mode", "contexture_middle"),
            )
        )

        # 加载配置（支持字典访问）
        endpoint = config.get("ocr_endpoint")
        if not endpoint:
            endpoint = type(self).ocr_endpoint
        self.endpoint = str(endpoint)

        # 协议风格：默认走 LM Studio 原生协议
        self.api_style = str(_coalesce_config_value(config.get("ocr_api_style"), "lmstudio-native")).strip().lower()

        # 端点自动补全：
        # - openai            : root or /v1 -> /v1/chat/completions
        # - lmstudio-native   : root or /v1 -> /api/v1/chat
        if self.endpoint.endswith("/v1"):
            if self.api_style == "lmstudio-native":
                self.endpoint = self.endpoint.replace("/v1", "/api/v1/chat")
            else:
                self.endpoint = self.endpoint.replace("/v1", "/v1/chat/completions")
        elif self.api_style != "lmstudio-native" and not self.endpoint.rstrip("/").endswith("/chat/completions"):
            self.endpoint = self.endpoint.rstrip("/") + "/v1/chat/completions"
        elif self.api_style == "lmstudio-native" and not self.endpoint.rstrip("/").endswith("/api/v1/chat"):
            self.endpoint = self.endpoint.rstrip("/") + "/api/v1/chat"

        self.model = _coalesce_config_value(config.get("ocr_model"), self.ocr_model)
        self.api_key = _coalesce_config_value(config.get("ocr_api_key"), self.ocr_api_key)
        self.output_format = _coalesce_config_value(config.get("ocr_output_format"), self.ocr_output_format)
        self.max_tokens = _coalesce_config_value(config.get("ocr_max_tokens"), self.ocr_max_tokens)
        self.temperature = _coalesce_config_value(config.get("ocr_temperature"), self.ocr_temperature)
        self.timeout = _coalesce_config_value(config.get("ocr_timeout"), self.ocr_timeout)
        self.max_retries = _coalesce_config_value(config.get("ocr_max_retries"), self.ocr_max_retries)

        self.ocr_concurrency = _coalesce_config_value(config.get("ocr_concurrency"), self.ocr_concurrency)
        self.ocr_batch_size = _coalesce_config_value(config.get("ocr_batch_size"), self.ocr_batch_size)
        self.ocr_batch_rest = _coalesce_config_value(config.get("ocr_batch_rest"), self.ocr_batch_rest)
        self.concurrency = self.ocr_concurrency
        self.batch_size = self.ocr_batch_size
        self.batch_rest = self.ocr_batch_rest

        self.ocr_resize_max = _coalesce_config_value(config.get("ocr_resize_max"), self.ocr_resize_max)
        self.ocr_image_format = str(_coalesce_config_value(config.get("ocr_image_format"), self.ocr_image_format)).upper()
        self.ocr_image_quality = _coalesce_config_value(config.get("ocr_image_quality"), self.ocr_image_quality)
        self.resize_max = self.ocr_resize_max
        self.image_format = self.ocr_image_format
        self.image_quality = self.ocr_image_quality

        self.page_anchor_enabled = _coalesce_config_value(
            config.get("ocr_page_anchor_enabled"), self.ocr_page_anchor_enabled
        )

        # 页码范围配置
        page_range_str = config.get("page_range", None)
        self.page_start = None  # 0-based inclusive
        self.page_end = None    # 0-based inclusive
        if page_range_str:
            parts = page_range_str.split("-")
            if len(parts) == 2:
                self.page_start = int(parts[0])
                self.page_end = int(parts[1])
                logger.info(f"[OcrDirectAsyncConverter] Page range: {self.page_start}-{self.page_end} (0-based)")

        # 🆕 后处理配置
        self.noise_removal_enabled = config.get("ocr_noise_removal", True)
        self.noise_patterns = self._parse_noise_patterns(config.get("ocr_noise_patterns", ""))
        self.footnote_fix_enabled = config.get("ocr_footnote_fix", True)
        self.hyphenation_fix_enabled = config.get("ocr_hyphenation_fix", True)
        self.filter_page_header = config.get("ocr_filter_page_header", False)
        self.filter_page_footer = config.get("ocr_filter_page_footer", False)
        self.filter_margin_notes = config.get("ocr_filter_margin_notes", False)

        # 初始化 OCR 服务（使用工厂模式）
        ocr_service_config = {
            "ocr_backend": self.backend,
            "chandra_version": self.chandra_version,
            "ocr_api_style": self.api_style,
            "ocr_endpoint": self.endpoint,
            "ocr_model": self.model,
            "ocr_api_key": self.api_key or "",
            "ocr_output_format": self.output_format,
            "ocr_max_tokens": self.max_tokens,
            "ocr_temperature": self.temperature,
            "ocr_timeout": self.timeout,
            "max_retries": self.max_retries,
            "ocr_image_quality": self.image_quality,
            "paddleocr_vl_prompt_label": config.get("paddleocr_vl_prompt_label", "layout_detection"),
            "paddleocr_vl_mode": config.get("paddleocr_vl_mode", "auto"),
            "paddleocr_vl_version": config.get("paddleocr_vl_version"),
            "paddleocr_vl_layout_parsing_url": config.get("paddleocr_vl_layout_parsing_url"),
            "paddleocr_vl_endpoint": config.get("paddleocr_vl_endpoint"),
            "paddleocr_vl_model": config.get("paddleocr_vl_model"),
            "paddleocr_vl_api_key": config.get("paddleocr_vl_api_key"),
            "paddleocr_vl_api_style": config.get("paddleocr_vl_api_style"),
            "paddleocr_vl_image_quality": config.get("paddleocr_vl_image_quality", self.image_quality),
            "mineru_vl_block_concurrency": config.get("mineru_vl_block_concurrency", 4),
            "mineru_vl_request_concurrency": config.get("mineru_vl_request_concurrency"),
            "mineru_vl_layout_image_size": config.get("mineru_vl_layout_image_size", (1036, 1036)),
            "mineru_vl_version": config.get("mineru_vl_version"),
            "mineru_vl_quant": config.get("mineru_vl_quant"),
        }
        self.ocr_service = OcrServiceFactory.create_service(ocr_service_config)
        self.runtime_profile = self._build_runtime_profile(config)

        # 初始化解析器
        self.parser = OcrParser(config)

        # API 密钥池
        api_keys = config.get("ocr_api_keys")
        if api_keys:
            self.api_key_pool = APIKeyPool(api_keys)
        else:
            self.api_key_pool = None

        # 页码锚点（参考 VLM Direct 的实现）
        if self.page_anchor_enabled:
            from aih_contexture.formatters import PageAnchorFormatter, CustomIDInjector

            # 获取页码锚点配置
            anchor_wrapper = config.get("ocr_page_anchor_wrapper", "{{{}}}")
            anchor_position = config.get("ocr_page_anchor_position", "before")
            extract_printed = config.get("ocr_extract_printed_pages", True)
            self.extract_printed_pages = extract_printed  # 保存为实例属性
            custom_patterns = config.get("ocr_printed_page_patterns", None)

            # 自定义编号配置
            custom_id_source = config.get("ocr_custom_id_source", "none")
            custom_id_data = config.get("ocr_custom_id_data", None)

            # 初始化格式化器
            formatter = PageAnchorFormatter(wrapper=anchor_wrapper)

            # 初始化自定义编号注入器
            custom_id_injector = CustomIDInjector(
                source_type=custom_id_source,
                source_data=custom_id_data
            ) if custom_id_source != "none" else None

            # 初始化页码锚点插件
            self.page_anchor_plugin = PageAnchorPlugin(
                formatter=formatter,
                enabled=True,
                position=anchor_position,
                separator="\n\n",
                page_separator="\n\n---\n\n",
                custom_id_injector=custom_id_injector
            )

            # 初始化印刷页码提取器
            if extract_printed:
                self.printed_page_extractor = PrintedPageExtractor(
                    patterns=custom_patterns
                )
            else:
                self.printed_page_extractor = None
        else:
            self.page_anchor_plugin = None
            self.printed_page_extractor = None

        # 初始化输出缓存变量（用于 Streamlit 文件保存）
        self._last_xml_pages = None
        self._last_clean_html_pages = None
        self._last_chunks = None
        self._last_printed_pages = None
        self._last_official_markdown_pages = None
        self._last_contexture_middle_markdown = None

    def _emit_progress(self, **event: Any) -> None:
        if self.progress_callback is None:
            return
        try:
            self.progress_callback(event)
        except Exception as exc:
            logger.debug(f"[OcrDirectAsyncConverter] progress callback ignored: {exc}")

    def _build_runtime_profile(self, config: dict) -> dict:
        """
        构建当前执行 profile 元数据。

        这里先提供一个稳定的读取口，便于后续在 1.0 / 2.0 之间透传
        bbox_scale、preprocess profile 等元信息。
        """
        service_profile = {}
        get_runtime_profile = getattr(self.ocr_service, "get_runtime_profile", None)
        if callable(get_runtime_profile):
            service_profile = get_runtime_profile() or {}

        bbox_scale = service_profile.get("bbox_scale")
        if bbox_scale is None and self.backend == "chandra":
            bbox_scale = int(config.get("chandra_bbox_scale", 1024))

        return {
            "backend": self.backend,
            "api_style": self.api_style,
            "chandra_version": self.chandra_version if self.backend == "chandra" else None,
            "bbox_scale": bbox_scale,
            "preprocess_profile": service_profile.get("preprocess_profile"),
            "sampling_profile": service_profile.get("sampling_profile"),
            "image_transport": service_profile.get("image_transport", self.ocr_image_format),
            "official_protocol": service_profile.get("official_protocol"),
            "model_family": service_profile.get("model_family"),
            "request_concurrency": service_profile.get("request_concurrency"),
            "specialized_vlm_markdown_mode": self.specialized_vlm_markdown_mode
            if self.backend in {"paddleocr_vl", "mineru_vl"}
            else None,
        }

    def _get_chandra_bbox_scale(self) -> int:
        """获取当前 Chandra profile 的 bbox scale。"""
        bbox_scale = self.runtime_profile.get("bbox_scale")
        if isinstance(bbox_scale, int):
            return bbox_scale
        return 1024

    @staticmethod
    def _normalize_specialized_vlm_markdown_mode(value: Any) -> str:
        mode = str(value or "contexture_middle").strip().lower().replace("-", "_")
        if mode in {"middle", "contexture", "contexture_scholarly", "scholarly"}:
            return "contexture_middle"
        if mode == "official":
            return "official"
        return "contexture_middle"

    def _render_specialized_vlm_middle_markdown(
        self,
        *,
        source_name: str | None,
        source: str | None,
    ) -> str | None:
        chunks = getattr(self, "_last_chunks", None)
        if self.backend not in {"paddleocr_vl", "mineru_vl"} or not chunks:
            return None

        try:
            from aih_contexture.middle.adapters import ocr_direct_outputs_to_middle_document
            from aih_contexture.middle.scholarly_markdown import render_middle_scholarly_markdown

            middle = ocr_direct_outputs_to_middle_document(
                chunks,
                backend=str(self.backend),
                model=str(self.model) if self.model is not None else None,
                source_name=source_name,
                source=source,
                printed_pages=getattr(self, "_last_printed_pages", None),
            ).to_dict()
            markdown = render_middle_scholarly_markdown(
                middle,
                include_page_header_comments=not bool(getattr(self, "filter_page_header", False)),
                include_page_footer_comments=not bool(getattr(self, "filter_page_footer", False)),
                include_margin_comments=not bool(getattr(self, "filter_margin_notes", False)),
            )
            self._last_contexture_middle_markdown = markdown
            return markdown
        except Exception as exc:
            logger.warning(f"Failed to render specialized VLM output through Contexture Middle: {exc}")
            return None

    def _get_preprocess_profile(self) -> Optional[str]:
        """获取当前 OCR profile 的图像预处理策略。"""
        return self.runtime_profile.get("preprocess_profile")

    def _parse_noise_patterns(self, patterns_text: str) -> List[str]:
        """解析噪音模式文本为列表"""
        if not patterns_text:
            return []
        return [p.strip() for p in patterns_text.split('\n') if p.strip()]

    def _fix_unicode_superscript_footnotes(self, markdown_pages: List[str]) -> List[str]:
        """转换行首 Unicode 上标脚注：¹) → <sup>1</sup>"""
        fixed = []
        superscript_map = {
            '¹': '1', '²': '2', '³': '3', '⁴': '4', '⁵': '5',
            '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9', '⁰': '0'
        }
        for page in markdown_pages:
            for sup_char, normal_char in superscript_map.items():
                page = re.sub(f'^{sup_char}\\)', f'<sup>{normal_char}</sup>', page, flags=re.MULTILINE)
            fixed.append(page)
        return fixed

    def _fix_hyphenation(self, markdown_pages: List[str]) -> List[str]:
        """删除 Markdown 强制换行，让文本连续流动"""
        fixed = []
        for page in markdown_pages:
            # 把"一个或多个空格+换行"替换为"一个空格"
            page = re.sub(r' +\r?\n', ' ', page)
            fixed.append(page)
        return fixed

    def _preprocess_image(self, img: Image.Image) -> Image.Image:
        """
        图像预处理管道

        Args:
            img: 原始图像

        Returns:
            预处理后的图像
        """
        preprocess_profile = self._get_preprocess_profile()

        # 1. Chandra 2.0 对齐：优先保证较高的最短边
        if preprocess_profile == "official_v2":
            min_dim = min(img.size)
            if min_dim < 1536:
                scale = 1536 / min_dim
                new_size = (int(img.width * scale), int(img.height * scale))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                logger.info(f"[Chandra v2] Upscaled image from {min_dim}px min side to {min(new_size)}px")

        # 2. 调整大小
        img = self._resize_if_needed(img)

        # 3. 颜色空间转换
        if img.mode != "RGB":
            img = img.convert("RGB")

        return img

    def _resize_if_needed(self, img: Image.Image) -> Image.Image:
        """
        调整图像大小（如果超过最大尺寸）

        Args:
            img: 原始图像

        Returns:
            调整后的图像
        """
        max_size = self.resize_max

        if max(img.size) > max_size:
            ratio = max_size / max(img.size)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            logger.info(f"Resized image from {img.size} to {new_size}")

        return img

    def _img_to_base64(self, img: Image.Image) -> str:
        """
        图像转 base64

        Args:
            img: PIL Image 对象

        Returns:
            base64 编码的字符串
        """
        buffered = BytesIO()

        img_format = self.image_format if self.image_format in {"PNG", "JPEG", "JPG"} else "JPEG"
        if img_format == "JPG":
            img_format = "JPEG"
        quality = min(self.image_quality, 70)  # 限制最大质量为 70（LM Studio 上下文窗口限制）

        # 确保是 RGB 模式（JPEG 不支持 RGBA）
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")

        save_kwargs = {"format": img_format}
        if img_format == "JPEG":
            save_kwargs.update({"quality": quality, "optimize": True})
        img.save(buffered, **save_kwargs)

        base64_str = base64.b64encode(buffered.getvalue()).decode()

        # 记录 base64 大小
        size_kb = len(base64_str) / 1024
        logger.info(f"Image base64 size: {size_kb:.1f} KB")

        return base64_str

    def _ocr_html_to_markdown(self, html: str) -> str:
        """
        将 OCR HTML 输出转换为 Markdown（对齐 Pipeline 模式标准）

        支持 Chandra 的 15 种标签：
        Caption, Footnote, Equation-Block, List-Group, Page-Header, Page-Footer,
        Image, Section-Header, Table, Text, Complex-Block, Code-Block, Form,
        Table-Of-Contents, Figure

        Args:
            html: Chandra 返回的 HTML（带 data-bbox 和 data-label）

        Returns:
            Markdown 字符串
        """
        if not html or not html.strip():
            return ""

        soup = BeautifulSoup(html, "html.parser")
        top_level_divs = soup.find_all("div", recursive=False)

        markdown_parts = []
        footnote_counter = 1  # 脚注计数器

        for div in top_level_divs:
            label = div.get("data-label", "Text")
            label_lower = label.lower()

            # 获取内部 HTML（保留格式化标签）
            inner_html = div.decode_contents()

            # 对于结构化内容，进行专门的转换
            if label_lower in {"table"}:
                # 表格保留 HTML 或转换为 Markdown 表格
                formatted_text = inner_html.strip()
            elif label_lower in {"list-group", "list"}:
                # 列表：转换为 Markdown 列表格式
                formatted_text = self._html_list_to_markdown(inner_html)
            elif label_lower in {"code-block", "code"}:
                # 代码块保留原始格式
                formatted_text = inner_html.strip()
            else:
                # 其他类型：转换内部格式化标签为 Markdown
                formatted_text = self._convert_inner_html(inner_html)

            if not formatted_text.strip():
                continue

            # 根据标签类型格式化（对齐 Pipeline 模式）
            md_block = self._format_block_by_label(
                label_lower, formatted_text, footnote_counter
            )

            if md_block:
                markdown_parts.append(md_block)
                # 更新脚注计数器
                if label_lower == "footnote":
                    footnote_counter += 1

        result = "\n\n".join(markdown_parts)

        # 应用 MarkdownFormatter 后处理（对齐 Pipeline 模式）
        from aih_contexture.renderers.markdown import MarkdownFormatter
        formatter = MarkdownFormatter()
        result = formatter.format(result)

        return result

    def _convert_inner_html(self, inner_html: str) -> str:
        """
        转换内部 HTML 格式化标签为 Markdown

        支持的标签：math, b, i, u, del, sub, sup, a, code, br

        Args:
            inner_html: 内部 HTML 字符串

        Returns:
            转换后的 Markdown 字符串
        """
        if not inner_html:
            return ""

        soup = BeautifulSoup(inner_html, "html.parser")

        # 处理数学公式
        for math_tag in soup.find_all("math"):
            display = math_tag.get("display", "")
            math_text = math_tag.get_text()
            if display == "block":
                math_tag.replace_with(f"\n$$\n{math_text}\n$$\n")
            else:
                math_tag.replace_with(f"${math_text}$")

        # 处理粗体
        for tag in soup.find_all("b"):
            tag.replace_with(f"**{tag.get_text()}**")
        for tag in soup.find_all("strong"):
            tag.replace_with(f"**{tag.get_text()}**")

        # 处理斜体
        for tag in soup.find_all("i"):
            tag.replace_with(f"*{tag.get_text()}*")
        for tag in soup.find_all("em"):
            tag.replace_with(f"*{tag.get_text()}*")

        # 处理下划线（Markdown 不支持，使用 HTML）
        for tag in soup.find_all("u"):
            tag.replace_with(f"<u>{tag.get_text()}</u>")

        # 处理删除线
        for tag in soup.find_all("del"):
            tag.replace_with(f"~~{tag.get_text()}~~")
        for tag in soup.find_all("s"):
            tag.replace_with(f"~~{tag.get_text()}~~")

        # 处理下标
        for tag in soup.find_all("sub"):
            tag.replace_with(f"<sub>{tag.get_text()}</sub>")

        # 处理上标（保留 <sup> 格式，对齐 Pipeline 模式）
        for tag in soup.find_all("sup"):
            sup_text = tag.get_text()
            tag.replace_with(f"<sup>{sup_text}</sup>")

        # 处理链接
        for tag in soup.find_all("a"):
            href = tag.get("href", "")
            text = tag.get_text()
            if href:
                tag.replace_with(f"[{text}]({href})")
            else:
                tag.replace_with(text)

        # 处理行内代码
        for tag in soup.find_all("code"):
            tag.replace_with(f"`{tag.get_text()}`")

        # 处理换行
        for tag in soup.find_all("br"):
            tag.replace_with("\n")

        return soup.get_text()

    def _format_block_by_label(self, label: str, text: str, footnote_num: int) -> str:
        """
        根据 Chandra 标签格式化为 Markdown 块

        Args:
            label: 标签名称（小写）
            text: 格式化后的文本
            footnote_num: 当前脚注编号

        Returns:
            Markdown 格式的块
        """
        text = text.strip()
        if not text:
            return ""

        # 1. Section-Header（章节标题）
        if label in ["section-header", "section", "title"]:
            # 检测标题级别（如果文本以数字开头，可能是子标题）
            if re.match(r'^\d+\.\d+', text):
                return f"### {text}"
            elif re.match(r'^\d+\.', text):
                return f"## {text}"
            else:
                return f"## {text}"

        # 2. Footnote（脚注）- 保留规范化 <sup>n</sup> 格式，不转换为 [^n]:
        elif label == "footnote":
            return text

        # 3. Equation-Block（块级公式）
        elif label in ["equation", "equation-block"]:
            # 如果文本已经包含 $$ 则不重复添加
            if text.startswith("$$") and text.endswith("$$"):
                return text
            return f"$$\n{text}\n$$"

        # 4. List-Group（列表）
        elif label in ["list-group", "list"]:
            return self._format_list(text)

        # 5. Page-Header（页眉）
        elif label == "page-header":
            # 页眉通常包含页码，使用小字体或注释
            return f"<!-- PageHeader: {text} -->"

        # 6. Page-Footer（页脚）
        elif label == "page-footer":
            # 页脚通常包含页码，使用小字体或注释
            return f"<!-- PageFooter: {text} -->"

        # 7. Image/Picture（图片）
        elif label in ["image", "picture"]:
            return f"![Image]({text})" if text.startswith("http") else f"![Image]()"

        # 8. Figure（图形）
        elif label == "figure":
            return f"![Figure]()\n\n*{text}*" if text else "![Figure]()"

        # 9. Caption（图表标题）
        elif label == "caption":
            return f"*{text}*"

        # 10. Table（表格）
        elif label == "table":
            return self._format_table(text)

        # 11. Code-Block（代码块）
        elif label in ["code-block", "code"]:
            return f"```\n{text}\n```"

        # 12. Form（表单）
        elif label == "form":
            # 表单转换为表格格式
            return self._format_form(text)

        # 13. Table-Of-Contents（目录）
        elif label in ["table-of-contents", "toc"]:
            return self._format_toc(text)

        # 14. Complex-Block（复杂区块）
        elif label in ["complex-block", "complex"]:
            # 复杂区块保留原样，添加分隔
            return f"---\n\n{text}\n\n---"

        # 15. Blockquote（引文）
        elif label in ["blockquote", "quote", "citation"]:
            return self._format_blockquote(text)

        # 16. Text（普通文本）- 默认
        else:
            return text

    def _format_list(self, text: str) -> str:
        """格式化列表文本"""
        lines = text.split("\n")
        formatted_lines = []
        for line in lines:
            line = line.strip()
            if line:
                # 如果行不是以列表标记开头，添加 -
                if not re.match(r'^[-*+•]\s', line) and not re.match(r'^\d+\.\s', line):
                    formatted_lines.append(f"- {line}")
                else:
                    formatted_lines.append(line)
        return "\n".join(formatted_lines)

    def _format_table(self, text: str) -> str:
        """格式化表格文本（支持 HTML 表格转 Markdown）"""
        # 如果已经是 Markdown 表格格式，直接返回
        if "|" in text and "---" in text:
            return text

        # 检查是否包含 HTML 表格标签
        if "<table" in text.lower() or "<tr" in text.lower():
            return self._html_table_to_markdown(text)

        # 简单文本处理：每行作为一个单元格
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if len(lines) < 2:
            return text

        table_lines = []
        for i, line in enumerate(lines):
            table_lines.append(f"| {line} |")
            if i == 0:
                table_lines.append("| --- |")

        return "\n".join(table_lines)

    def _html_list_to_markdown(self, html: str) -> str:
        """将 HTML 列表转换为 Markdown 列表"""
        soup = BeautifulSoup(html, "html.parser")
        return self._convert_list_element(soup, 0)

    def _convert_list_element(self, element, depth: int = 0) -> str:
        """递归转换列表元素"""
        lines = []
        indent = "   " * depth

        # 查找所有列表（ol 和 ul）
        for list_tag in element.find_all(["ol", "ul"], recursive=False):
            is_ordered = list_tag.name == "ol"
            list_type = list_tag.get("type", "1")  # 支持 type="a" 等
            counter = 1

            for li in list_tag.find_all("li", recursive=False):
                # 获取列表项的直接文本内容
                text_parts = []
                for child in li.children:
                    if child.name in ["ol", "ul"]:
                        continue  # 跳过嵌套列表
                    elif hasattr(child, "get_text"):
                        text_parts.append(child.get_text().strip())
                    else:
                        text_parts.append(str(child).strip())

                text = " ".join(filter(None, text_parts))

                # 生成列表标记
                if is_ordered:
                    if list_type == "a":
                        marker = f"{chr(96 + counter)}."
                    else:
                        marker = f"{counter}."
                    counter += 1
                else:
                    marker = "-"

                if text:
                    lines.append(f"{indent}{marker} {text}")

                # 递归处理嵌套列表
                nested = self._convert_list_element(li, depth + 1)
                if nested:
                    lines.append(nested)

        # 如果没有找到列表标签，尝试直接处理 li 标签
        if not lines:
            for li in element.find_all("li", recursive=False):
                text = li.get_text().strip()
                if text:
                    lines.append(f"{indent}- {text}")

        return "\n".join(lines)

    def _html_table_to_markdown(self, html: str) -> str:
        """将 HTML 表格转换为 Markdown 表格"""
        from collections import defaultdict

        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        if not table:
            # 如果没有 table 标签，尝试直接解析 tr
            rows = soup.find_all("tr")
            if not rows:
                return html  # 返回原始内容
        else:
            rows = table.find_all("tr")

        if not rows:
            return html

        # 计算列数（考虑 colspan）
        total_rows = len(rows)
        colspans = []
        rowspan_cols = defaultdict(int)

        for i, row in enumerate(rows):
            row_cols = rowspan_cols[i]
            for cell in row.find_all(["td", "th"]):
                colspan = int(cell.get("colspan", 1))
                row_cols += colspan
                for r in range(int(cell.get("rowspan", 1)) - 1):
                    rowspan_cols[i + r + 1] += colspan
            colspans.append(row_cols)

        total_cols = max(colspans) if colspans else 0
        if total_cols == 0:
            return html

        # 创建网格
        grid = [[None for _ in range(total_cols)] for _ in range(total_rows)]

        for row_idx, tr in enumerate(rows):
            col_idx = 0
            for cell in tr.find_all(["td", "th"]):
                while col_idx < total_cols and grid[row_idx][col_idx] is not None:
                    col_idx += 1

                value = cell.get_text().replace("\n", " ").replace("|", " ").strip()
                rowspan = int(cell.get("rowspan", 1))
                colspan = int(cell.get("colspan", 1))

                if col_idx >= total_cols:
                    continue

                for r in range(rowspan):
                    for c in range(colspan):
                        try:
                            if r == 0 and c == 0:
                                grid[row_idx + r][col_idx + c] = value
                            else:
                                grid[row_idx + r][col_idx + c] = ""
                        except IndexError:
                            pass
                col_idx += colspan

        # 生成 Markdown 表格
        markdown_lines = []
        for row_idx, row in enumerate(grid):
            cells = [cell if cell is not None else "" for cell in row]
            markdown_lines.append("| " + " | ".join(cells) + " |")
            if row_idx == 0:
                markdown_lines.append("| " + " | ".join(["---"] * total_cols) + " |")

        return "\n".join(markdown_lines)

    def _format_form(self, text: str) -> str:
        """格式化表单文本"""
        # 表单通常包含标签和值，转换为表格
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if not lines:
            return text

        table_lines = ["| Field | Value |", "| --- | --- |"]
        for line in lines:
            # 尝试分割标签和值
            if ":" in line:
                parts = line.split(":", 1)
                table_lines.append(f"| {parts[0].strip()} | {parts[1].strip()} |")
            else:
                table_lines.append(f"| {line} | |")

        return "\n".join(table_lines)

    def _format_toc(self, text: str) -> str:
        """格式化目录文本"""
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        formatted_lines = ["**Table of Contents**\n"]
        for line in lines:
            # 检测缩进级别
            indent = 0
            if re.match(r'^\d+\.\d+\.\d+', line):
                indent = 2
            elif re.match(r'^\d+\.\d+', line):
                indent = 1

            prefix = "  " * indent + "- "
            formatted_lines.append(f"{prefix}{line}")

        return "\n".join(formatted_lines)

    def _format_blockquote(self, text: str) -> str:
        """格式化引文文本"""
        lines = text.split("\n")
        formatted_lines = []
        for line in lines:
            line = line.strip()
            if line:
                # 如果行不是以 > 开头，添加 >
                if not line.startswith(">"):
                    formatted_lines.append(f"> {line}")
                else:
                    formatted_lines.append(line)
        return "\n".join(formatted_lines)

    def _clean_page_separators(self, markdown_pages: List[str]) -> List[str]:
        """
        清理页面内容中的分隔符（避免嵌套）

        Args:
            markdown_pages: Markdown 页面列表

        Returns:
            清理后的页面列表
        """
        cleaned = []
        for page in markdown_pages:
            # 移除页面内的 --- 分隔符
            page = re.sub(r'\n---\n', '\n', page)
            page = re.sub(r'^---\n', '', page)
            page = re.sub(r'\n---$', '', page)
            cleaned.append(page.strip())
        return cleaned

    def _remove_noise(self, markdown_pages: List[str]) -> List[str]:
        """
        移除噪音（水印、扫描标记等）

        Args:
            markdown_pages: Markdown 页面列表

        Returns:
            清理后的页面列表
        """
        # 始终包含 HTML 清理模式（包括不完整的标签）
        # 排除 sup/sub 标签（脚注和上下标需要保留）
        base_patterns = [r"</(?!sup|sub)[a-z]+>?"]  # 负向前瞻，不匹配 </sup> 和 </sub>

        # 添加用户配置的模式或默认模式
        if self.noise_patterns:
            noise_patterns = base_patterns + self.noise_patterns
        else:
            noise_patterns = base_patterns + [
                r"Digitized\s+by\s+Google",
                r"Digitized\s+by\s+the\s+Internet\s+Archive",
            ]

        cleaned = []
        for page in markdown_pages:
            for pattern in noise_patterns:
                try:
                    page = re.sub(pattern, '', page, flags=re.IGNORECASE)
                except re.error:
                    pass
            page = re.sub(r'\n{3,}', '\n\n', page)
            cleaned.append(page.strip())
        return cleaned

    def _fix_footnotes(self, markdown_pages: List[str]) -> List[str]:
        """
        修复脚注格式

        处理：
        1. 未识别的脚注（如 "1) 文本", "*) 文本"）添加 <sup> 标签
        2. 重复的括号（如 "<sup>1</sup>)"）
        3. 统一脚注格式
        4. 清理脚注中的 HTML 残留

        Args:
            markdown_pages: Markdown 页面列表

        Returns:
            修复后的页面列表
        """
        fixed = []
        for page in markdown_pages:
            # 1. 转换行首的Unicode上标脚注（脚注定义）
            # ¹) → <sup>1</sup>
            superscript_map = {
                '¹': '1', '²': '2', '³': '3', '⁴': '4', '⁵': '5',
                '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9', '⁰': '0'
            }
            for sup_char, normal_char in superscript_map.items():
                page = re.sub(f'^{sup_char}\\)', f'<sup>{normal_char}</sup>', page, flags=re.MULTILINE)

            # 2. 识别 Markdown 转义的脚注并添加 sup 标签
            # \*) → <sup>*</sup>
            page = re.sub(r'\\(\*+)\)', r'<sup>\1</sup>', page)
            # \1) → <sup>1</sup>
            page = re.sub(r'\\(\d+)\)', r'<sup>\1</sup>', page)

            # 3. 修复可能的重复括号
            page = re.sub(r'<sup>(\d+|\*+)\)</sup>\)?', r'<sup>\1</sup>', page)
            page = re.sub(r'<sup>(\d+|\*+)</sup>\)', r'<sup>\1</sup>', page)

            fixed.append(page)
        return fixed

    def _extract_page_number_from_html(self, html: str) -> Optional[str]:
        """
        从 Chandra HTML 中提取印刷页码（基于 data-label）

        Args:
            html: Chandra 原始 HTML

        Returns:
            页码字符串或 None
        """
        from bs4 import BeautifulSoup

        try:
            soup = BeautifulSoup(html, "html.parser")
            # 查找 Page-Header 或 Page-Footer 标签
            for label in ["Page-Header", "Page-Footer"]:
                divs = soup.find_all("div", {"data-label": label})
                for div in divs:
                    text = div.get_text(strip=True)
                    # 提取阿拉伯数字（1-999）
                    match = re.match(r'^(\d{1,3})$', text)
                    if match:
                        return match.group(1)
                    # 提取罗马数字（i-vi, I-VI）
                    match = re.match(r'^([ivxIVX]{1,6})$', text)
                    if match:
                        return match.group(1)
            return None
        except Exception as e:
            logger.warning(f"Failed to extract page number from HTML: {e}")
            return None

    def _validate_page_sequence(self, page_numbers: List[Optional[str]]) -> List[Optional[str]]:
        """
        验证页码序列的连续性

        Args:
            page_numbers: 提取的页码列表

        Returns:
            验证后的页码列表（无效的设为 None）
        """
        validated = list(page_numbers)

        # 转换为数字（阿拉伯数字）
        numeric = []
        for pn in page_numbers:
            if pn and pn.isdigit():
                numeric.append(int(pn))
            else:
                numeric.append(None)

        # 检查连续性
        for i in range(1, len(numeric)):
            if numeric[i] is not None and numeric[i-1] is not None:
                diff = numeric[i] - numeric[i-1]
                # 允许 +1（正常）或 +0（重复页）或 -1（回退）
                if diff not in [0, 1, -1]:
                    # 检查前后页是否支持当前页
                    if i + 1 < len(numeric) and numeric[i+1] is not None:
                        next_diff = numeric[i+1] - numeric[i]
                        if next_diff not in [0, 1]:
                            # 当前页不连续，标记为无效
                            logger.warning(f"Page {i+1}: Invalid sequence {numeric[i-1]} -> {numeric[i]} -> {numeric[i+1]}")
                            validated[i] = None

        return validated

    def _filter_page_markers(self, markdown_pages: List[str]) -> List[str]:
        """
        过滤页眉/页脚/边注语法标识，但保留内容

        例如：
        - 输入: <!-- PageHeader: 0115 -->
        - 输出: 0115
        - 输入: <!-- Margin:left -->\n> Side note\n<!-- /Margin -->
        - 输出: Side note

        Args:
            markdown_pages: Markdown 页面列表

        Returns:
            过滤后的页面列表
        """
        filtered = []
        for page_idx, page in enumerate(markdown_pages):
            # 过滤页眉标记，保留内容
            if self.filter_page_header:
                # 匹配统一 PageHeader 和历史 page-header 格式（内容可以为空）
                header_pattern = r'<!--\s*(?:PageHeader|page-header):\s*(.*?)\s*-->'
                matches = re.findall(header_pattern, page)

                if matches:
                    logger.debug("[Converter.OcrDirectAsync] Page %d: Found PageHeader(s): %s", page_idx + 1, matches)
                    # 替换为捕获的内容
                    page = re.sub(header_pattern, r'\1', page)
                    logger.debug("[Converter.OcrDirectAsync] Page %d: Header filter applied", page_idx + 1)
                else:
                    # 检查是否有未匹配的页眉注释
                    if '<!-- page-header' in page or '<!-- PageHeader' in page:
                        logger.warning("[Converter.OcrDirectAsync] Page %d: Unmatched PageHeader comment", page_idx + 1)

            # 过滤页脚标记，保留内容
            if self.filter_page_footer:
                footer_pattern = r'<!--\s*(?:PageFooter|page-footer):\s*(.*?)\s*-->'
                matches = re.findall(footer_pattern, page)

                if matches:
                    logger.debug("[Converter.OcrDirectAsync] Page %d: Found PageFooter(s): %s", page_idx + 1, matches)
                    page = re.sub(footer_pattern, r'\1', page)
                    logger.debug("[Converter.OcrDirectAsync] Page %d: Footer filter applied", page_idx + 1)
                else:
                    if '<!-- page-footer' in page or '<!-- PageFooter' in page:
                        logger.warning("[Converter.OcrDirectAsync] Page %d: Unmatched PageFooter comment", page_idx + 1)

            if self.filter_margin_notes:
                page = self._filter_margin_markers(page, page_idx=page_idx)

            filtered.append(page.strip())
        return filtered

    def _filter_margin_markers(self, page: str, *, page_idx: int) -> str:
        """Remove Margin comment wrappers and render quoted marginalia as plain text."""
        margin_block_pattern = r'<!--\s*Margin(?::[A-Za-z_-]+)?(?:\s+[^>]*)?\s*-->\s*(.*?)\s*<!--\s*/Margin\s*-->'
        matches = re.findall(margin_block_pattern, page, flags=re.IGNORECASE | re.DOTALL)
        if matches:
            logger.debug("[Converter.OcrDirectAsync] Page %d: Found Margin block(s): %d", page_idx + 1, len(matches))
        elif "<!-- Margin" in page or "<!-- /Margin" in page:
            logger.warning("[Converter.OcrDirectAsync] Page %d: Unmatched Margin comment", page_idx + 1)
        return strip_margin_comment_markers(page)

    def _load_document(self, filepath: str) -> List[Image.Image]:
        """
        加载文档为图片列表

        Args:
            filepath: 文档路径

        Returns:
            图片列表
        """
        filepath = Path(filepath)

        if filepath.suffix.lower() == '.pdf':
            return self._load_pdf(filepath)
        else:
            # 单张图片
            return [Image.open(filepath)]

    def _load_pdf(self, pdf_path: Path) -> List[Image.Image]:
        """
        加载 PDF 为图片列表

        Args:
            pdf_path: PDF 文件路径

        Returns:
            图片列表
        """
        doc = fitz.open(pdf_path)
        images = []

        total_pages = len(doc)
        if self.page_start is not None and self.page_end is not None:
            actual_end = min(self.page_end, total_pages - 1)
            page_range = range(self.page_start, actual_end + 1)
            logger.info(f"[OcrDirectAsyncConverter] Loading pages {self.page_start}-{actual_end} (total {total_pages} pages)")
        else:
            page_range = range(total_pages)

        for page_num in page_range:
            page = doc[page_num]

            # 渲染为图片（高分辨率）
            mat = fitz.Matrix(2.0, 2.0)  # 2x zoom
            pix = page.get_pixmap(matrix=mat)

            # 转为 PIL Image
            img = Image.frombytes(
                "RGB",
                [pix.width, pix.height],
                pix.samples
            )
            images.append(img)

        doc.close()
        return images

    async def _convert_page_async(
        self,
        session: aiohttp.ClientSession,
        img: Image.Image,
        page_num: int,
        semaphore: asyncio.Semaphore
    ) -> Tuple[int, any, Any, Tuple[int, int], Image.Image]:
        """
        异步处理单页

        Args:
            session: aiohttp ClientSession
            img: 页面图像
            page_num: 页面编号
            semaphore: 并发控制信号量

        Returns:
            (page_num, PageGroup, markdown, img_size) 元组
        """
        async with semaphore:
            try:
                # 1. 图像预处理
                processed_img = self._preprocess_image(img)
                img_size = processed_img.size

                # 2. 获取 API 密钥
                api_key = None
                if self.api_key_pool:
                    api_key = self.api_key_pool.get_key()

                # 3. 调用 OCR
                ocr_output = await self.ocr_service.process_page_async(
                    session, processed_img, api_key
                )

                # 调试：记录 OCR 输出类型和内容
                logger.info(f"Page {page_num + 1}: OCR output type = {type(ocr_output)}")
                if isinstance(ocr_output, str):
                    logger.info(f"Page {page_num + 1}: OCR output is string, length = {len(ocr_output)}")

                # 4. 保存官方原始输出（供后续官方协议适配）
                raw_output = ocr_output

                # 5. 解析输出为 PageGroup
                if self.backend == "churro":
                    page = _empty_page_result(page_num, processed_img)[1]
                else:
                    page = self.parser.parse_to_page(
                        ocr_output,
                        page_num,
                        img_size,
                        self.ocr_service.ocr_output_format,
                        bbox_scale=self._get_chandra_bbox_scale(),
                    )

                raw_len = len(raw_output) if isinstance(raw_output, str) else len(str(type(raw_output)))
                logger.info(f"Processed page {page_num + 1}, raw output marker length: {raw_len}")
                return (page_num, page, raw_output, img_size, processed_img)

            except Exception as e:
                logger.error(f"Failed to process page {page_num + 1}: {e}")
                if self.backend in ("paddleocr_vl", "mineru_vl"):
                    return _empty_page_result(
                        page_num,
                        img,
                        _specialized_vlm_error_page(self.backend, page_num, e),
                    )
                error_xml = (
                    f"<Page>"
                    f"<Metadata><Error>Churro OCR failed on page {page_num + 1}: {e}</Error></Metadata>"
                    f"<Body/></Page>"
                ) if self.backend == "churro" else ""
                return _empty_page_result(page_num, img, error_xml)

    async def _convert_page_async_no_semaphore(
        self,
        session: aiohttp.ClientSession,
        img: Image.Image,
        page_num: int
    ) -> Tuple[int, any, Any, Tuple[int, int], Image.Image]:
        """
        异步处理单页（无信号量版本，用于严格批次模式）

        Args:
            session: aiohttp ClientSession
            img: 页面图像
            page_num: 页面编号

        Returns:
            (page_num, PageGroup, markdown, img_size) 元组
        """
        try:
            # 1. 图像预处理
            processed_img = self._preprocess_image(img)
            img_size = processed_img.size

            # 2. 获取 API 密钥
            api_key = None
            if self.api_key_pool:
                api_key = self.api_key_pool.get_key()

            # 3. 调用 OCR
            ocr_output = await self.ocr_service.process_page_async(
                session, processed_img, api_key
            )

            # 4. 保存官方原始输出（供后续官方协议适配）
            raw_output = ocr_output

            # 5. 解析输出为 PageGroup
            if self.backend == "churro":
                page = _empty_page_result(page_num, processed_img)[1]
            else:
                page = self.parser.parse_to_page(
                    ocr_output,
                    page_num,
                    img_size,
                    self.ocr_service.ocr_output_format,
                    bbox_scale=self._get_chandra_bbox_scale(),
                )

            logger.info(f"Processed page {page_num + 1}")
            return (page_num, page, raw_output, img_size, processed_img)

        except Exception as e:
            logger.error(f"Failed to process page {page_num + 1}: {e}")
            if self.backend in ("paddleocr_vl", "mineru_vl"):
                return _empty_page_result(
                    page_num,
                    img,
                    _specialized_vlm_error_page(self.backend, page_num, e),
                )
            error_xml = (
                f"<Page>"
                f"<Metadata><Error>Churro OCR failed on page {page_num + 1}: {e}</Error></Metadata>"
                f"<Body/></Page>"
            ) if self.backend == "churro" else ""
            return _empty_page_result(page_num, img, error_xml)

    async def _process_batch_async(
        self,
        batch: List[Image.Image],
        batch_start_idx: int,
        global_semaphore: Optional[asyncio.Semaphore] = None
    ):
        """
        异步处理一批页面（严格批次模式）

        LM Studio 优化：一批全部完成后才送下一批，避免 promote 阶段导致的性能下降。

        Args:
            batch: 页面图像列表
            batch_start_idx: 批次起始索引
            global_semaphore: 全局信号量（已弃用，保留兼容性）

        Returns:
            处理结果列表
        """
        all_results = []
        concurrency = self.concurrency

        async with aiohttp.ClientSession() as session:
            # 将 batch 分成小批次，每批 = 并发数
            for sub_batch_start in range(0, len(batch), concurrency):
                sub_batch = batch[sub_batch_start:sub_batch_start + concurrency]
                sub_batch_idx = batch_start_idx + sub_batch_start

                logger.info(f"Processing sub-batch: {len(sub_batch)} pages (concurrency={concurrency})")
                logger.info("%s", "=" * 60)
                logger.info("[STRICT BATCH] Starting sub-batch with %s pages", len(sub_batch))
                logger.info("[STRICT BATCH] Concurrency setting: %s", concurrency)
                logger.info("%s", "=" * 60)

                # 创建当前小批次的所有任务
                tasks = []
                for idx, img in enumerate(sub_batch):
                    page_num = sub_batch_idx + idx
                    # 不使用 semaphore，直接并行
                    task = self._convert_page_async_no_semaphore(session, img, page_num)
                    tasks.append(task)

                # 等待当前小批次全部完成
                logger.info("[STRICT BATCH] Waiting for all %s tasks to complete...", len(tasks))
                sub_results = await asyncio.gather(*tasks, return_exceptions=True)
                for idx, result in enumerate(sub_results):
                    page_num = sub_batch_idx + idx + 1
                    self._emit_progress(
                        event="page_done",
                        page_num=page_num,
                        ok=_page_result_ok(result),
                        stage="processing",
                    )
                logger.info("[STRICT BATCH] Sub-batch completed! %s results", len(sub_results))
                all_results.extend(sub_results)

                logger.info(f"Sub-batch completed: {len(sub_results)} pages")

        return all_results

    async def __call__(
        self,
        filepath: str,
        global_semaphore: Optional[asyncio.Semaphore] = None
    ) -> Union[str, Document]:
        """
        异步转换文档

        Args:
            filepath: 文档路径
            global_semaphore: 全局信号量（用于多文件并发控制）

        Returns:
            Markdown 字符串（带页码锚点）或 Document 对象
        """
        logger.info(f"Starting OCR Direct conversion: {filepath}")
        start_time = time.time()

        # 1. 加载图片
        pages_images = self._load_document(filepath)
        logger.info(f"Loaded {len(pages_images)} pages")
        self._emit_progress(event="pages_loaded", total_pages=len(pages_images), stage="processing")

        # 2. 批处理
        all_results = []
        for batch_idx in range(0, len(pages_images), self.batch_size):
            batch = pages_images[batch_idx:batch_idx + self.batch_size]
            batch_num = batch_idx // self.batch_size + 1
            total_batches = (len(pages_images) + self.batch_size - 1) // self.batch_size

            logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} pages)")

            # 3. 并发处理批次（传递全局信号量）
            batch_results = await self._process_batch_async(batch, batch_idx, global_semaphore)
            all_results.extend(batch_results)

            # 4. 批次间休息
            if batch_idx + self.batch_size < len(pages_images):
                logger.info(f"Resting for {self.batch_rest} seconds...")
                await asyncio.sleep(self.batch_rest)

        # 5. 按页码排序
        all_results.sort(key=lambda x: x[0])

        # 6. 提取 pages、raw_output_pages、img_list
        pages = [result[1] for result in all_results]
        raw_output_pages = [result[2] for result in all_results]  # HTML/XML 或官方 JSON-like 输出
        img_list = [result[4] for result in all_results]

        # 6.1 根据后端类型处理输出
        logger.debug("Backend type: %s", self.backend)
        logger.debug("raw_output_pages count: %d", len(raw_output_pages))
        if self.backend in ("paddleocr_vl", "mineru_vl"):
            logger.info("Processing specialized VLM official output...")
            self._last_xml_pages = None
            self._last_clean_html_pages = None
            markdown_pages = [
                str(page.get("markdown") or "") if isinstance(page, dict) else str(page or "")
                for page in raw_output_pages
            ]
            self._last_official_markdown_pages = list(markdown_pages)
            html_extracted_pages = [None] * len(raw_output_pages)
            self._last_chunks = []
            for i, (page_output, img) in enumerate(zip(raw_output_pages, img_list)):
                if isinstance(page_output, dict):
                    self._last_chunks.append({
                        "page_num": i,
                        "img_size": list(img.size) if img else [],
                        "backend": self.backend,
                        "official_protocol": page_output.get("official_protocol"),
                        "markdown": page_output.get("markdown", ""),
                        "blocks": page_output.get("blocks", []),
                        "raw": page_output.get("raw", page_output),
                        "error": page_output.get("error"),
                    })
                else:
                    self._last_chunks.append({
                        "page_num": i,
                        "img_size": list(img.size) if img else [],
                        "backend": self.backend,
                        "official_protocol": "unknown",
                        "markdown": str(page_output or ""),
                        "blocks": [],
                        "raw": page_output,
                    })

        elif self.backend == "churro":
            # Churro: XML 输出
            logger.info("Processing Churro XML output...")
            from aih_contexture.utils.churro_output import xml_to_markdown, xml_to_json, xml_to_html, extract_page_number

            # 保存原始 XML
            self._last_xml_pages = raw_output_pages
            logger.debug("Saved %d XML pages", len(self._last_xml_pages))
            if self._last_xml_pages:
                logger.debug("First XML page length: %d", len(self._last_xml_pages[0]))
            empty_xml_pages = [idx + 1 for idx, xml in enumerate(raw_output_pages) if not isinstance(xml, str) or not xml.strip()]
            if empty_xml_pages:
                raise ValueError(f"Churro returned empty XML for pages: {empty_xml_pages}")

            # 转换为 Markdown
            markdown_pages = [xml_to_markdown(xml) for xml in raw_output_pages]

            # 提取印刷页码
            html_extracted_pages = [extract_page_number(xml) for xml in raw_output_pages]

            # 生成其他格式
            self._last_clean_html_pages = [xml_to_html(xml) for xml in raw_output_pages]
            self._last_chunks = [xml_to_json(xml) for xml in raw_output_pages]

        else:
            # Chandra: HTML 输出
            logger.info("Converting HTML to Markdown via official Chandra tools...")
            _include_hf = not (
                getattr(self, "filter_page_header", False) or
                getattr(self, "filter_page_footer", False)
            )
            _extract_page = self.extract_printed_pages if hasattr(self, 'extract_printed_pages') else False

            if _extract_page:
                results = [
                    parse_markdown(html, include_headers_footers=_include_hf, extract_printed_page=True)
                    for html in raw_output_pages
                ]
                markdown_pages = [r[0] for r in results]
                html_extracted_pages = [r[1] for r in results]
                found_count = sum(1 for p in html_extracted_pages if p is not None)
                logger.info(f"Extracted {found_count}/{len(html_extracted_pages)} printed page numbers")
            else:
                markdown_pages = [
                    parse_markdown(html, include_headers_footers=_include_hf)
                    for html in raw_output_pages
                ]
                html_extracted_pages = [None] * len(raw_output_pages)

            # 生成 clean_html
            logger.info("Generating clean HTML via official Chandra tools...")
            self._last_clean_html_pages = [
                parse_html(html, include_headers_footers=_include_hf)
                for html in raw_output_pages
            ]

            # 生成 chunks
            logger.info("Generating chunks via official Chandra tools...")
            self._last_chunks = []
            for i, (html, img) in enumerate(zip(raw_output_pages, img_list)):
                try:
                    chunks = parse_chunks(html, img, bbox_scale=self._get_chandra_bbox_scale())
                    self._last_chunks.append({
                        "page_num": i,
                        "img_size": list(img.size),
                        "chunks": chunks
                    })
                except Exception as e:
                    logger.warning(f"parse_chunks failed for page {i + 1}: {e}")
                    self._last_chunks.append({
                        "page_num": i,
                        "img_size": list(img.size) if img else [],
                        "chunks": []
                    })

        # 7. 提取印刷页码（优先使用 HTML 提取，regex 作为 fallback）
        printed_pages = html_extracted_pages  # 使用 HTML 提取的结果

        if self.printed_page_extractor:
            logger.info("Applying regex fallback for missing page numbers...")
            # 对 HTML 提取失败的页面，尝试 regex 提取
            markdown_pages, regex_pages = self.printed_page_extractor.extract_batch(markdown_pages)

            # 合并结果：HTML 优先，regex 作为 fallback
            for i in range(len(printed_pages)):
                if printed_pages[i] is None and regex_pages[i] is not None:
                    printed_pages[i] = regex_pages[i]
                    logger.info(f"Page {i+1}: Used regex fallback, found '{regex_pages[i]}'")

            found_count = sum(1 for p in printed_pages if p is not None)
            logger.info(f"Final: {found_count} printed pages (HTML + regex fallback)")
        else:
            found_count = sum(1 for p in printed_pages if p is not None)
            logger.info(f"Final: {found_count} printed pages (HTML only)")
        self._last_printed_pages = printed_pages
        self._emit_progress(event="postprocess", stage="saving")

        if (
            self.backend in ("paddleocr_vl", "mineru_vl")
            and self.specialized_vlm_markdown_mode == "contexture_middle"
        ):
            logger.info("Rendering specialized VLM primary Markdown through Contexture Middle...")
            middle_markdown = self._render_specialized_vlm_middle_markdown(
                source_name=Path(filepath).name,
                source=filepath,
            )
            if middle_markdown and middle_markdown.strip():
                elapsed_time = time.time() - start_time
                logger.info(f"OCR Direct conversion completed in {elapsed_time:.1f}s")
                logger.info(f"Total: {len(middle_markdown)} chars")
                logger.info(f"Speed: {len(pages_images) / elapsed_time:.2f} pages/sec")
                self._emit_progress(event="file_done", stage="saving")
                return middle_markdown
            logger.warning("Contexture Middle rendering produced no Markdown; falling back to official Markdown.")

        # 8. 清理页面分隔符（避免嵌套）
        logger.info("Cleaning page separators...")
        markdown_pages = self._clean_page_separators(markdown_pages)

        # 8.5 移除噪音（水印等）
        if self.noise_removal_enabled:
            logger.info("Removing noise...")
            markdown_pages = self._remove_noise(markdown_pages)

        # 8.6 修复Unicode上标脚注
        if self.footnote_fix_enabled:
            logger.info("Fixing unicode superscript footnotes...")
            markdown_pages = self._fix_unicode_superscript_footnotes(markdown_pages)

        # 8.7 修复断行
        if self.hyphenation_fix_enabled:
            logger.info("Fixing hyphenation...")
            markdown_pages = self._fix_hyphenation(markdown_pages)

        # 8.8 过滤页眉/页脚/边注标记
        if self.filter_page_header or self.filter_page_footer or self.filter_margin_notes:
            logger.info("Filtering page markers...")
            markdown_pages = self._filter_page_markers(markdown_pages)

        # 9. 添加页码锚点（如果启用）
        if self.page_anchor_plugin and self.page_anchor_plugin.enabled:
            logger.info("Adding page anchors...")
            markdown_pages = self.page_anchor_plugin.process_pages(markdown_pages, printed_pages)

        # 10. 拼接所有页面
        anchors_enabled = bool(self.page_anchor_plugin and self.page_anchor_plugin.enabled)
        full_markdown = join_markdown_pages(
            markdown_pages,
            page_separator="\n\n---\n\n",
            page_anchors_enabled=anchors_enabled,
        )

        # 11. 添加文档末尾的额外锚点（用于区间提取）
        if anchors_enabled:
            page_count = len(pages_images)
            final_anchor = f"{{{page_count}}}"
            full_markdown += f"\n\n{final_anchor}\n\n---"
            logger.info(f"Added final anchor: {final_anchor}")

        elapsed_time = time.time() - start_time
        logger.info(f"OCR Direct conversion completed in {elapsed_time:.1f}s")
        logger.info(f"Total: {len(full_markdown)} chars")
        logger.info(f"Speed: {len(pages_images) / elapsed_time:.2f} pages/sec")
        self._emit_progress(event="file_done", stage="saving")

        return full_markdown
