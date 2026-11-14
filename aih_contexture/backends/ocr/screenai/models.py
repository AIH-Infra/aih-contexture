"""Public data model for OCR results."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class BoundingBox:
    x: float
    y: float
    width: float
    height: float
    angle: float = 0.0  # clockwise rotation in degrees (from screen-ai Rect.angle)


@dataclass
class OcrWord:
    text: str
    confidence: float | None = None
    bounding_box: BoundingBox | None = None


@dataclass
class OcrLine:
    text: str
    words: list[OcrWord] = field(default_factory=list)
    bounding_box: BoundingBox | None = None


@dataclass
class OcrBlock:
    block_type: str  # "paragraph", "heading", "image", ...
    lines: list[OcrLine] = field(default_factory=list)
    bounding_box: BoundingBox | None = None

    @property
    def text(self) -> str:
        return "\n".join(ln.text for ln in self.lines)


@dataclass
class OcrPage:
    page_number: int
    blocks: list[OcrBlock] = field(default_factory=list)
    width: float | None = None
    height: float | None = None

    @property
    def text(self) -> str:
        return "\n\n".join(blk.text for blk in self.blocks if blk.text.strip())


@dataclass
class OcrResult:
    pages: list[OcrPage] = field(default_factory=list)

    def to_text(self) -> str:
        """Plain text, pages separated by form-feed."""
        return "\f".join(page.text for page in self.pages)

    def to_dict(self) -> dict:
        d = asdict(self)
        _strip_none_boxes(d)
        return d


def _strip_none_boxes(obj: object) -> None:
    """Recursively remove bounding_box keys that are None."""
    if isinstance(obj, dict):
        for k in [k for k, v in obj.items() if k == "bounding_box" and v is None]:
            del obj[k]
        for v in obj.values():
            _strip_none_boxes(v)
    elif isinstance(obj, list):
        for item in obj:
            _strip_none_boxes(item)
