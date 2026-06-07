"""
行内小字注识别处理器

识别并重新分类以下类型的行内注释：
- 双行小字
- 夹注
- 割注
- 括号包裹的短注释
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


class InlineAnnotationProcessor(BaseProcessor):
    """
    识别并重新分类行内小字注。

    处理流程：
    1. 遍历所有 Text 块
    2. 根据字体大小、格式、内容判断是否为行内注释
    3. 重新分类为 InlineAnnotation
    """

    # 处理的块类型
    block_types = (BlockTypes.Text,)

    # 配置参数
    enable_inline_detection: Annotated[
        bool,
        "是否启用行内注释检测"
    ] = True

    font_size_ratio_threshold: Annotated[
        float,
        "字体大小比例阈值（相对于主文本）"
    ] = 0.75

    max_inline_annotation_length: Annotated[
        int,
        "行内注释的最大字符数"
    ] = 100

    def __call__(self, document: Document):
        if not self.enable_inline_detection:
            return

        relabeled_count = 0

        for page in document.pages:
            # 获取页面主文本的平均字体大小
            main_font_size = self._get_page_main_font_size(document, page.page_id)

            # 收集页面上所有候选文本块
            candidate_blocks = page.contained_blocks(document, self.block_types)

            for block in candidate_blocks:
                # 获取文本内容
                text = self._extract_text(block, document)

                # 获取块的平均字体大小
                avg_font_size = self._get_average_font_size(block, document)

                # 判断是否为行内注释
                if self._is_inline_annotation(
                    block, text, avg_font_size, main_font_size, document
                ):
                    # 重新分类为 InlineAnnotation
                    subtype, font_ratio = self._classify_inline_subtype(
                        block, text, avg_font_size, main_font_size, document
                    )

                    self._relabel_block(
                        page, block, BlockTypes.InlineAnnotation,
                        subtype, font_ratio
                    )
                    relabeled_count += 1

        if relabeled_count > 0:
            logger.info(f"[InlineAnnotationProcessor] Relabeled {relabeled_count} blocks as InlineAnnotation")

    def _extract_text(self, block, document):
        """从块中提取所有文本"""
        spans = block.contained_blocks(document, (BlockTypes.Span,))
        if not spans:
            return ""
        return " ".join(span.text for span in spans).strip()

    def _is_inline_annotation(self, block, text, avg_font_size, main_font_size, document):
        """判断是否为行内注释"""

        # 空文本不处理
        if not text or len(text.strip()) == 0:
            return False

        # 文本过长不太可能是注释
        if len(text) > self.max_inline_annotation_length:
            return False

        # 规则 1：字体大小判断
        if avg_font_size is not None and main_font_size is not None:
            font_ratio = avg_font_size / main_font_size
            if font_ratio < self.font_size_ratio_threshold:
                return True

        # 规则 2：格式判断 - 检查是否有 "small" 格式
        spans = block.contained_blocks(document, (BlockTypes.Span,))
        has_small_format = any(
            hasattr(span, 'formats') and 'small' in span.formats
            for span in spans
        )
        if has_small_format:
            return True

        # 规则 3：括号包裹的短文本
        if self._is_parenthetical_text(text):
            return True

        # 规则 4：双行小字特征 - 检查是否有多个不同高度的 span
        if self._has_multi_line_heights(block, document):
            return True

        return False

    def _classify_inline_subtype(self, block, text, avg_font_size, main_font_size, document):
        """
        细分行内注释类型

        返回：(subtype, font_ratio)
        """
        # 计算字体比例
        if avg_font_size is not None and main_font_size is not None:
            font_ratio = avg_font_size / main_font_size
        else:
            font_ratio = 1.0

        # 确定细分类型
        subtype = "unknown"

        # 括号注
        if self._is_parenthetical_text(text):
            subtype = "括号注"
        # 双行小字
        elif self._has_multi_line_heights(block, document):
            subtype = "双行小字"
        # 夹注（字体小且文本短）
        elif font_ratio < 0.7 and len(text) < 30:
            subtype = "夹注"
        # 割注（字体小且文本中等长度）
        elif font_ratio < 0.7 and 30 <= len(text) < 100:
            subtype = "割注"
        # 其他小字注
        else:
            subtype = "其他小字注"

        return subtype, font_ratio

    def _is_parenthetical_text(self, text):
        """判断是否为括号包裹的文本"""
        text = text.strip()

        # 检查各种括号
        parentheses = [
            ('(', ')'),
            ('（', '）'),
            ('[', ']'),
            ('【', '】'),
            ('{', '}'),
            ('〔', '〕'),
            ('〈', '〉'),
            ('《', '》'),
        ]

        for open_p, close_p in parentheses:
            if text.startswith(open_p) and text.endswith(close_p):
                return True

        return False

    def _has_multi_line_heights(self, block, document):
        """检查是否有多个不同高度的 span（双行小字特征）"""
        spans = block.contained_blocks(document, (BlockTypes.Span,))
        if len(spans) < 2:
            return False

        # 获取所有 span 的字体大小
        font_sizes = [
            span.font_size for span in spans
            if hasattr(span, 'font_size')
        ]

        if len(font_sizes) < 2:
            return False

        # 检查是否有明显的字体大小差异
        min_size = min(font_sizes)
        max_size = max(font_sizes)

        # 如果最大和最小字体大小差异超过 30%，认为是双行小字
        if max_size > 0 and (max_size - min_size) / max_size > 0.3:
            return True

        return False

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

        # 使用中位数而不是平均值，更能代表主文本大小
        all_font_sizes.sort()
        mid = len(all_font_sizes) // 2
        if len(all_font_sizes) % 2 == 0:
            return (all_font_sizes[mid - 1] + all_font_sizes[mid]) / 2
        else:
            return all_font_sizes[mid]

    def _relabel_block(self, page, block, new_block_type, subtype, font_ratio):
        """重新标记块类型"""
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
        new_block.set_internal_metadata("inline_subtype", subtype)
        new_block.set_internal_metadata("font_size_ratio", font_ratio)
        new_block.set_internal_metadata("is_parenthetical", self._is_parenthetical_text(
            self._extract_text(block, page.document if hasattr(page, 'document') else None)
        ))

        # 替换块
        page.replace_block(block, new_block)

        logger.debug(
            f"[InlineAnnotationProcessor] Relabeled block {block.id} "
            f"to InlineAnnotation (subtype={subtype}, font_ratio={font_ratio:.2f})"
        )
