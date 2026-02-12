from typing import Tuple

from aih_contexture.builders.document import DocumentBuilder
from aih_contexture.builders.line import LineBuilder
from aih_contexture.builders.ocr import OcrBuilder
from aih_contexture.converters.pdf import PdfConverter
from aih_contexture.processors import BaseProcessor
from aih_contexture.processors.equation import EquationProcessor
from aih_contexture.providers.registry import provider_from_filepath
from aih_contexture.renderers.ocr_json import OCRJSONRenderer


class OCRConverter(PdfConverter):
    default_processors: Tuple[BaseProcessor, ...] = (EquationProcessor,)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.config:
            self.config = {}

        self.config["force_ocr"] = True
        self.renderer = OCRJSONRenderer

    def build_document(self, filepath: str):
        provider_cls = provider_from_filepath(filepath)
        layout_builder = self.resolve_dependencies(self.layout_builder_class)
        line_builder = self.resolve_dependencies(LineBuilder)
        ocr_builder = self.resolve_dependencies(OcrBuilder)
        document_builder = DocumentBuilder(self.config)

        provider = provider_cls(filepath, self.config)
        document = document_builder(provider, layout_builder, line_builder, ocr_builder)

        for processor in self.processor_list:
            processor(document)

        return document

    def __call__(self, filepath: str):
        document = self.build_document(filepath)
        self.page_count = len(document.pages)
        renderer = self.resolve_dependencies(self.renderer)
        return renderer(document)
