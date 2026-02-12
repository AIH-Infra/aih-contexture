"""
印刷页码修正处理器

基于模式识别自动修正和补全印刷页码
"""

from collections import Counter
from dataclasses import dataclass
from typing import Annotated, Dict, List, Optional, Tuple

from aih_contexture.processors import BaseProcessor
from aih_contexture.schema.document import Document
from aih_contexture.logger import get_logger

logger = get_logger()


@dataclass
class Pattern:
    """页码模式"""
    type: str  # "continuous", "skip"
    offset: int  # 偏移量
    step: int  # 步长
    confidence: float  # 置信度


class PrintedPageNumberCorrector:
    """印刷页码修正器"""

    def __init__(self, min_confidence: float = 0.7):
        self.min_confidence = min_confidence

    def correct_page_numbers(self, document: Document) -> Dict[int, str]:
        """
        修正文档的印刷页码

        Args:
            document: 文档对象

        Returns:
            修正后的页码映射 {page_idx: corrected_page_number}
        """
        # 1. 提取现有页码
        extracted = self._extract_existing_numbers(document)

        # 2. 识别数字序列模式
        patterns = self._identify_patterns(extracted)

        # 3. 选择最佳模式
        best_pattern = self._select_best_pattern(patterns)

        # 4. 基于模式修正和补全
        corrected = self._apply_pattern(extracted, best_pattern)

        return corrected

    def _extract_existing_numbers(self, document: Document) -> Dict[int, Optional[int]]:
        """提取现有页码并转换为数值"""
        extracted = {}
        for page_idx, page in enumerate(document.pages):
            if hasattr(page, "_internal_metadata"):
                metadata = page._internal_metadata
                if "printed_page_number_numeric" in metadata:
                    extracted[page_idx] = metadata["printed_page_number_numeric"]
                else:
                    extracted[page_idx] = None
            else:
                extracted[page_idx] = None
        return extracted

    def _identify_patterns(self, extracted: Dict[int, Optional[int]]) -> List[Pattern]:
        """
        识别可能的数字序列模式

        可能的模式：
        1. 连续递增: 1, 2, 3, 4, 5...
        2. 跳跃递增: 1, 3, 5, 7... (奇数页)
        """
        patterns = []

        # 获取非空页码
        valid_pairs = [(idx, num) for idx, num in extracted.items() if num is not None]
        if len(valid_pairs) < 2:
            return patterns

        # 模式 1: 连续递增
        pattern = self._check_continuous_pattern(valid_pairs)
        if pattern:
            patterns.append(pattern)

        # 模式 2: 跳跃递增
        pattern = self._check_skip_pattern(valid_pairs)
        if pattern:
            patterns.append(pattern)

        return patterns

    def _check_continuous_pattern(self, valid_pairs: List[Tuple[int, int]]) -> Optional[Pattern]:
        """
        检查连续递增模式: page_number = page_idx + offset

        例如:
        - page_idx=0, page_num=1 → offset=1
        - page_idx=1, page_num=2 → offset=1
        - page_idx=2, page_num=3 → offset=1
        """
        offsets = [num - idx for idx, num in valid_pairs]

        # 检查 offset 是否一致
        if len(set(offsets)) == 1:
            offset = offsets[0]
            confidence = 1.0
            return Pattern(
                type="continuous",
                offset=offset,
                step=1,
                confidence=confidence
            )

        # 允许少量误差
        offset_counts = Counter(offsets)
        most_common_offset, count = offset_counts.most_common(1)[0]
        confidence = count / len(offsets)

        if confidence >= self.min_confidence:
            return Pattern(
                type="continuous",
                offset=most_common_offset,
                step=1,
                confidence=confidence
            )

        return None

    def _check_skip_pattern(self, valid_pairs: List[Tuple[int, int]]) -> Optional[Pattern]:
        """
        检查跳跃递增模式: page_number = page_idx * step + offset

        例如（奇数页）:
        - page_idx=0, page_num=1 → step=2, offset=1
        - page_idx=1, page_num=3 → step=2, offset=1
        - page_idx=2, page_num=5 → step=2, offset=1
        """
        if len(valid_pairs) < 3:
            return None

        # 计算步长
        steps = []
        for i in range(len(valid_pairs) - 1):
            idx1, num1 = valid_pairs[i]
            idx2, num2 = valid_pairs[i + 1]
            if idx2 - idx1 > 0:
                step = (num2 - num1) / (idx2 - idx1)
                steps.append(step)

        if not steps:
            return None

        # 检查步长是否一致
        avg_step = sum(steps) / len(steps)
        if abs(avg_step - round(avg_step)) < 0.1:  # 接近整数
            step = round(avg_step)
            if step > 1:  # 跳跃模式
                # 计算 offset
                idx0, num0 = valid_pairs[0]
                offset = num0 - idx0 * step

                # 验证模式
                errors = 0
                for idx, num in valid_pairs:
                    expected = idx * step + offset
                    if abs(num - expected) > 0.5:
                        errors += 1

                confidence = 1.0 - (errors / len(valid_pairs))
                if confidence >= self.min_confidence:
                    return Pattern(
                        type="skip",
                        offset=offset,
                        step=step,
                        confidence=confidence
                    )

        return None

    def _select_best_pattern(self, patterns: List[Pattern]) -> Optional[Pattern]:
        """选择置信度最高的模式"""
        if not patterns:
            return None
        return max(patterns, key=lambda p: p.confidence)

    def _apply_pattern(
        self,
        extracted: Dict[int, Optional[int]],
        pattern: Optional[Pattern]
    ) -> Dict[int, str]:
        """基于模式修正和补全页码"""
        if pattern is None:
            # 无模式，返回原始数据
            return {idx: str(num) if num is not None else None
                    for idx, num in extracted.items()}

        corrected = {}
        for page_idx in extracted.keys():
            if pattern.type == "continuous":
                # page_number = page_idx + offset
                expected_num = page_idx + pattern.offset
            elif pattern.type == "skip":
                # page_number = page_idx * step + offset
                expected_num = page_idx * pattern.step + pattern.offset
            else:
                expected_num = None

            if expected_num is not None:
                # 检查是否需要修正
                actual_num = extracted[page_idx]
                if actual_num is None:
                    # 补全缺失页码
                    corrected[page_idx] = str(expected_num)
                elif abs(actual_num - expected_num) <= 1:
                    # 保留原始页码（误差在 1 以内）
                    corrected[page_idx] = str(actual_num)
                else:
                    # 修正错误页码
                    corrected[page_idx] = str(expected_num)
            else:
                # 无法推断，保留原始
                corrected[page_idx] = str(actual_num) if actual_num else None

        return corrected


class PrintedPageNumberCorrectorProcessor(BaseProcessor):
    """
    印刷页码修正处理器

    基于模式识别自动修正和补全印刷页码
    """

    # 是否启用印刷页码修正
    printed_page_correction_enabled: Annotated[
        bool,
        "是否启用印刷页码修正"
    ] = True

    # 最小置信度阈值
    min_confidence: Annotated[
        float,
        "模式识别的最小置信度阈值"
    ] = 0.7

    def __call__(self, document: Document):
        """
        处理文档，修正印刷页码

        Args:
            document: 文档对象
        """
        if not self.printed_page_correction_enabled:
            logger.info("[PrintedPageNumberCorrectorProcessor] ❌ Disabled")
            return

        logger.info(f"[PrintedPageNumberCorrectorProcessor] ✅ Enabled, processing {len(document.pages)} pages")

        # 创建修正器
        corrector = PrintedPageNumberCorrector(min_confidence=self.min_confidence)

        # 修正页码
        corrected = corrector.correct_page_numbers(document)

        # 更新页面元数据
        corrected_count = 0
        for page_idx, page in enumerate(document.pages):
            if page_idx in corrected and corrected[page_idx] is not None:
                if not hasattr(page, "_internal_metadata"):
                    page._internal_metadata = {}

                # 获取原始页码
                original = page._internal_metadata.get("printed_page_number")

                # 更新为修正后的页码
                page._internal_metadata["printed_page_number"] = corrected[page_idx]
                page._internal_metadata["printed_page_number_corrected"] = True

                if original != corrected[page_idx]:
                    logger.info(f"[PrintedPageNumberCorrectorProcessor] Page {page_idx}: {original} → {corrected[page_idx]}")
                    corrected_count += 1

        logger.info(f"[PrintedPageNumberCorrectorProcessor] Completed: {corrected_count} pages corrected")
