"""Automatic text reference from a PDF's own text layer, with a trust gate.

A PDF text layer is only a usable reference when it is the real text of the page:
digital-born PDFs usually qualify, scanned PDFs with an OCR layer on top do not
(the layer is itself an OCR result, often invisible, sometimes stacked twice).
``judge_text_layer`` refuses to call a page trusted unless it passes the checks
below; untrusted pages are reported but never enter an aggregate.

The thresholds for invisible text and bad characters follow the values used by
Datalab's Indra text-layer checks (invisible > 5 %, bad characters > 0.5 %).
They were not tuned on our corpus.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aih_contexture.evaluation.metrics import normalize_text

MAX_INVISIBLE_FRACTION = 0.05
MAX_BAD_CHAR_FRACTION = 0.005
MIN_CHARS = 30
# Two halves of a page text that are near-identical mean the layer was stacked twice.
DUPLICATE_HALF_SIMILARITY = 0.85


@dataclass(slots=True)
class LayerChar:
    char: str
    center: tuple[float, float]
    seq: int


@dataclass(slots=True)
class TextLayerTruth:
    page_index: int
    width: float
    height: float
    chars: list[LayerChar] = field(default_factory=list)
    invisible_chars: int = 0

    @property
    def text(self) -> str:
        return "".join(item.char for item in self.chars)

    def text_in_bbox(self, bbox: list[float] | tuple[float, ...]) -> str:
        return "".join(item.char for item in self.chars_in_bbox(bbox))

    def chars_in_bbox(self, bbox: list[float] | tuple[float, ...]) -> list[LayerChar]:
        x0, y0, x1, y1 = bbox
        return [item for item in self.chars if x0 <= item.center[0] <= x1 and y0 <= item.center[1] <= y1]


def extract_text_layer(pdf_path: str | Path, page_index: int, *, include_invisible: bool = False) -> TextLayerTruth:
    """Visible fill-text characters of one page, in content-stream order, with positions.

    Invisible text (render mode 3, clipped, stroke-only) is counted but not returned:
    it is exactly what an OCR layer on a scan looks like. ``include_invisible`` returns it
    as well, for scoring against an embedded OCR layer; ``invisible_chars`` still counts it.
    """
    import pymupdf

    with pymupdf.open(str(pdf_path)) as document:
        page = document[page_index]
        truth = TextLayerTruth(page_index=page_index, width=float(page.rect.width), height=float(page.rect.height))
        seq = 0
        for trace in page.get_texttrace():
            visible = trace.get("type") == 0 and float(trace.get("opacity", 1.0)) > 0
            for entry in trace.get("chars", ()):
                codepoint, bbox = entry[0], entry[3]
                if not visible:
                    truth.invisible_chars += 1
                    if not include_invisible:
                        continue
                char = chr(codepoint)
                truth.chars.append(
                    LayerChar(char, ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0), seq)
                )
                seq += 1
    return truth


def _is_bad_char(char: str) -> bool:
    if char == "�":
        return True
    category = unicodedata.category(char)
    return category in {"Cc", "Co", "Cs", "Cn"} and char not in "\t\n\r"


def judge_text_layer(truth: TextLayerTruth, *, allow_embedded_ocr: bool = False) -> dict[str, Any]:
    """Return {"trusted": bool, "reasons": [...], "stats": {...}} for one page.

    With ``allow_embedded_ocr`` a page whose text is *only* an invisible layer (a scan with an
    OCR layer) is accepted as a reference of kind ``embedded_ocr``. That reference is somebody
    else's OCR output: scores against it measure agreement, not accuracy. A page that has both
    a visible and an invisible layer is never accepted in that mode, since which one is the
    real text is exactly what is unknown.
    """
    from aih_contexture.evaluation.metrics import edit_distance

    total_chars = len(truth.chars)
    visible = total_chars - (truth.invisible_chars if allow_embedded_ocr else 0)
    total = visible + truth.invisible_chars
    invisible_fraction = truth.invisible_chars / total if total else 0.0
    bad = sum(1 for item in truth.chars if _is_bad_char(item.char))
    bad_fraction = bad / total_chars if total_chars else 0.0

    duplicate_similarity = None
    normalized = normalize_text(truth.text)
    if len(normalized) >= 2 * MIN_CHARS:
        half = len(normalized) // 2
        first, second = normalized[:half], normalized[half : 2 * half]
        duplicate_similarity = 1.0 - edit_distance(first, second) / max(len(first), 1)

    reasons: list[str] = []
    if len(normalized) < MIN_CHARS:
        reasons.append("too_few_visible_chars")
    reference_kind = "visible_text_layer"
    if invisible_fraction > MAX_INVISIBLE_FRACTION:
        if allow_embedded_ocr and (1.0 - invisible_fraction) <= MAX_INVISIBLE_FRACTION:
            reference_kind = "embedded_ocr_layer"
        elif allow_embedded_ocr:
            reasons.append("mixed_visible_and_invisible_layers")
        else:
            reasons.append("invisible_text_layer")
    if bad_fraction > MAX_BAD_CHAR_FRACTION:
        reasons.append("bad_characters")
    if duplicate_similarity is not None and duplicate_similarity >= DUPLICATE_HALF_SIMILARITY:
        reasons.append("duplicated_text_layer")
    return {
        "trusted": not reasons,
        "reasons": reasons,
        "reference_kind": reference_kind,
        "stats": {
            "visible_chars": visible,
            "invisible_chars": truth.invisible_chars,
            "invisible_fraction": round(invisible_fraction, 4),
            "bad_char_fraction": round(bad_fraction, 4),
            "duplicate_half_similarity": None if duplicate_similarity is None else round(duplicate_similarity, 4),
        },
    }
