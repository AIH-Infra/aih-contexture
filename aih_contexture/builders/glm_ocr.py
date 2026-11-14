from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import aiohttp

from aih_contexture.builders.surya2_ocr import Surya2OcrBuilder, Surya2RegionCrop
from aih_contexture.logger import get_logger
from aih_contexture.providers.pdf import PdfProvider
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document
from aih_contexture.schema.groups.page import PageGroup
from aih_contexture.services.ocr_vlm_specialized import OcrGlmOcrService

logger = get_logger()

# A generation that was cut off, empty, or stuck in a loop is not a transcription.
# These are reported on the block and left unwritten; they are never trimmed to
# something that merely looks plausible.
FATAL_ISSUES = frozenset({"empty_output", "truncated_max_tokens", "repetition_loop"})


@dataclass(frozen=True)
class GlmOcrRegionCrop(Surya2RegionCrop):
    prompt_label: str = "text"


class GlmOcrBuilder(Surya2OcrBuilder):
    """Pipeline block OCR through GLM-OCR (OpenAI-compatible service).

    Same shape as the Surya 2 block OCR: it reuses the layout blocks already in
    the document, crops each one, and asks the service for one task prompt per
    crop. Differences that matter for traceability:

    * GLM-OCR returns no coordinates, so every written line keeps the layout
      block's polygon and the block is marked ``ocr_bbox_precision="block"``.
    * A failed, truncated or looping block is recorded on the block
      (``ocr_failure``) and counted in the log instead of being skipped silently.
    * Equation blocks are only sent when ``glm_ocr_recognize_formulas`` is true:
      the formula prompt has not been validated on our material.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        service: OcrGlmOcrService | None = None,
    ):
        cfg = config or {}
        super().__init__(cfg, service=service or OcrGlmOcrService(cfg))
        self.crop_padding_px = int(cfg.get("glm_ocr_crop_padding_px", 4) or 0)
        self.crop_padding_frac = float(cfg.get("glm_ocr_crop_padding_frac", 0.02) or 0.0)
        self.block_concurrency = max(1, int(cfg.get("glm_ocr_block_concurrency", 4) or 4))
        self.api_key = cfg.get("glm_ocr_api_key") or cfg.get("ocr_api_key")
        self.recognize_formulas = bool(cfg.get("glm_ocr_recognize_formulas", False))
        self.last_summary: dict[str, Any] = {}
        self._formulas_skipped = 0

    def __call__(self, document: Document, provider: PdfProvider):
        pages_to_ocr = [page for page in document.pages if page.text_extraction_method == "surya"]
        if not pages_to_ocr:
            return document
        crops = self._collect_crops(document, pages_to_ocr, provider)
        if not crops:
            return document
        results = asyncio.run(self._recognize_crops(crops))
        written = 0
        failures: list[tuple[str, str]] = []
        for crop, result in zip(crops, results):
            if isinstance(result, Exception):
                reason = f"{type(result).__name__}: {str(result)[:200]}"
            else:
                reason = self._fatal_reason(result)
            if reason:
                self._record_failure(crop, reason)
                failures.append((str(getattr(crop.block, "id", "?")), reason))
                continue
            self._write_result(document, crop, result)
            written += 1
        self.last_summary = {
            "backend": "glm_ocr",
            "requested": len(crops),
            "written": written,
            "failed": len(failures),
            "formulas_skipped": self._formulas_skipped,
        }
        if failures:
            logger.warning(
                "[GLM-OCR] %s of %s blocks not written (kept without text, marked ocr_failure): %s",
                len(failures),
                len(crops),
                "; ".join(f"{block_id}: {reason}" for block_id, reason in failures[:5])
                + (" ..." if len(failures) > 5 else ""),
            )
        logger.info("[GLM-OCR] %s", self.last_summary)
        return document

    def _collect_crops(
        self,
        document: Document,
        pages: list[PageGroup],
        provider: PdfProvider,
    ) -> list[GlmOcrRegionCrop]:
        self._formulas_skipped = 0
        crops: list[GlmOcrRegionCrop] = []
        for page in pages:
            page_image = page.get_image(highres=True) or page.get_image(highres=False)
            if page_image is None:
                continue
            page_size = provider.get_page_bbox(page.page_id).size
            image_size = page_image.size
            for block in page.structure_blocks(document):
                if getattr(block, "removed", False) or block.block_type in self.skip_ocr_blocks:
                    continue
                if block.block_type == BlockTypes.Equation and not self.recognize_formulas:
                    self._formulas_skipped += 1
                    continue
                crop_bbox = self._block_crop_bbox(block, page_size=page_size, image_size=image_size)
                if crop_bbox is None:
                    continue
                crops.append(
                    GlmOcrRegionCrop(
                        page=page,
                        block=block,
                        image=page_image.crop(crop_bbox),
                        image_size=image_size,
                        page_size=list(page_size),
                        crop_bbox_px=crop_bbox,
                        prompt_label=self._prompt_label_for_block(block),
                    )
                )
        return crops

    async def _recognize_crops(self, crops: list[GlmOcrRegionCrop]) -> list[Any]:
        sem = asyncio.Semaphore(self.block_concurrency)
        async with aiohttp.ClientSession() as session:
            async def run_one(crop: GlmOcrRegionCrop) -> Any:
                async with sem:
                    return await self.service.recognize_image_async(
                        session,
                        crop.image,
                        api_key=self.api_key,
                        prompt_label=crop.prompt_label,
                    )

            return await asyncio.gather(*(run_one(crop) for crop in crops), return_exceptions=True)

    @staticmethod
    def _prompt_label_for_block(block: Any) -> str:
        block_type = getattr(block, "block_type", None)
        if block_type == BlockTypes.Table:
            return "table"
        if block_type == BlockTypes.Equation:
            return "formula"
        return "text"

    @staticmethod
    def _fatal_reason(result: Any) -> str:
        if not isinstance(result, dict):
            return "invalid_result"
        fatal = [issue for issue in (result.get("issues") or []) if issue in FATAL_ISSUES]
        return ",".join(fatal)

    @staticmethod
    def _record_failure(crop: GlmOcrRegionCrop, reason: str) -> None:
        try:
            crop.block.set_internal_metadata("ocr_backend", "glm_ocr")
            crop.block.set_internal_metadata("ocr_failure", reason)
            crop.block.set_internal_metadata("ocr_prompt_label", crop.prompt_label)
        except Exception:
            pass

    def _write_result(self, document: Document, crop: GlmOcrRegionCrop, result: dict[str, Any]) -> None:
        text = str(result.get("markdown") or "")
        # No bbox on purpose: the parent falls back to the layout block's polygon.
        super()._write_result(document, crop, {"blocks": [{"text": text}]})
        block = crop.block
        try:
            block.set_internal_metadata("ocr_backend", "glm_ocr")
            block.set_internal_metadata("ocr_prompt_label", crop.prompt_label)
            block.set_internal_metadata("ocr_bbox_precision", "block")
        except Exception:
            pass
        table_html = str(result.get("html") or "")
        if table_html and block.block_type == BlockTypes.Table:
            block.html = table_html

    @staticmethod
    def _span(SpanClass, page: PageGroup, text: str, polygon):
        span = Surya2OcrBuilder._span(SpanClass, page, text, polygon)
        try:
            span.set_internal_metadata("ocr_backend", "glm_ocr")
        except Exception:
            pass
        return span
