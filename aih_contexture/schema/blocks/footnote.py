import re

from aih_contexture.schema import BlockTypes
from aih_contexture.utils.footnote_markers import normalize_footnote_marker
from aih_contexture.schema.blocks import Block


class Footnote(Block):
    block_type: BlockTypes = BlockTypes.Footnote
    block_description: str = (
        "A footnote that explains a term or concept in the document."
    )
    replace_output_newlines: bool = True
    html: str | None = None

    def assemble_html(
        self, document, child_blocks, parent_structure, block_config=None
    ):
        if self.html:
            html = super().handle_html_output(
                document, child_blocks, parent_structure, block_config
            )
        else:
            html = super().assemble_html(
                document, child_blocks, parent_structure, block_config
            )

        # Layout/text-layer extraction can preserve a footnote number's
        # visual bold formatting as <b>25</b>. At this point the block type is
        # authoritative, so normalize only the leading marker of this
        # Footnote block and leave bold text in the note body untouched.
        return self._normalize_leading_marker(html)

    @staticmethod
    def _normalize_leading_marker(html: str) -> str:
        marker_re = re.compile(
            r"^(?P<prefix>\s*<p\b[^>]*>\s*)"
            r"<(?P<tag>b|strong)\b[^>]*>\s*"
            r"(?P<marker>\d{1,4}|[IVXLCDMivxlcdm]{1,12}|[*†‡§¶#]+)"
            r"(?P<suffix>[)\].-]?)\s*"
            r"</(?P=tag)>",
            re.IGNORECASE,
        )

        def replace(match: re.Match[str]) -> str:
            marker = normalize_footnote_marker(match.group("marker"))
            if marker is None:
                return match.group(0)
            return f"{match.group('prefix')}<sup>{marker}</sup>"

        return marker_re.sub(replace, str(html or ""), count=1)
