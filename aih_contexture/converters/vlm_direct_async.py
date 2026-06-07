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
import json
import os
import time
import re
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Annotated, Any, Callable, List, Optional

import aiohttp
from PIL import Image
from tqdm.asyncio import tqdm

from aih_contexture.converters import BaseConverter
from aih_contexture.logger import get_logger
from aih_contexture.utils.markdown_filters import strip_margin_comment_markers
from aih_contexture.providers.registry import provider_from_filepath
from aih_contexture.formatters import PageAnchorFormatter, PageAnchorPlugin, PrintedPageExtractor, join_markdown_pages
from aih_contexture.builders.markdown import MarkdownDocumentBuilder
from aih_contexture.utils.api_key_pool import APIKeyPool

logger = get_logger()


@dataclass
class PageResult:
    page_num: int
    ok: bool
    raw_text: str
    cleaned_text: str
    content_kind: str
    error_kind: str
    http_status: Optional[int] = None
    finish_reason: Optional[str] = None
    truncated: bool = False
    provider: str = "unknown"
    parse_stage: str = "none"
    parse_detail: Optional[str] = None
    raw_json_text: Optional[str] = None


GEMINI_JSON_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "printed_page_number": {"type": "STRING", "nullable": True},
        "page_width": {"type": "NUMBER"},
        "page_height": {"type": "NUMBER"},
        "regions": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "label": {"type": "STRING"},
                    "bbox": {
                        "type": "ARRAY",
                        "items": {"type": "NUMBER"},
                        "nullable": True,
                    },
                    "text": {"type": "STRING"},
                    "confidence": {"type": "NUMBER", "nullable": True},
                },
                "required": ["label", "bbox", "text", "confidence"],
            },
        },
    },
    "required": ["printed_page_number", "page_width", "page_height", "regions"],
}


# 默认提示词 - JSON 输出模式；运行时优先使用 PromptBuilder 生成的模板。
DEFAULT_PROMPT = """OCR this document page and return one structured JSON object with layout regions and text content.

## CRITICAL - Historical Documents
- Preserve historical ligatures: æ, œ, ſ (long s)
- Do NOT modernize: keep "hæc" not "haec", "quæ" not "quae"
- Transcribe EXACTLY as printed

## Region Labels (use EXACTLY one per region)

**Main:** Section-Header, Text, List-Group, Table, Figure, Equation-Block
**Margins:** Footnote
**Structure:** Page-Header, Page-Footer, Caption
**Special:** Code-Block, Table-Of-Contents, Complex-Block

## JSON Schema

{
  "printed_page_number": string | null,
  "page_width": number,
  "page_height": number,
  "regions": [
    {
      "label": string,
      "bbox": [number, number, number, number] | null,
      "text": string,
      "confidence": number | null
    }
  ]
}

## Field Rules

- `printed_page_number`: extract from visible Page-Header/Page-Footer only; otherwise use null.
- `page_width` and `page_height`: use actual image dimensions when available; do not invent fixed example dimensions.
- Estimate bbox in image pixels as [x0, y0, x1, y1] for each visible region. If uncertain, use null.
- `text`: transcribe exactly as printed. Use `***bold italic***`, `**bold**`, `*italic*`, `^superscript^`, `~subscript~`, `\\n` for line breaks, and `\\t` for table columns only when visible.
- Set confidence to null unless it can be estimated reliably.

## Anti-Hallucination Rules
- Include only regions and text that are actually visible on the page.
- If a value is not visible or cannot be determined, use null or an empty array.
- Do not guess missing text, page numbers, labels, coordinates, confidence, captions, or image descriptions.
- Do not copy values from schema examples; the schema above shows types, not page content.

## Detection Rules

1. **Granularity:** 5-30 semantic blocks per page (paragraphs, not lines)
2. **Marginal Notes:** Do not use Marginal-Note-Left or Marginal-Note-Right labels unless marginalia recognition is explicitly enabled.
3. **Reading Order:** Top-to-bottom, left-to-right
4. **Preserve:** Historical characters, original spelling, formatting, line breaks
5. **Do NOT:** Modernize, translate, correct "errors", add comments

## Output
- Output ONLY the JSON object
- Start with `{` and end with `}`
- No markdown fences
- No text before or after the JSON
- Stop immediately after the closing `}`
- Detect all visible content including small/faint text"""


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
    vlm_direct_prompt: Annotated[str, "自定义提示词（覆盖模板）"] = ""
    vlm_direct_prompt_template: Annotated[str, "提示词模板ID"] = "default"

    # JSON输出模式配置（新增）
    vlm_direct_output_mode: Annotated[str, "输出模式: json/markdown"] = "json"
    vlm_direct_enable_historical_ligatures: Annotated[bool, "保留历史连字符(æ,œ,ſ)"] = False
    vlm_direct_enable_marginalia: Annotated[bool, "识别边注"] = False
    vlm_direct_text_direction: Annotated[str, "文本方向: horizontal/vertical/rtl"] = "horizontal"
    vlm_direct_document_language: Annotated[str, "文档语言提示"] = ""

    # Markdown格式化配置（新增）
    vlm_direct_marginal_note_enabled: Annotated[bool, "启用边注显示"] = False
    vlm_direct_use_markdown_footnotes: Annotated[bool, "兼容旧配置：新输出固定使用Contexture脚注规范"] = False
    vlm_direct_footnote_backlink: Annotated[bool, "兼容旧配置：新输出不再生成HTML脚注回链"] = False

    # 图像处理配置
    vlm_direct_image_format: Annotated[str, "图像格式: jpeg, png, webp"] = "png"
    vlm_direct_max_image_dimension: Annotated[int, "图像最大边长（像素，0=不缩放）"] = 0
    vlm_direct_jpeg_quality: Annotated[int, "JPEG 压缩质量 (1-100)"] = 90

    # API 调用配置
    vlm_direct_timeout: Annotated[int, "单次读取超时（秒），120秒内无新数据包则超时"] = 120
    vlm_direct_max_tokens: Annotated[int, "最大输出 token 数（0=不限制）"] = 0
    vlm_direct_max_retries: Annotated[int, "最大重试次数"] = 3
    vlm_direct_json_safe_max_tokens: Annotated[int, "JSON模式安全最大输出token"] = 4096
    vlm_direct_allow_empty_api_key: Annotated[bool, "允许在本地重渲染等场景下不提供 API Key"] = True

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

    # 输出格式配置（Phase 3新增）
    vlm_direct_output_format: Annotated[str, "输出格式: markdown/html/json"] = "markdown"

    # 后处理配置
    vlm_direct_disable_postprocess: Annotated[bool, "禁用后处理（信任VLM原始输出）"] = False
    vlm_direct_streaming_batches: Annotated[bool, "按页并发数流式渲染/请求"] = True
    vlm_direct_checkpoint_dir: Annotated[str | None, "VLM中途checkpoint目录"] = None
    vlm_direct_checkpoint_name: Annotated[str | None, "VLM中途checkpoint文件名"] = None
    vlm_direct_resume_checkpoint: Annotated[bool, "从checkpoint恢复已成功页面"] = True
    vlm_auto_repair_failed_pages: Annotated[bool, "转换结束前自动低并发补跑失败页"] = False
    vlm_repair_max_concurrent: Annotated[int, "失败页补跑并发数"] = 2
    vlm_repair_rounds: Annotated[int, "失败页补跑轮数"] = 2

    # 提示词模板配置（新增）
    vlm_direct_prompt_template: Annotated[str, "提示词模板名称"] = "modern_publication"
    vlm_direct_prompt_params: Annotated[dict, "自定义模板参数"] = {}
    vlm_direct_api_preset: Annotated[str, "API 参数预设"] = "high_accuracy"

    # API 参数配置（新增）
    vlm_direct_temperature: Annotated[float, "Temperature (0.0-1.0)"] = 0.0
    vlm_direct_top_p: Annotated[float, "Top P (0.0-1.0)"] = 0.1
    vlm_direct_top_k: Annotated[int | None, "Top K"] = None
    vlm_direct_disable_thinking: Annotated[bool, "Disable thinking/reasoning mode when supported"] = True

    def __init__(self, config: Optional[dict] = None, *, progress_callback: Callable[[dict[str, Any]], None] | None = None):
        super().__init__(config)
        config = config or {}
        self.progress_callback = progress_callback

        # 🆕 API 提供商配置
        self.api_provider = config.get("vlm_api_provider", "openai_compatible")

        # 加载配置
        self.base_url = config.get("vlm_direct_base_url", self.vlm_direct_base_url)
        self.model = config.get("vlm_direct_model", self.vlm_direct_model)
        self.api_key = config.get("vlm_direct_api_key", self.vlm_direct_api_key)

        self.prompt = config.get("vlm_direct_prompt", self.vlm_direct_prompt)

        # JSON输出模式配置
        self.output_mode = config.get("vlm_direct_output_mode", "json")
        self.output_format = config.get("vlm_direct_output_format", "markdown")
        self.enable_historical_ligatures = config.get("vlm_direct_enable_historical_ligatures", False)
        self.enable_marginalia = config.get("vlm_direct_enable_marginalia", False)
        self.text_direction = config.get("vlm_direct_text_direction", "horizontal")
        self.document_language = config.get("vlm_direct_document_language", "")

        self.image_format = config.get("vlm_direct_image_format", self.vlm_direct_image_format)
        self.max_image_dimension = int(config.get("vlm_direct_max_image_dimension", self.vlm_direct_max_image_dimension))
        self.jpeg_quality = int(config.get("vlm_direct_jpeg_quality", self.vlm_direct_jpeg_quality))

        self.timeout = int(config.get("vlm_direct_timeout", self.vlm_direct_timeout))
        self.max_tokens = int(config.get("vlm_direct_max_tokens", self.vlm_direct_max_tokens))
        self.max_retries = int(config.get("vlm_direct_max_retries", self.vlm_direct_max_retries))
        self.json_safe_max_tokens = int(
            config.get("vlm_direct_json_safe_max_tokens", self.vlm_direct_json_safe_max_tokens)
        )
        self.allow_empty_api_key = bool(
            config.get("vlm_direct_allow_empty_api_key", self.vlm_direct_allow_empty_api_key)
        )

        self.max_concurrent = int(config.get("vlm_direct_max_concurrent", self.vlm_direct_max_concurrent))

        # 多格式输出配置（新增）
        self.final_output_formats = config.get("final_output_formats", ["markdown"])
        logger.info(f"[VlmDirectAsyncConverter] Output formats: {self.final_output_formats}")

        # 后处理配置
        self.disable_postprocess = config.get("vlm_direct_disable_postprocess", self.vlm_direct_disable_postprocess)
        self.footnote_fix_enabled = bool(config.get("vlm_footnote_fix", False))
        self.hyphenation_fix_enabled = bool(config.get("vlm_hyphenation_fix", False))
        self.streaming_batches = bool(config.get("vlm_direct_streaming_batches", True))
        self.resume_checkpoint = bool(config.get("vlm_direct_resume_checkpoint", True))
        self.checkpoint_dir = config.get("vlm_direct_checkpoint_dir", self.vlm_direct_checkpoint_dir)
        self.checkpoint_name = config.get("vlm_direct_checkpoint_name", self.vlm_direct_checkpoint_name)
        self.auto_repair_failed_pages = bool(
            config.get("vlm_auto_repair_failed_pages", self.vlm_auto_repair_failed_pages)
        )
        self.repair_max_concurrent = max(1, int(config.get("vlm_repair_max_concurrent", self.vlm_repair_max_concurrent)))
        self.repair_rounds = max(0, int(config.get("vlm_repair_rounds", self.vlm_repair_rounds)))

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

        # 初始化 API Key Pool；本地重渲染/无认证服务允许空 key
        self.key_pool = None
        if self.api_key:
            self.key_pool = APIKeyPool(self.api_key)
            if self.key_pool.get_key_count() > 1:
                logger.info(f"[VlmDirectAsyncConverter] Using {self.key_pool.get_key_count()} API keys with concurrent pool")
        elif not self.allow_empty_api_key:
            raise ValueError("At least one API key is required")
        else:
            logger.info("[VlmDirectAsyncConverter] No API key configured; auth headers will be omitted")

        # 初始化提示词模板管理器（保留用于自定义模板/回退）
        from aih_contexture.prompts.manager import PromptTemplateManager
        from aih_contexture.prompts.builder import PromptBuilder

        self.template_manager = PromptTemplateManager()
        self.prompt_builder = PromptBuilder()
        self.prompt_params = config.get("vlm_direct_prompt_params", self.vlm_direct_prompt_params) or {}

        # 确定最终使用的 prompt
        custom_prompt = config.get("vlm_direct_prompt", self.vlm_direct_prompt)
        template_id = config.get("vlm_direct_prompt_template", self.vlm_direct_prompt_template)

        if custom_prompt and custom_prompt.strip():
            # 优先使用自定义提示词
            self.prompt = custom_prompt
            logger.info(f"[VlmDirectAsyncConverter] Using custom prompt")
        else:
            self.prompt = self._build_prompt_from_template(template_id)
            logger.info(f"[VlmDirectAsyncConverter] Using generated prompt from template: {template_id}")

        # API 参数配置
        preset_name = config.get("vlm_direct_api_preset", self.vlm_direct_api_preset)
        preset_params = {}
        try:
            preset_params = self.prompt_builder.from_preset(preset_name)
        except Exception:
            if preset_name and preset_name != "custom":
                logger.warning(f"[VlmDirectAsyncConverter] Unknown API preset ignored: {preset_name}")

        self.api_params = {
            "temperature": float(config.get("vlm_direct_temperature", preset_params.get("temperature", 0.0))),
            "top_p": float(config.get("vlm_direct_top_p", preset_params.get("top_p", 0.1))),
        }
        top_k = config.get("vlm_direct_top_k", preset_params.get("top_k"))
        if top_k is not None:
            self.api_params["top_k"] = int(top_k)
        self.disable_thinking = bool(config.get("vlm_direct_disable_thinking", self.vlm_direct_disable_thinking))

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

        # 初始化多格式存储变量（新增）
        self._last_json_pages = None      # JSON格式页面
        self._last_clean_html_pages = None  # HTML格式页面
        self._last_markdown_pages = None   # Markdown格式页面（带锚点）
        self._last_page_results = None
        self._last_json_diagnostics = None
        self._last_response_metadata = []

        logger.info(f"[VlmDirectAsyncConverter] Init: base_url={self.base_url}, model={self.model}")
        logger.info(f"[VlmDirectAsyncConverter] Concurrent: max_concurrent={self.max_concurrent}")
        logger.info(f"[VlmDirectAsyncConverter] Image: format={self.image_format}, max_dim={self.max_image_dimension}")
        if self.use_markdown_builder:
            logger.info(f"[VlmDirectAsyncConverter] Markdown builder enabled, renderer={self.renderer_path}")

    def _build_prompt_from_template(self, template_id: str) -> str:
        params = dict(self.prompt_params or {})
        enable_marginalia = params.pop("enable_marginalia", None)

        try:
            prompt_template = self.prompt_builder.from_template(template_id)
        except Exception:
            fallback_prompt = self.template_manager.get_template(template_id)
            logger.warning(f"[VlmDirectAsyncConverter] Falling back to static template for: {template_id}")
            return self._append_runtime_prompt_controls(fallback_prompt, self.prompt_params or {})

        for key, value in params.items():
            if key == "primary_language" and value == "auto":
                continue
            if hasattr(prompt_template, key):
                setattr(prompt_template, key, value)

        special_features = list(getattr(prompt_template, "special_features", []) or [])
        if enable_marginalia is True and "marginal_notes" not in special_features:
            special_features.append("marginal_notes")
        elif enable_marginalia is False:
            special_features = [feature for feature in special_features if feature != "marginal_notes"]
        prompt_template.special_features = special_features

        return prompt_template.build_prompt()

    def _append_runtime_prompt_controls(self, prompt: str, params: dict) -> str:
        """Append UI switch instructions to static/custom template presets.

        Static UI presets are plain prompt strings, so they cannot consume the
        VlmPromptTemplate fields directly. This section keeps those switches real
        without changing the user's selected template text.
        """
        if not params:
            return prompt

        controls = [
            "## Runtime Controls",
            "- These runtime controls override conflicting template examples or older label lists.",
            "- Output ONLY one valid JSON object. Do not include markdown fences, emojis, emoticons, uncertainty tags, or commentary.",
        ]

        text_direction = params.get("text_direction")
        if text_direction == "vertical":
            controls.append("- Text direction: vertical; read right-to-left, top-to-bottom, then transcribe in reading order.")
        elif text_direction == "mixed":
            controls.append("- Text direction: mixed; detect horizontal/vertical regions and transcribe each in reading order.")

        primary_language = params.get("primary_language")
        if primary_language and primary_language != "auto":
            controls.append(f"- Primary language hint: {primary_language}; preserve original spelling and characters exactly.")

        handwriting_mode = params.get("handwriting_mode")
        if handwriting_mode == "mixed":
            controls.append("- Handwriting: transcribe visible handwritten notes and mark every handwritten span as `**[handwritten]** content` inside the text field.")
            controls.append("- Handwriting in margins: when marginalia recognition is enabled, keep handwritten side notes as separate Marginal-Note-Left/Right/Top/Bottom regions; do not merge them into printed body text.")
        elif handwriting_mode == "none":
            controls.append("- Handwriting: ignore handwritten content entirely. Do not transcribe pencil notes, manuscript marginalia, signatures, reader annotations, or any `**[handwritten]**` / `**[手写]**` spans.")

        if params.get("extract_bboxes") is False:
            controls.append("- Bboxes: set every `bbox` field to null.")
        elif params.get("extract_bboxes") is True:
            controls.append("- Bboxes: estimate visible region coordinates as `[x0, y0, x1, y1]` in image pixels; use null when uncertain.")

        if params.get("include_confidence") is False:
            controls.append("- Confidence: set every `confidence` field to null.")
        elif params.get("include_confidence") is True:
            controls.append("- Confidence: include only conservative approximate values from 0.0 to 1.0; use null when uncertain.")

        if params.get("anti_hallucination", True):
            controls.append("- Anti-hallucination: include only visible content; use null or empty strings instead of guessing missing text, labels, page numbers, captions, or coordinates.")

        if params.get("may_have_page_numbers") is True:
            controls.append("- Page numbers: extract visible printed page numbers into `printed_page_number` and/or Page-Header/Page-Footer regions.")
        elif params.get("may_have_page_numbers") is False:
            controls.append("- Page numbers: do not invent printed page numbers; use null if no visible page number exists.")

        if params.get("may_have_footnotes") is True:
            controls.append('- Footnotes: output bottom footnotes as separate regions with label "Footnote".')
        elif params.get("may_have_footnotes") is False:
            controls.append("- Footnotes: do not force footnote regions unless the page clearly contains them.")

        if params.get("enable_marginalia") is True:
            if handwriting_mode == "mixed":
                controls.append('- Marginalia: separate all side/top/bottom notes from body text, including printed side references, glosses, scholarly notes, and handwritten marginal notes. Use exactly "Marginal-Note-Left", "Marginal-Note-Right", "Marginal-Note-Top", or "Marginal-Note-Bottom".')
                controls.append("- Marginalia + handwriting: if the marginal note is handwritten, keep the Marginal-Note-* label and mark its text with `**[handwritten]**`.")
            else:
                controls.append('- Marginalia: separate printed/typographic side/top/bottom notes from body text, including printed side references, glosses, and scholarly notes. Use exactly "Marginal-Note-Left", "Marginal-Note-Right", "Marginal-Note-Top", or "Marginal-Note-Bottom".')
                controls.append("- Marginalia + handwriting off: ignore handwritten marks, but do not ignore nearby printed marginalia or printed side references.")
            controls.append("- Marginalia: do not merge marginal notes into nearby paragraphs; do not label running headers, page numbers, or ordinary footnotes as marginal notes.")
        elif params.get("enable_marginalia") is False:
            controls.append("- Marginalia: do not use Marginal-Note labels; transcribe visible side text as Text unless it is clearly a Footnote.")

        if params.get("describe_images") is True:
            controls.append("- Figures/images: describe only explicit non-text visual content such as photos, stamps, diagrams, maps, or illustrations.")
        elif params.get("describe_images") is False:
            controls.append("- Figures/images: do not invent image descriptions; use visible captions as Caption regions, otherwise leave Figure text empty.")

        if params.get("enhance_tables_equations") is True:
            controls.append("- Tables/equations: preserve tables and standalone formulas structurally when visible.")
        elif params.get("enhance_tables_equations") is False:
            controls.append("- Tables/equations: do not force table or equation structure when uncertain; use Text regions instead.")

        return f"{prompt.rstrip()}\n\n" + "\n".join(controls)

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

    def _apply_noise_patterns(self, text: str) -> str:
        if not text or not self.config.get("vlm_noise_removal", False):
            return text

        patterns = self.config.get("vlm_noise_patterns", "") or ""
        cleaned = text
        for pattern in [p.strip() for p in str(patterns).splitlines() if p.strip()]:
            try:
                cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.MULTILINE)
            except re.error:
                logger.warning(f"[VlmDirectAsyncConverter] Invalid noise regex skipped: {pattern}")
        return cleaned.strip()

    def _filter_page_markup(self, text: str) -> str:
        if not text:
            return text

        cleaned = text
        if self.config.get("vlm_filter_page_header", False):
            cleaned = re.sub(r"<!--\s*(?:PageHeader|page-header):\s*(.*?)\s*-->", r"\1", cleaned)
        if self.config.get("vlm_filter_page_footer", False):
            cleaned = re.sub(r"<!--\s*(?:PageFooter|page-footer):\s*(.*?)\s*-->", r"\1", cleaned)
        if self.config.get("vlm_filter_margin_notes", False):
            cleaned = strip_margin_comment_markers(cleaned)
        return cleaned.strip()

    def _fix_unicode_superscript_footnotes(self, markdown_pages: List[str]) -> List[str]:
        """Convert leading Unicode superscript footnote markers to HTML sup tags."""
        superscript_map = {
            "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5",
            "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9", "⁰": "0",
        }
        fixed = []
        for page in markdown_pages:
            for sup_char, normal_char in superscript_map.items():
                page = re.sub(
                    rf"(?m)^(\s*){re.escape(sup_char)}\)",
                    rf"\1<sup>{normal_char})</sup>",
                    page,
                )
            fixed.append(page)
        return fixed

    def _fix_hyphenation(self, markdown_pages: List[str]) -> List[str]:
        """Merge common OCR/VLM line breaks and end-of-line hyphenation."""
        fixed = []
        for page in markdown_pages:
            page = re.sub(r"(?<=\w)-\s*\r?\n\s*(?=\w)", "", page)
            page = re.sub(r" +\r?\n", " ", page)
            fixed.append(page)
        return fixed

    def _postprocess_markdown_pages(self, pages: List[str]) -> List[str]:
        processed_pages = []
        for page in pages:
            page_text = self._apply_noise_patterns(page)
            page_text = self._filter_page_markup(page_text)
            processed_pages.append(page_text)
        if self.footnote_fix_enabled:
            processed_pages = self._fix_unicode_superscript_footnotes(processed_pages)
        if self.hyphenation_fix_enabled:
            processed_pages = self._fix_hyphenation(processed_pages)
        return processed_pages

    def _is_json_mode(self) -> bool:
        return self.output_mode == "json"

    def _effective_max_tokens(self) -> int:
        api_max_tokens = None
        if hasattr(self, "api_params") and self.api_params:
            api_max_tokens = self.api_params.get("max_tokens")
            if api_max_tokens is not None:
                try:
                    api_max_tokens = int(api_max_tokens)
                except (TypeError, ValueError):
                    api_max_tokens = None

        if api_max_tokens and api_max_tokens > 0:
            return api_max_tokens

        if self.max_tokens > 0:
            return self.max_tokens

        if self._is_json_mode():
            return self.json_safe_max_tokens

        return 8192

    def _supports_gemini_native_json_constraints(self) -> bool:
        base_url_lower = (self.base_url or "").lower()
        return "generativelanguage.googleapis.com" in base_url_lower

    def _apply_openai_thinking_off(self, payload: dict):
        if not self.disable_thinking:
            return
        payload["chat_template_kwargs"] = {"enable_thinking": False}
        payload["enable_thinking"] = False
        payload["thinking"] = {"type": "disabled"}

    def _apply_gemini_thinking_off(self, generation_config: dict):
        if self.disable_thinking:
            generation_config["thinkingConfig"] = {"thinkingBudget": 0}

    def _apply_anthropic_thinking_off(self, payload: dict):
        if self.disable_thinking:
            payload["thinking"] = {"type": "disabled"}

    def _sanitize_openai_payload_metadata(self, payload: dict, page_num: int) -> dict:
        metadata = {
            "page_number": page_num,
            "provider": "openai",
            "model": payload.get("model"),
            "temperature": payload.get("temperature"),
            "top_p": payload.get("top_p"),
            "top_k": payload.get("top_k"),
            "max_tokens": payload.get("max_tokens"),
            "response_format": payload.get("response_format"),
            "thinking": payload.get("thinking"),
            "enable_thinking": payload.get("enable_thinking"),
            "chat_template_kwargs": payload.get("chat_template_kwargs"),
        }
        messages = payload.get("messages") or []
        if messages:
            content = messages[0].get("content") if isinstance(messages[0], dict) else None
            if isinstance(content, list):
                image_parts = [part for part in content if isinstance(part, dict) and part.get("type") == "image_url"]
                text_parts = [part for part in content if isinstance(part, dict) and part.get("type") == "text"]
                metadata["image_part_count"] = len(image_parts)
                metadata["prompt_chars"] = sum(len(part.get("text") or "") for part in text_parts)
                if image_parts:
                    url = ((image_parts[0].get("image_url") or {}).get("url") or "")
                    metadata["image_data_url_chars"] = len(url)
                    metadata["image_mime"] = url.split(";", 1)[0].replace("data:", "") if url.startswith("data:") else None
        return metadata

    def _record_response_metadata(self, metadata: dict):
        if not isinstance(self._last_response_metadata, list):
            self._last_response_metadata = []
        self._last_response_metadata.append(metadata)

    def _acquire_api_key(self) -> str | None:
        if self.key_pool is None:
            return None
        return self.key_pool.acquire()

    def _mark_api_key_success(self, key: str | None) -> None:
        if key is not None and self.key_pool is not None:
            self.key_pool.mark_success(key)

    def _mark_api_key_failure(self, key: str | None) -> None:
        if key is not None and self.key_pool is not None:
            self.key_pool.mark_failure(key)

    def _finalize_page_output(self, text: str) -> str:
        text = (text or "").strip()
        if self._is_json_mode():
            return text
        if not self.disable_postprocess:
            return self._clean_markdown_output(text)
        return text

    def _log_and_validate_finish_reason(
        self,
        provider: str,
        finish_reason: str,
        page_num: int,
        completion_tokens,
    ) -> bool:
        valid_reasons = {
            "openai": {"stop"},
            "gemini": {"STOP"},
            "anthropic": {"end_turn", "stop_sequence"},
        }
        ok = finish_reason in valid_reasons.get(provider, set())

        if ok:
            logger.info(
                f"[{provider}] Page {page_num}: finish_reason={finish_reason}, tokens={completion_tokens}"
            )
            return False

        logger.warning(
            f"[{provider}] Page {page_num}: non-terminal finish_reason={finish_reason}, tokens={completion_tokens}"
        )
        if self._is_json_mode():
            return True
        return False

    def _is_likely_html_error(self, text: str) -> bool:
        if not text or not text.strip():
            return False

        lowered = text.strip().lower()
        html_markers = [
            "<!doctype html",
            "<html",
            "<head",
            "<body",
            "cloudflare",
            "bad gateway",
            "502 bad gateway",
            "error 502",
            "nginx",
        ]
        return any(marker in lowered for marker in html_markers)

    def _build_error_page_text(self, page_num: int, detail: str) -> str:
        return f"<!-- Error converting page {page_num}: {detail} -->"

    def _json_extraction_error_kind(self, text: str, error: Exception) -> tuple[str, str]:
        message = str(error)
        if not text or not text.strip():
            return "empty_response", message
        if "No JSON object" in message:
            return "no_json_produced", message
        if "Unbalanced JSON" in message:
            return "malformed_json", message
        if "No valid JSON" in message:
            return "malformed_json" if "{" in text else "no_json_produced", message
        return "malformed_json", message

    def _validate_vlm_json_shape(self, parsed) -> tuple[bool, str, Optional[str]]:
        if not isinstance(parsed, dict):
            return False, "invalid_field_types", "top-level JSON must be an object"

        required_keys = {"printed_page_number", "page_width", "page_height", "regions"}
        missing = sorted(required_keys - set(parsed.keys()))
        if missing:
            return False, "missing_required_fields", f"missing required keys: {', '.join(missing)}"

        printed_page = parsed.get("printed_page_number")
        if printed_page is not None and not isinstance(printed_page, str):
            return False, "invalid_field_types", "printed_page_number must be string or null"

        if not isinstance(parsed.get("page_width"), (int, float)):
            return False, "invalid_field_types", "page_width must be numeric"
        if not isinstance(parsed.get("page_height"), (int, float)):
            return False, "invalid_field_types", "page_height must be numeric"

        regions = parsed.get("regions")
        if not isinstance(regions, list):
            return False, "invalid_field_types", "regions must be a list"

        for idx, region in enumerate(regions):
            if not isinstance(region, dict):
                return False, "invalid_field_types", f"regions[{idx}] must be an object"
            label = region.get("label")
            if label is not None and not isinstance(label, str):
                return False, "invalid_field_types", f"regions[{idx}].label must be a string"
            text = region.get("text")
            if text is not None and not isinstance(text, str):
                return False, "invalid_field_types", f"regions[{idx}].text must be a string"
            bbox = region.get("bbox")
            if bbox is not None:
                if not isinstance(bbox, list) or len(bbox) != 4 or not all(isinstance(v, (int, float)) for v in bbox):
                    return False, "invalid_field_types", f"regions[{idx}].bbox must be a list of 4 numbers"
            confidence = region.get("confidence")
            if confidence is not None and not isinstance(confidence, (int, float)):
                return False, "invalid_field_types", f"regions[{idx}].confidence must be numeric"

        return True, "none", None

    def _classify_page_output(
        self,
        page_num: int,
        raw_text: str,
        provider: str,
        *,
        http_status: Optional[int] = None,
        finish_reason: Optional[str] = None,
        truncated: bool = False,
        error_kind: Optional[str] = None,
    ) -> PageResult:
        raw_text = raw_text or ""
        finalized_text = self._finalize_page_output(raw_text)
        stripped = finalized_text.strip()

        if http_status is not None and http_status >= 400:
            detail = error_kind or f"upstream_http ({http_status})"
            content_kind = "html_error" if self._is_likely_html_error(raw_text) else "unknown"
            return PageResult(
                page_num=page_num,
                ok=False,
                raw_text=raw_text,
                cleaned_text=self._build_error_page_text(page_num, detail),
                content_kind=content_kind,
                error_kind=error_kind or "upstream_http",
                http_status=http_status,
                finish_reason=finish_reason,
                truncated=truncated,
                provider=provider,
                parse_stage="request",
                parse_detail=detail,
            )

        if not stripped:
            detail = error_kind or ("truncated_response" if truncated else "empty_response")
            return PageResult(
                page_num=page_num,
                ok=False,
                raw_text=raw_text,
                cleaned_text=self._build_error_page_text(page_num, detail),
                content_kind="empty",
                error_kind=detail,
                http_status=http_status,
                finish_reason=finish_reason,
                truncated=truncated,
                provider=provider,
                parse_stage="extract",
                parse_detail=detail,
            )

        if self._is_likely_html_error(stripped):
            detail = error_kind or "html_error"
            return PageResult(
                page_num=page_num,
                ok=False,
                raw_text=raw_text,
                cleaned_text=self._build_error_page_text(page_num, detail),
                content_kind="html_error",
                error_kind=detail,
                http_status=http_status,
                finish_reason=finish_reason,
                truncated=truncated,
                provider=provider,
                parse_stage="extract",
                parse_detail=detail,
            )

        if self._is_json_mode():
            try:
                json_str = self._extract_json_from_output(stripped)
            except Exception as e:
                detail, parse_detail = self._json_extraction_error_kind(stripped, e)
                if truncated:
                    detail = error_kind or "truncated_response"
                return PageResult(
                    page_num=page_num,
                    ok=False,
                    raw_text=raw_text,
                    cleaned_text=self._build_error_page_text(page_num, detail),
                    content_kind="unknown",
                    error_kind=detail,
                    http_status=http_status,
                    finish_reason=finish_reason,
                    truncated=truncated,
                    provider=provider,
                    parse_stage="extract",
                    parse_detail=parse_detail,
                )

            try:
                parsed = json.loads(json_str)
            except json.JSONDecodeError as e:
                detail = error_kind or ("truncated_response" if truncated else "malformed_json")
                return PageResult(
                    page_num=page_num,
                    ok=False,
                    raw_text=raw_text,
                    cleaned_text=self._build_error_page_text(page_num, detail),
                    content_kind="unknown",
                    error_kind=detail,
                    http_status=http_status,
                    finish_reason=finish_reason,
                    truncated=truncated,
                    provider=provider,
                    parse_stage="json_decode",
                    parse_detail=str(e),
                    raw_json_text=json_str,
                )

            valid_shape, shape_error, shape_detail = self._validate_vlm_json_shape(parsed)
            if not valid_shape:
                detail = error_kind or ("truncated_response" if truncated else shape_error)
                parse_stage = "schema_required" if shape_error == "missing_required_fields" else "schema_types"
                return PageResult(
                    page_num=page_num,
                    ok=False,
                    raw_text=raw_text,
                    cleaned_text=self._build_error_page_text(page_num, detail),
                    content_kind="unknown",
                    error_kind=detail,
                    http_status=http_status,
                    finish_reason=finish_reason,
                    truncated=truncated,
                    provider=provider,
                    parse_stage=parse_stage,
                    parse_detail=shape_detail,
                    raw_json_text=json_str,
                )

            detail = "truncated_response" if truncated else "none"
            return PageResult(
                page_num=page_num,
                ok=not truncated,
                raw_text=raw_text,
                cleaned_text=json_str,
                content_kind="json",
                error_kind=detail,
                http_status=http_status,
                finish_reason=finish_reason,
                truncated=truncated,
                provider=provider,
                parse_stage="none" if not truncated else "finish_reason",
                parse_detail="response did not finish naturally" if truncated else None,
                raw_json_text=json_str,
            )

        return PageResult(
            page_num=page_num,
            ok=not truncated,
            raw_text=raw_text,
            cleaned_text=finalized_text if not truncated else self._build_error_page_text(page_num, "truncated"),
            content_kind="markdown" if stripped else "empty",
            error_kind="truncated" if truncated else "none",
            http_status=http_status,
            finish_reason=finish_reason,
            truncated=truncated,
            provider=provider,
        )

    def _error_page_result(
        self,
        page_num: int,
        provider: str,
        error_message: str,
        *,
        http_status: Optional[int] = None,
        finish_reason: Optional[str] = None,
        truncated: bool = False,
        raw_text: str = "",
        content_kind: Optional[str] = None,
        error_kind: str = "retry_exhausted",
    ) -> PageResult:
        return PageResult(
            page_num=page_num,
            ok=False,
            raw_text=raw_text,
            cleaned_text=self._build_error_page_text(page_num, error_message),
            content_kind=content_kind or ("html_error" if self._is_likely_html_error(raw_text) else "unknown"),
            error_kind=error_kind,
            http_status=http_status,
            finish_reason=finish_reason,
            truncated=truncated,
            provider=provider,
            parse_stage="request" if error_kind in {"upstream_http", "retry_exhausted"} else "none",
            parse_detail=str(error_message),
        )

    def _page_result_diagnostic(self, page_result: PageResult) -> dict:
        return {
            "page_number": page_result.page_num,
            "ok": page_result.ok,
            "content_kind": page_result.content_kind,
            "error_kind": page_result.error_kind,
            "parse_stage": page_result.parse_stage,
            "parse_detail": page_result.parse_detail,
            "http_status": page_result.http_status,
            "finish_reason": page_result.finish_reason,
            "truncated": page_result.truncated,
            "provider": page_result.provider,
            "raw_text_length": len(page_result.raw_text or ""),
            "json_text_length": len(page_result.raw_json_text or ""),
        }

    def _build_error_json_page(self, page_num: int, error_message: str, page_result: Optional[PageResult] = None) -> str:
        error_payload = {
            "error": str(error_message),
            "page_number": page_num,
            "printed_page_number": None,
            "page_width": 0,
            "page_height": 0,
            "regions": [],
        }
        if page_result is not None:
            error_payload["diagnostic"] = self._page_result_diagnostic(page_result)
        return json.dumps(error_payload, ensure_ascii=False)

    def _validate_json_page_output(self, provider: str, page_num: int, page_text: str) -> None:
        """JSON 模式下，确保单页输出可提取为有效 JSON 对象。"""
        if not self._is_json_mode():
            return
        result = self._classify_page_output(page_num, page_text, provider)
        if not result.ok or result.content_kind != "json":
            raise ValueError(
                f"{provider} response is not valid JSON on page {page_num}: {result.error_kind}"
            )

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
            # 尝试匹配普通 ``` 代码块（含语言标记如 ```json）
            match = re.search(r'```(\w+)?\s*\n?(.*?)\s*```', text, re.DOTALL)
            if match:
                text = match.group(2).strip()
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

    def _extract_balanced_json_object(self, text: str, start: int) -> str:
        depth = 0
        in_string = False
        escape = False

        for idx in range(start, len(text)):
            char = text[idx]

            if escape:
                escape = False
                continue

            if char == "\\" and in_string:
                escape = True
                continue

            if char == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : idx + 1]

        raise ValueError("Unbalanced JSON object in model output")

    def _extract_first_json_object(self, text: str) -> str:
        starts = [idx for idx, ch in enumerate(text) if ch == "{"]
        if not starts:
            raise ValueError("No JSON object found in model output")

        for start in starts:
            try:
                candidate = self._extract_balanced_json_object(text, start)
            except ValueError:
                continue

            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue

            if isinstance(parsed, dict):
                return candidate

        raise ValueError("No valid JSON object found in model output")

    def _extract_json_from_output(self, text: str) -> str:
        """从VLM输出中提取并验证JSON

        Args:
            text: VLM原始输出

        Returns:
            纯JSON字符串
        """
        if not text or not text.strip():
            raise ValueError("Empty model output")

        candidates = []
        stripped = text.strip()

        match = re.search(r"```(?:json)?\s*\n?(.*?)\s*```", stripped, re.DOTALL)
        if match:
            candidates.append(match.group(1).strip())

        candidates.append(stripped)

        for candidate in candidates:
            if candidate.startswith("json"):
                candidate = candidate[4:].lstrip()

            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass

            try:
                extracted = self._extract_first_json_object(candidate)
                logger.info(f"[Extract] Extracted balanced JSON object ({len(extracted)} chars)")
                return extracted
            except ValueError:
                continue

        raise ValueError("No valid JSON object found in model output")

    def _get_json_format_config(self) -> dict:
        return {
            "vlm_direct_marginal_note_enabled": self.config.get("vlm_direct_marginal_note_enabled", False),
            "vlm_direct_use_markdown_footnotes": self.config.get("vlm_direct_use_markdown_footnotes", False),
            "vlm_direct_footnote_backlink": self.config.get("vlm_direct_footnote_backlink", False),
            "vlm_filter_margin_notes": self.config.get("vlm_filter_margin_notes", False),
            "vlm_direct_handwriting_mode": (self.prompt_params or {}).get("handwriting_mode", "none"),
        }

    def _process_json_outputs(self, raw_outputs: List[str | PageResult]) -> tuple[List[str], List[Optional[str]], List[str]]:
        from aih_contexture.utils.vlm_json_output import parse_json_to_markdown

        json_pages = []
        markdown_pages = []
        printed_pages = []
        diagnostics = []
        page_results = []
        format_config = self._get_json_format_config()

        for page_num, raw_output in enumerate(raw_outputs, start=1):
            page_result = raw_output if isinstance(raw_output, PageResult) else self._classify_page_output(page_num, raw_output, self.api_provider)
            page_results.append(page_result)

            if page_result.content_kind != "json":
                logger.error(
                    f"[VlmDirectAsyncConverter] Page {page_num} has no usable JSON: {page_result.error_kind} ({page_result.parse_detail})"
                )
                json_pages.append(self._build_error_json_page(page_num, page_result.error_kind, page_result))
                markdown_pages.append(f"<!-- Error parsing page {page_num}: {page_result.error_kind} -->")
                printed_pages.append(None)
                diagnostics.append(self._page_result_diagnostic(page_result))
                continue

            json_str = page_result.cleaned_text
            try:
                markdown, printed_page = parse_json_to_markdown(json_str, format_config)
            except Exception as e:
                logger.error(f"[VlmDirectAsyncConverter] Failed to convert JSON to Markdown for page {page_num}: {e}")
                failed_result = PageResult(
                    page_num=page_result.page_num,
                    ok=False,
                    raw_text=page_result.raw_text,
                    cleaned_text=page_result.cleaned_text,
                    content_kind="json",
                    error_kind="json_markdown_parse_error",
                    http_status=page_result.http_status,
                    finish_reason=page_result.finish_reason,
                    truncated=page_result.truncated,
                    provider=page_result.provider,
                    parse_stage="markdown_conversion",
                    parse_detail=str(e),
                    raw_json_text=page_result.raw_json_text or json_str,
                )
                json_pages.append(self._build_error_json_page(page_num, str(e), failed_result))
                markdown_pages.append(f"<!-- Error parsing page {page_num}: json_markdown_parse_error -->")
                printed_pages.append(None)
                diagnostics.append(self._page_result_diagnostic(failed_result))
            else:
                json_pages.append(json_str)
                markdown_pages.append(markdown)
                printed_pages.append(printed_page)
                diagnostics.append(self._page_result_diagnostic(page_result))

        self._last_json_pages = json_pages
        self._last_page_results = page_results
        self._last_json_diagnostics = diagnostics
        logger.info(f"[VlmDirectAsyncConverter] JSON mode: parsed {len(markdown_pages)} pages")
        logger.info(f"[VlmDirectAsyncConverter] Stored {len(json_pages)} JSON pages")
        return markdown_pages, printed_pages, json_pages

    def _failed_page_nums(self, page_results: List[PageResult]) -> list[int]:
        return [
            int(result.page_num)
            for result in page_results
            if not result.ok or result.content_kind != "json"
        ]

    def _prepare_markdown_pages(
        self,
        raw_outputs: List[str | PageResult],
    ) -> tuple[list[str], list[Optional[str]] | None]:
        if self.output_mode == "json":
            markdown_pages, printed_pages, _ = self._process_json_outputs(raw_outputs)
        else:
            markdown_pages = [
                result.cleaned_text if isinstance(result, PageResult) else str(result)
                for result in raw_outputs
            ]
            printed_pages = None
            logger.info(f"[VlmDirectAsyncConverter] Markdown mode: {len(markdown_pages)} pages")
        return markdown_pages, printed_pages

    def _finalize_markdown_pages(
        self,
        markdown_pages: list[str],
        printed_pages: list[Optional[str]] | None,
        page_count: int,
    ) -> str:
        self._emit_progress(event="postprocess", stage="saving")

        logger.debug("After processing: %d pages", len(markdown_pages))
        for i, page in enumerate(markdown_pages):
            logger.debug("Page %d length: %d chars", i + 1, len(page))
            if len(page) < 200:
                logger.debug("Page %d content: %s", i + 1, repr(page[:500]))

        if self.printed_page_extractor and printed_pages is None:
            logger.info(f"[VlmDirectAsyncConverter] Extracting printed pages...")
            markdown_pages, printed_pages = self.printed_page_extractor.extract_batch(markdown_pages)
            found_count = sum(1 for p in printed_pages if p is not None)
            logger.info(f"[VlmDirectAsyncConverter] Found {found_count} printed pages")

        logger.info(f"[VlmDirectAsyncConverter] Cleaning page separators...")
        markdown_pages = self._clean_page_separators(markdown_pages)
        markdown_pages = self._postprocess_markdown_pages(markdown_pages)

        if self.page_anchor_plugin.enabled:
            logger.info(f"[VlmDirectAsyncConverter] Adding page anchors...")
            markdown_pages = self.page_anchor_plugin.process_pages(markdown_pages, printed_pages)

        self._last_markdown_pages = markdown_pages
        logger.info(f"[VlmDirectAsyncConverter] Stored {len(markdown_pages)} Markdown pages")

        if "html" in self.final_output_formats:
            from aih_contexture.utils.vlm_json_output import markdown_to_html
            self._last_clean_html_pages = [markdown_to_html(page) for page in self._last_markdown_pages]
            logger.info(f"[VlmDirectAsyncConverter] Generated {len(self._last_clean_html_pages)} HTML pages")

        full_markdown = join_markdown_pages(
            markdown_pages,
            page_separator=self.page_separator,
            page_anchors_enabled=self.page_anchor_plugin.enabled,
        )

        if self.page_anchor_plugin.enabled:
            final_anchor = f"{{{page_count}}}"
            full_markdown += f"\n\n{final_anchor}\n\n{self.page_separator.strip()}"
            logger.info(f"[VlmDirectAsyncConverter] Added final anchor: {final_anchor}")

        return full_markdown

    def _resolve_image_mime(self) -> str:
        fmt = (self.image_format or "png").lower()
        if fmt in ("jpg", "jpeg"):
            return "image/jpeg"
        if fmt == "webp":
            return "image/webp"
        return "image/png"

    def _resize_if_needed(self, img: Image.Image) -> Image.Image:
        """如果图像超过最大尺寸则缩放"""
        w, h = img.size
        if self.max_image_dimension <= 0:
            return img
        if w <= self.max_image_dimension and h <= self.max_image_dimension:
            return img
        scale = min(self.max_image_dimension / w, self.max_image_dimension / h)
        new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
        return img.resize(new_size, Image.Resampling.LANCZOS)

    def _emit_progress(self, **event: Any) -> None:
        if self.progress_callback is None:
            return
        try:
            self.progress_callback(event)
        except Exception as exc:
            logger.debug(f"[VlmDirectAsyncConverter] progress callback ignored: {exc}")

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
    ) -> PageResult:
        """异步转换单个页面"""
        async with semaphore:  # 控制并发数
            logger.debug("Converting page %d", page_num)

            # 🆕 根据 API 提供商选择不同的调用方式
            if self.api_provider == "gemini":
                return await self._convert_page_gemini(session, img, page_num)
            elif self.api_provider == "anthropic":
                return await self._convert_page_anthropic(session, img, page_num)
            else:
                return await self._convert_page_openai(session, img, page_num)

    def _extract_openai_message_text(self, data: dict) -> str:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
            return "".join(parts)
        return ""

    async def _convert_page_openai(
        self,
        session: aiohttp.ClientSession,
        img: Image.Image,
        page_num: int
    ) -> PageResult:
        """使用 OpenAI 兼容 API 转换页面"""
        # 构建请求
        b64_img = self._img_to_base64(img)
        mime = self._resolve_image_mime().split("/", 1)[1]

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

        # 从 api_params 读取参数，fallback 到默认值
        _temperature = self.api_params.get('temperature', 0.0) if hasattr(self, 'api_params') else 0.0
        _top_p = self.api_params.get('top_p', 0.1) if hasattr(self, 'api_params') else 0.1
        _max_tokens = self._effective_max_tokens()

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "temperature": _temperature,
            "top_p": _top_p,
            "max_tokens": _max_tokens,
            "store": False,
        }
        if "top_k" in getattr(self, "api_params", {}):
            payload["top_k"] = self.api_params["top_k"]
        self._apply_openai_thinking_off(payload)

        # JSON输出模式：强制模型只输出JSON，自然停止
        if getattr(self, 'output_mode', 'json') == 'json':
            payload['response_format'] = {"type": "json_object"}

        request_metadata = self._sanitize_openai_payload_metadata(payload, page_num)

        if page_num == 1:
            logger.info(f"[VlmDirectAsyncConverter] OpenAI params: temperature={_temperature}, top_p={_top_p}, top_k={payload.get('top_k')}, max_tokens={_max_tokens}, json_mode={payload.get('response_format')}")

        # API 调用（带重试和Key Pool）
        last_error = None
        last_raw_text = ""
        last_http_status = None
        last_finish_reason = None
        last_truncated = False
        last_error_kind = "retry_exhausted"
        max_retries = self.max_retries

        for attempt in range(max_retries + 1):
            current_key = None
            try:
                current_key = self._acquire_api_key()
                headers = {
                    "Content-Type": "application/json",
                }
                if current_key:
                    headers["Authorization"] = f"Bearer {current_key}"

                async with session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(connect=15, sock_read=self.timeout, total=None)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        page_text = self._extract_openai_message_text(data).strip()

                        finish_reason = data["choices"][0].get("finish_reason", "unknown")
                        usage = data.get("usage", {})
                        self._record_response_metadata({
                            **request_metadata,
                            "attempt": attempt + 1,
                            "http_status": response.status,
                            "finish_reason": finish_reason,
                            "usage": usage,
                            "raw_text_length": len(page_text),
                        })
                        completion_tokens = usage.get("completion_tokens", "N/A")
                        truncated = self._log_and_validate_finish_reason(
                            "openai",
                            finish_reason,
                            page_num,
                            completion_tokens,
                        )

                        result = self._classify_page_output(
                            page_num,
                            page_text,
                            "openai",
                            http_status=response.status,
                            finish_reason=finish_reason,
                            truncated=truncated,
                        )

                        if result.ok:
                            logger.info(f"[VlmDirectAsyncConverter] Page {page_num} converted ({len(result.cleaned_text)} chars)")
                            self._mark_api_key_success(current_key)
                            return result

                        last_error = ValueError(result.error_kind)
                        last_raw_text = page_text
                        last_http_status = response.status
                        last_finish_reason = finish_reason
                        last_truncated = truncated
                        last_error_kind = result.error_kind
                        logger.warning(
                            f"[VlmDirectAsyncConverter] Invalid page {page_num}: kind={result.content_kind}, error={result.error_kind}, truncated={result.truncated}"
                        )
                        self._mark_api_key_failure(current_key)
                        if attempt < max_retries:
                            await asyncio.sleep(2 * (attempt + 1))
                            continue
                        return result

                    error_text = await response.text()
                    self._record_response_metadata({
                        **request_metadata,
                        "attempt": attempt + 1,
                        "http_status": response.status,
                        "finish_reason": None,
                        "error_text_length": len(error_text),
                    })
                    last_error = Exception(f"API error {response.status}: {error_text}")
                    last_raw_text = error_text
                    last_http_status = response.status
                    last_finish_reason = None
                    last_truncated = False
                    last_error_kind = "upstream_http"
                    logger.error(f"[VlmDirectAsyncConverter] Error on page {page_num}: {last_error}")
                    self._mark_api_key_failure(current_key)
                    if attempt < max_retries:
                        await asyncio.sleep(2 * (attempt + 1))
                        continue
                    break

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
                last_raw_text = ""
                last_http_status = None
                last_finish_reason = None
                last_truncated = False
                last_error_kind = "retry_exhausted"
                logger.warning(f"[VlmDirectAsyncConverter] Retryable error on page {page_num} (attempt {attempt + 1}): {e}")
                self._mark_api_key_failure(current_key)
                if attempt < max_retries:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue

            except Exception as e:
                last_error = e
                last_error_kind = "retry_exhausted"
                logger.error(f"[VlmDirectAsyncConverter] Error on page {page_num}: {e}")
                self._mark_api_key_failure(current_key)
                if attempt < max_retries:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                break

        logger.error(f"[VlmDirectAsyncConverter] Failed to convert page {page_num}: {last_error}")
        return self._error_page_result(
            page_num,
            "openai",
            str(last_error),
            http_status=last_http_status,
            finish_reason=last_finish_reason,
            truncated=last_truncated,
            raw_text=last_raw_text,
            error_kind=last_error_kind,
        )

    async def _convert_page_gemini(
        self,
        session: aiohttp.ClientSession,
        img: Image.Image,
        page_num: int
    ) -> PageResult:
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
            url = f"{base_url}/models/{self.model}:generateContent"
        elif base_url.endswith('/gemini') or base_url.endswith('/google'):
            url = f"{base_url}/v1beta/models/{self.model}:generateContent"
        else:
            url = f"{base_url}/v1beta/models/{self.model}:generateContent"

        payload = {
            "contents": [{
                "role": "user",
                "parts": [
                    {"inline_data": {"mime_type": self._resolve_image_mime(), "data": b64_img}},
                    {"text": self.prompt}
                ]
            }]
        }

        api_params = getattr(self, "api_params", {}) or {}
        generation_config = {}
        if 'temperature' in api_params:
            generation_config['temperature'] = api_params['temperature']
        if 'top_p' in api_params:
            generation_config['topP'] = api_params['top_p']
        if 'top_k' in api_params:
            generation_config['topK'] = api_params['top_k']
        generation_config['maxOutputTokens'] = self._effective_max_tokens()
        self._apply_gemini_thinking_off(generation_config)

        if self._is_json_mode() and self._supports_gemini_native_json_constraints():
            generation_config["responseMimeType"] = "application/json"
            generation_config["responseSchema"] = GEMINI_JSON_SCHEMA
        elif self._is_json_mode() and page_num == 1:
            logger.info("[Gemini] Native JSON constraints disabled for relay/non-official endpoint")

        if generation_config:
            payload['generationConfig'] = generation_config
            if page_num == 1:
                logger.info(f"[Gemini] generationConfig: {generation_config}")

        def extract_result(data, finish_reason, *, http_status=200):
            parts = data["candidates"][0]["content"]["parts"]
            text_parts = []
            thinking_chars = 0
            for part in parts:
                if part.get("thought", False):
                    thinking_chars += len(part.get("text", ""))
                    continue
                if "text" in part:
                    text_parts.append(part["text"])

            if thinking_chars > 0:
                logger.info(f"[Gemini] Filtered out {thinking_chars} chars of thinking content")

            page_text = "\n".join(text_parts).strip()
            usage = data.get("usageMetadata", {})
            completion_tokens = usage.get("candidatesTokenCount", "N/A")
            truncated = self._log_and_validate_finish_reason(
                "gemini",
                finish_reason,
                page_num,
                completion_tokens,
            )
            result = self._classify_page_output(
                page_num,
                page_text,
                "gemini",
                http_status=http_status,
                finish_reason=finish_reason,
                truncated=truncated,
            )
            return result, page_text, truncated

        last_error = None
        last_raw_text = ""
        last_http_status = None
        last_finish_reason = None
        last_truncated = False
        last_error_kind = "retry_exhausted"

        for attempt in range(self.max_retries + 1):
            current_key = None
            try:
                current_key = self._acquire_api_key()

                headers = {
                    "Content-Type": "application/json",
                }
                if current_key:
                    headers["Authorization"] = f"Bearer {current_key}"

                if page_num == 1 and attempt == 0:
                    logger.info(f"[Gemini] URL: {url}")
                    logger.info(f"[Gemini] Using Authorization Bearer auth")

                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(connect=15, sock_read=self.timeout, total=None)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        finish_reason = data["candidates"][0].get("finishReason", "unknown")
                        result, page_text, truncated = extract_result(data, finish_reason, http_status=response.status)

                        if result.ok:
                            logger.info(f"[Gemini] Page {page_num} converted ({len(result.cleaned_text)} chars)")
                            self._mark_api_key_success(current_key)
                            return result

                        last_error = ValueError(result.error_kind)
                        last_raw_text = page_text
                        last_http_status = response.status
                        last_finish_reason = finish_reason
                        last_truncated = truncated
                        last_error_kind = result.error_kind
                        logger.warning(
                            f"[Gemini] Invalid page {page_num}: kind={result.content_kind}, error={result.error_kind}, truncated={result.truncated}"
                        )
                        self._mark_api_key_failure(current_key)
                        if attempt < self.max_retries:
                            await asyncio.sleep(2 * (attempt + 1))
                            continue
                        return result

                    if response.status in (401, 403):
                        error_text = await response.text()
                        logger.warning(f"[Gemini] Header auth failed ({response.status}), trying query param...")

                        headers_simple = {"Content-Type": "application/json"}
                        async with session.post(
                            f"{url}?key={current_key}",
                            json=payload,
                            headers=headers_simple,
                            timeout=aiohttp.ClientTimeout(connect=15, sock_read=self.timeout, total=None)
                        ) as response2:
                            if response2.status == 200:
                                data = await response2.json()
                                finish_reason = data["candidates"][0].get("finishReason", "unknown")
                                result, page_text, truncated = extract_result(data, finish_reason, http_status=response2.status)

                                if result.ok:
                                    logger.info(f"[Gemini] Page {page_num} converted with query param auth ({len(result.cleaned_text)} chars)")
                                self._mark_api_key_success(current_key)
                                return result

                                last_error = ValueError(result.error_kind)
                                last_raw_text = page_text
                                last_http_status = response2.status
                                last_finish_reason = finish_reason
                                last_truncated = truncated
                                last_error_kind = result.error_kind
                                logger.warning(
                                    f"[Gemini] Invalid page {page_num} with query param auth: kind={result.content_kind}, error={result.error_kind}, truncated={result.truncated}"
                                )
                                self._mark_api_key_failure(current_key)
                                if attempt < self.max_retries:
                                    await asyncio.sleep(2 * (attempt + 1))
                                    continue
                                return result

                            error_text2 = await response2.text()
                            last_error = Exception(f"Gemini API error {response2.status}: {error_text2}")
                            last_raw_text = error_text2
                            last_http_status = response2.status
                            last_finish_reason = None
                            last_truncated = False
                            last_error_kind = "upstream_http"
                            logger.warning(f"[Gemini] Error on page {page_num} (attempt {attempt + 1}): {last_error}")
                            self._mark_api_key_failure(current_key)
                            if attempt < self.max_retries:
                                await asyncio.sleep(2 * (attempt + 1))
                                continue
                            break

                    error_text = await response.text()
                    last_error = Exception(f"Gemini API error {response.status}: {error_text}")
                    last_raw_text = error_text
                    last_http_status = response.status
                    last_finish_reason = None
                    last_truncated = False
                    last_error_kind = "upstream_http"
                    logger.warning(f"[Gemini] Error on page {page_num} (attempt {attempt + 1}): {last_error}")
                    self._mark_api_key_failure(current_key)
                    if attempt < self.max_retries:
                        await asyncio.sleep(2 * (attempt + 1))
                        continue
                    break

            except Exception as e:
                last_error = e
                if isinstance(e, (aiohttp.ClientError, asyncio.TimeoutError)):
                    last_error_kind = "retry_exhausted"
                logger.warning(f"[Gemini] Error on page {page_num} (attempt {attempt + 1}): {e}")
                self._mark_api_key_failure(current_key)
                if attempt < self.max_retries:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                break

        logger.error(f"[Gemini] Failed to convert page {page_num}: {last_error}")
        return self._error_page_result(
            page_num,
            "gemini",
            str(last_error),
            http_status=last_http_status,
            finish_reason=last_finish_reason,
            truncated=last_truncated,
            raw_text=last_raw_text,
            error_kind=last_error_kind,
        )

    async def _convert_page_anthropic(
        self,
        session: aiohttp.ClientSession,
        img: Image.Image,
        page_num: int
    ) -> PageResult:
        """使用 Anthropic Claude 原生 API 转换页面"""
        b64_img = self._img_to_base64(img)

        # 构建 Anthropic API 端点
        base_url = self.base_url.rstrip('/') if self.base_url else "https://api.anthropic.com"
        url = f"{base_url}/v1/messages"

        # 构建 Anthropic 请求体
        anthropic_max_tokens = self.max_tokens if self.max_tokens > 0 else 4096
        payload = {
            "model": self.model,
            "max_tokens": anthropic_max_tokens,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": self._resolve_image_mime(),
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
        self._apply_anthropic_thinking_off(payload)

        if hasattr(self, 'api_params') and self.api_params:
            if 'temperature' in self.api_params:
                payload['temperature'] = self.api_params['temperature']
            if 'top_p' in self.api_params:
                payload['top_p'] = self.api_params['top_p']

        last_error = None
        last_raw_text = ""
        last_http_status = None
        last_finish_reason = None
        last_truncated = False
        last_error_kind = "retry_exhausted"

        for attempt in range(self.max_retries + 1):
            current_key = None
            try:
                current_key = self._acquire_api_key()
                headers = {
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01"
                }
                if current_key:
                    headers["x-api-key"] = current_key

                if page_num == 1 and attempt == 0:
                    logger.info(f"[Anthropic] URL: {url}")
                    logger.info(f"[Anthropic] Model: {self.model}")

                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(connect=15, sock_read=self.timeout, total=None)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        page_text = data["content"][0]["text"].strip()
                        stop_reason = data.get("stop_reason", "unknown")
                        usage = data.get("usage", {})
                        completion_tokens = usage.get("output_tokens", "N/A")
                        truncated = self._log_and_validate_finish_reason(
                            "anthropic",
                            stop_reason,
                            page_num,
                            completion_tokens,
                        )

                        result = self._classify_page_output(
                            page_num,
                            page_text,
                            "anthropic",
                            http_status=response.status,
                            finish_reason=stop_reason,
                            truncated=truncated,
                        )

                        if result.ok:
                            logger.info(f"[Anthropic] Page {page_num} converted ({len(result.cleaned_text)} chars)")
                            self._mark_api_key_success(current_key)
                            return result

                        last_error = ValueError(result.error_kind)
                        last_raw_text = page_text
                        last_http_status = response.status
                        last_finish_reason = stop_reason
                        last_truncated = truncated
                        last_error_kind = result.error_kind
                        logger.warning(
                            f"[Anthropic] Invalid page {page_num}: kind={result.content_kind}, error={result.error_kind}, truncated={result.truncated}"
                        )
                        self._mark_api_key_failure(current_key)
                        if attempt < self.max_retries:
                            await asyncio.sleep(2 * (attempt + 1))
                            continue
                        return result

                    error_text = await response.text()
                    last_error = Exception(f"Anthropic API error {response.status}: {error_text}")
                    last_raw_text = error_text
                    last_http_status = response.status
                    last_finish_reason = None
                    last_truncated = False
                    last_error_kind = "upstream_http"
                    logger.warning(f"[Anthropic] Error on page {page_num} (attempt {attempt + 1}): {last_error}")
                    self._mark_api_key_failure(current_key)
                    if attempt < self.max_retries:
                        await asyncio.sleep(2 * (attempt + 1))
                        continue
                    break

            except Exception as e:
                last_error = e
                if isinstance(e, (aiohttp.ClientError, asyncio.TimeoutError)):
                    last_error_kind = "retry_exhausted"
                logger.warning(f"[Anthropic] Error on page {page_num} (attempt {attempt + 1}): {e}")
                self._mark_api_key_failure(current_key)
                if attempt < self.max_retries:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                break

        logger.error(f"[Anthropic] Failed to convert page {page_num}: {last_error}")
        return self._error_page_result(
            page_num,
            "anthropic",
            str(last_error),
            http_status=last_http_status,
            finish_reason=last_finish_reason,
            truncated=last_truncated,
            raw_text=last_raw_text,
            error_kind=last_error_kind,
        )

    async def _convert_page_async_no_semaphore(
        self,
        session: aiohttp.ClientSession,
        img: Image.Image,
        page_num: int
    ) -> PageResult:
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

    def _uses_strict_batch_page_scheduling(self) -> bool:
        if self.api_provider != "openai_compatible":
            return False
        base_url_lower = (self.base_url or "").lower()
        local_markers = ("localhost", "127.0.0.1", "0.0.0.0", "host.docker.internal", "lmstudio", ":1234", ":12345")
        return any(marker in base_url_lower for marker in local_markers)

    def _normalize_page_result(self, page_num: int, result) -> PageResult:
        if isinstance(result, Exception):
            logger.error(f"[VLM] Page {page_num} raised exception: {result}")
            return self._error_page_result(page_num, self.api_provider, str(result))

        if isinstance(result, PageResult):
            logger.debug(
                "Page %d result: ok=%s kind=%s error=%s len=%d",
                result.page_num, result.ok, result.content_kind, result.error_kind, len(result.cleaned_text)
            )
            return result

        logger.warning(f"[VLM] Page {page_num} returned unexpected result type: {type(result)}")
        return self._error_page_result(
            page_num,
            self.api_provider,
            f"unexpected result type: {type(result).__name__}"
        )

    def _checkpoint_path(self) -> Optional[Path]:
        if not self.checkpoint_dir or not self.checkpoint_name:
            return None
        safe_name = re.sub(r'[<>:"/\\\\|?*]+', "_", str(self.checkpoint_name)).strip() or "vlm_checkpoint"
        return Path(self.checkpoint_dir) / f"{safe_name}.vlm_checkpoint.json"

    def _load_checkpoint_results(self, total_pages: int) -> dict[int, PageResult]:
        path = self._checkpoint_path()
        if not path or not self.resume_checkpoint or not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"[VLM] Failed to read checkpoint {path}: {exc}")
            return {}

        if int(data.get("total_pages") or 0) != int(total_pages):
            logger.warning(f"[VLM] Ignoring checkpoint with mismatched total_pages: {path}")
            return {}

        loaded: dict[int, PageResult] = {}
        for item in data.get("pages", []):
            if not isinstance(item, dict):
                continue
            try:
                result = PageResult(**item)
            except TypeError:
                continue
            if result.ok:
                loaded[int(result.page_num)] = result
        if loaded:
            logger.info(f"[VLM] Loaded {len(loaded)} successful pages from checkpoint: {path}")
        return loaded

    def _save_checkpoint_results(self, total_pages: int, results_by_page: dict[int, PageResult]) -> None:
        path = self._checkpoint_path()
        if not path:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "format": "vlm_generalized_checkpoint",
                "version": 1,
                "total_pages": int(total_pages),
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "model": self.model,
                "provider": self.api_provider,
                "pages": [
                    asdict(results_by_page[page_num])
                    for page_num in sorted(results_by_page)
                ],
            }
            tmp_path = path.with_suffix(path.suffix + ".tmp")
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp_path, path)
            ok_count = sum(1 for result in results_by_page.values() if result.ok)
            logger.info(f"[VLM] Checkpoint saved: {path} ({ok_count}/{total_pages} successful pages)")
        except Exception as exc:
            logger.warning(f"[VLM] Failed to save checkpoint: {exc}")

    async def _convert_all_pages_strict_batches_async(
        self,
        images: List[Image.Image],
        page_offset: int = 0,
    ) -> List[PageResult]:
        concurrency = max(1, self.max_concurrent)
        total_pages = len(images)
        all_results: List[PageResult] = []

        async with aiohttp.ClientSession() as session:
            for batch_start in range(0, total_pages, concurrency):
                batch_end = min(batch_start + concurrency, total_pages)
                batch_images = images[batch_start:batch_end]

                logger.info(
                    f"[VLM][LM Studio] Processing batch {batch_start//concurrency + 1}: "
                    f"pages {page_offset + batch_start + 1}-{page_offset + batch_end}"
                )

                tasks = [
                    self._convert_page_async_no_semaphore(session, img, page_offset + batch_start + idx + 1)
                    for idx, img in enumerate(batch_images)
                ]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                for idx, result in enumerate(batch_results):
                    page_num = page_offset + batch_start + idx + 1
                    page_result = self._normalize_page_result(page_num, result)
                    all_results.append(page_result)
                    self._emit_progress(
                        event="page_done",
                        page_num=page_num,
                        ok=bool(page_result.ok),
                        stage="processing",
                    )

                logger.info(f"[VLM][LM Studio] Batch completed: {len(batch_results)} pages")

        all_results.sort(key=lambda x: x.page_num)
        valid_results = [result for result in all_results if result.ok]
        logger.debug("Total results: %d, Valid results: %d", len(all_results), len(valid_results))
        return all_results

    async def _convert_all_pages_sliding_window_async(
        self,
        images: List[Image.Image],
        global_semaphore: Optional[asyncio.Semaphore] = None,
        page_offset: int = 0,
    ) -> List[PageResult]:
        concurrency = max(1, self.max_concurrent)
        total_pages = len(images)
        results: List[Optional[PageResult]] = [None] * total_pages
        local_semaphore = asyncio.Semaphore(concurrency)

        async def run_page(session: aiohttp.ClientSession, idx: int, img: Image.Image):
            page_num = page_offset + idx + 1
            semaphore = global_semaphore or local_semaphore
            async with semaphore:
                try:
                    result = await self._convert_page_async_no_semaphore(session, img, page_num)
                except Exception as e:
                    result = e
            page_result = self._normalize_page_result(page_num, result)
            results[idx] = page_result
            self._emit_progress(
                event="page_done",
                page_num=page_num,
                ok=bool(page_result.ok),
                stage="processing",
            )

        async with aiohttp.ClientSession() as session:
            logger.info(f"[VLM] Processing {total_pages} pages with sliding-window concurrency={concurrency}")
            tasks = [
                asyncio.create_task(run_page(session, idx, img))
                for idx, img in enumerate(images)
            ]

            for task in asyncio.as_completed(tasks):
                await task

        ordered_results = [
            result if result is not None else self._error_page_result(
                page_offset + idx + 1,
                self.api_provider,
                "missing page result"
            )
            for idx, result in enumerate(results)
        ]
        valid_results = [result for result in ordered_results if result.ok]
        logger.debug("Total results: %d, Valid results: %d", len(ordered_results), len(valid_results))
        return ordered_results

    async def _convert_all_pages_async(
        self,
        images: List[Image.Image],
        global_semaphore: Optional[asyncio.Semaphore] = None,
        page_offset: int = 0,
    ) -> List[PageResult]:
        """异步转换所有页面。"""
        if self._uses_strict_batch_page_scheduling():
            return await self._convert_all_pages_strict_batches_async(images, page_offset=page_offset)
        return await self._convert_all_pages_sliding_window_async(images, global_semaphore, page_offset=page_offset)

    async def _convert_pages_streaming_async(
        self,
        provider,
        page_indices: List[int],
        global_semaphore: Optional[asyncio.Semaphore] = None,
    ) -> List[PageResult]:
        total_pages = len(page_indices)
        concurrency = max(1, self.max_concurrent)
        results_by_page = self._load_checkpoint_results(total_pages)
        self._emit_progress(event="pages_discovered", total_pages=total_pages, stage="preprocessing")
        for restored_page_num in sorted(results_by_page):
            restored = results_by_page[restored_page_num]
            self._emit_progress(
                event="page_done",
                page_num=restored_page_num,
                ok=bool(restored.ok),
                stage="processing",
            )

        for batch_start in range(0, total_pages, concurrency):
            batch_end = min(batch_start + concurrency, total_pages)
            batch_page_nums = list(range(batch_start + 1, batch_end + 1))
            missing_positions = [
                pos for pos, page_num in enumerate(batch_page_nums, start=batch_start)
                if page_num not in results_by_page or not results_by_page[page_num].ok
            ]
            if not missing_positions:
                logger.info(f"[VLM] Batch pages {batch_start + 1}-{batch_end} already completed by checkpoint")
                continue

            runs: list[list[int]] = []
            for pos in missing_positions:
                if not runs or pos != runs[-1][-1] + 1:
                    runs.append([pos])
                else:
                    runs[-1].append(pos)

            for run in runs:
                render_indices = [page_indices[pos] for pos in run]
                start_page = run[0] + 1
                end_page = run[-1] + 1
                self._emit_progress(
                    event="render_batch",
                    start_page=start_page,
                    end_page=end_page,
                    stage="preprocessing",
                )
                logger.info(f"[VLM] Rendering streaming batch pages {start_page}-{end_page}")
                images = provider.get_images(render_indices, self.dpi)

                try:
                    batch_results = await self._convert_all_pages_async(
                        images,
                        global_semaphore,
                        page_offset=run[0],
                    )
                    for page_result in batch_results:
                        results_by_page[page_result.page_num] = page_result
                    self._save_checkpoint_results(total_pages, results_by_page)
                finally:
                    for img in images:
                        try:
                            img.close()
                        except Exception:
                            pass
                    del images

        return [
            results_by_page.get(page_num)
            or self._error_page_result(page_num, self.api_provider, "missing page result")
            for page_num in range(1, total_pages + 1)
        ]

    async def _convert_sparse_pages_async(
        self,
        provider,
        page_pairs: list[tuple[int, int]],
        global_semaphore: Optional[asyncio.Semaphore] = None,
    ) -> list[PageResult]:
        """Convert sparse PDF pages while preserving absolute logical page numbers."""
        if not page_pairs:
            return []

        old_max_concurrent = self.max_concurrent
        self.max_concurrent = max(1, self.repair_max_concurrent)
        results: list[PageResult] = []
        concurrency = self.max_concurrent

        try:
            for batch_start in range(0, len(page_pairs), concurrency):
                batch_pairs = page_pairs[batch_start:batch_start + concurrency]
                logical_nums = [logical for _, logical in batch_pairs]
                logger.info(f"[VLM Repair] Rendering sparse pages: {logical_nums}")
                self._emit_progress(
                    event="repair_batch",
                    pages=logical_nums,
                    stage="repairing",
                )
                images = provider.get_images([pdf_index for pdf_index, _ in batch_pairs], self.dpi)
                try:
                    async with aiohttp.ClientSession() as session:
                        tasks = [
                            self._convert_page_async_no_semaphore(session, img, logical_num)
                            for img, (_, logical_num) in zip(images, batch_pairs)
                        ]
                        batch_raw = await asyncio.gather(*tasks, return_exceptions=True)
                    for (_, logical_num), raw_result in zip(batch_pairs, batch_raw):
                        result = self._normalize_page_result(logical_num, raw_result)
                        results.append(result)
                        self._emit_progress(
                            event="page_done",
                            page_num=logical_num,
                            ok=bool(result.ok),
                            stage="repairing",
                        )
                finally:
                    for img in images:
                        try:
                            img.close()
                        except Exception:
                            pass
                    del images
        finally:
            self.max_concurrent = old_max_concurrent

        return results

    async def _auto_repair_failed_results_async(
        self,
        provider,
        page_indices: list[int],
        raw_outputs: list[PageResult],
        global_semaphore: Optional[asyncio.Semaphore] = None,
    ) -> list[PageResult]:
        if not self.auto_repair_failed_pages or self.repair_rounds <= 0:
            return raw_outputs

        results_by_page = {int(result.page_num): result for result in raw_outputs}
        total_pages = len(page_indices)

        for round_idx in range(1, self.repair_rounds + 1):
            failed_pages = [
                page_num
                for page_num in range(1, total_pages + 1)
                if page_num not in results_by_page
                or not results_by_page[page_num].ok
                or results_by_page[page_num].content_kind != "json"
            ]
            if not failed_pages:
                logger.info(f"[VLM Repair] No failed pages before repair round {round_idx}")
                break

            logger.info(
                f"[VLM Repair] Round {round_idx}/{self.repair_rounds}: retrying {len(failed_pages)} pages "
                f"with concurrency={self.repair_max_concurrent}: {failed_pages}"
            )
            self._emit_progress(
                event="repair_start",
                round=round_idx,
                total_rounds=self.repair_rounds,
                failed_pages=failed_pages,
                stage="repairing",
            )

            page_pairs = [(page_indices[page_num - 1], page_num) for page_num in failed_pages]
            repaired_results = await self._convert_sparse_pages_async(provider, page_pairs, global_semaphore)
            for repaired in repaired_results:
                if repaired.ok and repaired.content_kind == "json":
                    results_by_page[int(repaired.page_num)] = repaired

            remaining = [
                page_num
                for page_num in failed_pages
                if page_num not in results_by_page
                or not results_by_page[page_num].ok
                or results_by_page[page_num].content_kind != "json"
            ]
            self._emit_progress(
                event="repair_done",
                round=round_idx,
                repaired_pages=len(failed_pages) - len(remaining),
                remaining_failed_pages=remaining,
                stage="repairing",
            )

        return [
            results_by_page.get(page_num)
            or self._error_page_result(page_num, self.api_provider, "missing page result after repair")
            for page_num in range(1, total_pages + 1)
        ]

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
        provider_config = {**self.config, "force_ocr": True}
        provider = provider_cls(filepath, provider_config)

        # 2. 获取所有页面图像（支持页码范围过滤）
        num_pages = len(provider)
        if self.page_start is not None and self.page_end is not None:
            actual_end = min(self.page_end, num_pages - 1)
            page_indices = list(range(self.page_start, actual_end + 1))
            logger.info(f"[VlmDirectAsyncConverter] Page range: {self.page_start}-{actual_end} (total {num_pages} pages)")
        else:
            page_indices = list(range(num_pages))

        logger.info(f"[VlmDirectAsyncConverter] Using {self.max_concurrent} concurrent workers")

        # 3. 异步并发转换（传递全局信号量）
        start_time = time.time()
        if self.streaming_batches:
            raw_outputs = asyncio.run(self._convert_pages_streaming_async(provider, page_indices, global_semaphore))
            images = [None] * len(page_indices)
        else:
            images = provider.get_images(page_indices, self.dpi)
            logger.info(f"[VlmDirectAsyncConverter] Loaded {len(images)} pages")
            self._emit_progress(event="pages_loaded", total_pages=len(images), stage="processing")
            raw_outputs = asyncio.run(self._convert_all_pages_async(images, global_semaphore))
        elapsed_time = time.time() - start_time

        if self.output_mode == "json":
            raw_outputs = asyncio.run(
                self._auto_repair_failed_results_async(provider, page_indices, raw_outputs, global_semaphore)
            )
        markdown_pages, printed_pages = self._prepare_markdown_pages(raw_outputs)
        full_markdown = self._finalize_markdown_pages(markdown_pages, printed_pages, len(page_indices))

        logger.info(f"[VlmDirectAsyncConverter] Conversion complete in {elapsed_time:.1f}s")
        logger.info(f"[VlmDirectAsyncConverter] Total: {len(full_markdown)} chars")
        logger.info(f"[VlmDirectAsyncConverter] Speed: {len(page_indices) / elapsed_time:.2f} pages/sec")
        self._emit_progress(event="file_done", stage="saving")

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

        # 9. 返回主格式（markdown）
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
        provider_config = {**self.config, "force_ocr": True}
        provider = provider_cls(filepath, provider_config)

        # 2. 获取所有页面图像（支持页码范围过滤）
        num_pages = len(provider)
        if self.page_start is not None and self.page_end is not None:
            actual_end = min(self.page_end, num_pages - 1)
            page_indices = list(range(self.page_start, actual_end + 1))
            logger.info(f"[VlmDirectAsyncConverter] Page range: {self.page_start}-{actual_end} (total {num_pages} pages)")
        else:
            page_indices = list(range(num_pages))

        logger.info(f"[VlmDirectAsyncConverter] Using {self.max_concurrent} concurrent workers")

        # 3. 异步并发转换
        start_time = time.time()
        if self.streaming_batches:
            raw_outputs = await self._convert_pages_streaming_async(provider, page_indices, global_semaphore)
        else:
            images = provider.get_images(page_indices, self.dpi)
            logger.info(f"[VlmDirectAsyncConverter] Loaded {len(images)} pages")
            self._emit_progress(event="pages_loaded", total_pages=len(images), stage="processing")
            raw_outputs = await self._convert_all_pages_async(images, global_semaphore)
        elapsed_time = time.time() - start_time

        if self.output_mode == "json":
            raw_outputs = await self._auto_repair_failed_results_async(provider, page_indices, raw_outputs, global_semaphore)
        markdown_pages, printed_pages = self._prepare_markdown_pages(raw_outputs)
        full_markdown = self._finalize_markdown_pages(markdown_pages, printed_pages, len(page_indices))

        logger.info(f"[VlmDirectAsyncConverter] Conversion complete in {elapsed_time:.1f}s")
        logger.info(f"[VlmDirectAsyncConverter] Total: {len(full_markdown)} chars")
        logger.info(f"[VlmDirectAsyncConverter] Speed: {len(page_indices) / elapsed_time:.2f} pages/sec")
        self._emit_progress(event="file_done", stage="saving")

        return full_markdown
