from typing import List

from aih_contexture.schema import BlockTypes
from aih_contexture.schema.blocks import BlockOutput
from aih_contexture.schema.groups.base import Group


class TableGroup(Group):
    block_type: BlockTypes = BlockTypes.TableGroup
    block_description: str = "A table along with associated captions."
    html: str | None = None

    def assemble_html(
        self,
        document,
        child_blocks: List[BlockOutput],
        parent_structure=None,
        block_config: dict | None = None,
    ):
        if self.html:
            return self.handle_html_output(
                document, child_blocks, parent_structure, block_config
            )

        return super().assemble_html(
            document, child_blocks, parent_structure, block_config
        )
