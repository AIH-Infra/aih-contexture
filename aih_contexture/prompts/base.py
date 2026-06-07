"""
VLM Prompt Template System - Base Template Class

Provides customizable prompt templates for different document types
with API parameter control and cross-API compatibility.
"""

import re
from typing import Dict, List, Optional
from pydantic import BaseModel

from aih_contexture.logger import get_logger
from aih_contexture.prompts.api_adapter import APIParameterAdapter

logger = get_logger()


class VlmPromptTemplate(BaseModel):
    """VLM 提示词模板基类 - 优化版"""

    # 文档特征参数
    text_direction: str = "horizontal"  # "horizontal" | "vertical" | "mixed"
    may_have_footnotes: bool = False  # 是否识别脚注
    may_have_references: bool = False  # 是否识别引用
    language_mode: str = "monolingual"  # "monolingual" | "multilingual"
    primary_language: str = "zh"  # 主要语言
    document_era: str = "modern"  # "ancient" | "modern" | "contemporary"
    may_have_page_numbers: bool = False  # 是否提取页码
    may_have_headers_footers: bool = False  # 是否保留页眉页脚

    # 🆕 手写识别模式（替代原来的 may_have_handwriting）
    handwriting_mode: str = "none"  # "none" | "mixed" | "pure"
    # none: 忽略手写内容
    # mixed: 混合内容，识别并标记手写部分
    # pure: 纯手写文档，不需要标记（默认全是手写）

    # 🆕 图片描述功能
    describe_images: bool = False  # 是否描述图片/印章/照片
    anti_hallucination: bool = True  # 缺失信息不猜测
    extract_bboxes: bool = True  # 是否提取 bbox
    include_confidence: bool = False  # 是否输出近似置信度
    enhance_tables_equations: bool = True  # 是否增强表格/公式结构
    special_features: List[str] = []

    # API 参数配置
    temperature: float = 0.0
    top_p: float = 0.1
    top_k: Optional[int] = None
    max_tokens: int = 0  # 0 = 不限制，让模型自然停止
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    seed: Optional[int] = None

    # 自定义提示词片段
    custom_instructions: str = ""

    # 🆕 向后兼容
    may_have_handwriting: bool = False  # 保留旧参数，映射到 handwriting_mode

    class Config:
        arbitrary_types_allowed = True

    def build_prompt(self) -> str:
        """构建精简提示词"""
        sections = []

        # 1. 核心指令（精简版）
        sections.append(self._get_core_instruction())

        # 2. 特殊功能指导（按需添加）
        special = self._get_special_instructions()
        if special:
            sections.append(special)

        # 3. 自定义指导
        if self.custom_instructions:
            sections.append(self.custom_instructions)

        return "\n\n".join(sections)

    def get_api_params(self, api_type: str = "unknown") -> Dict:
        """获取适配后的 API 参数"""
        params = {
            "temperature": self.temperature,
            "top_p": self.top_p,
        }

        # 只有 max_tokens > 0 时才传递
        if self.max_tokens > 0:
            params["max_tokens"] = self.max_tokens

        if self.top_k is not None:
            params["top_k"] = self.top_k
        if self.presence_penalty != 0.0:
            params["presence_penalty"] = self.presence_penalty
        if self.frequency_penalty != 0.0:
            params["frequency_penalty"] = self.frequency_penalty
        if self.seed is not None:
            params["seed"] = self.seed

        # 适配不同 API
        return APIParameterAdapter.adapt_params(api_type, params)

    def _get_core_instruction(self) -> str:
        """获取核心指令 - JSON输出模式"""
        direction_hint = ""
        if self.text_direction == "vertical":
            direction_hint = "\n\n## Text Direction\n- Text is vertical (read right-to-left, top-to-bottom)\n- Transcribe in reading order"
        elif self.text_direction == "mixed":
            direction_hint = "\n\n## Text Direction\n- Text may be horizontal or vertical\n- Transcribe in reading order"

        language_hint = ""
        if self.primary_language:
            lang_names = {
                "zh": "Chinese",
                "zh-Hans": "Simplified Chinese",
                "zh-Hant": "Traditional Chinese",
                "en": "English",
                "de": "German",
                "fr": "French",
                "ja": "Japanese",
                "ko": "Korean"
            }
            lang_name = lang_names.get(self.primary_language, self.primary_language)
            language_hint = f"\n\n## Primary Language\n- Document is primarily in {lang_name}\n- Preserve original text exactly"

        bbox_rule = (
            "- Estimate bbox in image pixels as [x0, y0, x1, y1] for each visible region. If uncertain, use null."
            if self.extract_bboxes
            else "- Set every bbox field to null."
        )
        confidence_rule = (
            "- Use confidence only as an approximate self-assessment from 0.0 to 1.0. If uncertain, use null."
            if self.include_confidence
            else "- Set every confidence field to null."
        )
        anti_hallucination_rule = ""
        if self.anti_hallucination:
            anti_hallucination_rule = """
## Anti-Hallucination Rules
- Include only regions and text that are actually visible on the page.
- If a value is not visible or cannot be determined, use null or an empty array.
- Do not guess missing text, page numbers, labels, coordinates, confidence, captions, or image descriptions.
- Do not copy values from schema examples; the schema below shows types, not page content."""

        marginalia_enabled = "marginal_notes" in self.special_features
        margin_labels = (
            "**Margins:** Marginal-Note-Left, Marginal-Note-Right, Marginal-Note-Top, Marginal-Note-Bottom, Footnote"
            if marginalia_enabled
            else "**Margins:** Footnote"
        )
        marginalia_rule = (
            "2. **Marginal Notes:** Treat text outside the main text column as a separate marginal note region. "
            "Use Marginal-Note-Left or Marginal-Note-Right for side notes, and Marginal-Note-Top or "
            "Marginal-Note-Bottom only for true marginal annotations, not running headers, page numbers, or footnotes. "
            "Do NOT merge marginal notes into nearby paragraphs."
            if marginalia_enabled
            else "2. **Marginal Notes:** Do not use Marginal-Note-Left, Marginal-Note-Right, Marginal-Note-Top, or Marginal-Note-Bottom labels; transcribe visible side text as normal Text unless it is clearly a Footnote"
        )
        reading_order_rule = (
            "3. **Reading Order:** Top-to-bottom, left-to-right; marginal notes near associated text"
            if marginalia_enabled
            else "3. **Reading Order:** Top-to-bottom, left-to-right"
        )

        return f"""OCR this document page and return one structured JSON object with layout regions and text content.{direction_hint}{language_hint}

## Region Labels (use EXACTLY one per region)

**Main:** Section-Header, Text, List-Group, Table, Figure, Equation-Block
{margin_labels}
**Structure:** Page-Header, Page-Footer, Caption
**Special:** Code-Block, Table-Of-Contents, Complex-Block

## JSON Schema

{{
  "printed_page_number": string | null,
  "page_width": number,
  "page_height": number,
  "regions": [
    {{
      "label": string,
      "bbox": [number, number, number, number] | null,
      "text": string,
      "confidence": number | null
    }}
  ]
}}

## Field Rules

- `printed_page_number`: extract from visible Page-Header/Page-Footer only; otherwise use null.
- `page_width` and `page_height`: use the actual image dimensions when available; do not invent fixed example dimensions.
{bbox_rule}
- `text`: transcribe exactly as printed. Use `***bold italic***`, `**bold**`, `*italic*`, `^superscript^`, `~subscript~`, `\\n` for line breaks, and `\\t` for table columns only when visible.
{confidence_rule}
{anti_hallucination_rule}

## Detection Rules

1. **Granularity:** 5-30 semantic blocks per page (paragraphs, not lines)
{marginalia_rule}
{reading_order_rule}
4. **Preserve:** Original text, spelling, formatting, line breaks
5. **Do NOT:** Modernize, translate, correct "errors", add comments

## Output
- Output ONLY the JSON object
- Start with `{{` and end with `}}`
- No markdown fences
- No text before or after the JSON
- Do not add emojis, emoticons, uncertainty tags, or commentary
- Stop immediately after the closing `}}`
- Detect all visible content including small/faint text"""

    def _get_special_instructions(self) -> str:
        """根据参数生成特殊指导 - JSON模式"""
        instructions = []

        # 手写识别（混合模式才标记）
        if self.handwriting_mode == "mixed":
            instructions.append("""## Handwriting Recognition
- Transcribe visible handwritten notes and handwritten marginalia.
- Mark every handwritten text span as `**[handwritten]** content` inside the text field.
- If handwritten text is in the page margin, keep it as a separate Marginal-Note-Left/Right/Top/Bottom region when marginalia recognition is enabled.
- Distinguish printed vs handwritten content; do not merge handwritten notes into printed body text.""")
        elif self.handwriting_mode == "none":
            instructions.append("""## Handwriting Handling
- Ignore handwritten content entirely.
- Do not transcribe handwritten notes, pencil marks, manuscript marginalia, signatures, or reader annotations.
- Do not output `**[handwritten]**`, `**[手写]**`, Handwriting, Signature, or handwritten Annotation regions.""")

        # 脚注
        if self.may_have_footnotes:
            instructions.append("## Footnotes\n- Create separate regions with label \"Footnote\"\n- Place at bottom of page in reading order")

        # 页码提取
        if self.may_have_page_numbers:
            instructions.append("## Page Numbers\n- Extract printed page number from Page-Header or Page-Footer regions\n- Set \"printed_page_number\" field (string or null)")

        # 图片描述
        if self.describe_images:
            instructions.append("""## Image Description
- This is non-mandatory: only describe explicit non-text visual content such as figures, photos, stamps, diagrams, maps, or illustrations.
- Do not describe ordinary text blocks as images.
- For Figure regions, describe only visible image content concisely in the text field.
- Keep image descriptions in the document's primary language.
- If the image content is unclear, use an empty string.""")
        else:
            instructions.append("## Images\n- For Figure regions, do not invent descriptions. Use visible captions as separate Caption regions; otherwise use an empty string in the Figure text field.")

        if self.enhance_tables_equations:
            instructions.append("""## Tables and Equations
- Preserve tables as structured text or markdown tables when possible.
- Label standalone formulas as Equation-Block and preserve mathematical notation.""")
        else:
            instructions.append("## Tables and Equations\n- Do not force table or equation structure when uncertain; use Text regions instead.")

        # 边注（如果启用）
        if "marginal_notes" in self.special_features:
            if self.handwriting_mode == "mixed":
                marginalia_scope = "all visible marginalia, including printed side notes, scholarly references, glosses, and handwritten marginal notes"
                handwritten_rule = "- If a marginal note is handwritten, still use the appropriate Marginal-Note-* label and mark its text with `**[handwritten]**`."
            else:
                marginalia_scope = "all visible printed/typographic marginalia, including printed side notes, scholarly references, and glosses"
                handwritten_rule = "- Ignore handwritten marks or reader annotations, but do not let them suppress nearby printed marginalia."
            instructions.append("""## Marginal Notes
- Create separate regions for {marginalia_scope}.
- Use "Marginal-Note-Left" or "Marginal-Note-Right" for side notes outside the main text column.
- Use "Marginal-Note-Top" or "Marginal-Note-Bottom" only for true annotations; use Page-Header/Page-Footer for running titles, page numbers, and ordinary footers.
- Keep each marginal note exactly as printed/written, in its own reading order.
- Do not treat small printed references in the margin as body paragraphs or footnotes unless they are visibly in the footnote area.
{handwritten_rule}""".format(
                marginalia_scope=marginalia_scope,
                handwritten_rule=handwritten_rule,
            ))

        return "\n\n".join(instructions) if instructions else ""


def validate_and_clean_output(markdown: str, strict: bool = True) -> tuple:
    """
    验证 VLM 输出是否符合要求，并清理多余内容

    Args:
        markdown: VLM 原始输出
        strict: 是否启用严格模式

    Returns:
        (is_valid, cleaned_markdown)
    """
    original_markdown = markdown

    # 1. 移除代码块包装
    if markdown.strip().startswith("```"):
        lines = markdown.strip().split("\n")
        # 移除开头的 ```markdown 或 ```
        if lines[0].startswith("```"):
            lines = lines[1:]
        # 移除结尾的 ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        markdown = "\n".join(lines)

    # 2. 移除常见的说明性前缀
    prefixes_to_remove = [
        "以下是转换结果：",
        "以下是转换后的内容：",
        "这是转换后的 Markdown：",
        "Markdown 内容如下：",
        "转换结果：",
        "Here is the converted content:",
        "The markdown content is:",
        "Converted markdown:",
    ]
    for prefix in prefixes_to_remove:
        if markdown.strip().startswith(prefix):
            markdown = markdown.strip()[len(prefix):].strip()

    # 3. 移除结尾的说明性文字
    suffixes_to_remove = [
        "注：",
        "Note:",
        "说明：",
        "以上是",
        "This is",
    ]
    lines = markdown.split("\n")
    while lines:
        last_line = lines[-1].strip()
        should_remove = False
        for suffix in suffixes_to_remove:
            if last_line.startswith(suffix):
                should_remove = True
                break
        if should_remove:
            lines.pop()
        else:
            break
    markdown = "\n".join(lines)

    # 4. 检查是否包含元信息（严格模式）
    if strict:
        meta_patterns = [
            r"^注[：:].+$",
            r"^Note[：:].+$",
            r"^\[说明\].+$",
            r"^\[Note\].+$",
        ]

        cleaned_lines = []
        for line in markdown.split("\n"):
            is_meta = False
            for pattern in meta_patterns:
                if re.match(pattern, line.strip()):
                    is_meta = True
                    logger.warning(f"Removed meta line: {line.strip()}")
                    break
            if not is_meta:
                cleaned_lines.append(line)

        markdown = "\n".join(cleaned_lines)

    # 5. 检测并截断重复内容
    markdown = _detect_and_truncate_repetition(markdown)

    # 6. 合并段落内的断行（新增）
    markdown = _merge_paragraph_lines(markdown)

    # 6. 验证是否有实际内容
    if len(markdown.strip()) < 10:
        logger.error(f"Output too short: {len(markdown)} chars")
        return False, original_markdown

    # 7. 记录清理情况
    if markdown != original_markdown:
        logger.info(f"Cleaned output: {len(original_markdown)} -> {len(markdown)} chars")

    return True, markdown.strip()


def _detect_and_truncate_repetition(markdown: str, min_repeat_len: int = 50) -> str:
    """
    检测并截断重复内容

    当模型开始重复输出相同内容时，截断到第一次出现的位置。

    Args:
        markdown: 输入文本
        min_repeat_len: 最小重复片段长度

    Returns:
        截断后的文本
    """
    if len(markdown) < min_repeat_len * 2:
        return markdown

    # 方法1: 检测连续重复的段落
    paragraphs = markdown.split('\n\n')
    if len(paragraphs) > 3:
        seen = set()
        unique_paragraphs = []
        for p in paragraphs:
            p_stripped = p.strip()
            if len(p_stripped) < 20:  # 短段落不检测
                unique_paragraphs.append(p)
                continue
            if p_stripped in seen:
                logger.warning(f"Detected repeated paragraph, truncating...")
                break
            seen.add(p_stripped)
            unique_paragraphs.append(p)

        if len(unique_paragraphs) < len(paragraphs):
            return '\n\n'.join(unique_paragraphs)

    # 方法2: 检测长文本中的重复模式
    text_len = len(markdown)
    for pattern_len in range(min_repeat_len, min(500, text_len // 3)):
        # 检查文本后半部分是否重复前半部分的内容
        mid_point = text_len // 2
        pattern = markdown[mid_point:mid_point + pattern_len]

        # 在前半部分查找这个模式
        first_occurrence = markdown[:mid_point].find(pattern)
        if first_occurrence != -1:
            # 找到重复，截断到第一次出现后
            logger.warning(f"Detected repetition pattern at position {first_occurrence}")
            return markdown[:first_occurrence + pattern_len]

    return markdown


def _merge_paragraph_lines(markdown: str) -> str:
    """
    合并段落内的不必要断行，但保留段落分隔和特殊格式

    规则：
    1. 空行表示段落分隔，保留
    2. 标题行（# 开头）独立，不合并
    3. 列表项（- 或 1. 开头）独立，不合并
    4. 代码块（``` 包围）内容不处理
    5. 表格行（| 开头）独立，不合并
    6. 数学公式（$$ 包围）内容不处理
    7. 脚注定义（<sup>1</sup> 或兼容的 [^1]: 开头）独立，不合并
    8. 普通文本行：连续的非空行合并为一个段落
    """
    lines = markdown.split("\n")
    result = []
    current_paragraph = []
    in_code_block = False
    in_math_block = False

    def is_special_line(line: str) -> bool:
        """判断是否是特殊格式的行（不应该合并）"""
        stripped = line.strip()
        if not stripped:
            return True  # 空行

        # 标题
        if stripped.startswith("#"):
            return True

        # 列表项
        if stripped.startswith("- ") or stripped.startswith("* ") or stripped.startswith("+ "):
            return True
        if re.match(r"^\d+\.\s", stripped):
            return True

        # 表格行
        if stripped.startswith("|"):
            return True

        # 脚注定义
        if re.match(r"^\[\^\d+\]:", stripped):
            return True

        # HTML 标签（如 <span>, <sub>, <sup>）
        if stripped.startswith("<") and ">" in stripped:
            return True

        # 水平线
        if re.match(r"^[-*_]{3,}$", stripped):
            return True

        return False

    def flush_paragraph():
        """输出当前段落"""
        if current_paragraph:
            # 合并段落内的行，用空格连接
            merged = " ".join(line.strip() for line in current_paragraph if line.strip())
            if merged:
                result.append(merged)
            current_paragraph.clear()

    for line in lines:
        stripped = line.strip()

        # 检测代码块
        if stripped.startswith("```"):
            flush_paragraph()
            in_code_block = not in_code_block
            result.append(line)
            continue

        # 代码块内不处理
        if in_code_block:
            result.append(line)
            continue

        # 检测数学公式块
        if stripped.startswith("$$"):
            flush_paragraph()
            in_math_block = not in_math_block
            result.append(line)
            continue

        # 数学公式块内不处理
        if in_math_block:
            result.append(line)
            continue

        # 空行：段落分隔
        if not stripped:
            flush_paragraph()
            result.append("")  # 保留空行
            continue

        # 特殊格式行：独立输出
        if is_special_line(line):
            flush_paragraph()
            result.append(line)
            continue

        # 普通文本行：加入当前段落
        current_paragraph.append(line)

    # 处理最后的段落
    flush_paragraph()

    return "\n".join(result)
