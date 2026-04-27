from aih_contexture.logger import get_logger
from aih_contexture.processors import BaseProcessor
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.blocks import Code
from aih_contexture.schema.document import Document

logger = get_logger()


class CodeProcessor(BaseProcessor):
    """
    A processor for formatting code blocks.
    """
    block_types = (BlockTypes.Code, )

    def __call__(self, document: Document):
        code_block_count = 0
        total_lines = 0
        total_characters = 0

        for page in document.pages:
            for block in page.contained_blocks(document, self.block_types):
                line_count, char_count = self.format_block(document, block)
                code_block_count += 1
                total_lines += line_count
                total_characters += char_count

        logger.info(
            "[CodeProcessor] completed: code_blocks=%s total_lines=%s total_characters=%s",
            code_block_count,
            total_lines,
            total_characters,
        )

    def format_block(self, document: Document, block: Code):
        min_left = 9999  # will contain x- coord of column 0
        total_width = 0
        total_chars = 0

        contained_lines = block.contained_blocks(document, (BlockTypes.Line,))
        for line in contained_lines:
            min_left = min(line.polygon.bbox[0], min_left)
            total_width += line.polygon.width
            total_chars += len(line.raw_text(document))

        avg_char_width = total_width / max(total_chars, 1)
        code_text = ""
        is_new_line = False
        for line in contained_lines:
            text = line.raw_text(document)
            if avg_char_width == 0:
                prefix = ""
            else:
                total_spaces = int((line.polygon.bbox[0] - min_left) / avg_char_width)
                prefix = " " * max(0, total_spaces)

            if is_new_line:
                text = prefix + text

            code_text += text
            is_new_line = text.endswith("\n")

        block.code = code_text.rstrip()
        return len(contained_lines), len(block.code)
