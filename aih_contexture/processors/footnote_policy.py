from copy import deepcopy
from typing import Annotated

from aih_contexture.processors import BaseProcessor
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.blocks.text import Text
from aih_contexture.schema.document import Document


class FootnotePolicyProcessor(BaseProcessor):
    """
    Align footnote-related structure with the footnote_enabled switch.

    When footnote detection is disabled, existing Footnote blocks are relabeled
    back to Text so downstream output no longer treats them as footnotes.
    """

    footnote_enabled: Annotated[bool, "是否启用脚注检测"] = True

    def __call__(self, document: Document):
        if self.footnote_enabled:
            return

        for page in document.pages:
            footnote_blocks = list(page.contained_blocks(document, (BlockTypes.Footnote,)))
            for block in footnote_blocks:
                new_block = Text(
                    polygon=deepcopy(block.polygon),
                    page_id=block.page_id,
                    structure=deepcopy(block.structure),
                    text_extraction_method=block.text_extraction_method,
                    source="processor",
                    top_k=deepcopy(block.top_k),
                    metadata=deepcopy(block.metadata),
                    html=getattr(block, "html", None),
                )
                page.replace_block(block, new_block)
