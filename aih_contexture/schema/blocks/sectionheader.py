from typing import Optional
import re

from aih_contexture.schema import BlockTypes
from aih_contexture.schema.blocks import Block
from aih_contexture.utils.toc_entries import is_toc_line_cluster, plain_toc_text


class SectionHeader(Block):
    block_type: BlockTypes = BlockTypes.SectionHeader
    heading_level: Optional[int] = None
    block_description: str = "The header of a section of text or other blocks."
    html: str | None = None

    def assemble_html(
        self, document, child_blocks, parent_structure, block_config=None
    ):
        if self.ignore_for_output:
            return ""

        if self.html:
            return super().handle_html_output(
                document, child_blocks, parent_structure, block_config
            )

        template = super().assemble_html(
            document, child_blocks, parent_structure, block_config
        )
        toc_lines = [
            line.strip()
            for line in re.split(r"\n|<br\s*/?>", template)
            if plain_toc_text(line)
        ]
        if is_toc_line_cluster(toc_lines):
            return "<p>" + "<br>".join(toc_lines) + "</p>"
        template = template.replace("\n", " ")
        tag = f"h{self.heading_level}" if self.heading_level else "h2"
        return f"<{tag}>{template}</{tag}>"
