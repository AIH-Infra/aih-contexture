from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

SCHEMA_VERSION = "contexture-middle-json/0.1"

CanonicalBlockType = Literal[
    "Text",
    "SectionHeader",
    "PageHeader",
    "PageFooter",
    "PageNumber",
    "Footnote",
    "MarginalNote",
    "InlineAnnotation",
    "Reference",
    "Caption",
    "Figure",
    "Picture",
    "ImageDescription",
    "Table",
    "Equation",
    "ListItem",
    "Code",
    "Form",
    "Handwriting",
    "TableOfContents",
    "ComplexRegion",
]

CANONICAL_BLOCK_TYPES: tuple[str, ...] = (
    "Text",
    "SectionHeader",
    "PageHeader",
    "PageFooter",
    "PageNumber",
    "Footnote",
    "MarginalNote",
    "InlineAnnotation",
    "Reference",
    "Caption",
    "Figure",
    "Picture",
    "ImageDescription",
    "Table",
    "Equation",
    "ListItem",
    "Code",
    "Form",
    "Handwriting",
    "TableOfContents",
    "ComplexRegion",
)


@dataclass(slots=True)
class MiddleProvenance:
    backend: str
    stage: str
    raw_label: str | None = None
    model: str | None = None
    confidence: float | None = None
    source: str | None = None
    notes: str | None = None


@dataclass(slots=True)
class MiddleSpan:
    text: str
    bbox: list[float] | None = None
    polygon: list[list[float]] | None = None
    confidence: float | None = None
    attrs: dict[str, Any] = field(default_factory=dict)
    provenance: list[MiddleProvenance] = field(default_factory=list)


@dataclass(slots=True)
class MiddleBlock:
    id: str
    type: CanonicalBlockType | str
    page_index: int
    order: int
    text: str = ""
    anchor_start: int | None = None
    anchor_end: int | None = None
    bbox: list[float] | None = None
    polygon: list[list[float]] | None = None
    confidence: float | None = None
    spans: list[MiddleSpan] = field(default_factory=list)
    children: list["MiddleBlock"] = field(default_factory=list)
    attrs: dict[str, Any] = field(default_factory=dict)
    provenance: list[MiddleProvenance] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.anchor_start is None:
            self.anchor_start = self.page_index
        if self.anchor_end is None:
            self.anchor_end = self.page_index + 1


@dataclass(slots=True)
class MiddlePage:
    index: int
    width: float | None = None
    height: float | None = None
    printed_page: str | None = None
    blocks: list[MiddleBlock] = field(default_factory=list)
    attrs: dict[str, Any] = field(default_factory=dict)
    provenance: list[MiddleProvenance] = field(default_factory=list)

    @property
    def anchor_start(self) -> int:
        return self.index

    @property
    def anchor_end(self) -> int:
        return self.index + 1


@dataclass(slots=True)
class MiddleDocument:
    pages: list[MiddlePage]
    source_name: str | None = None
    schema_version: str = SCHEMA_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)
    backends: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["page_count"] = len(self.pages)
        for page in data["pages"]:
            page["anchor_start"] = page["index"]
            page["anchor_end"] = page["index"] + 1
        return data

    @property
    def page_count(self) -> int:
        return len(self.pages)
