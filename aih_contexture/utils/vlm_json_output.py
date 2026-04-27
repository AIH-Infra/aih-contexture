"""
VLM JSON Output Parser

将VLM输出的JSON转换为Markdown格式
"""

import json
import re
from typing import Optional, Tuple

from aih_contexture.logger import get_logger

logger = get_logger()


def load_and_validate_vlm_json(json_str: str) -> dict:
    if not json_str or not json_str.strip():
        raise ValueError("Empty JSON output")

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {e}")
        raise ValueError(f"Invalid JSON: {e}") from e

    if not isinstance(data, dict):
        raise ValueError("Top-level VLM JSON output must be an object")

    regions = data.get("regions")
    if not isinstance(regions, list):
        raise ValueError("VLM JSON output must contain a list field 'regions'")

    return data


def parse_json_to_markdown(
    json_str: str,
    config: Optional[dict] = None
) -> Tuple[str, Optional[str]]:
    """
    将VLM输出的JSON转换为Markdown

    Args:
        json_str: JSON字符串
        config: 配置字典

    Returns:
        (markdown_text, printed_page_number)
    """
    data = load_and_validate_vlm_json(json_str)

    printed_page = data.get("printed_page_number")
    regions = data["regions"]

    markdown_parts = []
    for region in regions:
        label = region.get("label") or ""
        text = region.get("text") or ""
        confidence = region.get("confidence")

        md = _convert_region_to_markdown(label, text, config or {})
        if md:
            if isinstance(confidence, (int, float)) and confidence < 0.7:
                md = f"{md} `[不确定]`"
            markdown_parts.append(md)

    return ("\n\n".join(markdown_parts), printed_page)


def _convert_region_to_markdown(label: str, text: str, config: dict) -> str:
    """
    将单个区域转换为Markdown格式

    Args:
        label: 区域标签
        text: 区域文本
        config: 配置字典

    Returns:
        Markdown字符串
    """
    if not text:
        return ""

    # 配置参数
    marginal_note_enabled = config.get("vlm_direct_marginal_note_enabled", False)
    use_markdown_footnotes = config.get("vlm_direct_use_markdown_footnotes", False)
    footnote_backlink = config.get("vlm_direct_footnote_backlink", False)

    # 🔧 修复1：转换上标和下标格式
    text = re.sub(r'\^([^^]+)\^', r'<sup>\1</sup>', text)
    text = re.sub(r'~([^~]+)~', r'<sub>\1</sub>', text)

    # Section-Header
    if label == "Section-Header":
        return f"## {text}"

    # Text（处理脚注引用）
    elif label == "Text":
        # 合并断行：连字符断行直接拼接，普通断行变空格
        text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)
        text = text.replace('\n', ' ')
        if use_markdown_footnotes:
            text = re.sub(r'<sup>(\d+|\*+)\)</sup>', r'[^\1]', text)
        else:
            text = re.sub(
                r'<sup>(\d+|\*+)\)</sup>',
                r'<sup id="ref\1"><a href="#fn\1">\1)</a></sup>',
                text
            )
        return text

    # Marginal-Note-Left/Right
    elif label in ("Marginal-Note-Left", "Marginal-Note-Right"):
        if marginal_note_enabled:
            side = "Marginal-Left" if label == "Marginal-Note-Left" else "Marginal-Right"
            # 合并断行连字符，换行变空格
            text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)
            text = text.replace('\n', ' ').strip()
            return f"> **[{side}]** {text}"
        else:
            return text

    # Footnote（含联动锚点）
    elif label == "Footnote":
        # 🔧 修复2：支持多种脚注格式
        match = re.match(r'<sup>(\d+|\*+)\)</sup>\s*(.*)', text, re.DOTALL)
        if not match:
            # 格式2: ^1)^ text
            match = re.match(r'\^(\d+|\*+)\)\^\s*(.*)', text, re.DOTALL)
        if not match:
            # 格式3: 1) text
            match = re.match(r'(\d+|\*+)\)\s*(.*)', text, re.DOTALL)

        if match:
            fn_id = match.group(1)
            fn_text = match.group(2)

            if use_markdown_footnotes:
                return f"[^{fn_id}]: {fn_text}"
            else:
                return f'<sup id="fn{fn_id}">{fn_id})</sup> {fn_text}'
        return text

    # List-Group
    elif label == "List-Group":
        # 🔧 修复7：区分有序/无序列表
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if not lines:
            return ""

        # 检测是否是有序列表（第一行以数字开头）
        if re.match(r'^\d+\.', lines[0]):
            return "\n".join(lines)  # 保持原格式
        else:
            return "\n".join(f"- {line}" for line in lines)

    # Table
    elif label == "Table":
        # 🔧 修复3：转换为Markdown表格
        lines = [line for line in text.split("\n") if line.strip()]
        if not lines:
            return ""

        rows = [line.split("\t") for line in lines]
        if not rows or not rows[0]:
            return text

        # 表头
        header = "| " + " | ".join(rows[0]) + " |"
        separator = "|" + "|".join(["------"] * len(rows[0])) + "|"

        # 数据行
        data_rows = ["| " + " | ".join(row) + " |" for row in rows[1:]]

        return "\n".join([header, separator] + data_rows)

    # Equation-Block
    elif label == "Equation-Block":
        return f"$$\n{text}\n$$"

    # Code-Block
    elif label == "Code-Block":
        return f"```\n{text}\n```"

    # Figure
    elif label == "Figure":
        return text.replace('[图表:', '[Figure:') if text else ""

    # Caption
    elif label == "Caption":
        return f"*{text}*"

    # Page-Header/Footer
    elif label in ("Page-Header", "Page-Footer"):
        return ""

    # 🔧 修复4：添加缺失的labels
    # Table-Of-Contents
    elif label == "Table-Of-Contents":
        return f"**目录**\n\n{text}"

    # Complex-Block
    elif label == "Complex-Block":
        return text

    # 其他
    else:
        return text


def markdown_to_html(markdown: str) -> str:
    """
    将Markdown转换为HTML

    Args:
        markdown: Markdown字符串

    Returns:
        HTML字符串（包含MathJax支持）
    """
    try:
        import markdown2
    except ImportError:
        logger.error("markdown2 not installed. Install with: pip install markdown2")
        return f"<pre>{markdown}</pre>"

    html_body = markdown2.markdown(
        markdown,
        extras=[
            "tables",
            "fenced-code-blocks",
            "footnotes",
            "cuddled-lists",
        ]
    )

    html_template = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <style>
        body {{ font-family: serif; max-width: 800px; margin: 40px auto; line-height: 1.6; }}
        blockquote {{ border-left: 3px solid #ccc; padding-left: 15px; color: #666; }}
        code {{ background: #f4f4f4; padding: 2px 5px; border-radius: 3px; }}
        pre {{ background: #f4f4f4; padding: 10px; border-radius: 5px; overflow-x: auto; }}
    </style>
</head>
<body>
{html_body}
</body>
</html>"""

    return html_template
