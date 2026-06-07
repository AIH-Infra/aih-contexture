from aih_contexture.schema import BlockTypes
from aih_contexture.schema.blocks import Block


class Char(Block):
    block_type: BlockTypes = BlockTypes.Char
    block_description: str = "A single character inside a span."

    text: str
    idx: int
