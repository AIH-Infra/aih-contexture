import re

from aih_contexture.logger import get_logger
from aih_contexture.processors import BaseProcessor
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document
from aih_contexture.schema.groups import PageGroup

logger = get_logger()


class FootnoteProcessor(BaseProcessor):
    """
    A processor for pushing footnotes to the bottom, and relabeling mislabeled text blocks.
    """
    block_types = (BlockTypes.Footnote,)

    def __call__(self, document: Document):
        moved_footnotes = 0
        superscripted_spans = 0

        for page in document.pages:
            moved_footnotes += self.push_footnotes_to_bottom(page, document)
            superscripted_spans += self.assign_superscripts(page, document)

        logger.info(
            "[FootnoteProcessor] completed: moved_footnotes=%s superscripted_spans=%s",
            moved_footnotes,
            superscripted_spans,
        )

    def push_footnotes_to_bottom(self, page: PageGroup, document: Document):
        footnote_blocks = sorted(
            page.contained_blocks(document, self.block_types),
            key=self._block_position_key,
        )
        moved_footnotes = 0

        for block in footnote_blocks:
            if block.id in page.structure:
                page.structure.remove(block.id)
                moved_footnotes += 1
            elif self._remove_from_nested_structures(page, block):
                moved_footnotes += 1

        for block in footnote_blocks:
            if block.id not in page.structure:
                page.add_structure(block)

        return moved_footnotes

    def _remove_from_nested_structures(self, page: PageGroup, block) -> bool:
        removed = False
        for candidate in page.current_children:
            structure = getattr(candidate, "structure", None)
            if structure and block.id in structure:
                structure.remove(block.id)
                removed = True
        return removed

    def _block_position_key(self, block):
        bbox = getattr(getattr(block, "polygon", None), "bbox", None)
        if not bbox or len(bbox) != 4:
            return (float("inf"), float("inf"))
        return (float(bbox[1]), float(bbox[0]))

    def assign_superscripts(self, page: PageGroup, document: Document):
        footnote_blocks = page.contained_blocks(document, self.block_types)
        superscripted_spans = 0

        for block in footnote_blocks:
            for span in block.contained_blocks(document, (BlockTypes.Span,)):
                if re.match(r"^[0-9\W]+", span.text):
                    span.has_superscript = True
                    superscripted_spans += 1
                break

        return superscripted_spans
