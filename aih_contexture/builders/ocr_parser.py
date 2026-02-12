"""
OCR Parser

将 OCR 输出解析为 Marker 的 Block 结构
"""

from typing import Dict, Any, List, Tuple, Optional
from PIL import Image
import json
from bs4 import BeautifulSoup

from aih_contexture.logger import get_logger
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.polygon import PolygonBox
from aih_contexture.schema.groups.page import PageGroup
from aih_contexture.schema.blocks.text import Text
from aih_contexture.schema.blocks.sectionheader import SectionHeader
from aih_contexture.schema.blocks.table import Table
from aih_contexture.schema.blocks.figure import Figure
from aih_contexture.schema.blocks.equation import Equation
from aih_contexture.schema.blocks.pageheader import PageHeader
from aih_contexture.schema.blocks.pagefooter import PageFooter
from aih_contexture.schema.blocks.caption import Caption
from aih_contexture.schema.blocks.footnote import Footnote
from aih_contexture.schema.blocks.code import Code
from aih_contexture.schema.blocks.form import Form
from aih_contexture.schema.blocks.picture import Picture
from aih_contexture.schema.blocks.toc import TableOfContents
from aih_contexture.schema.blocks.listitem import ListItem
from aih_contexture.schema.text.line import Line
from aih_contexture.schema.text.span import Span

logger = get_logger()


class OcrParser:
    """
    OCR 输出解析器

    将 OCR 模型的输出 (JSON/HTML/Markdown) 解析为 Marker 的 Block 结构
    """

    def __init__(self, config=None):
        self.config = config or {}

        # 块类型映射（完整支持 Chandra 15 种标签）
        self.type_map = {
            "text": Text,
            "section_header": SectionHeader,
            "table": Table,
            "figure": Figure,
            "equation": Equation,
            "page_header": PageHeader,
            "page_footer": PageFooter,
            "caption": Caption,
            "footnote": Footnote,
            "code": Code,
            "form": Form,
            "picture": Picture,
            "toc": TableOfContents,
            "list_group": ListItem,  # 列表组映射到 ListItem
        }

        # 需要保留 HTML 结构的类型
        self.html_preserve_types = {
            "table",      # 表格
            "equation",   # 公式（含 <math> 标签）
            "code",       # 代码块（含 <pre>/<code> 标签）
            "list_group", # 列表（含 <ul>/<ol>/<li> 标签）
            "form",       # 表单（含 <input> 等标签）
        }

    def _bbox_to_polygon(self, bbox: List[float], page_size: Tuple[int, int]) -> PolygonBox:
        """
        将 bbox 坐标转换为 PolygonBox

        Args:
            bbox: [x1, y1, x2, y2] 格式的坐标
            page_size: (width, height) 页面尺寸

        Returns:
            PolygonBox 对象
        """
        if not bbox or len(bbox) != 4:
            # 返回默认的小框
            return PolygonBox.from_bbox([0, 0, 100, 100])

        x1, y1, x2, y2 = bbox

        # 确保坐标在页面范围内
        x1 = max(0, min(x1, page_size[0]))
        x2 = max(0, min(x2, page_size[0]))
        y1 = max(0, min(y1, page_size[1]))
        y2 = max(0, min(y2, page_size[1]))

        return PolygonBox.from_bbox([x1, y1, x2, y2])

    def _create_block(
        self,
        text: str,
        polygon: PolygonBox,
        block_type: str,
        page_id: int
    ):
        """
        创建 Block 对象（简化版，直接使用 html 字段）

        Args:
            text: 文本内容（表格为 HTML，其他为纯文本）
            polygon: PolygonBox 坐标
            block_type: 块类型字符串
            page_id: 页面 ID

        Returns:
            Block 对象
        """
        # 获取 Block 类
        block_cls = self.type_map.get(block_type, Text)

        # 结构化内容直接使用 HTML；其他类型包装在 <p> 中
        if block_type in self.html_preserve_types:
            html_content = text  # 已经是 HTML 格式
        else:
            html_content = f"<p>{text}</p>"

        block = block_cls(
            polygon=polygon,
            html=html_content,
            page_id=page_id,
        )

        return block

        return block

    def parse_chandra_html_to_page(
        self,
        html: str,
        page_id: int,
        page_size: Tuple[int, int],
        bbox_scale: int = 1024
    ) -> PageGroup:
        """
        解析 Chandra 输出的 HTML 为 PageGroup

        Args:
            html: Chandra 返回的 HTML（带 data-bbox 和 data-label）
            page_id: 页面 ID
            page_size: (width, height) 页面尺寸
            bbox_scale: 坐标归一化范围（默认 1024）

        Returns:
            PageGroup 对象
        """
        soup = BeautifulSoup(html, "html.parser")
        top_level_divs = soup.find_all("div", recursive=False)

        width_scaler = page_size[0] / bbox_scale
        height_scaler = page_size[1] / bbox_scale

        blocks = []

        for idx, div in enumerate(top_level_divs):
            try:
                # 1. 提取 bbox
                bbox_str = div.get("data-bbox")
                if not bbox_str:
                    logger.warning(f"Block {idx}: Missing data-bbox, skipping")
                    continue

                # 2. 解析 bbox
                try:
                    bbox = json.loads(bbox_str)
                    if not isinstance(bbox, list) or len(bbox) != 4:
                        raise ValueError(f"Invalid bbox format: {bbox}")
                except Exception as e:
                    logger.warning(f"Block {idx}: Failed to parse bbox '{bbox_str}': {e}")
                    continue

                # 3. 转换为实际像素坐标
                bbox_pixels = [
                    max(0, int(bbox[0] * width_scaler)),
                    max(0, int(bbox[1] * height_scaler)),
                    min(int(bbox[2] * width_scaler), page_size[0]),
                    min(int(bbox[3] * height_scaler), page_size[1])
                ]

                # 4. 提取标签
                label = div.get("data-label", "Text")

                # 5. 提取内容
                content_html = str(div.decode_contents())

                # 6. 映射标签
                block_type = self._map_chandra_label(label)

                # 7. 根据类型决定是否保留 HTML 结构
                if block_type in self.html_preserve_types:
                    # 结构化内容：保留 HTML
                    text = content_html.strip()
                    if not text:
                        logger.warning(f"Block {idx}: Empty {block_type}, skipping")
                        continue
                else:
                    # 其他类型：提取纯文本
                    text = BeautifulSoup(content_html, "html.parser").get_text()
                    text = text.strip()
                    if not text:
                        logger.warning(f"Block {idx}: Empty text, skipping")
                        continue

                # 8. 创建 PolygonBox
                polygon = PolygonBox.from_bbox(bbox_pixels)

                # 9. 创建 Block
                block = self._create_block(text, polygon, block_type, page_id)
                blocks.append(block)

                logger.info(f"Block {idx}: type={block_type}, label={label}, text_len={len(text)}")

            except Exception as e:
                logger.error(f"Block {idx}: Failed to parse: {e}")
                continue

        # 9. 给每个 block 分配 block_id 并创建 BlockId 引用
        from aih_contexture.schema.blocks.base import BlockId
        structure = []
        for i, block in enumerate(blocks):
            block.block_id = i
            block.page_id = page_id
            # 创建 BlockId 引用
            block_id_ref = BlockId(
                page_id=page_id,
                block_id=i,
                block_type=block.block_type
            )
            structure.append(block_id_ref)

        # 10. 创建 PageGroup（同时设置 children 和 structure）
        page_polygon = PolygonBox.from_bbox([0, 0, page_size[0], page_size[1]])
        page = PageGroup(
            page_id=page_id,
            polygon=page_polygon,
            children=blocks,
            structure=structure
        )

        logger.info(f"Page {page_id}: Created PageGroup with {len(blocks)} blocks")
        return page

    def _map_chandra_label(self, label: str) -> str:
        """
        映射 Chandra 标签到 Marker BlockTypes

        Chandra 标签 (15种，支持大小写):
        """
        mapping = {
            # 大写版本
            "Caption": "caption",
            "Footnote": "footnote",
            "Equation-Block": "equation",
            "List-Group": "list_group",
            "Page-Header": "page_header",
            "Page-Footer": "page_footer",
            "Image": "picture",
            "Section-Header": "section_header",
            "Table": "table",
            "Text": "text",
            "Complex-Block": "text",
            "Code-Block": "code",
            "Form": "form",
            "Table-Of-Contents": "toc",
            "Figure": "figure",
            # 小写版本
            "caption": "caption",
            "footnote": "footnote",
            "equation": "equation",
            "list": "list_group",
            "page-header": "page_header",
            "page-footer": "page_footer",
            "image": "picture",
            "section": "section_header",
            "table": "table",
            "text": "text",
            "code": "code",
            "form": "form",
            "toc": "toc",
            "figure": "figure",
        }
        return mapping.get(label, "text")

    def parse_json_to_page(
        self,
        json_data: Dict[str, Any],
        page_id: int,
        page_size: Tuple[int, int]
    ) -> PageGroup:
        """
        将 JSON 输出解析为 PageGroup

        Args:
            json_data: OCR 返回的 JSON 数据
            page_id: 页面 ID
            page_size: (width, height) 页面尺寸

        Returns:
            PageGroup 对象
        """
        blocks = []

        # 提取 blocks 数组
        block_list = json_data.get("blocks", [])

        for i, block_data in enumerate(block_list):
            # 跳过非字典类型的元素
            if not isinstance(block_data, dict):
                logger.warning(f"Skipping non-dict block at index {i}: {type(block_data)}")
                continue

            # 提取数据
            text = block_data.get("text", "").strip()
            if not text:
                logger.warning(f"Empty text in block {i}, skipping")
                continue

            bbox = block_data.get("bbox", [])

            # 如果 bbox 无效，使用整页作为 bbox
            if not bbox or not isinstance(bbox, list) or len(bbox) != 4:
                logger.warning(f"Invalid bbox in block {i}, using full page bbox")
                bbox = [0, 0, page_size[0], page_size[1]]

            block_type = block_data.get("type", "text")

            # 创建 PolygonBox
            try:
                polygon = self._bbox_to_polygon(bbox, page_size)
            except Exception as e:
                logger.error(f"Failed to create polygon for block {i}: {e}")
                continue

            # 创建 Block
            try:
                block = self._create_block(text, polygon, block_type, page_id)
                blocks.append(block)
                logger.info(f"Successfully parsed block {i}: {len(text)} chars, type={block_type}")
            except Exception as e:
                logger.error(f"Failed to create block {i}: {e}")
                continue

        # 创建 PageGroup
        page_polygon = PolygonBox.from_bbox([0, 0, page_size[0], page_size[1]])
        page = PageGroup(
            page_id=page_id,
            polygon=page_polygon,
            children=blocks  # 使用 children 而不是 structure
        )

        return page

    def parse_markdown_to_page(
        self,
        markdown_content: str,
        page_id: int,
        page_size: Tuple[int, int]
    ) -> PageGroup:
        """
        将 Markdown 输出解析为 PageGroup

        Args:
            markdown_content: OCR 返回的 Markdown 内容
            page_id: 页面 ID
            page_size: (width, height) 页面尺寸

        Returns:
            PageGroup 对象
        """
        # Markdown 没有坐标信息，创建单个文本块
        page_polygon = PolygonBox.from_bbox([0, 0, page_size[0], page_size[1]])

        block = self._create_block(
            text=markdown_content,
            polygon=page_polygon,
            block_type="text",
            page_id=page_id
        )

        page = PageGroup(
            page_id=page_id,
            polygon=page_polygon,
            structure=[block]
        )

        return page

    def parse_to_page(
        self,
        ocr_output: Dict[str, Any] | str,
        page_id: int,
        page_size: Tuple[int, int],
        output_format: str = "json"
    ) -> PageGroup:
        """
        将 OCR 输出解析为 PageGroup (主入口)

        Args:
            ocr_output: OCR 输出 (dict 或 str)
            page_id: 页面 ID
            page_size: (width, height) 页面尺寸
            output_format: 输出格式 (json/html/markdown)

        Returns:
            PageGroup 对象
        """
        # Chandra HTML 格式（带 data-bbox 和 data-label）
        if isinstance(ocr_output, str) and "data-bbox" in ocr_output and "data-label" in ocr_output:
            return self.parse_chandra_html_to_page(ocr_output, page_id, page_size)
        # 传统格式
        elif output_format == "json" and isinstance(ocr_output, dict):
            return self.parse_json_to_page(ocr_output, page_id, page_size)
        elif output_format == "html" and isinstance(ocr_output, str):
            return self.parse_html_to_page(ocr_output, page_id, page_size)
        elif output_format == "markdown" and isinstance(ocr_output, str):
            return self.parse_markdown_to_page(ocr_output, page_id, page_size)
        else:
            logger.error(f"Unsupported output format: {output_format}")
            # 返回空页面
            page_polygon = PolygonBox.from_bbox([0, 0, page_size[0], page_size[1]])
            return PageGroup(
                page_id=page_id,
                polygon=page_polygon,
                children=[]
            )

    def parse_html_to_page(
        self,
        html_content: str,
        page_id: int,
        page_size: Tuple[int, int]
    ) -> PageGroup:
        """
        将 HTML 输出解析为 PageGroup

        Args:
            html_content: OCR 返回的 HTML 内容
            page_id: 页面 ID
            page_size: (width, height) 页面尺寸

        Returns:
            PageGroup 对象
        """
        from bs4 import BeautifulSoup

        blocks = []
        soup = BeautifulSoup(html_content, 'html.parser')

        # 查找所有带 data-bbox 的元素
        for element in soup.find_all(attrs={"data-bbox": True}):
            text = element.get_text().strip()
            if not text:
                continue

            # 解析 bbox
            bbox_str = element.get("data-bbox", "")
            try:
                bbox = [float(x) for x in bbox_str.split(",")]
            except:
                bbox = []

            # 获取类型
            block_type = element.get("data-type", "text")

            # 创建 Block
            polygon = self._bbox_to_polygon(bbox, page_size)
            block = self._create_block(text, polygon, block_type, page_id)
            blocks.append(block)

        # 创建 PageGroup
        page_polygon = PolygonBox.from_bbox([0, 0, page_size[0], page_size[1]])
        page = PageGroup(
            page_id=page_id,
            polygon=page_polygon,
            children=blocks  # 使用 children 而不是 structure
        )

        return page

    def parse_markdown_to_page(
        self,
        markdown_content: str,
        page_id: int,
        page_size: Tuple[int, int]
    ) -> PageGroup:
        """
        将 Markdown 输出解析为 PageGroup

        Args:
            markdown_content: OCR 返回的 Markdown 内容
            page_id: 页面 ID
            page_size: (width, height) 页面尺寸

        Returns:
            PageGroup 对象
        """
        # Markdown 没有坐标信息，创建单个文本块
        page_polygon = PolygonBox.from_bbox([0, 0, page_size[0], page_size[1]])

        block = self._create_block(
            text=markdown_content,
            polygon=page_polygon,
            block_type="text",
            page_id=page_id
        )

        page = PageGroup(
            page_id=page_id,
            polygon=page_polygon,
            structure=[block]
        )

        return page

    def parse_to_page(
        self,
        ocr_output: Dict[str, Any] | str,
        page_id: int,
        page_size: Tuple[int, int],
        output_format: str = "json"
    ) -> PageGroup:
        """
        将 OCR 输出解析为 PageGroup (主入口)

        Args:
            ocr_output: OCR 输出 (dict 或 str)
            page_id: 页面 ID
            page_size: (width, height) 页面尺寸
            output_format: 输出格式 (json/html/markdown)

        Returns:
            PageGroup 对象
        """
        # Chandra HTML 格式（带 data-bbox 和 data-label）
        if isinstance(ocr_output, str) and "data-bbox" in ocr_output and "data-label" in ocr_output:
            return self.parse_chandra_html_to_page(ocr_output, page_id, page_size)
        # 传统格式
        elif output_format == "json" and isinstance(ocr_output, dict):
            return self.parse_json_to_page(ocr_output, page_id, page_size)
        elif output_format == "html" and isinstance(ocr_output, str):
            return self.parse_html_to_page(ocr_output, page_id, page_size)
        elif output_format == "markdown" and isinstance(ocr_output, str):
            return self.parse_markdown_to_page(ocr_output, page_id, page_size)
        else:
            logger.error(f"Unsupported output format: {output_format}")
            # 返回空页面
            page_polygon = PolygonBox.from_bbox([0, 0, page_size[0], page_size[1]])
            return PageGroup(
                page_id=page_id,
                polygon=page_polygon,
                children=[]
            )
