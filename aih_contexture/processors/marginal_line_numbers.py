import re
from copy import deepcopy
from typing import Annotated

from aih_contexture.logger import get_logger
from aih_contexture.processors import BaseProcessor
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document
from aih_contexture.schema.registry import get_block_class

logger = get_logger()


LINE_NUMBER_RE = re.compile(r"^\d{1,4}\|?$")


class MarginalLineNumberProcessor(BaseProcessor):
    """Move pdftext margin line-number spans out of body text.

    PDF text layers often merge European scholarly side line numbers into the
    nearest body line.  The spans then look like superscript footnote markers.
    This processor keeps real footnotes intact by requiring strong geometry:
    pure numeric Text spans must live in the extreme left/right page edge.
    """

    enabled: Annotated[bool, "Enable coordinate-based marginal line-number de-duplication."] = True
    left_edge_threshold: Annotated[float, "Left page-edge ratio for margin line numbers."] = 0.08
    right_edge_threshold: Annotated[float, "Right page-edge ratio for margin line numbers."] = 0.92
    top_exclusion_threshold: Annotated[float, "Ignore candidates in top running-head/page-number zone."] = 0.08
    bottom_exclusion_threshold: Annotated[float, "Ignore candidates in bottom footer/page-number zone."] = 0.94
    existing_margin_y_tolerance: Annotated[float, "Y distance in page units for merging with an existing margin note."] = 8.0
    max_line_match_distance: Annotated[float, "Maximum y distance for inserting a margin note next to a text line."] = 24.0

    def __call__(self, document: Document):
        if not self.enabled:
            return

        moved = 0
        reused = 0
        for page in document.pages:
            page_width = float(page.polygon.width or 1.0)
            page_height = float(page.polygon.height or 1.0)
            line_notes = self._margin_notes_for_reflow(page, document, page_width, page_height)
            existing = list(line_notes)
            for block in list(page.current_children):
                if block.block_type != BlockTypes.Text or getattr(block, "removed", False):
                    continue
                for span in block.contained_blocks(document, (BlockTypes.Span,)):
                    if not self._is_candidate_span(span, page_width, page_height):
                        continue

                    text = self._clean_marker(span.text)
                    side = self._span_side(span, page_width)
                    span.ignore_for_output = True
                    span.set_internal_metadata("suppressed_as_marginal_line_number", True)

                    margin_block = self._find_existing_note(existing, text, side, span)
                    if margin_block is None:
                        margin_block = self._create_margin_note(page, span, text, side)
                        existing.append(margin_block)
                        line_notes.append(margin_block)
                        moved += 1
                    else:
                        margin_block.set_internal_metadata("marginal_subtype", "line_number")
                        margin_block.set_internal_metadata("position_type", f"{side}_margin")
                        reused += 1

            if line_notes:
                self._reflow_margin_notes(page, document, line_notes)

        if moved or reused:
            logger.info(
                "[MarginalLineNumberProcessor] moved=%s reused_existing=%s",
                moved,
                reused,
            )

    def _is_candidate_span(self, span, page_width: float, page_height: float) -> bool:
        text = self._clean_marker(getattr(span, "text", ""))
        if not LINE_NUMBER_RE.fullmatch(text):
            return False
        polygon = getattr(span, "polygon", None)
        if polygon is None:
            return False

        cx = float(polygon.center[0]) / page_width
        cy = float(polygon.center[1]) / page_height
        if cy <= self.top_exclusion_threshold or cy >= self.bottom_exclusion_threshold:
            return False
        return cx <= self.left_edge_threshold or cx >= self.right_edge_threshold

    def _span_side(self, span, page_width: float) -> str:
        cx = float(span.polygon.center[0]) / page_width
        return "left" if cx < 0.5 else "right"

    def _margin_notes_for_reflow(self, page, document: Document, page_width: float, page_height: float) -> list:
        notes = []
        for block in page.current_children:
            if block.block_type != BlockTypes.MarginalAnnotation or getattr(block, "removed", False):
                continue
            text = self._clean_marker(block.raw_text(document))
            if not LINE_NUMBER_RE.fullmatch(text):
                continue
            cx = float(block.polygon.center[0]) / page_width
            cy = float(block.polygon.center[1]) / page_height
            if cy <= self.top_exclusion_threshold or cy >= self.bottom_exclusion_threshold:
                continue
            if not (cx <= self.left_edge_threshold or cx >= self.right_edge_threshold):
                continue
            side = "left" if cx < 0.5 else "right"
            block.set_internal_metadata("line_number_text", text)
            block.set_internal_metadata("marginal_subtype", "line_number")
            block.set_internal_metadata("position_type", f"{side}_margin")
            notes.append(block)
        return notes

    def _find_existing_note(self, notes: list, text: str, side: str, span):
        span_y = float(span.polygon.center[1])
        best = None
        best_dy = None
        for note in notes:
            note_text = self._clean_marker(
                note.get_internal_metadata("line_number_text")
                or getattr(note, "_cached_marker_text", "")
            )
            if note_text and note_text.rstrip("|") != text.rstrip("|"):
                continue
            position = note.get_internal_metadata("position_type") or ""
            if position and not str(position).startswith(side):
                continue
            dy = abs(float(note.polygon.center[1]) - span_y)
            if dy <= self.existing_margin_y_tolerance and (best_dy is None or dy < best_dy):
                best = note
                best_dy = dy
        return best

    def _create_margin_note(self, page, span, text: str, side: str):
        margin_cls = get_block_class(BlockTypes.MarginalAnnotation)
        line_cls = get_block_class(BlockTypes.Line)
        span_cls = get_block_class(BlockTypes.Span)

        margin = page.add_block(margin_cls, deepcopy(span.polygon))
        margin.source = "processor"
        margin.text_extraction_method = getattr(span, "text_extraction_method", None)
        margin.set_internal_metadata("marginal_subtype", "line_number")
        margin.set_internal_metadata("position_type", f"{side}_margin")
        margin.set_internal_metadata("created_from", str(span.id))
        margin._cached_marker_text = text

        line = line_cls(
            polygon=deepcopy(span.polygon),
            page_id=span.page_id,
            text_extraction_method=getattr(span, "text_extraction_method", None),
        )
        page.add_full_block(line)
        margin.add_structure(line)

        copied_span = span_cls(
            polygon=deepcopy(span.polygon),
            page_id=span.page_id,
            text=text,
            font=getattr(span, "font", ""),
            font_weight=getattr(span, "font_weight", 0.0),
            font_size=getattr(span, "font_size", 0.0),
            minimum_position=getattr(span, "minimum_position", 0),
            maximum_position=getattr(span, "maximum_position", len(text)),
            formats=list(getattr(span, "formats", []) or ["plain"]),
            has_superscript=False,
            has_subscript=False,
            url=getattr(span, "url", None),
            html=None,
        )
        page.add_full_block(copied_span)
        line.add_structure(copied_span)
        return margin

    def _reflow_margin_notes(self, page, document: Document, margin_blocks: list):
        if not page.structure:
            return

        margin_ids = {block.id for block in margin_blocks}
        assignments, unassigned = self._assign_margin_notes_to_lines(page, margin_blocks)
        original = [block_id for block_id in page.structure if block_id not in margin_ids]
        ordered = []

        for block_id in original:
            block = page.get_block(block_id)
            block_assignments = assignments.get(block_id)
            if (
                block is not None
                and block.block_type == BlockTypes.Text
                and block_assignments
                and not getattr(block, "html", None)
            ):
                ordered.extend(self._split_text_block_with_margins(page, document, block, block_assignments))
            else:
                ordered.append(block_id)

        for margin in sorted(unassigned, key=lambda block: (block.polygon.center[1], block.polygon.center[0])):
            insert_at = self._nearest_structure_index(page, ordered, margin)
            ordered.insert(insert_at, margin.id)
        page.structure = ordered

    def _assign_margin_notes_to_lines(self, page, margin_blocks: list):
        line_candidates = []
        for block_id in list(page.structure or []):
            block = page.get_block(block_id)
            if block is None or block.block_type != BlockTypes.Text or getattr(block, "removed", False):
                continue
            for line_index, line_id in enumerate(list(block.structure or [])):
                line = page.get_block(line_id)
                if line is None or line.block_type != BlockTypes.Line or getattr(line, "removed", False):
                    continue
                line_candidates.append((block_id, line_index, line))

        assignments = {}
        unassigned = []
        for margin in margin_blocks:
            best = None
            best_dy = None
            margin_y = float(margin.polygon.center[1])
            for block_id, line_index, line in line_candidates:
                dy = abs(float(line.polygon.center[1]) - margin_y)
                if best_dy is None or dy < best_dy:
                    best = (block_id, line_index, margin)
                    best_dy = dy
            if best is None or best_dy is None or best_dy > self.max_line_match_distance:
                unassigned.append(margin)
                continue
            assignments.setdefault(best[0], []).append((best[1], margin))
        return assignments, unassigned

    def _split_text_block_with_margins(self, page, document: Document, block, assignments: list) -> list:
        line_ids = [
            line_id
            for line_id in list(block.structure or [])
            if (page.get_block(line_id) is not None and page.get_block(line_id).block_type == BlockTypes.Line)
        ]
        if not line_ids:
            return [block.id]

        result = []
        start = 0
        grouped = {}
        for line_index, margin in assignments:
            line_index = max(0, min(int(line_index), len(line_ids) - 1))
            grouped.setdefault(line_index, []).append(margin)

        for line_index in sorted(grouped):
            if line_index > start:
                result.append(self._create_text_segment(page, block, line_ids[start:line_index]))
            for margin in sorted(grouped[line_index], key=lambda item: (item.polygon.center[1], item.polygon.center[0])):
                result.append(margin.id)
            start = line_index

        if start < len(line_ids):
            result.append(self._create_text_segment(page, block, line_ids[start:]))

        if result:
            block.removed = True
            return result
        return [block.id]

    def _create_text_segment(self, page, block, line_ids: list):
        line_blocks = [page.get_block(line_id) for line_id in line_ids if page.get_block(line_id) is not None]
        polygon = deepcopy(line_blocks[0].polygon)
        if len(line_blocks) > 1:
            polygon = polygon.merge([line.polygon for line in line_blocks[1:]])

        segment = block.__class__(
            polygon=polygon,
            page_id=block.page_id,
            structure=list(line_ids),
            text_extraction_method=block.text_extraction_method,
            source=block.source,
            top_k=deepcopy(block.top_k),
            metadata=deepcopy(block.metadata),
            has_continuation=getattr(block, "has_continuation", False),
            blockquote=getattr(block, "blockquote", False),
            blockquote_level=getattr(block, "blockquote_level", 0),
            html=None,
        )
        page.add_full_block(segment)
        return segment.id

    def _nearest_structure_index(self, page, structure: list, margin) -> int:
        if not structure:
            return 0
        margin_y = float(margin.polygon.center[1])
        best_idx = 0
        best_dy = None
        for idx, block_id in enumerate(structure):
            block = page.get_block(block_id)
            if block is None or block.block_type in {BlockTypes.PageHeader, BlockTypes.PageFooter}:
                continue
            dy = abs(float(block.polygon.center[1]) - margin_y)
            if best_dy is None or dy < best_dy:
                best_idx = idx
                best_dy = dy
        nearest = page.get_block(structure[best_idx])
        if nearest is not None and margin_y > float(nearest.polygon.center[1]):
            return best_idx + 1
        return best_idx

    def _clean_marker(self, text: str) -> str:
        return re.sub(r"\s+", "", str(text or "")).strip()
