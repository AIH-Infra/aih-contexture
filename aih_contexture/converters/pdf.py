import os

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
from aih_contexture.processors.ignoretext import IgnoreTextProcessor
from aih_contexture.processors.line_numbers import LineNumbersProcessor
from aih_contexture.processors.list import ListProcessor
from aih_contexture.processors.llm.llm_complex import LLMComplexRegionProcessor
from aih_contexture.processors.llm.llm_form import LLMFormProcessor
from aih_contexture.processors.llm.llm_image_description import LLMImageDescriptionProcessor
from aih_contexture.processors.llm.llm_table import LLMTableProcessor
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
from aih_contexture.processors.llm.llm_sectionheader import LLMSectionHeaderProcessor
from aih_contexture.processors.llm.llm_noise_removal import LLMNoiseRemovalProcessor
from aih_contexture.processors.page_number import PageNumberProcessor
from aih_contexture.processors.printed_page_correction import PrintedPageNumberCorrectorProcessor
from aih_contexture.processors.markdown_noise import MarkdownNoiseRemovalProcessor  # 🆕 Markdown 噪音清理
from aih_contexture.builders.vlm_ocr import VlmOcrBuilder
from aih_contexture.services.ocr_vlm import VlmOcrService


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
        IgnoreTextProcessor,
        LineNumbersProcessor,
        ListProcessor,
        PageHeaderProcessor,
        PageNumberProcessor,  # 提取页码
        PrintedPageNumberCorrectorProcessor,  # 🆕 修正页码
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
            print(f"[DEBUG] config['llm_service'] = {llm_service_str}")
            llm_service_cls = strings_to_classes([llm_service_str])[0]
            print(f"[DEBUG] llm_service_cls = {llm_service_cls}")
            llm_service = self.resolve_dependencies(llm_service_cls)
        elif config.get("use_llm", False):
            llm_service = self.resolve_dependencies(self.default_llm_service)

        # Inject llm service into artifact_dict so it can be picked up by processors, etc.
        self.artifact_dict["llm_service"] = llm_service
        self.llm_service = llm_service

        self.renderer = renderer

        # 🔍 调试：在过滤前检查 config
        print("\n" + "=" * 80)
        print("🔍 __init__ 中的 config 检查:")
        print(f"  config 类型: {type(config)}")
        print(f"  config 是否为空: {not config}")
        if config:
            print(f"  blockquote_enabled: {config.get('blockquote_enabled', 'NOT SET')}")
            print(f"  line_merge_enabled: {config.get('line_merge_enabled', 'NOT SET')}")
            print(f"  config 键数量: {len(config)}")
        print("=" * 80 + "\n")

        # 🆕 根据配置过滤处理器（包括 LLM 和非 LLM 处理器）
        processor_list = self._filter_llm_processors(processor_list, config)

        processor_list = self.initialize_processors(processor_list)
        self.processor_list = processor_list

        self.layout_builder_class = LayoutBuilder
        self.page_count = None  # Track how many pages were converted

    def _filter_llm_processors(self, processor_list, config):
        """根据配置过滤 LLM 处理器"""
        from aih_contexture.logger import get_logger
        logger = get_logger()

        # 🔍 强制打印配置（使用 print 确保输出）
        print("\n" + "=" * 80)
        print("🔍 _filter_llm_processors 调试信息:")
        print(f"  blockquote_enabled: {config.get('blockquote_enabled', 'NOT SET')}")
        print(f"  line_merge_enabled: {config.get('line_merge_enabled', 'NOT SET')}")
        print(f"  footnote_enabled: {config.get('footnote_enabled', 'NOT SET')}")
        print(f"  所有配置键: {list(config.keys())[:10]}...")  # 只显示前10个
        print("=" * 80 + "\n")

        # 处理器类到配置键的映射
        processor_config_map = {
            LLMTableProcessor: "llm_table_enabled",
            LLMTableMergeProcessor: "llm_table_enabled",  # 表格合并依赖表格优化
            LLMEquationProcessor: "llm_equation_enabled",
            LLMImageDescriptionProcessor: "llm_image_description_enabled",
            LLMHandwritingProcessor: "llm_handwriting_enabled",
            LLMPageCorrectionProcessor: "llm_page_correction_enabled",
            LLMSectionHeaderProcessor: "llm_section_header_enabled",
            LLMFormProcessor: "llm_form_enabled",
            LLMComplexRegionProcessor: "llm_complex_region_enabled",
            LLMMathBlockProcessor: "llm_equation_enabled",  # 数学块依赖公式识别
            LLMNoiseRemovalProcessor: "llm_noise_removal_enabled",  # 🆕 智能降噪
        }

        # 非 LLM 处理器的配置映射
        non_llm_processor_config_map = {
            PrintedPageNumberCorrectorProcessor: "printed_page_correction_enabled",  # 印刷页码修正
            BlockquoteProcessor: "blockquote_enabled",  # 引用块检测
            LineMergeProcessor: "line_merge_enabled",  # 行合并
            CodeProcessor: "code_enabled",  # 代码块检测
            FootnoteProcessor: "footnote_enabled",  # 脚注检测
            ListProcessor: "list_enabled",  # 列表检测
            TableProcessor: "table_enabled",  # 表格处理
            SectionHeaderProcessor: "section_header_enabled",  # 章节标题检测
            ReferenceProcessor: "reference_enabled",  # 参考文献检测
        }

        # 🆕 Markdown 噪音清理处理器（需要导入）
        try:
            from aih_contexture.processors.markdown_noise import MarkdownNoiseRemovalProcessor
            non_llm_processor_config_map[MarkdownNoiseRemovalProcessor] = "markdown_noise_removal_enabled"
        except ImportError:
            pass  # 如果模块不存在，跳过

        filtered_list = []
        for processor_cls in processor_list:
            # LLM 处理器，检查配置
            if processor_cls in processor_config_map:
                config_key = processor_config_map[processor_cls]
                if config.get(config_key, False):
                    filtered_list.append(processor_cls)
                    print(f"✅ Enabled {processor_cls.__name__} (config: {config_key}=True)")
                else:
                    print(f"❌ Skipping {processor_cls.__name__} (config: {config_key}=False)")
            # 非 LLM 处理器但需要配置控制
            elif processor_cls in non_llm_processor_config_map:
                config_key = non_llm_processor_config_map[processor_cls]
                if config.get(config_key, True):  # 默认启用
                    filtered_list.append(processor_cls)
                    print(f"✅ Enabled {processor_cls.__name__} (config: {config_key}={config.get(config_key, True)})")
                else:
                    print(f"❌ Skipping {processor_cls.__name__} (config: {config_key}=False)")
            # 其他处理器，保留
            else:
                filtered_list.append(processor_cls)
                print(f"⚪ Keeping {processor_cls.__name__} (no config)")

        print(f"\n📊 过滤结果: {len(filtered_list)}/{len(processor_list)} 处理器启用\n")
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
        from aih_contexture.logger import get_logger
        logger = get_logger()
        provider_cls = provider_from_filepath(filepath)
        line_builder = self.resolve_dependencies(LineBuilder)

        # ========== 版面后端选择 ==========
        layout_backend = (self.config or {}).get("layout_backend", "surya")
        ocr_backend = (self.config or {}).get("ocr_backend", "surya")
        force_ocr = (self.config or {}).get("force_ocr", False)
        disable_ocr = (self.config or {}).get("disable_ocr", False)

        #========== 强制可见调试(确认代码被加载) ==========
        print("=" * 60)
        print("[PdfConverter.build_document] 代码版本检查点v4.1")
        print(f"  layout_backend = {layout_backend}")
        print(f"  ocr_backend = {ocr_backend}")
        print(f"  disable_ocr = {disable_ocr}")
        print(f"  force_ocr = {force_ocr}")
        print(f"  config keys = {list((self.config or {}).keys())}")
        print("=" * 60)
        # ==================================================

        # ========== 版面识别后端选择 ==========
        if layout_backend == "vlm":
            from aih_contexture.services.layout_vlm import VlmLayoutService
            from aih_contexture.builders.vlm_layout import VlmLayoutBuilder

            print("[PdfConverter] ✅ 使用 VLM 版面识别后端")
            logger.info("[PdfConverter] 使用 VLM 版面识别后端")

            try:
                vlm_layout_service = VlmLayoutService(self.config)
                layout_builder = VlmLayoutBuilder(vlm_layout_service, config=self.config)
                print("[PdfConverter] ✅ VlmLayoutBuilder 创建成功")
            except Exception as e:
                print(f"[PdfConverter] ❌ VLM Layout 初始化失败: {e}")
                import traceback
                traceback.print_exc()
                print("[PdfConverter] ⚠️ 回退到 Surya 版面识别")
                layout_builder = self.resolve_dependencies(self.layout_builder_class)

        elif layout_backend == "yolo":
            from aih_contexture.services.layout_yolo import YoloLayoutService
            from aih_contexture.builders.yolo_layout import YoloLayoutBuilder

            print("[PdfConverter] ✅ 使用 YOLO 版面识别后端")
            logger.info("[PdfConverter] 使用 YOLO 版面识别后端")

            try:
                yolo_service = YoloLayoutService(self.config)

                if not yolo_service.health_check():
                    print("[PdfConverter] ⚠️ YOLO 服务不可用，回退到 Surya")
                    logger.warning("[PdfConverter] YOLO service unavailable, falling back to Surya")
                    layout_builder = self.resolve_dependencies(self.layout_builder_class)
                else:
                    layout_builder = YoloLayoutBuilder(yolo_service, config=self.config)
                    print("[PdfConverter] ✅ YoloLayoutBuilder 创建成功")
            except Exception as e:
                print(f"[PdfConverter] ❌ YOLO Layout 初始化失败: {e}")
                import traceback
                traceback.print_exc()
                print("[PdfConverter] ⚠️ 回退到 Surya 版面识别")
                layout_builder = self.resolve_dependencies(self.layout_builder_class)

        else:
            # 默认使用 Surya 版面识别
            print("[PdfConverter] ⚠️ 使用 Surya 版面识别后端 (默认)")
            logger.info("[PdfConverter] 使用 Surya 版面识别后端")
            layout_builder = self.resolve_dependencies(self.layout_builder_class)
        
        # ========== OCR 后端选择 ==========
        if disable_ocr:
            # OCR 已禁用，使用 PDF 内嵌文本
            print("[PdfConverter] 🚫 OCR 已禁用（使用 PDF 内嵌文本层）")
            logger.info("[PdfConverter] OCR disabled, using PDF embedded text")
            ocr_builder = self.resolve_dependencies(OcrBuilder)
        elif ocr_backend == "vlm":
            from aih_contexture.services.ocr_vlm import VlmOcrService
            from aih_contexture.builders.vlm_ocr import VlmOcrBuilder
            
            print("[PdfConverter]✅ 使用 VLM OCR 后端")
            logger.warning("[PdfConverter]✅ 使用 VLM OCR 后端")
            
            try:
                openai_service = VlmOcrService(self.config)
                ocr_builder = VlmOcrBuilder(openai_service, config=self.config)
                print("[PdfConverter] ✅ VlmOcrBuilder 创建成功")
            except Exception as e:
                print(f"[PdfConverter] ❌ VLM 初始化失败: {e}")
                import traceback
                traceback.print_exc()
                print("[PdfConverter]⚠️ 回退到 Surya OCR")
                ocr_builder = self.resolve_dependencies(OcrBuilder)
        
        elif ocr_backend == "calamari":
            from aih_contexture.services.ocr_calamari import CalamariOcrService
            from aih_contexture.builders.calamari_ocr import CalamariOcrBuilder
            
            print("[PdfConverter]✅ 使用 Calamari OCR 后端")
            logger.warning("[PdfConverter]✅ 使用 Calamari OCR 后端")
            
            try:
                calamari_service = CalamariOcrService(self.config)
                
                if not calamari_service.health_check():
                    print("[PdfConverter] ⚠️ Calamari 服务不可用，回退到 Surya")
                    logger.warning("[PdfConverter] Calamari service unavailable, falling back to Surya")
                    ocr_builder = self.resolve_dependencies(OcrBuilder)
                else:
                    ocr_builder = CalamariOcrBuilder(calamari_service, config=self.config)
                    print("[PdfConverter] ✅ CalamariOcrBuilder 创建成功")
            except Exception as e:
                print(f"[PdfConverter] ❌ Calamari 初始化失败: {e}")
                import traceback
                traceback.print_exc()
                print("[PdfConverter]⚠️ 回退到 Surya OCR")
                ocr_builder = self.resolve_dependencies(OcrBuilder)
        
        else:
            print("[PdfConverter] ⚠️ 使用 Surya OCR 后端 (默认)")
            logger.warning("[PdfConverter] 使用 Surya OCR 后端")
            ocr_builder = self.resolve_dependencies(OcrBuilder)

        provider = provider_cls(filepath, self.config)
        document = DocumentBuilder(self.config)(
            provider, layout_builder, line_builder, ocr_builder
        )
        structure_builder_cls = self.resolve_dependencies(StructureBuilder)
        structure_builder_cls(document)

        for processor in self.processor_list:
            processor(document)

        return document

    def __call__(self, filepath: str | io.BytesIO):
        with self.filepath_to_str(filepath) as temp_path:
            document = self.build_document(temp_path)
            self.page_count = len(document.pages)
            renderer = self.resolve_dependencies(self.renderer)
            rendered = renderer(document)
        return rendered
