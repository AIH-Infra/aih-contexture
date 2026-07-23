from __future__ import annotations

from typing import Annotated, Any

from aih_contexture.builders import BaseBuilder
from aih_contexture.builders.ocr import OcrBuilder
from aih_contexture.builders.ocr_line_crops import DEFAULT_SKIP_OCR_BLOCKS, OcrLineCropper
from aih_contexture.builders.tesseract_line_detection import ensure_tesseract_line_blocks
from aih_contexture.logger import get_logger
from aih_contexture.providers.pdf import PdfProvider
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document
from aih_contexture.schema.registry import get_block_class
from aih_contexture.services.ocr_tesseract import TesseractOcrService

logger = get_logger()


class TesseractOcrBuilder(BaseBuilder):
    """Pipeline OCR builder backed by a system Tesseract executable."""

    tesseract_lang: Annotated[str, "Tesseract language expression, e.g. eng or chi_sim+eng."] = "eng"
    tesseract_oem: Annotated[int, "Tesseract OCR Engine Mode."] = 1
    tesseract_psm: Annotated[int, "Tesseract Page Segmentation Mode."] = 7
    tesseract_timeout: Annotated[int, "Per-line OCR timeout in seconds."] = 30
    tesseract_omp_thread_limit: Annotated[int, "OMP thread limit for Tesseract subprocesses."] = 1

    skip_ocr_blocks = DEFAULT_SKIP_OCR_BLOCKS

    def __init__(self, config: dict[str, Any] | None = None, *, service: TesseractOcrService | None = None):
        super().__init__(config)
        self.config = config or {}
        self.service = service or TesseractOcrService(self.config)
        self.cropper = OcrLineCropper(self.config)
        self._ocr_helper = OcrBuilder(recognition_model=None, config=self.config)

    def __call__(self, document: Document, provider: PdfProvider):
        pages_to_ocr = [page for page in document.pages if page.text_extraction_method == "surya"]
        skipped_pages = len(document.pages) - len(pages_to_ocr)
        logger.info(
            "[TesseractOcrBuilder] OCR page selection: pages_to_ocr=%s skipped_pdftext=%s force_ocr=%s",
            len(pages_to_ocr),
            skipped_pages,
            bool(self.config.get("force_ocr", False)),
        )
        if not pages_to_ocr:
            logger.info("[TesseractOcrBuilder] No pages need OCR")
            return document

        ok, requested, missing = self.service.validate_languages()
        if not ok:
            raise RuntimeError(
                "Tesseract language pack missing: "
                + ", ".join(missing)
                + ". Requested: "
                + "+".join(requested)
            )

        command_info = self.service.resolve_command()
        logger.info(
            "[TesseractOcrBuilder] Using Tesseract: command=%s version=%s source=%s",
            command_info.command,
            command_info.version,
            command_info.source,
        )

        for page in pages_to_ocr:
            self._ocr_page(document, page, provider)
        return document

    def _ocr_page(self, document: Document, page, provider: PdfProvider) -> None:
        if str(self.config.get("ocr_line_source") or "").strip().lower() == "tesseract":
            written = ensure_tesseract_line_blocks(
                document,
                page,
                provider,
                self.service,
                skip_blocks=set(self.skip_ocr_blocks),
                write_tesseract_text=True,
            )
            logger.info(
                "[TesseractOcrBuilder] Page %s complete via Tesseract line detection: written=%s",
                page.page_id,
                written,
            )
            return

        crops = self.cropper.collect_page_crops(document, page, provider, skip_blocks=set(self.skip_ocr_blocks))
        if not crops:
            logger.info("[TesseractOcrBuilder] No line crops for page %s", page.page_id)
            return

        SpanClass = get_block_class(BlockTypes.Span)
        written = 0
        empty = 0
        failed = 0
        for crop in crops:
            line_block = page.get_block(crop.line_id)
            if line_block is None:
                failed += 1
                continue
            try:
                text = self.service.recognize_line(crop.image)
            except Exception as exc:
                failed += 1
                logger.warning(
                    "[TesseractOcrBuilder] OCR failed: page=%s line=%s error=%s",
                    page.page_id,
                    crop.line_id,
                    exc,
                )
                continue
            text = text.strip()
            if not text:
                empty += 1
                continue
            span = SpanClass(
                text=text + " ",
                formats=["plain"],
                page_id=page.page_id,
                polygon=line_block.polygon,
                minimum_position=0,
                maximum_position=0,
                font="Unknown",
                font_weight=0,
                font_size=0,
            )
            span.text_extraction_method = "surya"
            self._ocr_helper.replace_line_spans(document, page, line_block, [span])
            self._set_metadata(line_block, span)
            written += 1

        logger.info(
            "[TesseractOcrBuilder] Page %s complete: crops=%s written=%s empty=%s failed=%s",
            page.page_id,
            len(crops),
            written,
            empty,
            failed,
        )

    def _set_metadata(self, line_block, span) -> None:
        try:
            info = self.service.resolve_command()
            metadata = {
                "ocr_backend": "tesseract",
                "tesseract_profile": self.config.get("tesseract_profile", "printed_latin"),
                "tesseract_lang": self.service.tesseract_lang,
                "tesseract_oem": self.service.tesseract_oem,
                "tesseract_psm": self.service.tesseract_psm,
                "tesseract_command": info.command,
                "tesseract_version": info.version,
            }
            for key, value in metadata.items():
                line_block.set_internal_metadata(key, value)
                span.set_internal_metadata(key, value)
        except Exception:
            pass
