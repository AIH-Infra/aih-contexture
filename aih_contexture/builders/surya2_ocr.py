from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass
from typing import Any

import aiohttp
from PIL import Image

from aih_contexture.builders import BaseBuilder
from aih_contexture.builders.ocr import OcrBuilder
from aih_contexture.providers.pdf import PdfProvider
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document
from aih_contexture.schema.groups.page import PageGroup
from aih_contexture.schema.polygon import PolygonBox
from aih_contexture.schema.registry import get_block_class
from aih_contexture.services.ocr_vlm_specialized import OcrSurya2Service


@dataclass(frozen=True)
class Surya2RegionCrop:
    page: PageGroup
    block: Any
    image: Image.Image
    image_size: tuple[int, int]
    page_size: list[float]
    crop_bbox_px: tuple[int, int, int, int]


class Surya2OcrBuilder(BaseBuilder):
    """Pipeline block OCR builder backed by Surya 2 block HTML OCR."""

    skip_ocr_blocks = [
        BlockTypes.Figure,
        BlockTypes.Picture,
        BlockTypes.Form,
        BlockTypes.TableOfContents,
    ]

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        service: OcrSurya2Service | None = None,
    ):
        super().__init__(config)
        self.config = config or {}
        self.service = service or OcrSurya2Service(self.config)
        self._ocr_helper = OcrBuilder(recognition_model=None, config=self.config)
        self.crop_padding_px = int(self.config.get("surya2_crop_padding_px", 4) or 0)
        self.crop_padding_frac = float(self.config.get("surya2_crop_padding_frac", 0.02) or 0.0)
        self.block_concurrency = max(1, int(self.config.get("surya2_block_concurrency", 4) or 4))
        self.api_key = self.config.get("surya2_api_key") or self.config.get("ocr_api_key")

    def __call__(self, document: Document, provider: PdfProvider):
        pages_to_ocr = [page for page in document.pages if page.text_extraction_method == "surya"]
        if not pages_to_ocr:
            return document
        crops = self._collect_crops(document, pages_to_ocr, provider)
        if not crops:
            return document
        results = asyncio.run(self._recognize_crops(crops))
        for crop, result in zip(crops, results):
            if isinstance(result, Exception):
                continue
            self._write_result(document, crop, result)
        return document

    def _collect_crops(
        self,
        document: Document,
        pages: list[PageGroup],
        provider: PdfProvider,
    ) -> list[Surya2RegionCrop]:
        crops: list[Surya2RegionCrop] = []
        for page in pages:
            page_image = page.get_image(highres=True) or page.get_image(highres=False)
            if page_image is None:
                continue
            page_size = provider.get_page_bbox(page.page_id).size
            image_size = page_image.size
            for block in page.structure_blocks(document):
                if getattr(block, "removed", False) or block.block_type in self.skip_ocr_blocks:
                    continue
                crop_bbox = self._block_crop_bbox(block, page_size=page_size, image_size=image_size)
                if crop_bbox is None:
                    continue
                crops.append(
                    Surya2RegionCrop(
                        page=page,
                        block=block,
                        image=page_image.crop(crop_bbox),
                        image_size=image_size,
                        page_size=list(page_size),
                        crop_bbox_px=crop_bbox,
                    )
                )
        return crops

    async def _recognize_crops(self, crops: list[Surya2RegionCrop]) -> list[Any]:
        sem = asyncio.Semaphore(self.block_concurrency)
        async with aiohttp.ClientSession() as session:
            async def run_one(crop: Surya2RegionCrop) -> Any:
                async with sem:
                    return await self.service.recognize_image_async(session, crop.image, api_key=self.api_key)

            return await asyncio.gather(*(run_one(crop) for crop in crops), return_exceptions=True)

    def _block_crop_bbox(
        self,
        block: Any,
        *,
        page_size: list[float],
        image_size: tuple[int, int],
    ) -> tuple[int, int, int, int] | None:
        polygon = getattr(block, "polygon", None)
        if polygon is None:
            return None
        rescaled = copy.deepcopy(polygon).rescale(page_size, image_size).fit_to_bounds((0, 0, *image_size))
        x0, y0, x1, y1 = rescaled.bbox
        if x1 <= x0 or y1 <= y0:
            return None
        pad_x = max(self.crop_padding_px, round((x1 - x0) * self.crop_padding_frac))
        pad_y = max(self.crop_padding_px, round((y1 - y0) * self.crop_padding_frac))
        return (
            max(0, int(x0) - pad_x),
            max(0, int(y0) - pad_y),
            min(image_size[0], int(x1) + pad_x),
            min(image_size[1], int(y1) + pad_y),
        )

    def _write_result(self, document: Document, crop: Surya2RegionCrop, result: dict[str, Any]) -> None:
        lines = self._line_items_from_result(crop, result)
        if not lines:
            return
        SpanClass = get_block_class(BlockTypes.Span)
        LineClass = get_block_class(BlockTypes.Line)
        block = crop.block
        page = crop.page
        if block.block_type == BlockTypes.Line:
            spans = [self._span(SpanClass, page, text, polygon) for text, polygon in lines]
            self._ocr_helper.replace_line_spans(document, page, block, spans)
            return

        for old_line in block.contained_blocks(page, block_types=[BlockTypes.Line]):
            old_line.removed = True
        block.structure = []

        for text, polygon in lines:
            line = LineClass(
                polygon=polygon,
                page_id=block.page_id,
                text_extraction_method="surya",
            )
            span = self._span(SpanClass, page, text, polygon)
            page.add_full_block(line)
            block.add_structure(line)
            page.add_full_block(span)
            line.structure = [span.id]
        try:
            block.set_internal_metadata("ocr_backend", "surya2_ocr")
        except Exception:
            pass

    def _line_items_from_result(
        self,
        crop: Surya2RegionCrop,
        result: dict[str, Any],
    ) -> list[tuple[str, PolygonBox]]:
        items: list[tuple[str, PolygonBox]] = []
        blocks = result.get("blocks") if isinstance(result, dict) else None
        if isinstance(blocks, list):
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                text = str(block.get("text") or "").strip()
                if not text:
                    continue
                polygon = self._local_bbox_to_page_polygon(crop, block.get("bbox"))
                items.extend((line.strip(), polygon or crop.block.polygon) for line in text.splitlines() if line.strip())
        if items:
            return items

        markdown = str(result.get("markdown") or "") if isinstance(result, dict) else ""
        return [
            (line.strip(), crop.block.polygon)
            for line in markdown.splitlines()
            if line.strip()
        ]

    def _local_bbox_to_page_polygon(self, crop: Surya2RegionCrop, local_bbox: Any) -> PolygonBox | None:
        if not (
            isinstance(local_bbox, list)
            and len(local_bbox) == 4
            and all(isinstance(value, (int, float)) for value in local_bbox)
        ):
            return None
        crop_x0, crop_y0, _, _ = crop.crop_bbox_px
        page_bbox_px = [
            crop_x0 + float(local_bbox[0]),
            crop_y0 + float(local_bbox[1]),
            crop_x0 + float(local_bbox[2]),
            crop_y0 + float(local_bbox[3]),
        ]
        return PolygonBox.from_bbox(page_bbox_px, ensure_nonzero_area=True).rescale(crop.image_size, crop.page_size)

    @staticmethod
    def _span(SpanClass, page: PageGroup, text: str, polygon: PolygonBox):
        span = SpanClass(
            text=text.rstrip("\n") + " ",
            formats=["plain"],
            page_id=page.page_id,
            polygon=polygon,
            minimum_position=0,
            maximum_position=0,
            font="Unknown",
            font_weight=0,
            font_size=0,
        )
        span.text_extraction_method = "surya"
        try:
            span.set_internal_metadata("ocr_backend", "surya2_ocr")
        except Exception:
            pass
        return span
