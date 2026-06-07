import html
import re
from typing import ClassVar, List, Literal, Optional

from aih_contexture.schema import BlockTypes
from aih_contexture.schema.blocks import Block
from aih_contexture.util import unwrap_math


ESCAPED_ALLOWED_INLINE_TAG_RE = re.compile(r"&lt;(/?)(sup|sub)&gt;", re.IGNORECASE)


def cleanup_text(full_text):
    full_text = re.sub(r"(\n\s){3,}", "\n\n", full_text)
    full_text = full_text.replace("\xa0", " ")  # Replace non-breaking spaces
    return full_text


def restore_allowed_inline_tags(text: str) -> str:
    """Keep trusted inline semantic tags produced by upstream processors."""
    return ESCAPED_ALLOWED_INLINE_TAG_RE.sub(
        lambda match: f"<{match.group(1)}{match.group(2).lower()}>",
        text,
    )


class Span(Block):
    block_type: BlockTypes = BlockTypes.Span
    block_description: str = "A span of text inside a line."

    text: str
    font: str
    font_weight: float
    font_size: float
    minimum_position: int
    maximum_position: int
    formats: List[
        Literal[
            "plain",
            "math",
            "chemical",
            "bold",
            "italic",
            "highlight",
            "subscript",
            "superscript",
            "small",
            "code",
            "underline",
        ]
    ]
    has_superscript: bool = False
    has_subscript: bool = False
    url: Optional[str] = None
    html: Optional[str] = None

    FOOTNOTE_MARKER_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"^(?:\d{1,3}|[A-Za-z]{1,3}|[IVXLCDMivxlcdm]{1,4}|[*†‡§¶#]+)(?:[)\].-])?$"
    )

    @property
    def bold(self):
        return "bold" in self.formats

    @property
    def italic(self):
        return "italic" in self.formats

    @property
    def math(self):
        return "math" in self.formats

    @property
    def highlight(self):
        return "highlight" in self.formats

    @property
    def superscript(self):
        return "superscript" in self.formats

    @property
    def subscript(self):
        return "subscript" in self.formats

    @property
    def small(self):
        return "small" in self.formats

    @property
    def code(self):
        return "code" in self.formats

    @property
    def underline(self):
        return "underline" in self.formats

    def assemble_html(self, document, child_blocks, parent_structure, block_config):
        if self.ignore_for_output:
            return ""

        if self.html:
            return self.html

        text = self.text

        # Remove trailing newlines
        replaced_newline = False
        while len(text) > 0 and text[-1] in ["\n", "\r"]:
            text = text[:-1]
            replaced_newline = True

        # Remove leading newlines
        while len(text) > 0 and text[0] in ["\n", "\r"]:
            text = text[1:]

        if replaced_newline and not text.endswith("-"):
            text += " "

        text = text.replace(
            "-\n", ""
        )  # Remove hyphenated line breaks from the middle of the span
        text = html.escape(text)
        text = restore_allowed_inline_tags(text)
        text = cleanup_text(text)
        suppress_superscript = self._should_suppress_superscript(
            text, document, parent_structure, block_config
        )

        if self.has_superscript and not suppress_superscript and "<sup>" not in text.lower():
            text = re.sub(r"^([0-9\W]+)(.*)", r"<sup>\1</sup>\2", text)

            # Handle full block superscript
            if "<sup>" not in text:
                text = f"<sup>{text}</sup>"

        if self.url:
            text = f"<a href='{self.url}'>{text}</a>"

        # TODO Support multiple formats
        if self.italic:
            text = f"<i>{text}</i>"
        elif self.bold:
            text = f"<b>{text}</b>"
        elif self.math:
            block_envs = ["split", "align", "gather", "multline"]
            if any(f"\\begin{{{env}}}" in text for env in block_envs):
                display_mode = "block"
            else:
                display_mode = "inline"
            text = f"<math display='{display_mode}'>{text}</math>"
        elif self.highlight:
            text = f"<mark>{text}</mark>"
        elif self.subscript:
            text = f"<sub>{text}</sub>"
        elif self.superscript and not suppress_superscript and "<sup>" not in text.lower():
            text = f"<sup>{text}</sup>"
        elif self.underline:
            text = f"<u>{text}</u>"
        elif self.small:
            text = f"<small>{text}</small>"
        elif self.code:
            text = f"<code>{text}</code>"

        text = unwrap_math(text)
        return text

    def _should_suppress_superscript(self, text: str, document, parent_structure, block_config) -> bool:
        if block_config is None:
            return False

        if not (self.has_superscript or self.superscript):
            return False

        policy = block_config.get("superscript_policy", "auto")
        if policy == "auto":
            policy = "preserve_all" if block_config.get("footnote_enabled", True) else "suppress_footnote_like"

        if policy == "preserve_all":
            return False

        if policy == "suppress_all":
            return not self.math

        if policy != "suppress_footnote_like":
            return False

        marker = html.unescape(text).strip()
        if not marker:
            return False

        if self.math:
            return False

        if self.FOOTNOTE_MARKER_PATTERN.fullmatch(marker):
            return True

        if self._looks_like_embedded_ocr_noise(document, parent_structure, marker):
            return True

        return False

    def _looks_like_embedded_ocr_noise(self, document, parent_structure, marker: str) -> bool:
        if not parent_structure or document is None:
            return False

        try:
            structure_idx = parent_structure.index(self.id)
        except ValueError:
            return False

        prev_text = self._get_neighbor_span_text(document, parent_structure, structure_idx, -1)
        next_text = self._get_neighbor_span_text(document, parent_structure, structure_idx, 1)
        prev_char = self._extract_edge_alnum(prev_text, from_end=True)
        next_char = self._extract_edge_alnum(next_text, from_end=False)

        if len(marker) == 1 and marker.isalpha():
            if prev_char and next_char and prev_char.isalpha() and next_char.isalpha():
                return True

        return False

    def _get_neighbor_span_text(self, document, parent_structure, structure_idx: int, step: int) -> str:
        idx = structure_idx + step
        while 0 <= idx < len(parent_structure):
            neighbor = document.get_block(parent_structure[idx])
            if neighbor and getattr(neighbor, "block_type", None) == BlockTypes.Span:
                return getattr(neighbor, "text", "") or ""
            idx += step
        return ""

    def _extract_edge_alnum(self, text: str, from_end: bool) -> str:
        chars = reversed(text) if from_end else text
        for char in chars:
            if char.isalnum():
                return char
        return ""
