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
    # none: 不特别处理手写
    # mixed: 混合内容，标记手写部分
    # pure: 纯手写文档，不需要标记（默认全是手写）

    # 🆕 图片描述功能
    describe_images: bool = False  # 是否描述图片/印章/照片
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
        """获取核心指令 - 包含完整 Markdown 语法规范"""
        direction_hint = ""
        if self.text_direction == "vertical":
            direction_hint = "Note: Text is vertical (read right-to-left, top-to-bottom). Convert to horizontal output.\n\n"
        elif self.text_direction == "mixed":
            direction_hint = "Note: Text may be horizontal or vertical. Convert all to horizontal output.\n\n"

        return f"""Convert this document page to Markdown format.

{direction_hint}## Markdown Syntax (use as needed)

**Headings** (if present): # ## ###
**Lists** (if present): - item or 1. item
**Tables** (if present):
| Col1 | Col2 |
|------|------|
| data | data |
**Emphasis**: **bold**, *italic*
**Math** (if present): $inline$ or $$block$$
**Footnotes** (if present): [^1] reference, [^1]: definition
**Blockquote** (if present): > quoted text

## CRITICAL Output Rules
1. Wrap ALL your output in a single ```markdown``` code block
2. Do NOT add any explanations, introductions, or summaries OUTSIDE the code block
3. Do NOT say "以下是..." or "Here is..." before the code block
4. Inside the code block, output ONLY the document content
5. Preserve original text exactly - DO NOT translate
6. Keep the original language (Chinese stays Chinese, etc.)
7. Mark unclear text as [unclear]

Example output format:
```markdown
# Document Title
Content here...
```"""

    def _get_special_instructions(self) -> str:
        """根据参数生成特殊指导"""
        instructions = []

        # 手写识别（混合模式才标记）
        if self.handwriting_mode == "mixed":
            instructions.append("**Handwriting**: Mark handwritten parts as `**[手写]** content`")

        # 脚注
        if self.may_have_footnotes:
            instructions.append("**Footnotes**: Use [^1] for references, [^1]: for definitions")

        # 页码提取
        if self.may_have_page_numbers:
            instructions.append("**Page number**: If visible, output at start: `<!-- page-header: NUMBER -->`")

        # 图片描述
        if self.describe_images:
            instructions.append("""**Images/Stamps/Photos**: Describe in brackets:
- [印章: description]
- [照片: description]
- [图片: description]
- [图表: description]""")
        else:
            # 默认简单占位
            instructions.append("**Images**: Use [图片] as placeholder for images")

        # 边注
        if "marginal_notes" in self.special_features:
            instructions.append("**Marginal notes**: Include in parentheses: （边注：content）")

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
    7. 脚注定义（[^1]: 开头）独立，不合并
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
