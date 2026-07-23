import os

from aih_contexture.logger import get_logger
from aih_contexture.schema.document import Document

os.environ["TOKENIZERS_PARALLELISM"] = "false"  # disables a tokenizers warning

from collections import defaultdict
from typing import Annotated, Any, Dict, List, Optional, Type, Tuple, Union
import io
from contextlib import contextmanager
import tempfile

from aih_contexture.processors import BaseProcessor
from aih_contexture.services import BaseService
from aih_contexture.processors.llm.llm_table_merge import LLMTableMergeProcessor
from aih_contexture.providers.registry import provider_from_filepath
from aih_contexture.builders.document import DocumentBuilder
from aih_contexture.builders.layout import LayoutBuilder
from aih_contexture.builders.line import LineBuilder
from aih_contexture.builders.ocr import OcrBuilder
from aih_contexture.builders.structure import StructureBuilder
from aih_contexture.converters import BaseConverter
from aih_contexture.processors.blockquote import BlockquoteProcessor
from aih_contexture.processors.code import CodeProcessor
from aih_contexture.processors.debug import DebugProcessor
from aih_contexture.processors.document_toc import DocumentTOCProcessor
from aih_contexture.processors.equation import EquationProcessor
from aih_contexture.processors.footnote import FootnoteProcessor
from aih_contexture.processors.footnote_policy import FootnotePolicyProcessor
from aih_contexture.processors.ignoretext import IgnoreTextProcessor
from aih_contexture.processors.line_numbers import LineNumbersProcessor
from aih_contexture.processors.list import ListProcessor
from aih_contexture.processors.inline_annotation import InlineAnnotationProcessor
from aih_contexture.processors.llm.llm_complex import LLMComplexRegionProcessor
from aih_contexture.processors.llm.llm_form import LLMFormProcessor
from aih_contexture.processors.llm.llm_image_description import LLMImageDescriptionProcessor
from aih_contexture.processors.llm.llm_table import LLMTableProcessor
from aih_contexture.processors.marginal_annotation import MarginalAnnotationProcessor
from aih_contexture.processors.marginal_line_numbers import MarginalLineNumberProcessor
from aih_contexture.processors.page_footer import PageFooterProcessor
from aih_contexture.processors.page_header import PageHeaderProcessor
from aih_contexture.processors.reference import ReferenceProcessor
from aih_contexture.processors.sectionheader import SectionHeaderProcessor
from aih_contexture.processors.table import TableProcessor
from aih_contexture.processors.text import TextProcessor
from aih_contexture.processors.block_relabel import BlockRelabelProcessor
from aih_contexture.processors.blank_page import BlankPageProcessor
from aih_contexture.processors.llm.llm_equation import LLMEquationProcessor
from aih_contexture.renderers.markdown import MarkdownRenderer
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.blocks import Block
from aih_contexture.schema.registry import register_block_class
from aih_contexture.util import strings_to_classes
from aih_contexture.processors.llm.llm_handwriting import LLMHandwritingProcessor
from aih_contexture.processors.order import OrderProcessor
from aih_contexture.services.gemini import GoogleGeminiService
from aih_contexture.processors.line_merge import LineMergeProcessor
from aih_contexture.processors.llm.llm_mathblock import LLMMathBlockProcessor
from aih_contexture.processors.llm.llm_page_correction import LLMPageCorrectionProcessor
from aih_contexture.processors.llm.llm_printed_page_correction import LLMPrintedPageCorrectionProcessor
from aih_contexture.processors.llm.llm_sectionheader import LLMSectionHeaderProcessor
from aih_contexture.processors.llm.llm_noise_removal import LLMNoiseRemovalProcessor
from aih_contexture.processors.page_number import PageNumberProcessor
from aih_contexture.processors.printed_page_correction import PrintedPageNumberCorrectorProcessor
from aih_contexture.processors.markdown_noise import MarkdownNoiseRemovalProcessor  # 🆕 Markdown 噪音清理
from aih_contexture.backends.pipeline import create_layout_builder, create_ocr_builder


class PdfConverter(BaseConverter):
    """
    A converter for processing and rendering PDF files into Markdown, JSON, HTML and other formats.
    """

    override_map: Annotated[
        Dict[BlockTypes, Type[Block]],
        "A mapping to override the default block classes for specific block types.",
        "The keys are `BlockTypes` enum values, representing the types of blocks,",
        "and the values are corresponding `Block` class implementations to use",
        "instead of the defaults.",
    ] = defaultdict()
    use_llm: Annotated[
        bool,
        "Enable higher quality processing with LLMs.",
    ] = False
    default_processors: Tuple[BaseProcessor, ...] = (
        OrderProcessor,
        BlockRelabelProcessor,
        LineMergeProcessor,
        BlockquoteProcessor,
        CodeProcessor,
        DocumentTOCProcessor,
        EquationProcessor,
        FootnoteProcessor,
        FootnotePolicyProcessor,
        IgnoreTextProcessor,
        LineNumbersProcessor,
        ListProcessor,
        PageHeaderProcessor,
        PageFooterProcessor,
        PageNumberProcessor,  # 提取页码
        PrintedPageNumberCorrectorProcessor,  # 基于连续序列修正/补全印刷页码
        LLMPrintedPageCorrectionProcessor,  # 🆕 LLM辅助修正页码
        MarginalAnnotationProcessor,
        MarginalLineNumberProcessor,
        InlineAnnotationProcessor,
        SectionHeaderProcessor,
        TableProcessor,
        LLMTableProcessor,
        LLMTableMergeProcessor,
        LLMFormProcessor,
        MarkdownNoiseRemovalProcessor,  # 🆕 清理 Markdown 噪音（在 TextProcessor 之前）
        TextProcessor,
        LLMComplexRegionProcessor,
        LLMImageDescriptionProcessor,
        LLMEquationProcessor,
        LLMHandwritingProcessor,
        LLMMathBlockProcessor,
        LLMSectionHeaderProcessor,
        LLMPageCorrectionProcessor,
        LLMNoiseRemovalProcessor,  # 🆕 智能降噪
        ReferenceProcessor,
        BlankPageProcessor,
        DebugProcessor,
    )
    default_llm_service: BaseService = GoogleGeminiService
    logger = get_logger()

    PROCESSOR_LABELS = {
        BlockquoteProcessor: "blockquote",
        LineMergeProcessor: "line_merge",
        CodeProcessor: "code",
        EquationProcessor: "equation",
        FootnoteProcessor: "footnote",
        ListProcessor: "list",
        PageHeaderProcessor: "page_header",
        PageFooterProcessor: "page_footer",
        PageNumberProcessor: "page_number",
        PrintedPageNumberCorrectorProcessor: "printed_page_correction",
        MarginalAnnotationProcessor: "marginal_annotation",
        MarginalLineNumberProcessor: "marginal_line_numbers",
        InlineAnnotationProcessor: "inline_annotation",
        SectionHeaderProcessor: "section_header",
        TableProcessor: "table",
        ReferenceProcessor: "reference",
        MarkdownNoiseRemovalProcessor: "markdown_noise_removal",
        LLMPrintedPageCorrectionProcessor: "llm_printed_page_correction",
        LLMTableProcessor: "llm_table",
        LLMTableMergeProcessor: "llm_table_merge",
        LLMFormProcessor: "llm_form",
        LLMComplexRegionProcessor: "llm_complex_region",
        LLMImageDescriptionProcessor: "llm_image_description",
        LLMEquationProcessor: "llm_equation",
        LLMHandwritingProcessor: "llm_handwriting",
        LLMMathBlockProcessor: "llm_math_block",
        LLMSectionHeaderProcessor: "llm_section_header",
        LLMPageCorrectionProcessor: "llm_page_correction",
        LLMNoiseRemovalProcessor: "llm_noise_removal",
    }

    def __init__(
        self,
        artifact_dict: Dict[str, Any],
        processor_list: Optional[List[str]] = None,
        renderer: str | None = None,
        llm_service: str | None = None,
        config=None,
    ):
        super().__init__(config)

        if config is None:
            config = {}

        for block_type, override_block_type in self.override_map.items():
            register_block_class(block_type, override_block_type)

        if processor_list is not None:
            processor_list = strings_to_classes(processor_list)
        else:
            processor_list = self.default_processors

        if renderer:
            renderer = strings_to_classes([renderer])[0]
        else:
            renderer = MarkdownRenderer

        # Put here so that resolve_dependencies can access it
        self.artifact_dict = artifact_dict

        if llm_service:
            llm_service_cls = strings_to_classes([llm_service])[0]
            llm_service = self.resolve_dependencies(llm_service_cls)
        elif config.get("llm_service"):
            # 从 config 中读取 llm_service（支持 UI 配置）
            llm_service_str = config.get("llm_service")
            llm_service_cls = strings_to_classes([llm_service_str])[0]
            llm_service = self.resolve_dependencies(llm_service_cls)
        elif config.get("use_llm", False):
            llm_service = self.resolve_dependencies(self.default_llm_service)

        # Inject llm service into artifact_dict so it can be picked up by processors, etc.
        self.artifact_dict["llm_service"] = llm_service
        self.llm_service = llm_service

        self.renderer = renderer

        # 🆕 根据配置过滤处理器（包括 LLM 和非 LLM 处理器）
        processor_list = self._filter_llm_processors(processor_list, config)

        processor_list = self.initialize_processors(processor_list)
        self.processor_list = processor_list

        self.layout_builder_class = LayoutBuilder
        self.page_count = None  # Track how many pages were converted
        self.last_document = None
        self.processor_debug_summary = self._build_processor_debug_summary(config)

    @classmethod
    def _get_processor_config_maps(cls):
        processor_config_map = {
            LLMTableProcessor: "llm_table_enabled",
            LLMTableMergeProcessor: "llm_table_enabled",
            LLMEquationProcessor: "llm_equation_enabled",
            LLMImageDescriptionProcessor: "llm_image_description_enabled",
            LLMHandwritingProcessor: "llm_handwriting_enabled",
            LLMPageCorrectionProcessor: "llm_page_correction_enabled",
            LLMPrintedPageCorrectionProcessor: "llm_printed_page_correction_enabled",
            LLMSectionHeaderProcessor: "llm_section_header_enabled",
            LLMFormProcessor: "llm_form_enabled",
            LLMComplexRegionProcessor: "llm_complex_region_enabled",
            LLMMathBlockProcessor: "llm_equation_enabled",
            LLMNoiseRemovalProcessor: "llm_noise_removal_enabled",
        }

        non_llm_processor_config_map = {
            PrintedPageNumberCorrectorProcessor: "printed_page_correction_enabled",
            BlockquoteProcessor: "blockquote_enabled",
            LineMergeProcessor: "line_merge_enabled",
            CodeProcessor: "code_enabled",
            EquationProcessor: "equation_enabled",
            FootnoteProcessor: "footnote_enabled",
            ListProcessor: "list_enabled",
            TableProcessor: "table_enabled",
            SectionHeaderProcessor: "section_header_enabled",
            ReferenceProcessor: "reference_enabled",
            MarkdownNoiseRemovalProcessor: "markdown_noise_removal_enabled",
            MarginalAnnotationProcessor: "heuristic_marginal_detection_enabled",
            MarginalLineNumberProcessor: "marginal_line_number_dedupe_enabled",
            InlineAnnotationProcessor: "enable_inline_detection",
        }
        return processor_config_map, non_llm_processor_config_map

    @classmethod
    def _processor_enabled_default(cls, config_key):
        if config_key in {"enable_marginal_detection", "heuristic_marginal_detection_enabled", "enable_inline_detection"}:
            return False
        if config_key == "marginal_line_number_dedupe_enabled":
            return False
        return True

    @classmethod
    def _marginal_line_number_dedupe_enabled(cls, config):
        config = config or {}
        if "marginal_line_number_dedupe_enabled" in config:
            return bool(config.get("marginal_line_number_dedupe_enabled"))

        layout_backend = str(config.get("layout_backend") or "").lower()
        external_backend = str(config.get("external_layout_backend_name") or "").lower()
        if "mineru" in layout_backend or "mineru" in external_backend:
            return True
        if bool(config.get("enable_marginal_detection", False)):
            return True
        if bool(config.get("native_marginalia_enabled", False)):
            return True
        if bool(cls._heuristic_marginal_detection_enabled(config)):
            return True
        return False

    @classmethod
    def _heuristic_marginal_detection_enabled(cls, config):
        config = config or {}
        if "heuristic_marginal_detection_enabled" in config:
            return bool(config.get("heuristic_marginal_detection_enabled"))
        return bool(config.get("enable_marginal_detection", False))

    def _build_processor_debug_summary(self, config):
        config = config or {}
        llm_map, non_llm_map = self._get_processor_config_maps()
        tracked = []
        for processor_cls in self.default_processors:
            if processor_cls in llm_map:
                config_key = llm_map[processor_cls]
                enabled = bool(config.get(config_key, False))
            elif processor_cls in non_llm_map:
                config_key = non_llm_map[processor_cls]
                if config_key == "marginal_line_number_dedupe_enabled":
                    enabled = self._marginal_line_number_dedupe_enabled(config)
                elif config_key == "heuristic_marginal_detection_enabled":
                    enabled = self._heuristic_marginal_detection_enabled(config)
                else:
                    enabled = bool(config.get(config_key, self._processor_enabled_default(config_key)))
            else:
                config_key = None
                enabled = True

            tracked.append({
                "class": processor_cls,
                "label": self.PROCESSOR_LABELS.get(processor_cls, processor_cls.__name__),
                "config_key": config_key,
                "enabled": enabled,
            })

        enabled_labels = [item["label"] for item in tracked if item["enabled"]]
        disabled_labels = [item["label"] for item in tracked if not item["enabled"]]
        execution_order = [
            self.PROCESSOR_LABELS.get(processor.__class__, processor.__class__.__name__)
            for processor in self.processor_list
        ]
        return {
            "tracked": tracked,
            "enabled_labels": enabled_labels,
            "disabled_labels": disabled_labels,
            "execution_order": execution_order,
        }

    def get_processor_debug_summary(self):
        return self.processor_debug_summary

    def _filter_llm_processors(self, processor_list, config):
        """根据配置过滤 LLM 处理器"""
        config = config or {}
        processor_config_map, non_llm_processor_config_map = self._get_processor_config_maps()

        filtered_list = []
        for processor_cls in processor_list:
            if processor_cls in processor_config_map:
                config_key = processor_config_map[processor_cls]
                if config.get(config_key, False):
                    filtered_list.append(processor_cls)
            elif processor_cls in non_llm_processor_config_map:
                config_key = non_llm_processor_config_map[processor_cls]
                if config_key == "marginal_line_number_dedupe_enabled":
                    enabled = self._marginal_line_number_dedupe_enabled(config)
                elif config_key == "heuristic_marginal_detection_enabled":
                    enabled = self._heuristic_marginal_detection_enabled(config)
                else:
                    enabled = bool(config.get(config_key, self._processor_enabled_default(config_key)))
                if enabled:
                    filtered_list.append(processor_cls)
            else:
                filtered_list.append(processor_cls)

        return tuple(filtered_list)

    @contextmanager
    def filepath_to_str(self, file_input: Union[str, io.BytesIO]):
        temp_file = None
        try:
            if isinstance(file_input, str):
                yield file_input
            else:
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=".pdf"
                ) as temp_file:
                    if isinstance(file_input, io.BytesIO):
                        file_input.seek(0)
                        temp_file.write(file_input.getvalue())
                    else:
                        raise TypeError(
                            f"Expected str or BytesIO, got {type(file_input)}"
                        )

                yield temp_file.name
        finally:
            if temp_file is not None and os.path.exists(temp_file.name):
                os.unlink(temp_file.name)

    # ↓↓↓ 确保这里与 filepath_to_str 同级（4空格缩进，是类方法）↓↓↓
    def build_document(self, filepath: str) -> Document:
        logger = self.logger
        provider_cls = provider_from_filepath(filepath)
        line_builder = self.resolve_dependencies(LineBuilder)

        layout_builder = create_layout_builder(
            config=self.config or {},
            resolve_dependencies=self.resolve_dependencies,
            logger=logger,
            layout_builder_class=self.layout_builder_class,
        )
        ocr_builder = create_ocr_builder(
            config=self.config or {},
            resolve_dependencies=self.resolve_dependencies,
            logger=logger,
            ocr_builder_class=OcrBuilder,
        )

        logger.info("[PdfConverter] Creating provider: %s", provider_cls.__name__)
        provider = provider_cls(filepath, self.config)
        logger.info("[PdfConverter] Provider created: %s", provider_cls.__name__)

        logger.info("[PdfConverter] Building document via DocumentBuilder")
        document = DocumentBuilder(self.config)(
            provider, layout_builder, line_builder, ocr_builder
        )
        logger.info("[PdfConverter] DocumentBuilder completed")
        structure_builder_cls = self.resolve_dependencies(StructureBuilder)
        structure_builder_cls(document)

        summary = self.get_processor_debug_summary()
        logger.info(
            "[PdfConverter] Processor summary: enabled=%s | disabled=%s | execution_order=%s",
            ", ".join(summary["enabled_labels"]) or "none",
            ", ".join(summary["disabled_labels"]) or "none",
            " -> ".join(summary["execution_order"]) or "none",
        )

        for processor in self.processor_list:
            processor_label = self.PROCESSOR_LABELS.get(processor.__class__, processor.__class__.__name__)
            logger.info(
                "[PdfConverter] Running processor: %s",
                processor_label,
            )
            processor(document)
            logger.info("[PdfConverter] Completed processor: %s", processor_label)

        logger.info("[PdfConverter] build_document completed")
        return document

    def __call__(self, filepath: str | io.BytesIO):
        with self.filepath_to_str(filepath) as temp_path:
            document = self.build_document(temp_path)
            self.last_document = document
            self.page_count = len(document.pages)
            renderer = self.resolve_dependencies(self.renderer)
            rendered = renderer(document)
        return rendered
