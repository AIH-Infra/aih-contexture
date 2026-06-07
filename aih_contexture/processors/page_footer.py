from aih_contexture.processors import BaseProcessor
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document
from aih_contexture.schema.groups.page import PageGroup


class PageFooterProcessor(BaseProcessor):
    """
    A processor for moving PageFooters to the bottom.
    """

    block_types = (BlockTypes.PageFooter,)

    def __call__(self, document: Document):
        for page in document.pages:
            self.move_page_footer_to_bottom(page, document)

    def move_page_footer_to_bottom(self, page: PageGroup, document: Document):
        page_footer_blocks = page.contained_blocks(document, self.block_types)
        page_footer_block_ids = [block.id for block in page_footer_blocks]
        for block_id in page_footer_block_ids:
            page.structure.remove(block_id)
        page.structure.extend(page_footer_block_ids)
