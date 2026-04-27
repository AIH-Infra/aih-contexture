from typing import Annotated, List

from aih_contexture.logger import get_logger
from aih_contexture.processors import BaseProcessor
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.blocks import Block
from aih_contexture.schema.document import Document
from aih_contexture.schema.text import Line
from aih_contexture.util import matrix_intersection_area

logger = get_logger()


class LineMergeProcessor(BaseProcessor):
    """
    A processor for merging inline math lines.
    """
    block_types = (BlockTypes.Text, BlockTypes.TextInlineMath, BlockTypes.Caption, BlockTypes.Footnote, BlockTypes.SectionHeader)
    min_merge_pct: Annotated[
        float,
        "The minimum percentage of intersection area to consider merging."
    ] = .015
    block_expand_threshold: Annotated[
        float,
        "The percentage of the block width to expand the bounding box."
    ] = .05
    min_merge_ydist: Annotated[
        float,
        "The minimum y distance between lines to consider merging."
    ] = 5
    intersection_pct_threshold: Annotated[
        float,
        "The total amount of intersection area concentrated in the max intersection block."
    ] = .5
    vertical_overlap_pct_threshold: Annotated[
        float,
        "The minimum percentage of vertical overlap to consider merging."
    ] = .8
    use_llm: Annotated[
        bool,
        "Whether to use LLMs to improve accuracy."
    ] = False

    def __init__(self, config):
        super().__init__(config)

    def merge_lines(self, lines: List[Line], block: Block):
        merged_group_count = 0
        merged_line_count = 0
        original_line_count = len(lines)
        lines = [l for l in lines if l.polygon.width * 5 > l.polygon.height]  # Skip vertical lines
        line_bboxes = [l.polygon.expand(self.block_expand_threshold, 0).bbox for l in lines]  # Expand horizontally
        intersections = matrix_intersection_area(line_bboxes, line_bboxes)

        merges = []
        merge = []
        for i in range(len(line_bboxes)):
            intersection_row = intersections[i]
            intersection_row[i] = 0  # Zero out the current idx

            if i < len(line_bboxes) - 1:
                intersection_row[i+1] = 0 # Zero out the next idx, so we only evaluate merge from the left

            if len(merge) == 0:
                merge.append(i)
                continue

            # Zero out previous merge segments
            merge_intersection = sum([intersection_row[m] for m in merge])
            line_area = lines[i].polygon.area
            intersection_pct = merge_intersection / max(1, line_area)

            total_intersection = max(1, sum(intersection_row))

            line_start = lines[merge[0]].polygon.y_start
            line_end = lines[merge[0]].polygon.y_end

            vertical_overlap_start = max(line_start, lines[i].polygon.y_start)
            vertical_overlap_end = min(line_end, lines[i].polygon.y_end)
            vertical_overlap = max(0, vertical_overlap_end - vertical_overlap_start)
            vertical_overlap_pct = vertical_overlap / max(1, lines[i].polygon.height)

            if all([
                # Overlaps enough
                intersection_pct >= self.min_merge_pct,
                # Within same line
                vertical_overlap_pct > self.vertical_overlap_pct_threshold,
                # doesn't overlap with anything else
                merge_intersection / total_intersection > self.intersection_pct_threshold
            ]):
                merge.append(i)
            else:
                merges.append(merge)
                merge = []

        if merge:
            merges.append(merge)

        merges = [m for m in merges if len(m) > 1]
        merged_group_count = len(merges)
        merged = set()
        for merge in merges:
            merge = [m for m in merge if m not in merged]
            if len(merge) < 2:
                continue

            line: Line = lines[merge[0]]
            merged.add(merge[0])
            for idx in merge[1:]:
                other_line: Line = lines[idx]
                line.merge(other_line)
                block.structure.remove(other_line.id)
                other_line.removed = True  # Mark line as removed
                merged.add(idx)
                merged_line_count += 1

            # It is probably math if we are merging provider lines like this
            if not line.formats:
                line.formats = ["math"]
            elif "math" not in line.formats:
                line.formats.append("math")

        return {
            "original_line_count": original_line_count,
            "candidate_line_count": len(lines),
            "merged_group_count": merged_group_count,
            "merged_line_count": merged_line_count,
        }

    def __call__(self, document: Document):
        if not self.use_llm:
            logger.info("[LineMergeProcessor] skipped: use_llm=%s", self.use_llm)
            return

        processed_blocks = 0
        candidate_lines = 0
        original_lines = 0
        merged_groups = 0
        merged_lines = 0

        for page in document.pages:
            for block in page.contained_blocks(document, self.block_types):
                if block.structure is None:
                    continue

                if not len(block.structure) >= 2:
                    continue

                lines = block.contained_blocks(document, (BlockTypes.Line,))
                stats = self.merge_lines(lines, block)
                processed_blocks += 1
                original_lines += stats["original_line_count"]
                candidate_lines += stats["candidate_line_count"]
                merged_groups += stats["merged_group_count"]
                merged_lines += stats["merged_line_count"]

        logger.info(
            "[LineMergeProcessor] completed: processed_blocks=%s original_lines=%s candidate_lines=%s merged_groups=%s merged_lines=%s",
            processed_blocks,
            original_lines,
            candidate_lines,
            merged_groups,
            merged_lines,
        )
