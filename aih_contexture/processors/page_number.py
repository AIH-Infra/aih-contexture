"""
页码处理器

从文档页面中提取和规范化页码信息，支持多种页码格式。
"""

import re
from typing import Annotated, Dict, List, Optional, Tuple

from aih_contexture.processors import BaseProcessor
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document
from aih_contexture.logger import get_logger

logger = get_logger()


# 中文数字映射
CHINESE_NUMBERS = {
    "零": 0, "〇": 0,
    "一": 1, "壹": 1,
    "二": 2, "贰": 2, "兩": 2, "两": 2,
    "三": 3, "叁": 3,
    "四": 4, "肆": 4,
    "五": 5, "伍": 5,
    "六": 6, "陆": 6, "陸": 6,
    "七": 7, "柒": 7,
    "八": 8, "捌": 8,
    "九": 9, "玖": 9,
    "十": 10, "拾": 10,
    "百": 100, "佰": 100,
    "千": 1000, "仟": 1000,
}

# 罗马数字映射
ROMAN_NUMERALS = {
    "I": 1, "V": 5, "X": 10, "L": 50,
    "C": 100, "D": 500, "M": 1000,
}


class PageNumberProcessor(BaseProcessor):
    """
    页码处理器。

    从页眉/页脚中提取页码信息，支持多种格式：
    - 阿拉伯数字 (1, 2, 3...)
    - 罗马数字 (I, II, III... 或 i, ii, iii...)
    - 中文数字 (一, 二, 三... 或 第一頁, 第二葉...)
    - 自定义格式（正则表达式）
    """

    # 块类型：处理页眉和页脚
    block_types: Tuple[BlockTypes] = (
        BlockTypes.PageHeader,
        BlockTypes.PageFooter,
    )

    # 是否启用页码提取
    page_numbering_enabled: Annotated[
        bool,
        "是否启用页码提取"
    ] = True

    # 页码格式
    page_number_format: Annotated[
        str,
        "页码格式: arabic, roman, chinese, custom"
    ] = "arabic"

    # 是否使用印刷页码
    use_printed_page_number: Annotated[
        bool,
        "使用印刷页码而非机器页码"
    ] = True  # 临时修改为 True，解决配置传递问题

    # 自定义正则表达式
    page_number_custom_pattern: Annotated[
        Optional[str],
        "自定义页码正则表达式"
    ] = None

    # 页码前缀（如 "Page ", "第"）
    page_number_prefix: Annotated[
        str,
        "页码前缀"
    ] = ""

    # 页码后缀（如 "页", "葉"）
    page_number_suffix: Annotated[
        str,
        "页码后缀"
    ] = ""

    # 页码搜索区域
    printed_page_zones: Annotated[
        List[str],
        "页码搜索区域: header, footer, top-right, bottom-right, top-left, bottom-left"
    ] = None  # 默认值在 __init__ 中设置

    # 页眉区域阈值
    printed_page_header_y_frac: Annotated[
        float,
        "页眉区域阈值（页面顶部百分比）"
    ] = 0.15

    # 页脚区域阈值
    printed_page_footer_y_frac: Annotated[
        float,
        "页脚区域阈值（页面底部百分比）"
    ] = 0.83

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)

        # 默认搜索区域：先页脚再页眉
        if self.printed_page_zones is None:
            self.printed_page_zones = ["footer", "header"]

        # 从 config 读取配置
        if isinstance(config, dict):
            if config.get("page_numbering_enabled") is not None:
                self.page_numbering_enabled = bool(config["page_numbering_enabled"])
            if config.get("page_number_format") is not None:
                self.page_number_format = str(config["page_number_format"])
            if config.get("use_printed_page_number") is not None:
                self.use_printed_page_number = bool(config["use_printed_page_number"])
            if config.get("page_number_custom_pattern") is not None:
                self.page_number_custom_pattern = str(config["page_number_custom_pattern"])
            if config.get("page_number_prefix") is not None:
                self.page_number_prefix = str(config["page_number_prefix"])
            if config.get("page_number_suffix") is not None:
                self.page_number_suffix = str(config["page_number_suffix"])
            if config.get("printed_page_zones") is not None:
                self.printed_page_zones = list(config["printed_page_zones"])
            if config.get("printed_page_header_y_frac") is not None:
                self.printed_page_header_y_frac = float(config["printed_page_header_y_frac"])
            if config.get("printed_page_footer_y_frac") is not None:
                self.printed_page_footer_y_frac = float(config["printed_page_footer_y_frac"])

    def __call__(self, document: Document):
        """
        处理文档，提取页码信息。

        Args:
            document: 文档对象
        """
        if not self.page_numbering_enabled:
            logger.info("[PageNumberProcessor] ❌ Disabled by page_numbering_enabled=False")
            return

        logger.info(f"[PageNumberProcessor] ✅ Enabled, processing {len(document.pages)} pages")
        logger.info(f"[PageNumberProcessor] Config: use_printed_page_number={self.use_printed_page_number}")
        logger.info(f"[PageNumberProcessor] Config: zones={self.printed_page_zones}")
        logger.info(f"[PageNumberProcessor] Config: format={self.page_number_format}")

        extracted_count = 0
        for page_idx, page in enumerate(document.pages):
            # 机器页码（从 0 开始）
            machine_page_number = page_idx + 1

            # 尝试提取印刷页码
            printed_page_number = None
            if self.use_printed_page_number:
                printed_page_number = self._extract_page_number(page, document)
                if printed_page_number:
                    logger.info(f"[PageNumberProcessor] Page {page_idx}: Found printed page number '{printed_page_number}'")
                    extracted_count += 1
                else:
                    logger.warning(f"[PageNumberProcessor] Page {page_idx}: No printed page number found")

            # 设置页码元数据
            self._set_page_metadata(
                page,
                machine_page_number,
                printed_page_number
            )

        logger.info(f"[PageNumberProcessor] Completed: {extracted_count}/{len(document.pages)} pages with printed numbers")

    def _get_candidate_blocks(self, page, document: Document) -> List:
        """
        按配置的 zones 获取候选块。

        优先级：
        1. PageHeader/PageFooter 块类型（若 layout 识别出）
        2. 按坐标启发式（页眉/页脚区域）

        Args:
            page: 页面对象
            document: 文档对象

        Returns:
            候选块列表，按优先级排序
        """
        candidates = []

        # 调试：打印页面所有块的类型
        logger.info(f"[PageNumberProcessor] Page has {len(page.structure) if page.structure else 0} blocks")
        if page.structure:
            block_types = []
            for block_id in page.structure:
                block = document.get_block(block_id)
                if block:
                    block_types.append(str(block.block_type))
            logger.info(f"[PageNumberProcessor] Block types on page: {', '.join(block_types)}")

        # 阶段 1: 按 block_type 优先级收集
        for block_id in page.structure:
            block = document.get_block(block_id)
            if not block:
                continue

            if block.block_type == BlockTypes.PageHeader and "header" in self.printed_page_zones:
                logger.info(f"[PageNumberProcessor] Found PageHeader block")
                candidates.append((0, block))  # 优先级 0（最高）
            elif block.block_type == BlockTypes.PageFooter and "footer" in self.printed_page_zones:
                logger.info(f"[PageNumberProcessor] Found PageFooter block")
                candidates.append((1, block))  # 优先级 1

        # 阶段 2: 若无专用块，按坐标启发式
        if not candidates:
            logger.info(f"[PageNumberProcessor] No PageHeader/PageFooter blocks found, using coordinate heuristics")
            page_bbox = page.polygon.bbox
            page_height = page_bbox[3] - page_bbox[1]
            page_width = page_bbox[2] - page_bbox[0]

            header_y_threshold = page_bbox[1] + page_height * self.printed_page_header_y_frac
            footer_y_threshold = page_bbox[1] + page_height * self.printed_page_footer_y_frac

            logger.info(f"[PageNumberProcessor] Header threshold: {header_y_threshold}, Footer threshold: {footer_y_threshold}")

            for block_id in page.structure:
                block = document.get_block(block_id)
                if not block or not hasattr(block, "polygon"):
                    continue

                block_bbox = block.polygon.bbox
                y_center = (block_bbox[1] + block_bbox[3]) / 2
                x_center = (block_bbox[0] + block_bbox[2]) / 2

                # 页眉区域
                if "header" in self.printed_page_zones and y_center <= header_y_threshold:
                    logger.info(f"[PageNumberProcessor] Found block in header region: {block.block_type}")
                    candidates.append((2, block))
                # 页脚区域
                elif "footer" in self.printed_page_zones and y_center >= footer_y_threshold:
                    logger.info(f"[PageNumberProcessor] Found block in footer region: {block.block_type}")
                    candidates.append((3, block))
                # 右上角
                elif "top-right" in self.printed_page_zones and y_center <= header_y_threshold and x_center >= page_bbox[0] + page_width * 0.7:
                    candidates.append((4, block))
                # 右下角
                elif "bottom-right" in self.printed_page_zones and y_center >= footer_y_threshold and x_center >= page_bbox[0] + page_width * 0.7:
                    candidates.append((5, block))
                # 左上角
                elif "top-left" in self.printed_page_zones and y_center <= header_y_threshold and x_center <= page_bbox[0] + page_width * 0.3:
                    candidates.append((6, block))
                # 左下角
                elif "bottom-left" in self.printed_page_zones and y_center >= footer_y_threshold and x_center <= page_bbox[0] + page_width * 0.3:
                    candidates.append((7, block))

        # 按优先级排序
        candidates.sort(key=lambda x: x[0])
        return [block for _, block in candidates]

    def _extract_page_number(self, page, document: Document) -> Optional[str]:
        """
        从页眉/页脚中提取印刷页码。

        Args:
            page: 页面对象
            document: 文档对象

        Returns:
            提取的页码字符串，或 None
        """
        # 获取候选块
        candidate_blocks = self._get_candidate_blocks(page, document)

        if not candidate_blocks:
            logger.debug(f"[PageNumberProcessor] No candidate blocks found in search zones: {self.printed_page_zones}")
            return None

        logger.debug(f"[PageNumberProcessor] Found {len(candidate_blocks)} candidate blocks")

        # 尝试从候选块中提取页码
        for idx, block in enumerate(candidate_blocks):
            text = self._get_block_text(block, document)
            logger.info(f"[PageNumberProcessor] Candidate {idx}: block_type={block.block_type if hasattr(block, 'block_type') else 'unknown'}, text='{text[:100] if text else 'EMPTY'}'")

            if text:
                page_number = self._parse_page_number(text)
                if page_number:
                    logger.info(f"[PageNumberProcessor] Successfully parsed page number: '{page_number}'")
                    return page_number
                else:
                    logger.info(f"[PageNumberProcessor] Could not parse page number from text: '{text[:100]}'")

        return None

    def _get_block_text(self, block, document: Document) -> str:
        """
        获取块的文本内容。

        Args:
            block: 块对象
            document: 文档对象

        Returns:
            块的文本内容
        """
        texts = []

        # 调试：打印块的基本信息
        logger.debug(f"[PageNumberProcessor] _get_block_text: block_type={block.block_type if hasattr(block, 'block_type') else 'unknown'}")
        logger.debug(f"[PageNumberProcessor] _get_block_text: has structure={hasattr(block, 'structure')}, structure={block.structure if hasattr(block, 'structure') else 'N/A'}")
        logger.debug(f"[PageNumberProcessor] _get_block_text: has text={hasattr(block, 'text')}, text={block.text if hasattr(block, 'text') and block.text else 'N/A'}")
        logger.debug(f"[PageNumberProcessor] _get_block_text: has html={hasattr(block, 'html')}, html={block.html if hasattr(block, 'html') and block.html else 'N/A'}")

        # 遍历子块（使用 structure 属性，不是 children）
        if hasattr(block, "structure") and block.structure:
            logger.debug(f"[PageNumberProcessor] _get_block_text: traversing {len(block.structure)} child blocks")
            for child_id in block.structure:
                child = document.get_block(child_id)
                if child:
                    child_text = self._get_block_text(child, document)
                    if child_text:
                        texts.append(child_text)

        # 获取块自身的文本
        if hasattr(block, "text") and block.text:
            texts.append(block.text)
        elif hasattr(block, "html") and block.html:
            # 从 HTML 中提取纯文本
            text = re.sub(r"<[^>]+>", "", block.html)
            texts.append(text)

        result = " ".join(texts).strip()
        logger.debug(f"[PageNumberProcessor] _get_block_text: result='{result[:100] if result else 'EMPTY'}'")
        return result

    def _parse_page_number(self, text: str) -> Optional[str]:
        """
        从文本中解析页码。

        Args:
            text: 文本内容

        Returns:
            解析出的页码字符串，或 None
        """
        if not text:
            return None

        text = text.strip()

        # 自定义模式优先
        if self.page_number_custom_pattern:
            match = re.search(self.page_number_custom_pattern, text)
            if match:
                return match.group(0)

        # 根据格式解析
        if self.page_number_format == "arabic":
            return self._parse_arabic(text)
        elif self.page_number_format == "roman":
            return self._parse_roman(text)
        elif self.page_number_format == "chinese":
            return self._parse_chinese(text)
        else:
            # 默认尝试所有格式
            result = self._parse_arabic(text)
            if result:
                return result
            result = self._parse_roman(text)
            if result:
                return result
            result = self._parse_chinese(text)
            if result:
                return result

        return None

    def _parse_arabic(self, text: str) -> Optional[str]:
        """解析阿拉伯数字页码"""
        # 匹配纯数字
        match = re.search(r"\b(\d+)\b", text)
        if match:
            return match.group(1)

        # 匹配带前缀的数字（如 "Page 1", "第1页"）
        patterns = [
            r"[Pp]age\s*(\d+)",
            r"[Pp]\.\s*(\d+)",
            r"[第页頁]\s*(\d+)",
            r"(\d+)\s*[页頁]",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)

        return None

    def _parse_roman(self, text: str) -> Optional[str]:
        """解析罗马数字页码"""
        # 匹配大写罗马数字
        match = re.search(r"\b([IVXLCDM]+)\b", text)
        if match:
            return match.group(1)

        # 匹配小写罗马数字
        match = re.search(r"\b([ivxlcdm]+)\b", text)
        if match:
            return match.group(1)

        return None

    def _parse_chinese(self, text: str) -> Optional[str]:
        """解析中文数字页码"""
        # 常见古籍页码格式
        patterns = [
            r"第([一二三四五六七八九十百千]+)[頁葉页叶]",
            r"([一二三四五六七八九十百千]+)[頁葉页叶]",
            r"第([一二三四五六七八九十百千]+)",
            r"卷[一二三四五六七八九十百千]+\s*第([一二三四五六七八九十百千]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0)

        return None

    def _set_page_metadata(
        self,
        page,
        machine_page_number: int,
        printed_page_number: Optional[str]
    ):
        """
        设置页面的页码元数据。

        Args:
            page: 页面对象
            machine_page_number: 机器页码
            printed_page_number: 印刷页码
        """
        # 使用 internal_metadata 存储
        if not hasattr(page, "_internal_metadata"):
            page._internal_metadata = {}

        page._internal_metadata["machine_page_number"] = machine_page_number
        page._internal_metadata["page_number_format"] = self.page_number_format

        if printed_page_number:
            page._internal_metadata["printed_page_number"] = printed_page_number
            # 尝试转换为数值
            numeric = self._to_numeric(printed_page_number)
            if numeric is not None:
                page._internal_metadata["printed_page_number_numeric"] = numeric

    def _to_numeric(self, page_number: str) -> Optional[int]:
        """
        将页码字符串转换为数值。

        Args:
            page_number: 页码字符串

        Returns:
            数值，或 None
        """
        # 尝试阿拉伯数字
        try:
            return int(page_number)
        except ValueError:
            pass

        # 尝试罗马数字
        if re.match(r"^[IVXLCDMivxlcdm]+$", page_number):
            return self._roman_to_int(page_number.upper())

        # 尝试中文数字
        return self._chinese_to_int(page_number)

    def _roman_to_int(self, roman: str) -> Optional[int]:
        """将罗马数字转换为整数"""
        try:
            result = 0
            prev = 0
            for char in reversed(roman):
                curr = ROMAN_NUMERALS.get(char, 0)
                if curr < prev:
                    result -= curr
                else:
                    result += curr
                prev = curr
            return result if result > 0 else None
        except Exception:
            return None

    def _chinese_to_int(self, chinese: str) -> Optional[int]:
        """将中文数字转换为整数"""
        try:
            # 提取中文数字部分
            match = re.search(r"[一二三四五六七八九十百千零〇壹贰叁肆伍陆柒捌玖拾佰仟]+", chinese)
            if not match:
                return None

            num_str = match.group(0)
            result = 0
            temp = 0

            for char in num_str:
                if char in CHINESE_NUMBERS:
                    val = CHINESE_NUMBERS[char]
                    if val >= 10:
                        if temp == 0:
                            temp = 1
                        result += temp * val
                        temp = 0
                    else:
                        temp = temp * 10 + val if temp > 0 else val

            result += temp
            return result if result > 0 else None
        except Exception:
            return None


def get_page_number(page, prefer_printed: bool = True) -> Optional[str]:
    """
    获取页面的页码。

    这是一个便捷函数，用于从页面获取页码信息。

    Args:
        page: 页面对象
        prefer_printed: 优先返回印刷页码

    Returns:
        页码字符串，或 None
    """
    if not hasattr(page, "_internal_metadata"):
        return None

    metadata = page._internal_metadata

    if prefer_printed and "printed_page_number" in metadata:
        return metadata["printed_page_number"]

    if "machine_page_number" in metadata:
        return str(metadata["machine_page_number"])

    return None
