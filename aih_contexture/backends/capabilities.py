from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

BackendKind = Literal["layout", "ocr", "vlm", "office", "postprocess"]


@dataclass(frozen=True, slots=True)
class BackendCapabilities:
    name: str
    kind: BackendKind
    display_name: str
    implemented: bool = True
    requires_service: bool = False
    optional_dependency: str | None = None
    supports_cpu: bool = True
    supports_gpu: bool = True
    supports_bbox: bool = False
    supports_span: bool = False
    supports_confidence: bool = False
    supports_vertical_text: bool = False
    supports_footnote: bool = False
    supports_marginalia: bool = False
    supports_tables: bool = False
    supports_formulas: bool = False
    languages: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""
