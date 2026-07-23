import re

from aih_contexture.schema import BlockTypes
from aih_contexture.schema.blocks.base import BlockOutput
from aih_contexture.schema.blocks.basetable import BaseTable


ENTRY_START_RE = re.compile(r"^\s*\d{1,4}[.-]\s*")
PURE_PAGE_NUMBER_RE = re.compile(r"^\s*\d{1,4}\s*$")


class TableOfContents(BaseTable):
    block_type: str = BlockTypes.TableOfContents
    block_description: str = "A table of contents."

    @staticmethod
    def _plain_text(html: str) -> str:
        text = re.sub(r"<[^>]+>", "", html or "")
        return " ".join(text.strip().split())

    @staticmethod
    def _is_heading_line(text: str) -> bool:
        normalized = text.strip()
        if not normalized:
            return False
        if re.match(r"^(BOOK|CHAPTER)\b", normalized, re.IGNORECASE):
            return True
        if re.match(r"^[A-Z]\.\s+\S", normalized):
            return True
        letters = re.sub(r"[^A-Za-z]+", "", normalized)
        return len(letters) >= 6 and letters.upper() == letters

    @staticmethod
    def _line_height(block: BlockOutput) -> float:
        return max(float(block.polygon.height), 1.0)

    def _is_right_page_number_line(self, block: BlockOutput) -> bool:
        text = self._plain_text(block.html)
        if not PURE_PAGE_NUMBER_RE.match(text):
            return False

        toc_bbox = self.polygon.bbox
        toc_width = max(self.polygon.width, 1.0)
        line_width = block.polygon.width
        line_center_x = block.polygon.center[0]
        right_column_start = toc_bbox[0] + toc_width * 0.72
        return line_width <= toc_width * 0.12 and line_center_x >= right_column_start

    def _nearest_left_line(
        self,
        page_number_line: BlockOutput,
        text_lines: list[BlockOutput],
    ) -> BlockOutput | None:
        left_lines = [
            line
            for line in text_lines
            if line.polygon.x_end <= page_number_line.polygon.x_start
        ]
        if not left_lines:
            return None

        median_height = sorted(self._line_height(line) for line in text_lines)[len(text_lines) // 2]
        max_y_distance = max(median_height * 1.4, 12.0)
        page_y = page_number_line.polygon.center[1]
        nearest = min(left_lines, key=lambda line: abs(line.polygon.center[1] - page_y))
        if abs(nearest.polygon.center[1] - page_y) > max_y_distance:
            return None
        return nearest

    def _assemble_toc_entries(self, line_blocks: list[BlockOutput]) -> str | None:
        if not line_blocks:
            return None

        page_number_lines = [
            block for block in line_blocks if self._is_right_page_number_line(block)
        ]
        page_number_ids = {block.id for block in page_number_lines}
        text_lines = [block for block in line_blocks if block.id not in page_number_ids]

        entries = []
        line_to_entry_idx = {}
        current = None

        def finish_current():
            nonlocal current
            if current is not None:
                entries.append(current)
                current = None

        for line in text_lines:
            text = self._plain_text(line.html)
            if not text:
                continue

            if PURE_PAGE_NUMBER_RE.match(text):
                finish_current()
                entries.append({"kind": "entry", "lines": [line], "pages": []})
                line_to_entry_idx[line.id] = len(entries) - 1
                continue

            if ENTRY_START_RE.match(text):
                finish_current()
                current = {"kind": "entry", "lines": [line], "pages": []}
                line_to_entry_idx[line.id] = len(entries)
                continue

            if self._is_heading_line(text):
                finish_current()
                entries.append({"kind": "heading", "lines": [line], "pages": []})
                line_to_entry_idx[line.id] = len(entries) - 1
                continue

            if current is None:
                current = {"kind": "entry", "lines": [line], "pages": []}
            else:
                current["lines"].append(line)
            line_to_entry_idx[line.id] = len(entries)

        finish_current()

        unattached_page_lines = []
        for page_line in page_number_lines:
            nearest = self._nearest_left_line(page_line, text_lines)
            target_idx = line_to_entry_idx.get(nearest.id) if nearest else None
            if target_idx is None or entries[target_idx]["kind"] != "entry":
                unattached_page_lines.append(page_line)
                continue
            entries[target_idx]["pages"].append(page_line)

        for page_line in unattached_page_lines:
            entries.append({"kind": "entry", "lines": [page_line], "pages": []})

        paragraphs = []
        for entry in entries:
            refs = [
                f"<content-ref src='{line.id}'></content-ref>"
                for line in entry["lines"]
            ]
            refs.extend(
                f"<content-ref src='{line.id}'></content-ref>"
                for line in sorted(entry["pages"], key=lambda line: line.polygon.center[1])
            )
            if refs:
                paragraphs.append("<p>" + " ".join(refs) + "</p>")

        if not paragraphs:
            return None
        return "".join(paragraphs)

    def assemble_html(
        self,
        document,
        child_blocks: list[BlockOutput],
        parent_structure=None,
        block_config: dict | None = None,
    ):
        if self.ignore_for_output:
            return ""

        non_cell_blocks = [
            block for block in child_blocks if block.id.block_type != BlockTypes.TableCell
        ]
        if non_cell_blocks:
            toc_html = self._assemble_toc_entries(non_cell_blocks)
            if toc_html:
                return toc_html

            template = "<br>".join(
                f"<content-ref src='{block.id}'></content-ref>"
                for block in non_cell_blocks
            )
            return f"<p>{template}</p>"

        cell_blocks = [
            document.get_block(block.id)
            for block in child_blocks
            if block.id.block_type == BlockTypes.TableCell
        ]
        if cell_blocks:
            rows: dict[int, list] = {}
            for cell in cell_blocks:
                rows.setdefault(cell.row_id, []).append(cell)

            lines = []
            for row_id in sorted(rows):
                row_cells = sorted(rows[row_id], key=lambda cell: cell.col_id)
                row_parts = []
                for cell in row_cells:
                    cell_text = " ".join(
                        line.strip() for line in (cell.text_lines or []) if line.strip()
                    )
                    if cell_text:
                        row_parts.append(cell_text)
                row_text = " ".join(row_parts)
                if row_text:
                    lines.append(row_text)

            if lines:
                return "<p>" + "<br>".join(lines) + "</p>"

        return "<p></p>"
