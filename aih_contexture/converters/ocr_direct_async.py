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
from typing import List, Optional, Annotated, Tuple, Union

import aiohttp
from PIL import Image
import fitz  # PyMuPDF
from bs4 import BeautifulSoup

from aih_contexture.converters import BaseConverter
from aih_contexture.schema.document import Document
from aih_contexture.services.ocr_chandra import OcrChandraService
from aih_contexture.builders.ocr_parser import OcrParser
from aih_contexture.formatters import PageAnchorPlugin, PrintedPageExtractor
from aih_contexture.utils.api_key_pool import APIKeyPool
from aih_contexture.logger import get_logger

logger = get_logger()


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

    def __init__(self, config):
        super().__init__(config)
        config = config or {}

        # 加载配置（支持字典访问）
        self.endpoint = config.get("ocr_endpoint", self.ocr_endpoint)

        # 端点自动补全：如果只填了 /v1，自动补全为 /v1/chat/completions
        if self.endpoint.endswith("/v1"):
            self.endpoint = self.endpoint.replace("/v1", "/v1/chat/completions")

        self.model = config.get("ocr_model", self.ocr_model)
        self.api_key = config.get("ocr_api_key", self.ocr_api_key)
        self.output_format = config.get("ocr_output_format", self.ocr_output_format)
        self.max_tokens = config.get("ocr_max_tokens", self.ocr_max_tokens)
        self.temperature = config.get("ocr_temperature", self.ocr_temperature)
        self.timeout = config.get("ocr_timeout", self.ocr_timeout)
        self.max_retries = config.get("ocr_max_retries", self.ocr_max_retries)

        self.concurrency = config.get("ocr_concurrency", self.ocr_concurrency)
        self.batch_size = config.get("ocr_batch_size", self.ocr_batch_size)
        self.batch_rest = config.get("ocr_batch_rest", self.ocr_batch_rest)

        self.resize_max = config.get("ocr_resize_max", self.ocr_resize_max)
        self.image_format = config.get("ocr_image_format", self.ocr_image_format)
        self.image_quality = config.get("ocr_image_quality", self.ocr_image_quality)

        self.page_anchor_enabled = config.get("ocr_page_anchor_enabled", self.ocr_page_anchor_enabled)

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
        self.filter_page_header = config.get("ocr_filter_page_header", False)
        self.filter_page_footer = config.get("ocr_filter_page_footer", False)

        # 初始化 OCR 服务
        ocr_service_config = {
            "ocr_endpoint": self.endpoint,
            "ocr_model": self.model,
            "ocr_api_key": self.api_key or "",  # 确保不是 None
            "ocr_output_format": self.output_format,
            "ocr_max_tokens": self.max_tokens,  # 传递 max_tokens 参数
            "ocr_temperature": self.temperature,
            "ocr_timeout": self.timeout,
            "max_retries": self.max_retries
        }
        self.ocr_service = OcrChandraService(ocr_service_config)

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

    def _parse_noise_patterns(self, patterns_text: str) -> List[str]:
        """解析噪音模式文本为列表"""
        if not patterns_text:
            return []
        return [p.strip() for p in patterns_text.split('\n') if p.strip()]

    def _preprocess_image(self, img: Image.Image) -> Image.Image:
        """
        图像预处理管道

        Args:
            img: 原始图像

        Returns:
            预处理后的图像
        """
        # 1. 调整大小
        img = self._resize_if_needed(img)

        # 2. 颜色空间转换
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
        max_size = self.ocr_resize_max

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

        # 强制使用 JPEG 格式以减小大小
        # PNG 对于 LM Studio 来说太大了
        img_format = "JPEG"
        quality = min(self.ocr_image_quality, 70)  # 限制最大质量为 70（LM Studio 上下文窗口限制）

        # 确保是 RGB 模式（JPEG 不支持 RGBA）
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")

        img.save(buffered, format="JPEG", quality=quality, optimize=True)

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

        # 2. Footnote（脚注）- 保留 <sup> 格式（对齐 Pipeline 模式）
        # Pipeline 模式下脚注保留 <sup>1)</sup> 格式，不转换为 [^n]:
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
            return f"<!-- page-header: {text} -->"

        # 6. Page-Footer（页脚）
        elif label == "page-footer":
            # 页脚通常包含页码，使用小字体或注释
            return f"<!-- page-footer: {text} -->"

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
        # 使用配置的噪音模式，如果没有则使用默认
        noise_patterns = self.noise_patterns if self.noise_patterns else [
            r"Digitized\s+by\s+Google",
            r"Digitized\s+by\s+the\s+Internet\s+Archive",
        ]

        cleaned = []
        for page in markdown_pages:
            for pattern in noise_patterns:
                try:
                    page = re.sub(pattern, '', page, flags=re.IGNORECASE)
                except re.error:
                    pass  # 忽略无效正则
            page = re.sub(r'\n{3,}', '\n\n', page)
            cleaned.append(page.strip())
        return cleaned

    def _fix_footnotes(self, markdown_pages: List[str]) -> List[str]:
        """
        修复脚注格式

        处理：
        1. 未识别的脚注（如 "1) 文本"）添加 <sup> 标签
        2. 重复的括号（如 "<sup>1)</sup>)"）
        3. 统一脚注格式

        Args:
            markdown_pages: Markdown 页面列表

        Returns:
            修复后的页面列表
        """
        fixed = []
        for page in markdown_pages:
            # 1. 修复重复括号：<sup>1)</sup>) -> <sup>1)</sup>
            page = re.sub(r'<sup>(\d+)\)</sup>\)', r'<sup>\1)</sup>', page)

            # 2. 识别未标记的脚注（行首的 "1) 文本" 格式）
            page = re.sub(
                r'^(\d+)\)\s+',
                r'<sup>\1)</sup> ',
                page,
                flags=re.MULTILINE
            )

            fixed.append(page)
        return fixed

    def _filter_page_markers(self, markdown_pages: List[str]) -> List[str]:
        """
        过滤页眉/页脚语法标识，但保留内容

        例如：
        - 输入: <!-- page-header: 0115 -->
        - 输出: 0115

        Args:
            markdown_pages: Markdown 页面列表

        Returns:
            过滤后的页面列表
        """
        filtered = []
        for page_idx, page in enumerate(markdown_pages):
            # 过滤页眉标记，保留内容
            if self.filter_page_header:
                # 匹配 <!-- page-header: 内容 --> 格式（内容可以为空）
                header_pattern = r'<!--\s*page-header:\s*(.*?)\s*-->'
                matches = re.findall(header_pattern, page)

                if matches:
                    logger.info(f"[FILTER] Page {page_idx + 1}: Found page-header(s): {matches}")
                    # 替换为捕获的内容
                    page = re.sub(header_pattern, r'\1', page)
                    logger.info(f"[FILTER] Page {page_idx + 1}: Header filter applied")
                else:
                    # 检查是否有未匹配的页眉注释
                    if '<!-- page-header' in page:
                        logger.warning(f"[FILTER] Page {page_idx + 1}: Found unmatched page-header comment")

            # 过滤页脚标记，保留内容
            if self.filter_page_footer:
                footer_pattern = r'<!--\s*page-footer:\s*(.*?)\s*-->'
                matches = re.findall(footer_pattern, page)

                if matches:
                    logger.info(f"[FILTER] Page {page_idx + 1}: Found page-footer(s): {matches}")
                    page = re.sub(footer_pattern, r'\1', page)
                    logger.info(f"[FILTER] Page {page_idx + 1}: Footer filter applied")
                else:
                    if '<!-- page-footer' in page:
                        logger.warning(f"[FILTER] Page {page_idx + 1}: Found unmatched page-footer comment")

            filtered.append(page.strip())
        return filtered

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
    ) -> Tuple[int, any, str, Tuple[int, int]]:
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

                # 4. 转换为 Markdown
                if isinstance(ocr_output, str):
                    markdown = self._ocr_html_to_markdown(ocr_output)
                else:
                    # JSON 格式，提取文本
                    markdown = "\n\n".join(
                        block.get("text", "")
                        for block in ocr_output.get("blocks", [])
                        if isinstance(block, dict)
                    )

                # 5. 解析输出为 PageGroup
                page = self.parser.parse_to_page(
                    ocr_output,
                    page_num,
                    img_size,
                    self.ocr_service.ocr_output_format
                )

                logger.info(f"Processed page {page_num + 1}, markdown length: {len(markdown)}")
                return (page_num, page, markdown, img_size)

            except Exception as e:
                logger.error(f"Failed to process page {page_num + 1}: {e}")
                # 返回空页面
                from aih_contexture.schema.polygon import PolygonBox
                from aih_contexture.schema.groups.page import PageGroup
                page_polygon = PolygonBox.from_bbox([0, 0, img.width, img.height])
                empty_page = PageGroup(
                    page_id=page_num,
                    polygon=page_polygon,
                    structure=[]
                )
                return (page_num, empty_page, "", img.size)

    async def _convert_page_async_no_semaphore(
        self,
        session: aiohttp.ClientSession,
        img: Image.Image,
        page_num: int
    ) -> Tuple[int, any, str, Tuple[int, int]]:
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

            # 4. 转换为 Markdown
            if isinstance(ocr_output, str):
                markdown = self._ocr_html_to_markdown(ocr_output)
            else:
                markdown = "\n\n".join(
                    block.get("text", "")
                    for block in ocr_output.get("blocks", [])
                    if isinstance(block, dict)
                )

            # 5. 解析输出为 PageGroup
            page = self.parser.parse_to_page(
                ocr_output,
                page_num,
                img_size,
                self.ocr_service.ocr_output_format
            )

            logger.info(f"Processed page {page_num + 1}")
            return (page_num, page, markdown, img_size)

        except Exception as e:
            logger.error(f"Failed to process page {page_num + 1}: {e}")
            from aih_contexture.schema.polygon import PolygonBox
            from aih_contexture.schema.groups.page import PageGroup
            page_polygon = PolygonBox.from_bbox([0, 0, img.width, img.height])
            empty_page = PageGroup(
                page_id=page_num,
                polygon=page_polygon,
                structure=[]
            )
            return (page_num, empty_page, "", img.size)

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
        concurrency = self.ocr_concurrency

        async with aiohttp.ClientSession() as session:
            # 将 batch 分成小批次，每批 = 并发数
            for sub_batch_start in range(0, len(batch), concurrency):
                sub_batch = batch[sub_batch_start:sub_batch_start + concurrency]
                sub_batch_idx = batch_start_idx + sub_batch_start

                logger.info(f"Processing sub-batch: {len(sub_batch)} pages (concurrency={concurrency})")
                print(f"\n{'='*60}")
                print(f"[STRICT BATCH] Starting sub-batch with {len(sub_batch)} pages")
                print(f"[STRICT BATCH] Concurrency setting: {concurrency}")
                print(f"{'='*60}\n")

                # 创建当前小批次的所有任务
                tasks = []
                for idx, img in enumerate(sub_batch):
                    page_num = sub_batch_idx + idx
                    # 不使用 semaphore，直接并行
                    task = self._convert_page_async_no_semaphore(session, img, page_num)
                    tasks.append(task)

                # 等待当前小批次全部完成
                print(f"[STRICT BATCH] Waiting for all {len(tasks)} tasks to complete...")
                sub_results = await asyncio.gather(*tasks, return_exceptions=True)
                print(f"[STRICT BATCH] Sub-batch completed! {len(sub_results)} results")
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

        # 2. 批处理
        all_results = []
        for batch_idx in range(0, len(pages_images), self.ocr_batch_size):
            batch = pages_images[batch_idx:batch_idx + self.ocr_batch_size]
            batch_num = batch_idx // self.ocr_batch_size + 1
            total_batches = (len(pages_images) + self.ocr_batch_size - 1) // self.ocr_batch_size

            logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} pages)")

            # 3. 并发处理批次（传递全局信号量）
            batch_results = await self._process_batch_async(batch, batch_idx, global_semaphore)
            all_results.extend(batch_results)

            # 4. 批次间休息
            if batch_idx + self.ocr_batch_size < len(pages_images):
                logger.info(f"Resting for {self.ocr_batch_rest} seconds...")
                await asyncio.sleep(self.ocr_batch_rest)

        # 5. 按页码排序
        all_results.sort(key=lambda x: x[0])

        # 6. 提取 pages 和 markdown_pages
        pages = [result[1] for result in all_results]
        markdown_pages = [result[2] for result in all_results]

        # 7. 提取印刷页码（如果启用）
        printed_pages = None
        if self.printed_page_extractor:
            logger.info("Extracting printed pages...")
            markdown_pages, printed_pages = self.printed_page_extractor.extract_batch(markdown_pages)
            found_count = sum(1 for p in printed_pages if p is not None)
            logger.info(f"Found {found_count} printed pages")

        # 8. 清理页面分隔符（避免嵌套）
        logger.info("Cleaning page separators...")
        markdown_pages = self._clean_page_separators(markdown_pages)

        # 8.5 移除噪音（水印等）
        if self.noise_removal_enabled:
            logger.info("Removing noise...")
            markdown_pages = self._remove_noise(markdown_pages)

        # 8.6 修复脚注格式
        if self.footnote_fix_enabled:
            logger.info("Fixing footnotes...")
            markdown_pages = self._fix_footnotes(markdown_pages)

        # 8.7 过滤页眉/页脚标记
        if self.filter_page_header or self.filter_page_footer:
            logger.info("Filtering page markers...")
            markdown_pages = self._filter_page_markers(markdown_pages)

        # 9. 添加页码锚点（如果启用）
        if self.page_anchor_plugin and self.page_anchor_plugin.enabled:
            logger.info("Adding page anchors...")
            markdown_pages = self.page_anchor_plugin.process_pages(markdown_pages, printed_pages)

        # 10. 拼接所有页面
        page_separator = "\n\n---\n\n"
        full_markdown = page_separator.join(markdown_pages)

        # 11. 添加文档末尾的额外锚点（用于区间提取）
        if self.page_anchor_plugin and self.page_anchor_plugin.enabled:
            page_count = len(pages_images)
            final_anchor = f"{{{page_count}}}"
            full_markdown += f"\n\n{final_anchor}"
            logger.info(f"Added final anchor: {final_anchor}")

        elapsed_time = time.time() - start_time
        logger.info(f"OCR Direct conversion completed in {elapsed_time:.1f}s")
        logger.info(f"Total: {len(full_markdown)} chars")
        logger.info(f"Speed: {len(pages_images) / elapsed_time:.2f} pages/sec")

        return full_markdown
