from typing import Annotated

from pydantic import BaseModel

from aih_contexture.builders import BaseBuilder
from aih_contexture.builders.layout import LayoutBuilder
from aih_contexture.builders.line import LineBuilder
from aih_contexture.builders.ocr import OcrBuilder
from aih_contexture.config.dpi_presets import get_layout_dpi, get_ocr_dpi
from aih_contexture.providers.pdf import PdfProvider
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document
from aih_contexture.schema.groups.page import PageGroup
from aih_contexture.schema.registry import get_block_class


class DocumentBuilder(BaseBuilder):
    """
    Constructs a Document given a PdfProvider, LayoutBuilder, and OcrBuilder.
    """
    lowres_image_dpi: Annotated[
        int,
        "DPI setting for low-resolution page images used for Layout and Line Detection.",
    ] = 96
    highres_image_dpi: Annotated[
        int,
        "DPI setting for high-resolution page images used for OCR.",
    ] = 192
    layout_backend: Annotated[
        str,
        "Pipeline layout backend used to select default layout render DPI.",
    ] = "surya"
    ocr_backend: Annotated[
        str,
        "Pipeline OCR backend used to select default OCR render DPI.",
    ] = "surya"
    surya_layout_quality: Annotated[
        str,
        "Surya layout quality preset: fast, standard, or high.",
    ] = "fast"
    ocr_quality: Annotated[
        str,
        "OCR render quality preset: auto, low, medium, or high.",
    ] = "auto"
    layout_dpi_override: Annotated[
        int | None,
        "Advanced override for layout render DPI.",
    ] = None
    ocr_dpi_override: Annotated[
        int | None,
        "Advanced override for OCR render DPI.",
    ] = None
    disable_ocr: Annotated[
        bool,
        "Disable OCR processing.",
    ] = False
    build_highres_images: Annotated[
        bool,
        "Pre-render high-resolution page images for OCR and highres-dependent processors.",
    ] = True
    ocr_line_source: Annotated[
        str,
        "OCR-owned line detector. Set to 'tesseract' to skip the shared LineBuilder.",
    ] = ""

    def __init__(self, config=None):
        self._explicit_lowres_image_dpi = self._config_has_key(config, "lowres_image_dpi")
        self._explicit_highres_image_dpi = self._config_has_key(config, "highres_image_dpi")
        super().__init__(config)
        self.actual_lowres_dpi = self._compute_layout_dpi()
        self.actual_highres_dpi = self._compute_ocr_dpi()

    def __call__(self, provider: PdfProvider, layout_builder: LayoutBuilder, line_builder: LineBuilder, ocr_builder: OcrBuilder):
        document = self.build_document(provider)
        layout_builder(document, provider)
        if self._ocr_backend_owns_line_detection():
            for page in document.pages:
                page.text_extraction_method = "surya"
        else:
            line_builder(document, provider)
        if not self.disable_ocr:
            ocr_builder(document, provider)
        return document

    def _ocr_backend_owns_line_detection(self) -> bool:
        return str(getattr(self, "ocr_line_source", "") or "").strip().lower() == "tesseract"

    @staticmethod
    def _config_has_key(config, key: str) -> bool:
        if config is None:
            return False
        if isinstance(config, BaseModel):
            fields_set = getattr(config, "model_fields_set", getattr(config, "__fields_set__", set()))
            return key in fields_set
        if isinstance(config, dict):
            return key in config or f"DocumentBuilder_{key}" in config
        return False

    def _legacy_layout_dpi_override(self) -> int | None:
        if self._explicit_lowres_image_dpi or self.lowres_image_dpi != type(self).lowres_image_dpi:
            return self.lowres_image_dpi
        return None

    def _legacy_ocr_dpi_override(self) -> int | None:
        if self._explicit_highres_image_dpi or self.highres_image_dpi != type(self).highres_image_dpi:
            return self.highres_image_dpi
        return None

    def _compute_layout_dpi(self) -> int:
        override = self.layout_dpi_override
        if override is None:
            override = self._legacy_layout_dpi_override()
        return get_layout_dpi(
            self.layout_backend,
            surya_quality=self.surya_layout_quality,
            override=override,
        )

    def _compute_ocr_dpi(self) -> int:
        override = self.ocr_dpi_override
        if override is None:
            override = self._legacy_ocr_dpi_override()
        return get_ocr_dpi(
            self.ocr_backend,
            quality=self.ocr_quality,
            override=override,
        )

    def build_document(self, provider: PdfProvider):
        PageGroupClass: PageGroup = get_block_class(BlockTypes.Page)
        self.actual_lowres_dpi = self._compute_layout_dpi()
        self.actual_highres_dpi = self._compute_ocr_dpi()
        lowres_images = provider.get_images(provider.page_range, self.actual_lowres_dpi)
        highres_images = (
            provider.get_images(provider.page_range, self.actual_highres_dpi)
            if self.build_highres_images
            else [None] * len(provider.page_range)
        )
        initial_pages = [
            PageGroupClass(
                page_id=p,
                lowres_image=lowres_images[i],
                highres_image=highres_images[i],
                polygon=provider.get_page_bbox(p),
                refs=provider.get_page_refs(p)
            ) for i, p in enumerate(provider.page_range)
        ]
        DocumentClass: Document = get_block_class(BlockTypes.Document)
        return DocumentClass(filepath=provider.filepath, pages=initial_pages)
