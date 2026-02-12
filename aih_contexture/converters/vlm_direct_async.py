"""
VLM Direct Async Converter - 异步并发版本

完全跳过 Surya，纯用 VLM 处理，支持多线程并发。

特性：
- 异步并发处理（asyncio）
- 可配置并发数
- 自动重试机制
- 进度显示
- 错误处理
- 支持 OpenAI 兼容 API 和 Gemini 原生 API

性能：
- 串行：25页 × 10秒 = 4-8分钟
- 并发（5线程）：25页 ÷ 5 = 1-2分钟（提速 5倍）
"""

import asyncio
import base64
import time
import re
from io import BytesIO
from typing import Annotated, List, Optional

import aiohttp
from PIL import Image
from tqdm.asyncio import tqdm

from aih_contexture.converters import BaseConverter
from aih_contexture.logger import get_logger
from aih_contexture.providers.registry import provider_from_filepath
from aih_contexture.formatters import PageAnchorFormatter, PageAnchorPlugin, PrintedPageExtractor
from aih_contexture.builders.markdown import MarkdownDocumentBuilder
from aih_contexture.utils.api_key_pool import APIKeyPool

logger = get_logger()


# 默认提示词 - 要求输出在 markdown 代码块中（便于提取和处理推理模型输出）
DEFAULT_PROMPT = """Convert this document page to Markdown format.

## Markdown Syntax (use as needed)
**Headings**: # ## ###
**Lists**: - item or 1. item
**Tables**: | Col1 | Col2 |
**Emphasis**: **bold**, *italic*
**Math**: $inline$ or $$block$$

## CRITICAL Output Rules
1. Wrap ALL your output in a single ```markdown``` code block
2. Do NOT add any explanations OUTSIDE the code block
3. Inside the code block, output ONLY the document content
4. Preserve original text exactly - DO NOT translate
5. Keep the original language (Chinese stays Chinese, etc.)
6. Mark unclear text as [unclear]

Example output format:
```markdown
# Document Title
Content here...
```"""


class VlmDirectAsyncConverter(BaseConverter):
    """
    VLM Direct Async Converter - 异步并发版本

    配置参数：
    - vlm_direct_base_url: API Base URL
    - vlm_direct_model: 模型名称
    - vlm_direct_api_key: API 密钥
    - vlm_direct_prompt: 自定义提示词
    - vlm_direct_max_image_dimension: 图像最大边长
    - vlm_direct_jpeg_quality: JPEG 质量
    - vlm_direct_timeout: 超时时间
    - vlm_direct_max_tokens: 最大输出 token 数
    - vlm_direct_max_retries: 最大重试次数
    - vlm_direct_max_concurrent: 最大并发数（新增）
    """

    # API 配置 (默认使用 newcli Gemini 中转)
    vlm_direct_base_url: Annotated[str, "VLM API 的 Base URL"] = "https://code.newcli.com/gemini"
    vlm_direct_model: Annotated[str, "VLM 模型名称"] = "gemini-2.5-flash"
    vlm_direct_api_key: Annotated[str, "API 密钥"] = ""

    # 提示词配置
    vlm_direct_prompt: Annotated[str, "转换提示词"] = DEFAULT_PROMPT

    # 图像处理配置
    vlm_direct_image_format: Annotated[str, "图像格式: jpeg, png, webp"] = "jpeg"
    vlm_direct_max_image_dimension: Annotated[int, "图像最大边长（像素）"] = 2048
    vlm_direct_jpeg_quality: Annotated[int, "JPEG 压缩质量 (1-100)"] = 90

    # API 调用配置
    vlm_direct_timeout: Annotated[int, "API 超时时间（秒）"] = 600  # 10分钟，适应慢速API
    vlm_direct_max_tokens: Annotated[int, "最大输出 token 数（0=不限制）"] = 0
    vlm_direct_max_retries: Annotated[int, "最大重试次数"] = 3

    # 并发配置（新增）
    vlm_direct_max_concurrent: Annotated[int, "最大并发数"] = 5

    # 页面分隔符
    vlm_direct_page_separator: Annotated[str, "页面之间的分隔符"] = "\n\n---\n\n"

    # DPI 配置
    vlm_direct_dpi: Annotated[int, "PDF 渲染 DPI"] = 144

    # 页码锚点配置（新增）
    vlm_direct_enable_page_anchors: Annotated[bool, "是否启用页码锚点"] = True
    vlm_direct_page_anchor_wrapper: Annotated[str, "锚点包装格式（固定 {n}）"] = "{{{}}}"
    vlm_direct_page_anchor_position: Annotated[str, "锚点位置: before/after/both"] = "before"
    vlm_direct_extract_printed_pages: Annotated[bool, "是否从 VLM 输出提取印刷页码"] = True
    vlm_direct_printed_page_patterns: Annotated[list | None, "自定义页码提取正则模式列表"] = None

    # 自定义编号配置（新增）
    vlm_direct_custom_id_source: Annotated[str, "自定义编号来源: none/vlm/file/list/auto"] = "none"
    vlm_direct_custom_id_data: Annotated[any, "自定义编号数据"] = None

    # 渲染器配置（新增 - 支持多格式输出）
    renderer: Annotated[str | None, "渲染器类路径 (如: marker.renderers.markdown.MarkdownRenderer)"] = None
    use_markdown_builder: Annotated[bool, "是否使用MarkdownDocumentBuilder转换为Document对象"] = False

    # 后处理配置
    vlm_direct_disable_postprocess: Annotated[bool, "禁用后处理（信任VLM原始输出）"] = False

    # 提示词模板配置（新增）
    vlm_direct_prompt_template: Annotated[str, "提示词模板名称"] = "modern_publication"
    vlm_direct_prompt_params: Annotated[dict, "自定义模板参数"] = {}
    vlm_direct_api_preset: Annotated[str, "API 参数预设"] = "high_accuracy"

    # API 参数配置（新增）
    vlm_direct_temperature: Annotated[float, "Temperature (0.0-1.0)"] = 0.0
    vlm_direct_top_p: Annotated[float, "Top P (0.0-1.0)"] = 0.1
    vlm_direct_top_k: Annotated[int | None, "Top K"] = None

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        config = config or {}

        # 🆕 API 提供商配置
        self.api_provider = config.get("vlm_api_provider", "openai_compatible")

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

        self.max_concurrent = int(config.get("vlm_direct_max_concurrent", self.vlm_direct_max_concurrent))

        # 后处理配置
        self.disable_postprocess = config.get("vlm_direct_disable_postprocess", self.vlm_direct_disable_postprocess)

        self.page_separator = config.get("vlm_direct_page_separator", self.vlm_direct_page_separator)
        self.dpi = int(config.get("vlm_direct_dpi", self.vlm_direct_dpi))

        # 页码范围配置
        page_range_str = config.get("page_range", None)
        self.page_start = None  # 0-based inclusive
        self.page_end = None    # 0-based inclusive
        if page_range_str:
            parts = page_range_str.split("-")
            if len(parts) == 2:
                self.page_start = int(parts[0])
                self.page_end = int(parts[1])
                logger.info(f"[VlmDirectAsyncConverter] Page range: {self.page_start}-{self.page_end} (0-based)")

        # 页码锚点配置
        enable_anchors = config.get("vlm_direct_enable_page_anchors", self.vlm_direct_enable_page_anchors)
        anchor_wrapper = config.get("vlm_direct_page_anchor_wrapper", self.vlm_direct_page_anchor_wrapper)
        anchor_position = config.get("vlm_direct_page_anchor_position", self.vlm_direct_page_anchor_position)
        self.extract_printed_pages = config.get("vlm_direct_extract_printed_pages", self.vlm_direct_extract_printed_pages)

        # 🆕 读取自定义正则模式
        custom_patterns = config.get("vlm_direct_printed_page_patterns", self.vlm_direct_printed_page_patterns)

        # 自定义编号配置
        custom_id_source = config.get("vlm_direct_custom_id_source", self.vlm_direct_custom_id_source)
        custom_id_data = config.get("vlm_direct_custom_id_data", self.vlm_direct_custom_id_data)

        # 初始化页码锚点插件（简化版 - 固定使用 {n} 格式）
        from aih_contexture.formatters import PageAnchorFormatter, CustomIDInjector
        formatter = PageAnchorFormatter(wrapper=anchor_wrapper)

        # 初始化自定义编号注入器
        custom_id_injector = CustomIDInjector(
            source_type=custom_id_source,
            source_data=custom_id_data
        ) if custom_id_source != "none" else None

        self.page_anchor_plugin = PageAnchorPlugin(
            formatter=formatter,
            enabled=enable_anchors,
            position=anchor_position,
            separator="\n\n",
            page_separator=self.page_separator.strip(),  # 传递页面分隔符
            custom_id_injector=custom_id_injector
        )

        # 初始化印刷页码提取器（🆕 传递自定义正则模式）
        self.printed_page_extractor = PrintedPageExtractor(
            patterns=custom_patterns,
            remove_from_content=True
        ) if self.extract_printed_pages else None

        # 初始化 API Key Pool for multi-key concurrent support
        self.key_pool = APIKeyPool(self.api_key)
        if self.key_pool.get_key_count() > 1:
            logger.info(f"[VlmDirectAsyncConverter] Using {self.key_pool.get_key_count()} API keys with concurrent pool")

        # 初始化提示词模板系统（新增）
        from aih_contexture.prompts import PromptBuilder, APIParameterAdapter

        # 检查是否使用旧的 vlm_direct_prompt 参数（向后兼容）
        # 只有当明确提供了非空的自定义提示词时才使用旧模式
        if "vlm_direct_prompt" in config and config["vlm_direct_prompt"] and config["vlm_direct_prompt"].strip():
            # 使用旧的自定义提示词
            logger.info("[VlmDirectAsyncConverter] Using custom prompt (legacy mode)")
            self.prompt = config["vlm_direct_prompt"]
            self.api_params = {}  # 旧模式不使用 API 参数
        else:
            # 使用新的模板系统
            if config.get("vlm_direct_prompt_params"):
                # 自定义参数
                logger.info("[VlmDirectAsyncConverter] Using custom template parameters")
                self.prompt_template = PromptBuilder.from_params(
                    **config["vlm_direct_prompt_params"]
                )
            else:
                # 使用预置模板
                template_name = config.get("vlm_direct_prompt_template", self.vlm_direct_prompt_template)
                logger.info(f"[VlmDirectAsyncConverter] Using template: {template_name}")
                self.prompt_template = PromptBuilder.from_template(template_name)

                # 应用 API 预设
                preset = config.get("vlm_direct_api_preset", self.vlm_direct_api_preset)
                if preset and preset != "custom":
                    preset_params = PromptBuilder.from_preset(preset)
                    for key, value in preset_params.items():
                        setattr(self.prompt_template, key, value)
                    logger.info(f"[VlmDirectAsyncConverter] Applied API preset: {preset}")

            # 覆盖单独指定的 API 参数
            if "vlm_direct_temperature" in config:
                self.prompt_template.temperature = config["vlm_direct_temperature"]
            if "vlm_direct_top_p" in config:
                self.prompt_template.top_p = config["vlm_direct_top_p"]
            if "vlm_direct_top_k" in config:
                self.prompt_template.top_k = config["vlm_direct_top_k"]
            if "vlm_direct_max_tokens" in config:
                self.prompt_template.max_tokens = config["vlm_direct_max_tokens"]

            # 构建提示词
            self.prompt = self.prompt_template.build_prompt()

            # 🔍 调试日志：检查提示词中是否包含页码识别指令
            if "printed-page" in self.prompt:
                logger.info(f"[VlmDirectAsyncConverter] ✅ Prompt contains 'printed-page' instruction")
            else:
                logger.warning(f"[VlmDirectAsyncConverter] ❌ Prompt does NOT contain 'printed-page' instruction!")

            logger.info(f"[VlmDirectAsyncConverter] Prompt length: {len(self.prompt)} characters")

            # 检测 API 类型
            self.api_type = APIParameterAdapter.detect_api_type(
                self.base_url, self.model
            )

            # 获取适配后的 API 参数
            self.api_params = self.prompt_template.get_api_params(self.api_type)

            logger.info(f"[VlmDirectAsyncConverter] API Type: {self.api_type}")
            logger.info(f"[VlmDirectAsyncConverter] API Params: {self.api_params}")

        # 渲染器配置（新增）
        self.renderer_path = config.get("renderer", self.renderer)
        self.use_markdown_builder = config.get("use_markdown_builder", self.use_markdown_builder)

        # 如果指定了渲染器,自动启用markdown builder
        if self.renderer_path:
            self.use_markdown_builder = True

        # 初始化MarkdownDocumentBuilder
        if self.use_markdown_builder:
            self.markdown_builder = MarkdownDocumentBuilder(
                page_separator=self.page_separator,
                extract_page_anchors=enable_anchors,
            )
        else:
            self.markdown_builder = None

        logger.info(f"[VlmDirectAsyncConverter] Init: base_url={self.base_url}, model={self.model}")
        logger.info(f"[VlmDirectAsyncConverter] Concurrent: max_concurrent={self.max_concurrent}")
        logger.info(f"[VlmDirectAsyncConverter] Image: format={self.image_format}, max_dim={self.max_image_dimension}")
        if self.use_markdown_builder:
            logger.info(f"[VlmDirectAsyncConverter] Markdown builder enabled, renderer={self.renderer_path}")

    def _clean_page_separators(self, pages: List[str]) -> List[str]:
        """
        清理页面中的多余分隔符，避免与 page_separator 冲突。

        移除每个页面开头和结尾的 markdown 水平线（---）。
        """
        import re

        cleaned_pages = []
        # 匹配开头或结尾的 --- (可能有空白)
        separator_pattern = r'^\s*---+\s*$'

        for page in pages:
            lines = page.split('\n')

            # 移除开头的分隔符
            while lines and re.match(separator_pattern, lines[0]):
                lines.pop(0)

            # 移除结尾的分隔符
            while lines and re.match(separator_pattern, lines[-1]):
                lines.pop()

            cleaned_page = '\n'.join(lines).strip()
            cleaned_pages.append(cleaned_page)

        return cleaned_pages

    def _truncate_repetition(self, text: str, min_len: int = 50) -> str:
        """检测并截断重复内容"""
        if len(text) < min_len * 2:
            return text

        # 方法1: 检测重复段落
        paragraphs = text.split('\n\n')
        if len(paragraphs) > 3:
            seen = set()
            unique = []
            for p in paragraphs:
                p_clean = p.strip()
                if len(p_clean) < 20:
                    unique.append(p)
                    continue
                if p_clean in seen:
                    logger.warning(f"[Truncate] Found repeated paragraph, stopping")
                    break
                seen.add(p_clean)
                unique.append(p)
            if len(unique) < len(paragraphs):
                return '\n\n'.join(unique)

        # 方法2: 检测长文本中的重复模式
        for pattern_len in range(min_len, min(300, len(text) // 3)):
            mid = len(text) // 2
            pattern = text[mid:mid + pattern_len]
            first_pos = text[:mid].find(pattern)
            if first_pos != -1:
                logger.warning(f"[Truncate] Found repetition at {first_pos}")
                return text[:first_pos + pattern_len]

        return text

    def _clean_markdown_output(self, text: str) -> str:
        """清理VLM输出的markdown内容 - 增强版

        支持处理推理模型（如 gemini-3-pro）的输出：
        - 提取 ```markdown``` 代码块中的内容
        - 移除思考过程
        - 移除说明性前缀和后缀
        """
        if not text:
            return text

        import re
        text = text.strip()

        # 1. 用正则从文本中提取 ```markdown...``` 代码块内容
        match = re.search(r'```markdown\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            text = match.group(1).strip()
            logger.info(f"[Clean] Extracted from ```markdown ({len(text)} chars)")
        else:
            # 尝试匹配普通 ``` 代码块
            match = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL)
            if match:
                text = match.group(1).strip()
                logger.info(f"[Clean] Extracted from ``` ({len(text)} chars)")

        # 2. 二次保险：移除残留标记
        if text.startswith('```markdown'):
            text = text[len('```markdown'):].lstrip()
        elif text.startswith('```'):
            text = text[3:].lstrip()
        if text.endswith('```'):
            text = text[:-3].rstrip()

        text = text.strip()

        # 3. 如果没有代码块，尝试移除常见的说明性前缀
        prefixes = [
            "以下是", "这是", "下面是", "如下", "内容如下",
            "Here is", "Below is", "The following", "This is",
            "转换结果", "识别结果", "Markdown",
        ]
        lines = text.split('\n')
        # 检查前几行是否是说明性文字
        while lines and len(lines[0].strip()) < 100:
            first_line = lines[0].strip()
            is_prefix = False
            for prefix in prefixes:
                if prefix in first_line:
                    is_prefix = True
                    break
            # 如果第一行是说明性文字（不以markdown语法开头）
            if is_prefix or (first_line and not first_line[0] in '#|-*>0123456789[!$'):
                # 检查是否是纯说明文字（不包含实际内容）
                if len(first_line) < 80 and ':' in first_line or '：' in first_line:
                    lines.pop(0)
                    continue
                elif is_prefix:
                    lines.pop(0)
                    continue
            break
        text = '\n'.join(lines)

        # 3. 移除结尾的说明性文字
        suffixes = ["注：", "Note:", "说明：", "以上是", "This is", "---", "备注"]
        lines = text.split("\n")
        while lines:
            last_line = lines[-1].strip()
            if not last_line:
                lines.pop()
                continue
            should_remove = False
            for suffix in suffixes:
                if last_line.startswith(suffix):
                    should_remove = True
                    break
            if should_remove:
                lines.pop()
            else:
                break
        text = "\n".join(lines)

        # 4. 最后一道保险：直接字符串替换，确保移除所有代码块标记
        text = text.replace('```markdown', '')
        text = text.replace('```', '')

        return text.strip()

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

    async def _convert_page_async(
        self,
        session: aiohttp.ClientSession,
        img: Image.Image,
        page_num: int,
        semaphore: asyncio.Semaphore
    ) -> tuple[int, str]:
        """异步转换单个页面"""
        async with semaphore:  # 控制并发数
            logger.info(f"[VlmDirectAsyncConverter] Converting page {page_num}...")

            # 🆕 根据 API 提供商选择不同的调用方式
            if self.api_provider == "gemini":
                return await self._convert_page_gemini(session, img, page_num)
            elif self.api_provider == "anthropic":
                return await self._convert_page_anthropic(session, img, page_num)
            else:
                return await self._convert_page_openai(session, img, page_num)

    async def _convert_page_openai(
        self,
        session: aiohttp.ClientSession,
        img: Image.Image,
        page_num: int
    ) -> tuple[int, str]:
        """使用 OpenAI 兼容 API 转换页面"""
        # 构建请求
        b64_img = self._img_to_base64(img)
        fmt = (self.image_format or "jpeg").lower()
        mime = "jpeg" if fmt in ("jpg", "jpeg") else ("png" if fmt == "png" else "webp")

        content = [
            {
                "type": "text",
                "text": self.prompt
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/{mime};base64,{b64_img}"}
            }
        ]

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0.0,  # 最低温度，确保输出稳定
            "top_p": 0.1,        # 低top_p，减少随机性
        }

        # OCR 任务使用严格参数，防止模型过度脑补
        if page_num == 1:
            logger.info(f"[VlmDirectAsyncConverter] Using strict OCR params: temperature=0.0, top_p=0.1")

        # API 调用（带重试和Key Pool）
        last_error = None
        max_retries = self.max_retries

        for attempt in range(max_retries + 1):
            try:
                current_key = self.key_pool.acquire()
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {current_key}"
                }

                async with session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        markdown = data["choices"][0]["message"]["content"].strip()

                        # 🔍 检查 finish_reason - 诊断停止原因
                        finish_reason = data["choices"][0].get("finish_reason", "unknown")
                        usage = data.get("usage", {})
                        completion_tokens = usage.get("completion_tokens", "N/A")

                        if finish_reason == "length":
                            logger.warning(f"[VlmDirectAsyncConverter] ⚠️ Page {page_num}: finish_reason=length (hit token limit!), tokens={completion_tokens}")
                        elif finish_reason == "stop":
                            logger.info(f"[VlmDirectAsyncConverter] ✓ Page {page_num}: finish_reason=stop (normal), tokens={completion_tokens}")
                        else:
                            logger.info(f"[VlmDirectAsyncConverter] Page {page_num}: finish_reason={finish_reason}, tokens={completion_tokens}")

                        # 后处理 - 始终清理（提取代码块、移除思考过程）
                        if not self.disable_postprocess:
                            markdown = self._clean_markdown_output(markdown)

                        logger.info(f"[VlmDirectAsyncConverter] Page {page_num} converted ({len(markdown)} chars)")
                        self.key_pool.mark_success(current_key)
                        return (page_num, markdown)
                    else:
                        error_text = await response.text()
                        raise Exception(f"API error {response.status}: {error_text}")

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
                logger.warning(f"[VlmDirectAsyncConverter] Retryable error on page {page_num} (attempt {attempt + 1}): {e}")
                self.key_pool.mark_failure(current_key)
                if attempt < max_retries:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue

            except Exception as e:
                last_error = e
                logger.error(f"[VlmDirectAsyncConverter] Error on page {page_num}: {e}")
                self.key_pool.mark_failure(current_key)
                if attempt < max_retries:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                break

        # 所有重试失败
        logger.error(f"[VlmDirectAsyncConverter] Failed to convert page {page_num}: {last_error}")
        return (page_num, f"<!-- Error converting page {page_num}: {last_error} -->")

    async def _convert_page_gemini(
        self,
        session: aiohttp.ClientSession,
        img: Image.Image,
        page_num: int
    ) -> tuple[int, str]:
        """使用 Gemini 原生 API 转换页面

        支持多种中继服务格式：
        1. 官方 API: https://generativelanguage.googleapis.com
        2. 中继服务: https://example.com/gemini 或 https://example.com/v1beta
        """
        b64_img = self._img_to_base64(img)

        # 智能构建 Gemini API 端点
        base_url = self.base_url.rstrip('/') if self.base_url else "https://generativelanguage.googleapis.com"

        # 检测 base_url 是否已包含 API 版本路径
        if '/v1beta' in base_url or '/v1/' in base_url:
            # 中继服务已包含版本路径，直接拼接 models 路径
            url = f"{base_url}/models/{self.model}:generateContent"
        elif base_url.endswith('/gemini') or base_url.endswith('/google'):
            # 中继服务使用 /gemini 或 /google 后缀
            # 使用 v1beta 路径（经测试 newcli 等中转服务使用 v1beta）
            url = f"{base_url}/v1beta/models/{self.model}:generateContent"
        else:
            # 标准格式
            url = f"{base_url}/v1beta/models/{self.model}:generateContent"

        # 构建 Gemini 请求体 - 添加 role: "user" 以兼容更多中继服务
        payload = {
            "contents": [{
                "role": "user",
                "parts": [
                    {"inline_data": {"mime_type": "image/jpeg", "data": b64_img}},
                    {"text": self.prompt}
                ]
            }]
        }

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                current_key = self.key_pool.acquire()

                # 尝试多种认证方式
                # 方式1: x-goog-api-key 头部（推荐用于中继服务）
                headers = {
                    "Content-Type": "application/json",
                    "x-goog-api-key": current_key
                }

                if page_num == 1 and attempt == 0:
                    logger.info(f"[Gemini] URL: {url}")
                    logger.info(f"[Gemini] Using x-goog-api-key header auth")

                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        # 提取 Gemini 响应 - 过滤掉 thinking 内容
                        parts = data["candidates"][0]["content"]["parts"]
                        text_parts = []
                        thinking_chars = 0
                        for part in parts:
                            # 跳过 thinking 内容（thought: true 标识）
                            if part.get("thought", False):
                                thinking_chars += len(part.get("text", ""))
                                continue
                            if "text" in part:
                                text_parts.append(part["text"])

                        if thinking_chars > 0:
                            logger.info(f"[Gemini] Filtered out {thinking_chars} chars of thinking content")

                        markdown = "\n".join(text_parts).strip()

                        # 🔍 检查 finishReason - 诊断停止原因
                        finish_reason = data["candidates"][0].get("finishReason", "unknown")
                        usage = data.get("usageMetadata", {})
                        completion_tokens = usage.get("candidatesTokenCount", "N/A")

                        if finish_reason == "MAX_TOKENS":
                            logger.warning(f"[Gemini] ⚠️ Page {page_num}: finishReason=MAX_TOKENS (hit token limit!), tokens={completion_tokens}")
                        elif finish_reason == "STOP":
                            logger.info(f"[Gemini] ✓ Page {page_num}: finishReason=STOP (normal), tokens={completion_tokens}")
                        else:
                            logger.info(f"[Gemini] Page {page_num}: finishReason={finish_reason}, tokens={completion_tokens}")

                        # 🆕 输出后处理 - 始终清理（提取代码块、移除思考过程）
                        if not self.disable_postprocess:
                            markdown = self._clean_markdown_output(markdown)
                            logger.info(f"[Gemini] Page {page_num} cleaned ({len(markdown)} chars)")

                        logger.info(f"[Gemini] Page {page_num} converted ({len(markdown)} chars)")
                        self.key_pool.mark_success(current_key)
                        return (page_num, markdown)
                    elif response.status in (401, 403):
                        # 认证失败，尝试查询参数方式
                        error_text = await response.text()
                        logger.warning(f"[Gemini] Header auth failed ({response.status}), trying query param...")

                        # 方式2: 查询参数
                        headers_simple = {"Content-Type": "application/json"}
                        async with session.post(
                            f"{url}?key={current_key}",
                            json=payload,
                            headers=headers_simple,
                            timeout=aiohttp.ClientTimeout(total=self.timeout)
                        ) as response2:
                            if response2.status == 200:
                                data = await response2.json()
                                # 提取 Gemini 响应 - 过滤掉 thinking 内容
                                parts = data["candidates"][0]["content"]["parts"]
                                text_parts = []
                                for part in parts:
                                    if part.get("thought", False):
                                        continue
                                    if "text" in part:
                                        text_parts.append(part["text"])
                                markdown = "\n".join(text_parts).strip()

                                # 🆕 输出后处理 - 始终清理
                                if not self.disable_postprocess:
                                    markdown = self._clean_markdown_output(markdown)

                                logger.info(f"[Gemini] Page {page_num} converted with query param auth ({len(markdown)} chars)")
                                self.key_pool.mark_success(current_key)
                                return (page_num, markdown)
                            else:
                                error_text2 = await response2.text()
                                raise Exception(f"Gemini API error {response2.status}: {error_text2}")
                    else:
                        error_text = await response.text()
                        raise Exception(f"Gemini API error {response.status}: {error_text}")

            except Exception as e:
                last_error = e
                logger.warning(f"[Gemini] Error on page {page_num} (attempt {attempt + 1}): {e}")
                self.key_pool.mark_failure(current_key)
                if attempt < self.max_retries:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                break

        logger.error(f"[Gemini] Failed to convert page {page_num}: {last_error}")
        return (page_num, f"<!-- Error converting page {page_num}: {last_error} -->")

    async def _convert_page_anthropic(
        self,
        session: aiohttp.ClientSession,
        img: Image.Image,
        page_num: int
    ) -> tuple[int, str]:
        """使用 Anthropic Claude 原生 API 转换页面"""
        b64_img = self._img_to_base64(img)

        # 构建 Anthropic API 端点
        base_url = self.base_url.rstrip('/') if self.base_url else "https://api.anthropic.com"
        url = f"{base_url}/v1/messages"

        # 构建 Anthropic 请求体
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": b64_img
                        }
                    },
                    {
                        "type": "text",
                        "text": self.prompt
                    }
                ]
            }]
        }

        # 添加 API 参数
        if hasattr(self, 'api_params') and self.api_params:
            if 'temperature' in self.api_params:
                payload['temperature'] = self.api_params['temperature']
            if 'top_p' in self.api_params:
                payload['top_p'] = self.api_params['top_p']

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                current_key = self.key_pool.acquire()
                headers = {
                    "Content-Type": "application/json",
                    "x-api-key": current_key,
                    "anthropic-version": "2023-06-01"
                }

                if page_num == 1 and attempt == 0:
                    logger.info(f"[Anthropic] URL: {url}")
                    logger.info(f"[Anthropic] Model: {self.model}")

                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        # 提取 Anthropic 响应
                        markdown = data["content"][0]["text"].strip()

                        # 输出后处理 - 始终清理
                        if not self.disable_postprocess:
                            markdown = self._clean_markdown_output(markdown)

                        logger.info(f"[Anthropic] Page {page_num} converted ({len(markdown)} chars)")
                        self.key_pool.mark_success(current_key)
                        return (page_num, markdown)
                    else:
                        error_text = await response.text()
                        raise Exception(f"Anthropic API error {response.status}: {error_text}")

            except Exception as e:
                last_error = e
                logger.warning(f"[Anthropic] Error on page {page_num} (attempt {attempt + 1}): {e}")
                self.key_pool.mark_failure(current_key)
                if attempt < self.max_retries:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                break

        logger.error(f"[Anthropic] Failed to convert page {page_num}: {last_error}")
        return (page_num, f"<!-- Error converting page {page_num}: {last_error} -->")

    async def _convert_page_async_no_semaphore(
        self,
        session: aiohttp.ClientSession,
        img: Image.Image,
        page_num: int
    ) -> tuple[int, str]:
        """异步转换单个页面（无信号量版本，用于严格批次模式）

        根据 api_provider 选择不同的 API 格式。
        """
        logger.info(f"[VlmDirectAsyncConverter] Converting page {page_num}...")

        # 🆕 根据 API 提供商选择不同的调用方式
        if self.api_provider == "gemini":
            return await self._convert_page_gemini(session, img, page_num)
        elif self.api_provider == "anthropic":
            return await self._convert_page_anthropic(session, img, page_num)
        else:
            return await self._convert_page_openai(session, img, page_num)

    async def _convert_all_pages_async(
        self,
        images: List[Image.Image],
        global_semaphore: Optional[asyncio.Semaphore] = None
    ) -> List[str]:
        """异步转换所有页面（严格批次模式）

        LM Studio 优化：一批全部完成后才送下一批，避免 promote 阶段导致的性能下降。

        Args:
            images: 页面图像列表
            global_semaphore: 全局信号量（已弃用，保留兼容性）
        """
        all_results = []
        concurrency = self.max_concurrent
        total_pages = len(images)

        async with aiohttp.ClientSession() as session:
            # 将所有页面分成小批次，每批 = 并发数
            for batch_start in range(0, total_pages, concurrency):
                batch_end = min(batch_start + concurrency, total_pages)
                batch_images = images[batch_start:batch_end]

                logger.info(f"[VLM] Processing batch {batch_start//concurrency + 1}: pages {batch_start+1}-{batch_end}")

                # 创建当前批次的所有任务
                tasks = [
                    self._convert_page_async_no_semaphore(session, img, batch_start + idx + 1)
                    for idx, img in enumerate(batch_images)
                ]

                # 等待当前批次全部完成
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                # 🔍 DEBUG: 检查批次结果
                for i, result in enumerate(batch_results):
                    if isinstance(result, Exception):
                        logger.error(f"[DEBUG] Batch result {i}: EXCEPTION - {result}")
                    elif isinstance(result, tuple) and len(result) == 2:
                        page_num, content = result
                        logger.info(f"[DEBUG] Batch result {i}: page={page_num}, len={len(content)}")
                    else:
                        logger.warning(f"[DEBUG] Batch result {i}: UNEXPECTED - {type(result)}")

                all_results.extend(batch_results)

                logger.info(f"[VLM] Batch completed: {len(batch_results)} pages")

            # 按页码排序
            all_results.sort(key=lambda x: x[0] if isinstance(x, tuple) else 0)

            # 🔍 DEBUG: 检查过滤前后的结果数量
            valid_results = [(page_num, markdown) for page_num, markdown in all_results if isinstance(page_num, int)]
            logger.info(f"[DEBUG] Total results: {len(all_results)}, Valid results: {len(valid_results)}")

            return [markdown for page_num, markdown in valid_results]

    def __call__(self, filepath: str, global_semaphore: Optional[asyncio.Semaphore] = None):
        """
        转换文档为 Markdown 或其他格式

        Args:
            filepath: 文档路径
            global_semaphore: 全局信号量（用于多文件并发控制）

        Returns:
            - 如果未指定渲染器: 返回 Markdown 字符串 (str)
            - 如果指定了渲染器: 返回渲染器输出对象
        """
        logger.info(f"[VlmDirectAsyncConverter] Starting conversion: {filepath}")

        # 1. 加载文档
        provider_cls = provider_from_filepath(filepath)
        provider = provider_cls(filepath, self.config)

        # 2. 获取所有页面图像（支持页码范围过滤）
        num_pages = len(provider)
        if self.page_start is not None and self.page_end is not None:
            actual_end = min(self.page_end, num_pages - 1)
            page_indices = list(range(self.page_start, actual_end + 1))
            logger.info(f"[VlmDirectAsyncConverter] Page range: {self.page_start}-{actual_end} (total {num_pages} pages)")
        else:
            page_indices = list(range(num_pages))
        images = provider.get_images(page_indices, self.dpi)

        logger.info(f"[VlmDirectAsyncConverter] Loaded {len(images)} pages")
        logger.info(f"[VlmDirectAsyncConverter] Using {self.max_concurrent} concurrent workers")

        # 3. 异步并发转换（传递全局信号量）
        start_time = time.time()
        markdown_pages = asyncio.run(self._convert_all_pages_async(images, global_semaphore))
        elapsed_time = time.time() - start_time

        # 🔍 DEBUG: 检查 API 返回的原始内容
        logger.info(f"[DEBUG] After API call: {len(markdown_pages)} pages")
        for i, page in enumerate(markdown_pages):
            logger.info(f"[DEBUG] Page {i+1} raw length: {len(page)} chars")
            if len(page) < 200:
                logger.info(f"[DEBUG] Page {i+1} content: {repr(page[:500])}")

        # 4. 提取印刷页码（如果启用）
        printed_pages = None
        if self.printed_page_extractor:
            logger.info(f"[VlmDirectAsyncConverter] Extracting printed pages...")
            markdown_pages, printed_pages = self.printed_page_extractor.extract_batch(markdown_pages)
            found_count = sum(1 for p in printed_pages if p is not None)
            logger.info(f"[VlmDirectAsyncConverter] Found {found_count} printed pages")
            # 🔍 DEBUG
            for i, page in enumerate(markdown_pages):
                logger.info(f"[DEBUG] After extract, Page {i+1}: {len(page)} chars")

        # 5. 清理页面分隔符（避免嵌套）
        logger.info(f"[VlmDirectAsyncConverter] Cleaning page separators...")
        markdown_pages = self._clean_page_separators(markdown_pages)
        # 🔍 DEBUG
        for i, page in enumerate(markdown_pages):
            logger.info(f"[DEBUG] After clean, Page {i+1}: {len(page)} chars")

        # 6. 添加页码锚点（如果启用）
        if self.page_anchor_plugin.enabled:
            logger.info(f"[VlmDirectAsyncConverter] Adding page anchors...")
            markdown_pages = self.page_anchor_plugin.process_pages(markdown_pages, printed_pages)

        # 7. 拼接所有页面
        full_markdown = self.page_separator.join(markdown_pages)

        # 添加文档末尾的额外锚点（用于区间提取）
        if self.page_anchor_plugin.enabled:
            page_count = len(images)
            final_anchor = f"{{{page_count}}}"
            full_markdown += f"\n\n{final_anchor}"
            logger.info(f"[VlmDirectAsyncConverter] Added final anchor: {final_anchor}")

        logger.info(f"[VlmDirectAsyncConverter] Conversion complete in {elapsed_time:.1f}s")
        logger.info(f"[VlmDirectAsyncConverter] Total: {len(full_markdown)} chars")
        logger.info(f"[VlmDirectAsyncConverter] Speed: {len(images) / elapsed_time:.2f} pages/sec")

        # 8. 如果启用了渲染器,转换为Document并渲染
        if self.use_markdown_builder and self.markdown_builder:
            logger.info(f"[VlmDirectAsyncConverter] Building Document from Markdown...")
            document = self.markdown_builder.build(full_markdown, filepath)

            if self.renderer_path:
                logger.info(f"[VlmDirectAsyncConverter] Rendering with {self.renderer_path}...")
                renderer = self.resolve_dependencies(self.renderer_path)
                rendered = renderer(document)
                logger.info(f"[VlmDirectAsyncConverter] Rendered to {type(rendered).__name__}")
                return rendered
            else:
                # 只构建Document,不渲染
                logger.info(f"[VlmDirectAsyncConverter] Returning Document object")
                return document

        # 9. 默认行为: 返回Markdown字符串
        return full_markdown

    async def convert_async(self, filepath: str, global_semaphore: Optional[asyncio.Semaphore] = None):
        """
        异步版本的转换方法（避免多线程 pypdfium2 问题）

        Args:
            filepath: 文档路径
            global_semaphore: 全局信号量（用于多文件并发控制）

        Returns:
            Markdown 字符串
        """
        logger.info(f"[VlmDirectAsyncConverter] Starting conversion: {filepath}")

        # 1. 加载文档（同步操作，但在单线程中执行）
        provider_cls = provider_from_filepath(filepath)
        provider = provider_cls(filepath, self.config)

        # 2. 获取所有页面图像（支持页码范围过滤）
        num_pages = len(provider)
        if self.page_start is not None and self.page_end is not None:
            actual_end = min(self.page_end, num_pages - 1)
            page_indices = list(range(self.page_start, actual_end + 1))
            logger.info(f"[VlmDirectAsyncConverter] Page range: {self.page_start}-{actual_end} (total {num_pages} pages)")
        else:
            page_indices = list(range(num_pages))
        images = provider.get_images(page_indices, self.dpi)

        logger.info(f"[VlmDirectAsyncConverter] Loaded {len(images)} pages")
        logger.info(f"[VlmDirectAsyncConverter] Using {self.max_concurrent} concurrent workers")

        # 3. 异步并发转换
        start_time = time.time()
        markdown_pages = await self._convert_all_pages_async(images, global_semaphore)
        elapsed_time = time.time() - start_time

        # 4. 后处理（与同步版本相同）
        logger.info(f"[DEBUG] After API call: {len(markdown_pages)} pages")
        for i, page in enumerate(markdown_pages):
            logger.info(f"[DEBUG] Page {i+1} raw length: {len(page)} chars")
            if len(page) < 200:
                logger.info(f"[DEBUG] Page {i+1} content: {repr(page[:500])}")

        # 提取印刷页码
        printed_pages = None
        if self.printed_page_extractor:
            logger.info(f"[VlmDirectAsyncConverter] Extracting printed pages...")
            markdown_pages, printed_pages = self.printed_page_extractor.extract_batch(markdown_pages)
            found_count = sum(1 for p in printed_pages if p is not None)
            logger.info(f"[VlmDirectAsyncConverter] Found {found_count} printed pages")

        # 清理页面分隔符
        logger.info(f"[VlmDirectAsyncConverter] Cleaning page separators...")
        markdown_pages = self._clean_page_separators(markdown_pages)

        # 添加页码锚点
        if self.page_anchor_plugin.enabled:
            logger.info(f"[VlmDirectAsyncConverter] Adding page anchors...")
            markdown_pages = self.page_anchor_plugin.process_pages(markdown_pages, printed_pages)

        # 拼接所有页面
        full_markdown = self.page_separator.join(markdown_pages)

        # 添加文档末尾锚点
        if self.page_anchor_plugin.enabled:
            page_count = len(images)
            final_anchor = f"{{{page_count}}}"
            full_markdown += f"\n\n{final_anchor}"
            logger.info(f"[VlmDirectAsyncConverter] Added final anchor: {final_anchor}")

        logger.info(f"[VlmDirectAsyncConverter] Conversion complete in {elapsed_time:.1f}s")
        logger.info(f"[VlmDirectAsyncConverter] Total: {len(full_markdown)} chars")
        logger.info(f"[VlmDirectAsyncConverter] Speed: {len(images) / elapsed_time:.2f} pages/sec")

        return full_markdown
