from __future__ import annotations

from typing import Annotated

from aih_contexture.processors import BaseProcessor
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document


class RunningFurnitureProcessor(BaseProcessor):
    """Conservatively suppress missed running headers and footers."""

    block_types = (BlockTypes.Text, BlockTypes.SectionHeader, BlockTypes.Caption)
    running_furniture_enabled: Annotated[bool, "Enable conservative running header/footer heuristics."] = False
    header_zone: float = 0.08
    footer_zone: float = 0.13
    max_height_frac: float = 0.035
    max_chars: int = 150
    include_page_header_comments: bool = False
    include_page_footer_comments: bool = False

    def __call__(self, document: Document):
        if not self.running_furniture_enabled:
            return
        for page in document.pages:
            blocks = [b for b in page.structure_blocks(document) if b.block_type in self.block_types and not b.ignore_for_output]
            if len(blocks) < 2 or not page.polygon.height:
                continue
            top = page.polygon.bbox[1]
            height = page.polygon.height
            body = [b for b in blocks if (b.polygon.bbox[3]-top)/height > self.header_zone and (b.polygon.bbox[1]-top)/height < 1-self.footer_zone]
            if not body:
                continue
            body_top = min((b.polygon.bbox[1]-top)/height for b in body)
            body_bottom = max((b.polygon.bbox[3]-top)/height for b in body)
            for block in blocks:
                y0=(block.polygon.bbox[1]-top)/height; y1=(block.polygon.bbox[3]-top)/height
                text=block.raw_text(document).strip()
                is_header = y1 <= self.header_zone and y1 <= body_top and not self.include_page_header_comments
                is_footer = y0 >= 1-self.footer_zone and y0 >= body_bottom and not self.include_page_footer_comments
                if (is_header or is_footer) and block.polygon.height/height <= self.max_height_frac and len(text) <= self.max_chars:
                    block.ignore_for_output = True
                    block.source = "heuristics"
                    block.set_internal_metadata("running_furniture", {"kind": "header" if is_header else "footer", "reason": "position_size_length"})
