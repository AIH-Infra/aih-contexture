from typing import Annotated, Tuple

from aih_contexture.processors import BaseProcessor
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document


class BlockquoteProcessor(BaseProcessor):
    """
    A processor for tagging blockquotes.
    """
    block_types: Annotated[
        Tuple[BlockTypes],
        "The block types to process.",
    ] = (BlockTypes.Text, BlockTypes.TextInlineMath)
    min_x_indent: Annotated[
        float,
        "The minimum horizontal indentation required to consider a block as part of a blockquote.",
        "Expressed as a percentage of the block width.",
    ] = 0.1
    x_start_tolerance: Annotated[
        float,
        "The maximum allowable difference between the starting x-coordinates of consecutive blocks to consider them aligned.",
        "Expressed as a percentage of the block width.",
    ] = 0.01
    x_end_tolerance: Annotated[
        float,
        "The maximum allowable difference between the ending x-coordinates of consecutive blocks to consider them aligned.",
        "Expressed as a percentage of the block width.",
    ] = 0.01

    def __init__(self, config):
        super().__init__(config)

    def __call__(self, document: Document):
        for page in document.pages:
            prev_block = None
            for block in page.contained_blocks(document, self.block_types):
                if block.structure is None:
                    prev_block = block
                    continue

                if not len(block.structure) >= 2:
                    prev_block = block
                    continue

                # Check if current block is indented relative to previous block
                if prev_block is not None and prev_block.block_type in self.block_types:
                    if prev_block.structure is not None and not prev_block.ignore_for_output:
                        x_indent = block.polygon.x_start > prev_block.polygon.x_start + (self.min_x_indent * prev_block.polygon.width)
                        y_indent = block.polygon.y_start > prev_block.polygon.y_end

                        if prev_block.blockquote:
                            # Continue blockquote ONLY if both x_start and x_end match AND still indented
                            matching_x_end = abs(block.polygon.x_end - prev_block.polygon.x_end) < self.x_end_tolerance * prev_block.polygon.width
                            matching_x_start = abs(block.polygon.x_start - prev_block.polygon.x_start) < self.x_start_tolerance * prev_block.polygon.width
                            # Must not outdent (x_start cannot significantly decrease)
                            x_not_outdent = block.polygon.x_start >= prev_block.polygon.x_start - (self.x_start_tolerance * prev_block.polygon.width)
                            # Must match both start and end positions AND not outdent to continue blockquote
                            if matching_x_end and matching_x_start and y_indent and x_not_outdent:
                                block.blockquote = True
                                block.blockquote_level = prev_block.blockquote_level
                                if x_indent:
                                    block.blockquote_level += 1
                        elif x_indent and y_indent:
                            # Start new blockquote if current block is indented
                            block.blockquote = True
                            block.blockquote_level = 1

                prev_block = block