from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated, Any

from aih_contexture.backends.ocr.mineru_runtime import MineruPytorchPaddleOcrRuntime
from aih_contexture.builders.paddle_ocr import _item_polygon_to_page
from aih_contexture.builders import BaseBuilder
from aih_contexture.builders.ocr import OcrBuilder
from aih_contexture.providers.pdf import PdfProvider
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document
from aih_contexture.schema.groups.page import PageGroup
from aih_contexture.schema.polygon import PolygonBox
from aih_contexture.schema.registry import get_block_class


class MineruPytorchPaddleOcrBuilder(BaseBuilder):
    """OCR builder backed by MinerU's internal PytorchPaddleOCR engine."""

    mineru_ocr_lang: Annotated[str, "MinerU OCR language code."] = "ch"
    mineru_ocr_min_containment: Annotated[float, "Minimum OCR box containment ratio needed to attach to an existing line."] = 0.20
    mineru_ocr_append_unmatched_lines: Annotated[bool, "Append unmatched OCR boxes as new lines inside the best text block."] = True

    skip_ocr_blocks: Annotated[list[BlockTypes], "Block types to skip OCR."] = [
        BlockTypes.Equation,
        BlockTypes.Figure,
        BlockTypes.Picture,
        BlockTypes.Table,
        BlockTypes.Form,
        BlockTypes.TableOfContents,
    ]

    def __init__(self, config: dict[str, Any] | None = None, *, runtime: MineruPytorchPaddleOcrRuntime | None = None):
        super().__init__(config)
        self.config = config or {}
        self.runtime = runtime or MineruPytorchPaddleOcrRuntime(self.config)
        self._ocr_helper = OcrBuilder(recognition_model=None, config=self.config)
        self.last_runtime_payload: list[dict[str, Any]] | None = None

    def __call__(self, document: Document, provider: PdfProvider):
        pages_to_ocr = [page for page in document.pages if page.text_extraction_method == "surya"]
        if not pages_to_ocr:
            return document

        with tempfile.TemporaryDirectory(prefix="contexture-mineru-ocr-") as temp_dir:
            image_paths, page_sizes = self._save_page_images(pages_to_ocr, Path(temp_dir))
            payload = self.runtime.run(image_paths, page_sizes=page_sizes)
            self.last_runtime_payload = payload

        for page, page_payload, image_size in zip(pages_to_ocr, payload, page_sizes):
            self._write_page_ocr(document, page, page_payload, image_size=image_size, provider=provider)
        return document

    def _save_page_images(self, pages: list[PageGroup], output_dir: Path) -> tuple[list[Path], list[tuple[int, int]]]:
        image_paths: list[Path] = []
        page_sizes: list[tuple[int, int]] = []
        for sequential_index, page in enumerate(pages):
            image = page.get_image(highres=True) or page.get_image(highres=False)
            if image is None:
                raise ValueError(f"Cannot run MinerU OCR: page {sequential_index} has no renderable image.")
            image_path = output_dir / f"page_{sequential_index:06d}.png"
            image.save(image_path)
            image_paths.append(image_path)
            page_sizes.append((int(image.size[0]), int(image.size[1])))
        return image_paths, page_sizes

    def _write_page_ocr(
        self,
        document: Document,
        page: PageGroup,
        page_payload: dict[str, Any],
        *,
        image_size: tuple[int, int],
        provider: PdfProvider,
    ) -> None:
        page_size = provider.get_page_bbox(page.page_id).size
        res = page_payload.get("res") if isinstance(page_payload, dict) else {}
        items = res.get("items") if isinstance(res, dict) else []
        for item in items or []:
            polygon = _item_polygon_to_page(item, old_size=image_size, new_size=page_size)
            if polygon is None:
                continue
            line = self._best_line(document, page, polygon)
            if line is None and self.mineru_ocr_append_unmatched_lines:
                line = self._append_line_for_item(document, page, polygon)
            if line is None:
                continue
            span = self._span_from_item(page, item, polygon)
            self._ocr_helper.replace_line_spans(document, page, line, [span])
            try:
                line.set_internal_metadata("ocr_backend", "mineru_pytorch_paddle_ocr")
                line.set_internal_metadata("ocr_confidence", item.get("confidence"))
                span.set_internal_metadata("ocr_backend", "mineru_pytorch_paddle_ocr")
                span.set_internal_metadata("ocr_confidence", item.get("confidence"))
            except Exception:
                pass

    def _best_line(self, document: Document, page: PageGroup, polygon: PolygonBox):
        best_line = None
        best_score = 0.0
        for block in page.structure_blocks(document):
            if block.block_type in self.skip_ocr_blocks:
                continue
            for line in block.contained_blocks(document, [BlockTypes.Line]):
                score = polygon.intersection_pct(line.polygon)
                if score > best_score:
                    best_score = score
                    best_line = line
        if best_score >= float(self.mineru_ocr_min_containment):
            return best_line
        return None

    def _append_line_for_item(self, document: Document, page: PageGroup, polygon: PolygonBox):
        best_block = None
        best_score = 0.0
        for block in page.structure_blocks(document):
            if block.block_type in self.skip_ocr_blocks:
                continue
            score = polygon.intersection_pct(block.polygon)
            if score > best_score:
                best_score = score
                best_block = block
        if best_block is None or best_score <= 0:
            return None
        LineClass = get_block_class(BlockTypes.Line)
        new_line = LineClass(
            polygon=polygon,
            page_id=page.page_id,
            text_extraction_method="surya",
        )
        page.add_full_block(new_line)
        best_block.add_structure(new_line)
        return new_line

    def _span_from_item(self, page: PageGroup, item: dict[str, Any], polygon: PolygonBox):
        SpanClass = get_block_class(BlockTypes.Span)
        span = SpanClass(
            text=str(item.get("text") or "").strip() + " ",
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
        return span
