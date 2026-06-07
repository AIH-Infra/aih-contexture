from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aih_contexture.builders import BaseBuilder
from aih_contexture.builders.layout import LayoutBuilder
from aih_contexture.middle.adapters.external_layout import external_layout_document_to_middle_document
from aih_contexture.middle.schema import MiddleBlock, MiddleDocument, MiddlePage, MiddleProvenance
from aih_contexture.providers.pdf import PdfProvider
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document
from aih_contexture.schema.groups.page import PageGroup
from aih_contexture.schema.polygon import PolygonBox
from aih_contexture.services.layout_base import LayoutBox, LayoutResult


_MIDDLE_TO_LAYOUT_LABEL = {
    "MarginalNote": "MarginalAnnotation",
    "PageNumber": "PageFooter",
    "ImageDescription": "Caption",
    "Reference": "Text",
}


@dataclass(slots=True)
class _SidecarPage:
    index: int
    width: float | None
    height: float | None
    blocks: list[MiddleBlock]


class ExternalLayoutSidecarBuilder(BaseBuilder):
    """Use an existing external layout JSON file as the Pipeline layout backend.

    This builder is intentionally sidecar-only: MinerU/Paddle or other tools may
    produce JSON before Contexture runs, but this class only consumes that JSON
    and maps it into Contexture's normal layout block path.
    """

    external_layout_json: str | None = None
    external_layout_block_source: str = "auto"
    external_layout_backend_name: str = "external_layout_sidecar"
    external_layout_model: str | None = None
    external_layout_allow_missing_pages: bool = False
    max_expand_frac: float = 0.05

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self._layout_helper = LayoutBuilder(layout_model=None, config=config)
        if isinstance(config, dict):
            self.external_layout_json = (
                config.get("external_layout_json")
                or config.get("external_layout_sidecar_json")
                or self.external_layout_json
            )
            self.external_layout_block_source = str(
                config.get("external_layout_block_source", self.external_layout_block_source)
            )
            self.external_layout_backend_name = str(
                config.get("external_layout_backend_name", self.external_layout_backend_name)
            )
            self.external_layout_model = config.get("external_layout_model", self.external_layout_model)
            self.external_layout_allow_missing_pages = bool(
                config.get(
                    "external_layout_allow_missing_pages",
                    self.external_layout_allow_missing_pages,
                )
            )
            if config.get("max_expand_frac") is not None:
                self.max_expand_frac = float(config["max_expand_frac"])
                self._layout_helper.max_expand_frac = self.max_expand_frac

    def __call__(self, document: Document, provider: PdfProvider):
        sidecar_pages = self._load_pages()
        layout_results = self._layout_results_for_pages(document.pages, sidecar_pages)
        self._layout_helper.add_blocks_to_pages(document.pages, layout_results)
        self._layout_helper.expand_layout_blocks(document)

    def _load_pages(self) -> dict[int, _SidecarPage]:
        if not self.external_layout_json:
            raise ValueError(
                "layout_backend='external_layout_sidecar' requires "
                "'external_layout_json' to point to a MinerU/Paddle/generic layout JSON file "
                "or a Contexture Middle JSON file."
            )

        json_path = Path(self.external_layout_json).expanduser()
        return self._load_pages_from_path(json_path)

    def _load_pages_from_path(self, json_path: Path) -> dict[int, _SidecarPage]:
        if not json_path.exists():
            raise FileNotFoundError(f"External layout sidecar JSON not found: {json_path}")

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        return self._load_pages_from_payload(payload, source=str(json_path))

    def _load_pages_from_payload(
        self,
        payload: Any,
        *,
        source: str | None = None,
    ) -> dict[int, _SidecarPage]:
        if _looks_like_contexture_middle(payload):
            middle_doc = _middle_document_from_dict(payload)
        else:
            middle_doc = external_layout_document_to_middle_document(
                payload,
                backend=self.external_layout_backend_name,
                source=source,
                model=self.external_layout_model,
                block_source=self.external_layout_block_source,
            )

        return {
            page.index: _SidecarPage(
                index=page.index,
                width=page.width,
                height=page.height,
                blocks=list(page.blocks),
            )
            for page in middle_doc.pages
        }

    def _layout_results_for_pages(
        self,
        pages: list[PageGroup],
        sidecar_pages: dict[int, _SidecarPage],
    ) -> list[LayoutResult]:
        layout_results = []
        for sequential_index, page in enumerate(pages):
            page_index = _page_index(page, sequential_index)
            sidecar_page = sidecar_pages.get(page_index) or sidecar_pages.get(sequential_index)
            if sidecar_page is None:
                if self.external_layout_allow_missing_pages:
                    layout_results.append(_full_page_text_layout(page))
                    continue
                available = ", ".join(str(index) for index in sorted(sidecar_pages))
                raise ValueError(
                    "External layout sidecar does not contain a layout page for "
                    f"document page index {page_index}. Available sidecar pages: {available or '(none)'}."
                )

            layout_results.append(_sidecar_page_to_layout_result(sidecar_page, page))
        return layout_results


def _looks_like_contexture_middle(payload: Any) -> bool:
    return isinstance(payload, dict) and isinstance(payload.get("pages"), list) and (
        payload.get("schema_version") or payload.get("page_count") is not None
    )


def _middle_document_from_dict(payload: dict[str, Any]) -> MiddleDocument:
    pages = []
    for page_data in payload.get("pages", []):
        if not isinstance(page_data, dict):
            continue
        pages.append(_middle_page_from_dict(page_data))
    return MiddleDocument(
        source_name=payload.get("source_name"),
        schema_version=payload.get("schema_version", "contexture-middle-json/0.1"),
        metadata=dict(payload.get("metadata") or {}),
        backends=dict(payload.get("backends") or {}),
        pages=pages,
    )


def _middle_page_from_dict(page_data: dict[str, Any]) -> MiddlePage:
    page_index = int(page_data.get("index", page_data.get("page_index", 0)))
    blocks = [
        _middle_block_from_dict(block_data, page_index=page_index, order=order)
        for order, block_data in enumerate(page_data.get("blocks", []) or [])
        if isinstance(block_data, dict)
    ]
    return MiddlePage(
        index=page_index,
        width=_float_or_none(page_data.get("width")),
        height=_float_or_none(page_data.get("height")),
        printed_page=page_data.get("printed_page"),
        blocks=blocks,
        attrs=dict(page_data.get("attrs") or {}),
        provenance=_provenance_from_list(page_data.get("provenance")),
    )


def _middle_block_from_dict(
    block_data: dict[str, Any],
    *,
    page_index: int,
    order: int,
) -> MiddleBlock:
    return MiddleBlock(
        id=str(block_data.get("id") or f"p{page_index}-b{order}"),
        type=str(block_data.get("type") or "ComplexRegion"),
        page_index=int(block_data.get("page_index", page_index)),
        order=int(block_data.get("order", order)),
        text=str(block_data.get("text") or ""),
        anchor_start=block_data.get("anchor_start"),
        anchor_end=block_data.get("anchor_end"),
        bbox=_float_list(block_data.get("bbox"), expected_len=4),
        polygon=_polygon_or_none(block_data.get("polygon")),
        confidence=_float_or_none(block_data.get("confidence")),
        attrs=dict(block_data.get("attrs") or {}),
        provenance=_provenance_from_list(block_data.get("provenance")),
    )


def _provenance_from_list(items: Any) -> list[MiddleProvenance]:
    if not isinstance(items, list):
        return []
    provenance = []
    for item in items:
        if not isinstance(item, dict):
            continue
        provenance.append(
            MiddleProvenance(
                backend=str(item.get("backend") or "unknown"),
                stage=str(item.get("stage") or "layout"),
                raw_label=item.get("raw_label"),
                model=item.get("model"),
                confidence=_float_or_none(item.get("confidence")),
                source=item.get("source"),
                notes=item.get("notes"),
            )
        )
    return provenance


def _sidecar_page_to_layout_result(sidecar_page: _SidecarPage, page: PageGroup) -> LayoutResult:
    page_bbox = _page_image_bbox(sidecar_page, page)
    boxes = []
    for position, block in enumerate(sorted(sidecar_page.blocks, key=lambda item: (item.order, item.id))):
        polygon = _block_polygon(block)
        if polygon is None:
            continue
        label = _layout_label(block.type)
        confidence = block.confidence if block.confidence is not None else 1.0
        boxes.append(
            LayoutBox(
                label=label,
                position=position,
                top_k={label: confidence},
                polygon=polygon,
            )
        )

    return LayoutResult(image_bbox=page_bbox, bboxes=boxes, sliced=False)


def _full_page_text_layout(page: PageGroup) -> LayoutResult:
    return LayoutResult(
        image_bbox=page.polygon.bbox,
        bboxes=[
            LayoutBox(
                label="Text",
                position=0,
                top_k={"Text": 1.0},
                polygon=page.polygon.polygon,
            )
        ],
        sliced=False,
    )


def _layout_label(middle_type: str) -> str:
    mapped = _MIDDLE_TO_LAYOUT_LABEL.get(middle_type, middle_type)
    if mapped in BlockTypes.__members__:
        return mapped
    return "ComplexRegion"


def _block_polygon(block: MiddleBlock) -> list[list[float]] | None:
    if block.polygon:
        return _polygon_or_none(block.polygon)
    if block.bbox:
        return PolygonBox.from_bbox(block.bbox, ensure_nonzero_area=True).polygon
    return None


def _page_image_bbox(sidecar_page: _SidecarPage, page: PageGroup) -> list[float]:
    width = sidecar_page.width
    height = sidecar_page.height
    if width is not None and height is not None and width > 0 and height > 0:
        return [0.0, 0.0, float(width), float(height)]
    return [float(value) for value in page.polygon.bbox]


def _page_index(page: PageGroup, sequential_index: int) -> int:
    value = getattr(page, "page_id", None)
    if value is None:
        return sequential_index
    return int(value)


def _polygon_or_none(value: Any) -> list[list[float]] | None:
    if not (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(point, list) and len(point) == 2 for point in value)
    ):
        return None
    return [[float(point[0]), float(point[1])] for point in value]


def _float_list(value: Any, *, expected_len: int) -> list[float] | None:
    if not isinstance(value, list) or len(value) != expected_len:
        return None
    if not all(isinstance(item, (int, float)) for item in value):
        return None
    return [float(item) for item in value]


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None
