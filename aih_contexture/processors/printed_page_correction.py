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


@dataclass
class PageNumberSegment:
    """A locally validated printed-page sequence."""

    start_idx: int
    end_idx: int
    pattern: Pattern
    anchors: List[Tuple[int, int]]


class PrintedPageNumberCorrector:
    """印刷页码修正器"""

    def __init__(self, min_confidence: float = 0.7, min_sequence_anchors: int = 2):
        self.min_confidence = min_confidence
        self.min_sequence_anchors = max(2, min_sequence_anchors)

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

        return self.correct_extracted_numbers(extracted)

    def correct_extracted_numbers(self, extracted: Dict[int, Optional[int]]) -> Dict[int, Optional[str]]:
        """Correct and complete only locally validated page-number sequences."""
        segments = self._identify_segments(extracted)
        return self._apply_segments(extracted, segments)

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

    def _identify_segments(self, extracted: Dict[int, Optional[int]]) -> List[PageNumberSegment]:
        valid_pairs = [(idx, num) for idx, num in extracted.items() if num is not None and num > 0]
        if len(valid_pairs) < self.min_sequence_anchors:
            return []

        candidate_segments: List[PageNumberSegment] = []
        for step in (1, 2):
            by_offset: dict[int, List[Tuple[int, int]]] = {}
            for idx, num in valid_pairs:
                by_offset.setdefault(num - idx * step, []).append((idx, num))

            for offset, anchors in by_offset.items():
                anchors = sorted(anchors)
                for run in self._split_anchor_run(anchors, step):
                    if len(run) < self.min_sequence_anchors:
                        continue
                    confidence = len(run) / max((run[-1][0] - run[0][0]) + 1, 1)
                    if confidence < self.min_confidence and len(run) < 3:
                        continue
                    candidate_segments.append(
                        PageNumberSegment(
                            start_idx=run[0][0],
                            end_idx=run[-1][0],
                            pattern=Pattern(
                                type="continuous" if step == 1 else "skip",
                                offset=offset,
                                step=step,
                                confidence=min(confidence, 1.0),
                            ),
                            anchors=run,
                        )
                    )

        return self._select_non_overlapping_segments(candidate_segments)

    def _split_anchor_run(
        self,
        anchors: List[Tuple[int, int]],
        step: int,
    ) -> List[List[Tuple[int, int]]]:
        if not anchors:
            return []

        runs: List[List[Tuple[int, int]]] = []
        current = [anchors[0]]
        for previous, current_anchor in zip(anchors, anchors[1:]):
            prev_idx, prev_num = previous
            idx, num = current_anchor
            expected_gap = (idx - prev_idx) * step
            if idx > prev_idx and num - prev_num == expected_gap:
                current.append(current_anchor)
            else:
                runs.append(current)
                current = [current_anchor]
        runs.append(current)
        return runs

    def _select_non_overlapping_segments(
        self,
        segments: List[PageNumberSegment],
    ) -> List[PageNumberSegment]:
        ranked = sorted(
            segments,
            key=lambda segment: (
                len(segment.anchors),
                segment.pattern.confidence,
                segment.end_idx - segment.start_idx,
            ),
            reverse=True,
        )
        selected: List[PageNumberSegment] = []
        occupied: set[int] = set()
        for segment in ranked:
            pages = set(range(segment.start_idx, segment.end_idx + 1))
            if pages & occupied:
                continue
            selected.append(segment)
            occupied.update(pages)
        return sorted(selected, key=lambda segment: segment.start_idx)

    def _apply_segments(
        self,
        extracted: Dict[int, Optional[int]],
        segments: List[PageNumberSegment],
    ) -> Dict[int, Optional[str]]:
        corrected: Dict[int, Optional[str]] = {idx: None for idx in extracted}
        for segment in segments:
            for page_idx in range(segment.start_idx, segment.end_idx + 1):
                if page_idx not in extracted:
                    continue
                if segment.pattern.type == "continuous":
                    expected_num = page_idx + segment.pattern.offset
                elif segment.pattern.type == "skip":
                    expected_num = page_idx * segment.pattern.step + segment.pattern.offset
                else:
                    expected_num = None
                if expected_num is None or expected_num <= 0:
                    continue
                actual_num = extracted[page_idx]
                if actual_num is None or abs(actual_num - expected_num) > 1:
                    corrected[page_idx] = str(expected_num)
                else:
                    corrected[page_idx] = str(actual_num)
        return corrected

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

            actual_num = extracted[page_idx]
            if expected_num is not None and expected_num <= 0:
                # Printed page numbers are positive identifiers.  A negative or
                # zero value usually means a main-text sequence was projected
                # backward into front matter, so preserve only explicit values.
                corrected[page_idx] = str(actual_num) if actual_num is not None else None
                continue

            if expected_num is not None:
                # 检查是否需要修正
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

    @staticmethod
    def _safe_int(value) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _expected_number(pattern: Optional[Pattern], page_idx: int) -> Optional[int]:
        if pattern is None:
            return None
        if pattern.type == "continuous":
            return page_idx + pattern.offset
        if pattern.type == "skip":
            return page_idx * pattern.step + pattern.offset
        return None

    @staticmethod
    def _is_plain_arabic_page_number(value) -> bool:
        return isinstance(value, str) and value.strip().isdigit()

    @staticmethod
    def _drop_printed_page_metadata(page) -> None:
        if not hasattr(page, "_internal_metadata"):
            return
        page._internal_metadata.pop("printed_page_number", None)
        page._internal_metadata.pop("printed_page_number_numeric", None)
        page._internal_metadata.pop("printed_page_number_corrected", None)

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

        # 修正页码。Only validated local sequences are allowed to survive.
        extracted = corrector._extract_existing_numbers(document)
        corrected = corrector.correct_extracted_numbers(extracted)

        # 更新页面元数据
        corrected_count = 0
        for page_idx, page in enumerate(document.pages):
            original = (
                page._internal_metadata.get("printed_page_number")
                if hasattr(page, "_internal_metadata")
                else None
            )
            corrected_value = corrected.get(page_idx)
            if corrected_value is None:
                if original is not None:
                    logger.info(
                        "[PrintedPageNumberCorrectorProcessor] Page %s: dropping non-sequential page candidate %s",
                        page_idx,
                        original,
                    )
                    self._drop_printed_page_metadata(page)
                    corrected_count += 1
                continue

            if page_idx in corrected:
                if not hasattr(page, "_internal_metadata"):
                    page._internal_metadata = {}

                # 获取原始页码
                original_numeric = page._internal_metadata.get("printed_page_number_numeric")
                corrected_numeric = self._safe_int(corrected_value)

                if (
                    original is not None
                    and original_numeric is not None
                    and corrected_numeric is not None
                    and int(original_numeric) == corrected_numeric
                ):
                    # Keep the visible printed-page form (for example roman
                    # numerals such as "ix") when the correction only repeats
                    # the same numeric value.
                    continue

                # 更新为修正后的页码
                page._internal_metadata["printed_page_number"] = corrected_value
                page._internal_metadata["printed_page_number_corrected"] = True

                if original != corrected_value:
                    logger.info(f"[PrintedPageNumberCorrectorProcessor] Page {page_idx}: {original} → {corrected_value}")
                    corrected_count += 1

        logger.info(f"[PrintedPageNumberCorrectorProcessor] Completed: {corrected_count} pages corrected")
