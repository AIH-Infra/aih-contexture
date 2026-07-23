"""
边码/页边注识别处理器

识别并重新分类以下类型的边码：
- 中文古籍版心（书名、卷次、叶码）
- 鱼尾装饰符
- Stephanus/Bekker 页边编码
- 行号（Critical Edition）
- 眉批/批注
- 书耳
"""

import re
from typing import Annotated
from copy import deepcopy

from aih_contexture.processors import BaseProcessor
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document
from aih_contexture.schema.registry import get_block_class
from aih_contexture.logger import get_logger

logger = get_logger()


class MarginalAnnotationProcessor(BaseProcessor):
    """
    识别并重新分类边码/页边注。

    处理流程：
    1. 只遍历 Text 块
    2. 根据位置、内容、字体大小判断是否为边码
    3. 重新分类为 MarginalAnnotation

    后端原生的 PageHeader/PageFooter/Footnote/MarginalAnnotation 不在这里二次仲裁。
    这个处理器只负责从正文文本块中启发式恢复漏检的边码，避免把 MinerU 等
    后端已经识别出的页眉/页脚改坏。
    """

    # 只处理正文文本块；原生页眉/页脚/脚注/边注由后端标签优先保留。
    block_types = (BlockTypes.Text,)

    # 配置参数
    enable_marginal_detection: Annotated[
        bool,
        "是否启用边码检测"
    ] = True

    heuristic_marginal_detection_enabled: Annotated[
        bool | None,
        "是否启用坐标启发式边码恢复；None 时沿用 enable_marginal_detection"
    ] = None

    left_margin_threshold: Annotated[
        float,
        "左边栏阈值（页面宽度的比例）"
    ] = 0.15

    right_margin_threshold: Annotated[
        float,
        "右边栏阈值（页面宽度的比例）"
    ] = 0.85

    top_margin_threshold: Annotated[
        float,
        "上边栏阈值（页面高度的比例）"
    ] = 0.10

    bottom_margin_threshold: Annotated[
        float,
        "下边栏阈值（页面高度的比例）"
    ] = 0.90

    vertical_center_tolerance: Annotated[
        float,
        "垂直中线容差（页面宽度的比例）"
    ] = 0.05

    def __call__(self, document: Document):
        enabled = (
            self.enable_marginal_detection
            if self.heuristic_marginal_detection_enabled is None
            else self.heuristic_marginal_detection_enabled
        )
        if not enabled:
            return

        relabeled_count = 0

        for page in document.pages:
            page_height = page.polygon.height
            page_width = page.polygon.width

            # 收集页面上所有候选文本块
            candidate_blocks = page.contained_blocks(document, self.block_types)

            for block in candidate_blocks:
                # 获取块的位置信息
                center_x = block.polygon.center[0]
                center_y = block.polygon.center[1]

                # 获取文本内容
                text = self._extract_text(block, document)

                # 判断是否为边码
                if self._is_marginal_annotation(
                    block, text, center_x, center_y,
                    page_width, page_height, document
                ):
                    # 重新分类为 MarginalAnnotation
                    subtype, position_type = self._classify_marginal_subtype(
                        block, text, center_x, center_y, page_width, page_height
                    )

                    self._relabel_block(
                        page, block, BlockTypes.MarginalAnnotation,
                        subtype, position_type
                    )
                    relabeled_count += 1

        if relabeled_count > 0:
            logger.info(f"[MarginalAnnotationProcessor] Relabeled {relabeled_count} blocks as MarginalAnnotation")

    def _extract_text(self, block, document):
        """从块中提取所有文本"""
        spans = block.contained_blocks(document, (BlockTypes.Span,))
        if not spans:
            return ""
        return " ".join(span.text for span in spans).strip()

    def _is_marginal_annotation(self, block, text, cx, cy, pw, ph, document):
        """判断是否为边码"""

        if block.block_type != BlockTypes.Text:
            return False

        # 空文本不处理
        if not text or len(text.strip()) == 0:
            return False

        # 规则 1：位置判断 - 页面边缘
        is_left_margin = cx < pw * self.left_margin_threshold
        is_right_margin = cx > pw * self.right_margin_threshold
        is_top_margin = cy < ph * self.top_margin_threshold
        is_bottom_margin = cy > ph * self.bottom_margin_threshold
        is_vertical_center = abs(cx - pw/2) < pw * self.vertical_center_tolerance

        # 必须在边缘位置
        if not (is_left_margin or is_right_margin or is_top_margin or
                is_bottom_margin or is_vertical_center):
            return False

        # 规则 2：内容判断

        # 2.1 版心叶码特征（垂直中线 + 包含"卷"/"叶"/"第"/"页"）
        if is_vertical_center:
            if re.search(r'[卷叶第页]', text):
                return True
            # 鱼尾装饰符（通常是特殊符号或很短的文本）
            if len(text) < 5 and not text.isalnum():
                return True

        # 2.2 Stephanus 编码（左边栏或右边栏 + 数字+字母格式）
        # 格式：514a, 1047b8 等
        if (is_left_margin or is_right_margin):
            if re.match(r'^\d{3,4}[a-e]\d*$', text.strip()):
                return True

        # 2.3 Bekker 编码（左边栏 + 数字+字母+数字格式）
        # 格式：1047a8
        if is_left_margin:
            if re.match(r'^\d{4}[ab]\d+$', text.strip()):
                return True

        # 2.4 行号（左边栏或右边栏 + 纯数字 + 短文本）
        if (is_left_margin or is_right_margin):
            if re.match(r'^\d+$', text.strip()) and len(text.strip()) <= 4:
                return True

        # 2.5 书耳（上边栏 + 短文本）
        if is_top_margin:
            if len(text) < 20:
                return True

        # 2.6 眉批（上边栏 + 中等长度文本）
        if is_top_margin:
            if 20 <= len(text) < 100:
                return True

        # 规则 3：字体大小判断（如果可用）
        # 获取平均字体大小
        avg_font_size = self._get_average_font_size(block, document)
        if avg_font_size is not None:
            # 获取页面主文本的平均字体大小
            main_font_size = self._get_page_main_font_size(document, block.page_id)
            if main_font_size is not None and avg_font_size < main_font_size * 0.8:
                # 字体明显小于主文本，且在边缘位置
                if is_left_margin or is_right_margin or is_top_margin or is_bottom_margin:
                    return True

        return False

    def _classify_marginal_subtype(self, block, text, cx, cy, pw, ph):
        """
        细分边码类型

        返回：(subtype, position_type)
        """
        # 确定位置类型
        is_left_margin = cx < pw * self.left_margin_threshold
        is_right_margin = cx > pw * self.right_margin_threshold
        is_top_margin = cy < ph * self.top_margin_threshold
        is_bottom_margin = cy > ph * self.bottom_margin_threshold
        is_vertical_center = abs(cx - pw/2) < pw * self.vertical_center_tolerance

        if is_vertical_center:
            position_type = "vertical_center"
        elif is_left_margin:
            position_type = "left_margin"
        elif is_right_margin:
            position_type = "right_margin"
        elif is_top_margin:
            position_type = "top_margin"
        elif is_bottom_margin:
            position_type = "bottom_margin"
        else:
            position_type = "unknown"

        # 确定细分类型
        subtype = "unknown"

        # 版心叶码
        if is_vertical_center and re.search(r'[卷叶第页]', text):
            subtype = "版心叶码"
        # 鱼尾装饰
        elif is_vertical_center and len(text) < 5 and not text.isalnum():
            subtype = "鱼尾装饰"
        # Stephanus 编码
        elif re.match(r'^\d{3,4}[a-e]\d*$', text.strip()):
            subtype = "Stephanus编码"
        # Bekker 编码
        elif re.match(r'^\d{4}[ab]\d+$', text.strip()):
            subtype = "Bekker编码"
        # 行号
        elif re.match(r'^\d+$', text.strip()) and len(text.strip()) <= 4:
            subtype = "行号"
        # 书耳
        elif is_top_margin and len(text) < 20:
            subtype = "书耳"
        # 眉批
        elif is_top_margin and 20 <= len(text) < 100:
            subtype = "眉批"
        # 其他边码
        else:
            subtype = "其他边码"

        return subtype, position_type

    def _get_average_font_size(self, block, document):
        """获取块的平均字体大小"""
        spans = block.contained_blocks(document, (BlockTypes.Span,))
        if not spans:
            return None

        font_sizes = [span.font_size for span in spans if hasattr(span, 'font_size')]
        if not font_sizes:
            return None

        return sum(font_sizes) / len(font_sizes)

    def _get_page_main_font_size(self, document, page_id):
        """获取页面主文本的平均字体大小"""
        page = document.get_page(page_id)
        text_blocks = page.contained_blocks(document, (BlockTypes.Text,))

        all_font_sizes = []
        for block in text_blocks:
            spans = block.contained_blocks(document, (BlockTypes.Span,))
            for span in spans:
                if hasattr(span, 'font_size'):
                    all_font_sizes.append(span.font_size)

        if not all_font_sizes:
            return None

        return sum(all_font_sizes) / len(all_font_sizes)

    def _relabel_block(self, page, block, new_block_type, subtype, position_type):
        """重新标记块类��"""
        new_block_cls = get_block_class(new_block_type)
        new_block = new_block_cls(
            polygon=deepcopy(block.polygon),
            page_id=block.page_id,
            structure=deepcopy(block.structure),
            text_extraction_method=block.text_extraction_method,
            source="processor",
            top_k=block.top_k,
            metadata=block.metadata
        )

        # 设置元数据
        new_block.set_internal_metadata("marginal_subtype", subtype)
        new_block.set_internal_metadata("position_type", position_type)
        new_block.set_internal_metadata("marginal_source", "heuristic")
        new_block.set_internal_metadata("label_source", "heuristic")
        new_block.set_internal_metadata("original_block_type", block.block_type.name)

        # 替换块
        page.replace_block(block, new_block)

        logger.debug(
            f"[MarginalAnnotationProcessor] Relabeled block {block.id} "
            f"to MarginalAnnotation (subtype={subtype}, position={position_type})"
        )
