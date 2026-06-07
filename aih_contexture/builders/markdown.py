"""
Markdown Document Builder

将Markdown字符串解析成Document对象,使VLM模式可以使用渲染器系统。

特性:
- 解析Markdown为Document结构
- 支持页面分隔符
- 创建轻量级Block对象
- 兼容现有渲染器系统
"""

import re
from typing import List, Optional

from aih_contexture.schema import BlockTypes
from aih_contexture.schema.blocks import Block, Text
from aih_contexture.schema.blocks.base import BlockMetadata
from aih_contexture.schema.document import Document
from aih_contexture.schema.groups.page import PageGroup
from aih_contexture.schema.polygon import PolygonBox
from aih_contexture.logger import get_logger

logger = get_logger()


class MarkdownDocumentBuilder:
    """
    将Markdown字符串构建成Document对象

    配置参数:
    - page_separator: 页面分隔符 (默认: "\\n\\n---\\n\\n")
    - page_width: 虚拟页面宽度 (默认: 612, 标准Letter)
    - page_height: 虚拟页面高度 (默认: 792, 标准Letter)
    - extract_page_anchors: 是否提取页码锚点 (默认: True)
    """

    def __init__(
        self,
        page_separator: str = "\n\n---\n\n",
        page_width: float = 612.0,
        page_height: float = 792.0,
        extract_page_anchors: bool = True,
    ):
        self.page_separator = page_separator
        self.page_width = page_width
        self.page_height = page_height
        self.extract_page_anchors = extract_page_anchors

        # 页码锚点正则 (匹配 {1}, {2}, {{1}}, [[1]] 等格式)
        self.page_anchor_pattern = re.compile(r'[\{\[]+(\d+)[\}\]]+')

    def build(self, markdown: str, filepath: str = "vlm_generated.md") -> Document:
        """
        从Markdown字符串构建Document对象

        Args:
            markdown: Markdown字符串
            filepath: 文件路径 (用于Document元数据)

        Returns:
            Document对象
        """
        # 分割页面
        page_contents = self._split_pages(markdown)

        # 构建PageGroup列表
        pages = []
        for page_id, content in enumerate(page_contents):
            page = self._build_page(page_id, content)
            pages.append(page)

        # 创建Document
        document = Document(
            filepath=filepath,
            pages=pages,
            table_of_contents=None,  # VLM模式暂不支持TOC
        )

        logger.info(f"Built Document from Markdown: {len(pages)} pages")
        return document

    def _split_pages(self, markdown: str) -> List[str]:
        """
        分割Markdown为页面

        支持两种模式:
        1. 使用page_separator分隔
        2. 提取页码锚点并分割
        """
        if self.extract_page_anchors:
            # 尝试通过页码锚点分割
            pages = self._split_by_anchors(markdown)
            if pages:
                return pages

        # 回退到分隔符分割
        if self.page_separator in markdown:
            pages = markdown.split(self.page_separator)
            return [p.strip() for p in pages if p.strip()]

        # 没有分隔符,整个文档作为一页
        return [markdown]

    def _split_by_anchors(self, markdown: str) -> Optional[List[str]]:
        """
        通过页码锚点分割页面

        查找 {1}, {2}, {{1}}, [[1]] 等格式的页码标记
        """
        # 查找所有页码锚点
        matches = list(self.page_anchor_pattern.finditer(markdown))
        if not matches:
            return None

        # 检查是否是连续的页码
        page_numbers = [int(m.group(1)) for m in matches]
        if page_numbers != list(range(1, len(page_numbers) + 1)):
            logger.warning(f"Page anchors not sequential: {page_numbers}")
            return None

        # 按锚点位置分割
        pages = []
        for i, match in enumerate(matches):
            start = match.end()  # 锚点之后开始
            end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
            page_content = markdown[start:end].strip()
            if page_content:
                pages.append(page_content)

        return pages if pages else None

    def _build_page(self, page_id: int, content: str) -> PageGroup:
        """
        构建单个PageGroup

        创建一个包含单个Text block的简化页面
        """
        # 创建虚拟的页面边界框
        page_polygon = PolygonBox(
            polygon=[
                [0, 0],
                [self.page_width, 0],
                [self.page_width, self.page_height],
                [0, self.page_height],
            ]
        )

        # 创建Text block
        text_block = Text(
            block_type=BlockTypes.Text,
            polygon=page_polygon,  # 使用整个页面作为边界
            page_id=page_id,
            block_id=0,
            html=self._markdown_to_html(content),  # 简单转换
            metadata=BlockMetadata(),
        )

        # 创建PageGroup
        page = PageGroup(
            page_id=page_id,
            polygon=page_polygon,
            children=[text_block],
            structure=[text_block.id],
            lowres_image=None,  # VLM模式不需要图像
            highres_image=None,
        )

        return page

    def _markdown_to_html(self, markdown: str) -> str:
        """
        简单的Markdown到HTML转换

        注意: 这是一个简化版本,渲染器会进一步处理
        """
        # 保持原始Markdown,渲染器会处理转换
        # 这里只做基本的段落包装
        lines = markdown.split("\n")
        html_lines = []

        for line in lines:
            if line.strip():
                html_lines.append(f"<p>{line}</p>")
            else:
                html_lines.append("<br/>")

        return "\n".join(html_lines)