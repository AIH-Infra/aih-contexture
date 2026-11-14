from __future__ import annotations

import re
import unicodedata
from typing import Annotated

from aih_contexture.processors import BaseProcessor
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def assess_text_layer_quality(text: str) -> dict:
    text = text or ""
    reasons: list[str] = []
    if not text.strip():
        reasons.append("empty_text")
    control_ratio = len(_CONTROL_RE.findall(text)) / max(1, len(text))
    if control_ratio > 0.02:
        reasons.append("control_characters")
    replacement_ratio = text.count("�") / max(1, len(text))
    if replacement_ratio > 0.01:
        reasons.append("replacement_characters")
    tokens = re.findall(r"\S+", text)
    if len(tokens) >= 8 and len(set(tokens)) <= max(1, len(tokens) // 4):
        reasons.append("repeated_text")
    printable = sum(not unicodedata.category(ch).startswith("C") or ch in "\n\t" for ch in text)
    if text and printable / len(text) < 0.95:
        reasons.append("low_printable_ratio")
    status = "bad" if reasons else "good"
    return {"status": status, "score": 0.0 if status == "bad" else 1.0, "reasons": reasons, "action": "review" if reasons else "keep"}


class TextLayerQualityProcessor(BaseProcessor):
    block_types = (BlockTypes.Text, BlockTypes.SectionHeader, BlockTypes.Caption, BlockTypes.Footnote)
    text_layer_quality_enabled: Annotated[bool, "Record model-independent text-layer diagnostics."] = True

    def __call__(self, document: Document):
        if not self.text_layer_quality_enabled:
            return
        for page in document.pages:
            for block in page.contained_blocks(document, self.block_types):
                if block.text_extraction_method != "pdftext":
                    continue
                block.set_internal_metadata("text_layer_quality", assess_text_layer_quality(block.raw_text(document)))
