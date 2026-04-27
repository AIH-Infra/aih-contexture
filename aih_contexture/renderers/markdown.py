import re
from collections import defaultdict
from typing import Annotated, Tuple

import regex
import six
from bs4 import NavigableString
from markdownify import MarkdownConverter, re_whitespace
from aih_contexture.logger import get_logger
from pydantic import BaseModel

from aih_contexture.renderers.html import HTMLRenderer
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document
from aih_contexture.formatters import PageAnchorFormatter, CustomIDInjector
from aih_contexture.postprocess import MarkdownPostprocessEngine

logger = get_logger()


def escape_dollars(text):
    return text.replace("$", r"\$")


def cleanup_text(full_text):
    full_text = re.sub(r"\n{3,}", "\n\n", full_text)
    full_text = re.sub(r"(\n\s){3,}", "\n\n", full_text)
    return full_text.strip()


def normalize_page_comment_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip().lower()


def sanitize_page_comment_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text)).replace("--", "- -").strip()


def get_formatted_table_text(element):
    text = []
    for content in element.contents:
        if content is None:
            continue

        if isinstance(content, NavigableString):
            stripped = content.strip()
            if stripped:
                text.append(escape_dollars(stripped))
        elif content.name == "br":
            text.append("<br>")
        elif content.name == "math":
            text.append("$" + content.text + "$")
        else:
            content_str = escape_dollars(str(content))
            text.append(content_str)

    full_text = ""
    for i, t in enumerate(text):
        if t == "<br>":
            full_text += t
        elif i > 0 and text[i - 1] != "<br>":
            full_text += " " + t
        else:
            full_text += t
    return full_text


class Markdownify(MarkdownConverter):
    def __init__(
        self,
        paginate_output,
        page_separator,
        inline_math_delimiters,
        block_math_delimiters,
        html_tables_in_markdown,
        page_anchor_formatter=None,
        custom_id_injector=None,
        emit_page_header_comment=False,
        emit_page_footer_comment=False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.paginate_output = paginate_output
        self.page_separator = page_separator
        self.inline_math_delimiters = inline_math_delimiters
        self.block_math_delimiters = block_math_delimiters
        self.html_tables_in_markdown = html_tables_in_markdown
        self.page_anchor_formatter = page_anchor_formatter or PageAnchorFormatter()
        self.custom_id_injector = custom_id_injector
        self.emit_page_header_comment = emit_page_header_comment
        self.emit_page_footer_comment = emit_page_footer_comment
        self.page_image_description_counts = defaultdict(int)

    def convert_div(self, el, text, parent_tags):
        is_page = el.has_attr("class") and el["class"][0] == "page"
        if self.paginate_output and is_page:
            page_id = int(el["data-page-id"])
            printed_page_id = el.get("data-printed-page", "")
            page_header_text = sanitize_page_comment_text(el.get("data-page-header", ""))
            page_footer_text = sanitize_page_comment_text(el.get("data-page-footer", ""))
            if not printed_page_id:
                printed_page_id = None

            # 如果没有印刷页码，尝试从 CustomIDInjector 获取
            if not printed_page_id and self.custom_id_injector:
                printed_page_id = self.custom_id_injector.get_custom_id(page_id)

            # 使用格式化器生成页锚点
            page_anchor = self.page_anchor_formatter.format(page_id, printed_page_id)

            # 生成页码标记（如果有印刷页码或自定义编号）
            page_tag = ""
            if printed_page_id:
                page_tag = f"<!-- Page: {printed_page_id} -->\n"

            comment_lines = []
            seen_comments = set()
            normalized_printed_page = normalize_page_comment_text(printed_page_id)

            if self.emit_page_header_comment and page_header_text:
                normalized_header = normalize_page_comment_text(page_header_text)
                if normalized_header and normalized_header != normalized_printed_page:
                    seen_comments.add(normalized_header)
                    comment_lines.append(f"<!-- page-header: {page_header_text} -->")

            if self.emit_page_footer_comment and page_footer_text:
                normalized_footer = normalize_page_comment_text(page_footer_text)
                if normalized_footer and normalized_footer != normalized_printed_page and normalized_footer not in seen_comments:
                    comment_lines.append(f"<!-- page-footer: {page_footer_text} -->")

            comment_block = ""
            if comment_lines:
                comment_block = "\n".join(comment_lines) + "\n"

            # 调整顺序：{n} -> 分页符 -> <!-- Page: X -->
            pagination_item = (
                "\n\n" + page_anchor + "\n" + self.page_separator + "\n" + comment_block + page_tag + "\n"
            )
            return pagination_item + text
        else:
            return text

    def convert_p(self, el, text, parent_tags):
        if el.get("role") == "img" and el.get("data-original-image-id"):
            page_key = self._current_page_key(el)
            self.page_image_description_counts[page_key] += 1
            image_index = self.page_image_description_counts[page_key]
            description_text = sanitize_page_comment_text(text)
            if not description_text:
                return ""
            return f"\n\n<!-- image-description-{image_index}: {description_text} -->\n\n"

        hyphens = r"-—¬"
        has_continuation = el.has_attr("class") and "has-continuation" in el["class"]
        if has_continuation:
            block_type = BlockTypes[el["block-type"]]
            if block_type in [BlockTypes.TextInlineMath, BlockTypes.Text]:
                if regex.compile(
                    rf".*[\p{{Ll}}|\d][{hyphens}]\s?$", regex.DOTALL
                ).match(text):  # handle hypenation across pages
                    return regex.split(rf"[{hyphens}]\s?$", text)[0]
                return f"{text} "
            if block_type == BlockTypes.ListGroup:
                return f"{text}"
        return f"{text}\n\n" if text else ""  # default convert_p behavior

    def _current_page_key(self, el) -> str:
        page_container = el.find_parent(
            lambda tag: tag.name == "div"
            and tag.has_attr("class")
            and "page" in tag.get("class", [])
        )
        if page_container and page_container.has_attr("data-page-id"):
            return str(page_container["data-page-id"])
        return "global"

    def convert_math(self, el, text, parent_tags):
        block = el.has_attr("display") and el["display"] == "block"
        if block:
            return (
                "\n"
                + self.block_math_delimiters[0]
                + text.strip()
                + self.block_math_delimiters[1]
                + "\n"
            )
        else:
            return (
                " "
                + self.inline_math_delimiters[0]
                + text.strip()
                + self.inline_math_delimiters[1]
                + " "
            )

    def convert_table(self, el, text, parent_tags):
        if self.html_tables_in_markdown:
            return "\n\n" + str(el) + "\n\n"

        total_rows = len(el.find_all("tr"))
        colspans = []
        rowspan_cols = defaultdict(int)
        for i, row in enumerate(el.find_all("tr")):
            row_cols = rowspan_cols[i]
            for cell in row.find_all(["td", "th"]):
                colspan = int(cell.get("colspan", 1))
                row_cols += colspan
                for r in range(int(cell.get("rowspan", 1)) - 1):
                    rowspan_cols[i + r] += (
                        colspan  # Add the colspan to the next rows, so they get the correct number of columns
                    )
            colspans.append(row_cols)
        total_cols = max(colspans) if colspans else 0

        grid = [[None for _ in range(total_cols)] for _ in range(total_rows)]

        for row_idx, tr in enumerate(el.find_all("tr")):
            col_idx = 0
            for cell in tr.find_all(["td", "th"]):
                # Skip filled positions
                while col_idx < total_cols and grid[row_idx][col_idx] is not None:
                    col_idx += 1

                # Fill in grid
                value = (
                    get_formatted_table_text(cell)
                    .replace("\n", " ")
                    .replace("|", " ")
                    .strip()
                )
                rowspan = int(cell.get("rowspan", 1))
                colspan = int(cell.get("colspan", 1))

                if col_idx >= total_cols:
                    # Skip this cell if we're out of bounds
                    continue

                for r in range(rowspan):
                    for c in range(colspan):
                        try:
                            if r == 0 and c == 0:
                                grid[row_idx][col_idx] = value
                            else:
                                grid[row_idx + r][col_idx + c] = (
                                    ""  # Empty cell due to rowspan/colspan
                                )
                        except IndexError:
                            # Sometimes the colspan/rowspan predictions can overflow
                            logger.info(
                                f"Overflow in columns: {col_idx + c} >= {total_cols} or rows: {row_idx + r} >= {total_rows}"
                            )
                            continue

                col_idx += colspan

        markdown_lines = []
        col_widths = [0] * total_cols
        for row in grid:
            for col_idx, cell in enumerate(row):
                if cell is not None:
                    col_widths[col_idx] = max(col_widths[col_idx], len(str(cell)))

        def add_header_line():
            markdown_lines.append(
                "|" + "|".join("-" * (width + 2) for width in col_widths) + "|"
            )

        # Generate markdown rows
        added_header = False
        for i, row in enumerate(grid):
            is_empty_line = all(not cell for cell in row)
            if is_empty_line and not added_header:
                # Skip leading blank lines
                continue

            line = []
            for col_idx, cell in enumerate(row):
                if cell is None:
                    cell = ""
                padding = col_widths[col_idx] - len(str(cell))
                line.append(f" {cell}{' ' * padding} ")
            markdown_lines.append("|" + "|".join(line) + "|")

            if not added_header:
                # Skip empty lines when adding the header row
                add_header_line()
                added_header = True

        # Handle one row tables
        if total_rows == 1:
            add_header_line()

        table_md = "\n".join(markdown_lines)
        return "\n\n" + table_md + "\n\n"

    def convert_a(self, el, text, parent_tags):
        text = self.escape(text)
        # Escape brackets and parentheses in text
        text = re.sub(r"([\[\]()])", r"\\\1", text)
        return super().convert_a(el, text, parent_tags)

    def convert_span(self, el, text, parent_tags):
        if el.get("id"):
            return f'<span id="{el["id"]}">{text}</span>'
        else:
            return text

    def escape(self, text, parent_tags=None):
        text = super().escape(text, parent_tags)
        if self.options["escape_dollars"]:
            text = text.replace("$", r"\$")

        # 🔧 修复：转义行首的 # 符号，防止被误认为 Markdown 标题
        # 只转义行首的 #，不转义行中的 #
        lines = text.split('\n')
        escaped_lines = []
        for line in lines:
            # 如果行首是 # 后跟空格（Markdown 标题语法），则转义
            if line.lstrip().startswith('# '):
                # 保留前导空格，只转义 #
                leading_spaces = len(line) - len(line.lstrip())
                escaped_line = ' ' * leading_spaces + '\\' + line.lstrip()
                escaped_lines.append(escaped_line)
            else:
                escaped_lines.append(line)
        text = '\n'.join(escaped_lines)

        return text

    def process_text(self, el, parent_tags=None):
        text = six.text_type(el) or ""

        # normalize whitespace if we're not inside a preformatted element
        if not el.find_parent("pre"):
            text = re_whitespace.sub(" ", text)

        # escape special characters if we're not inside a preformatted or code element
        if not el.find_parent(["pre", "code", "kbd", "samp", "math"]):
            text = self.escape(text)

        # remove trailing whitespaces if any of the following condition is true:
        # - current text node is the last node in li
        # - current text node is followed by an embedded list
        if el.parent.name == "li" and (
            not el.next_sibling or el.next_sibling.name in ["ul", "ol"]
        ):
            text = text.rstrip()

        return text


class MarkdownFormatter:
    """Markdown 格式化器（后处理）"""

    def format(self, markdown_text: str) -> str:
        """格式化 Markdown 文本"""
        # 1. 修正标题格式
        markdown_text = self._fix_headers(markdown_text)

        # 2. 修正列表格式
        markdown_text = self._fix_lists(markdown_text)

        # 3. 修正代码块
        markdown_text = self._fix_code_blocks(markdown_text)

        # 4. 修正表格
        markdown_text = self._fix_tables(markdown_text)

        # 5. 统一空行
        markdown_text = self._normalize_spacing(markdown_text)

        return markdown_text

    def _fix_headers(self, text: str) -> str:
        """确保标题 # 后有空格"""
        # 确保 # 后有空格
        text = re.sub(r'^(#{1,6})([^\s#])', r'\1 \2', text, flags=re.MULTILINE)
        # 移除标题末尾多余空格
        text = re.sub(r'^(#{1,6}\s+.+?)\s+$', r'\1', text, flags=re.MULTILINE)
        return text

    def _fix_lists(self, text: str) -> str:
        """确保列表标记后有空格"""
        # 无序列表
        text = re.sub(r'^(\s*[-*+])([^\s])', r'\1 \2', text, flags=re.MULTILINE)
        # 有序列表
        text = re.sub(r'^(\s*\d+\.)([^\s])', r'\1 \2', text, flags=re.MULTILINE)
        return text

    def _fix_code_blocks(self, text: str) -> str:
        """修正代码块标记"""
        # 确保代码块前后有空行
        text = re.sub(r'([^\n])\n```', r'\1\n\n```', text)
        text = re.sub(r'```\n([^\n])', r'```\n\n\1', text)
        return text

    def _fix_tables(self, text: str) -> str:
        """修正表格格式"""
        # 确保表格单元格有空格
        text = re.sub(r'\|([^\s|])', r'| \1', text)
        text = re.sub(r'([^\s|])\|', r'\1 |', text)
        return text

    def _normalize_spacing(self, text: str) -> str:
        """统一空行"""
        # 最多两个连续换行
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text


class MarkdownOutput(BaseModel):
    markdown: str
    images: dict
    metadata: dict


class MarkdownRenderer(HTMLRenderer):
    page_separator: Annotated[
        str, "The separator to use between pages.", "Default is '-' * 48."
    ] = "-" * 48
    inline_math_delimiters: Annotated[
        Tuple[str], "The delimiters to use for inline math."
    ] = ("$", "$")
    block_math_delimiters: Annotated[
        Tuple[str], "The delimiters to use for block math."
    ] = ("$$", "$$")
    html_tables_in_markdown: Annotated[
        bool, "Return tables formatted as HTML, instead of in markdown"
    ] = False

    # Markdown 格式化配置
    markdown_formatting_enabled: Annotated[
        bool, "启用 Markdown 格式化（修正语法错误）"
    ] = True
    markdown_postprocess_enabled: Annotated[
        bool, "启用共享 Markdown 后处理引擎"
    ] = False
    markdown_postprocess_review_only: Annotated[
        bool, "Markdown 后处理仅 review，不覆盖原语义"
    ] = True
    markdown_postprocess_enable_cleanup: Annotated[
        bool, "Markdown 后处理中的基础清理"
    ] = True
    markdown_postprocess_enable_printed_page_repair: Annotated[
        bool, "Markdown 后处理中的印刷页码修正"
    ] = False
    markdown_postprocess_enable_llm: Annotated[
        bool, "Markdown 后处理中的 LLM 辅助"
    ] = False
    markdown_postprocess_llm_provider: Annotated[
        str, "Markdown 后处理 LLM 提供方"
    ] = "openai"
    markdown_postprocess_llm_base_url: Annotated[
        str | None, "Markdown 后处理 LLM Base URL"
    ] = None
    markdown_postprocess_llm_model: Annotated[
        str | None, "Markdown 后处理 LLM 模型"
    ] = None
    markdown_postprocess_llm_api_key: Annotated[
        str | None, "Markdown 后处理 LLM API Key"
    ] = None
    markdown_postprocess_llm_timeout: Annotated[
        int, "Markdown 后处理 LLM 超时秒数"
    ] = 60
    markdown_postprocess_llm_max_retries: Annotated[
        int, "Markdown 后处理 LLM 最大重试次数"
    ] = 1
    markdown_postprocess_strict_null_policy: Annotated[
        bool, "Markdown 后处理严格空值策略"
    ] = True

    # 自定义编号配置
    custom_id_source: Annotated[
        str, "Custom ID source: none, vlm, file, list, auto"
    ] = "none"
    custom_id_data: Annotated[
        any, "Custom ID data (depends on source type)"
    ] = None

    @property
    def md_cls(self):
        # 使用简化的 PageAnchorFormatter（固定 {n} 格式）
        formatter = PageAnchorFormatter(wrapper="{{{}}}")

        # 初始化 CustomIDInjector
        custom_id_injector = None
        if self.custom_id_source != "none":
            custom_id_injector = CustomIDInjector(self.custom_id_source, self.custom_id_data)

        return Markdownify(
            self.paginate_output,
            self.page_separator,
            heading_style="ATX",
            bullets="-",
            escape_misc=False,
            escape_underscores=True,
            escape_asterisks=True,
            escape_dollars=True,
            sub_symbol="<sub>",
            sup_symbol="<sup>",
            inline_math_delimiters=self.inline_math_delimiters,
            block_math_delimiters=self.block_math_delimiters,
            html_tables_in_markdown=self.html_tables_in_markdown,
            page_anchor_formatter=formatter,
            custom_id_injector=custom_id_injector,
            emit_page_header_comment=self.emit_page_header_comment,
            emit_page_footer_comment=self.emit_page_footer_comment,
        )

    def __call__(self, document: Document) -> MarkdownOutput:
        document_output = document.render(self.block_config)
        full_html, images = self.extract_html(document, document_output)
        markdown = self.md_cls.convert(full_html)
        markdown = cleanup_text(markdown)

        # 🆕 Markdown 格式化
        if self.markdown_formatting_enabled:
            formatter = MarkdownFormatter()
            markdown = formatter.format(markdown)

        # Ensure we set the correct blanks for pagination markers
        if self.paginate_output:
            if not markdown.startswith("\n\n"):
                markdown = "\n\n" + markdown
            if markdown.endswith(self.page_separator):
                markdown += "\n\n"

            # 添加额外锚点（用于区间提取）
            page_count = len(document.pages)
            final_anchor = f"{{{page_count}}}"
            markdown += f"\n\n{final_anchor}"

        if self.markdown_postprocess_enabled:
            engine = MarkdownPostprocessEngine({
                "markdown_postprocess_enabled": self.markdown_postprocess_enabled,
                "markdown_postprocess_review_only": self.markdown_postprocess_review_only,
                "markdown_postprocess_enable_cleanup": self.markdown_postprocess_enable_cleanup,
                "markdown_postprocess_enable_printed_page_repair": self.markdown_postprocess_enable_printed_page_repair,
                "markdown_postprocess_enable_llm": self.markdown_postprocess_enable_llm,
                "markdown_postprocess_llm_provider": self.markdown_postprocess_llm_provider,
                "markdown_postprocess_llm_base_url": self.markdown_postprocess_llm_base_url,
                "markdown_postprocess_llm_model": self.markdown_postprocess_llm_model,
                "markdown_postprocess_llm_api_key": self.markdown_postprocess_llm_api_key,
                "markdown_postprocess_llm_timeout": self.markdown_postprocess_llm_timeout,
                "markdown_postprocess_llm_max_retries": self.markdown_postprocess_llm_max_retries,
                "markdown_postprocess_strict_null_policy": self.markdown_postprocess_strict_null_policy,
            })
            result = engine.process(markdown)
            markdown = result.markdown

        return MarkdownOutput(
            markdown=markdown,
            images=images,
            metadata=self.generate_document_metadata(document, document_output),
        )
