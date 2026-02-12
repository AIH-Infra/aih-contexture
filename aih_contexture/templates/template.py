"""
模板数据结构定义

定义文档处理模板的各种配置类，支持场景化的版面识别、OCR 和页码处理。
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DocumentScenario(str, Enum):
    """文档场景枚举"""
    CHINESE_ANCIENT_BOOKS = "chinese_ancient_books"      # 中国古籍
    GERMAN_GOTHIC_PRINT = "german_gothic_print"          # 德语哥特体
    ARCHIVE_DOCUMENTS = "archive_documents"              # 档案文件
    MODERN_PUBLICATIONS = "modern_publications"          # 现代出版物
    JAPANESE_HISTORICAL = "japanese_historical"          # 日本历史文献
    ARABIC_MANUSCRIPTS = "arabic_manuscripts"            # 阿拉伯手稿
    MEDIEVAL_LATIN = "medieval_latin"                    # 中世纪拉丁文
    CUSTOM = "custom"                                    # 自定义


class PageNumberingConfig(BaseModel):
    """页码配置"""

    # 基本设置
    enabled: bool = Field(default=True, description="是否启用页码提取")
    format: str = Field(
        default="arabic",
        description="页码格式: arabic(阿拉伯数字), roman(罗马数字), chinese(中文数字), custom(自定义)"
    )
    prefix: str = Field(default="", description="页码前缀")
    suffix: str = Field(default="", description="页码后缀")
    start_page: int = Field(default=1, description="起始页码")

    # 自定义模式
    custom_pattern: Optional[str] = Field(
        default=None,
        description="自定义页码正则表达式"
    )

    # 印刷页码 vs 机器页码
    use_printed_page_number: bool = Field(
        default=False,
        description="使用印刷页码而非机器页码"
    )
    printed_number_location: str = Field(
        default="auto",
        description="印刷页码位置: auto, center, corner, margin, header, footer"
    )

    # 古籍特殊设置
    volume_prefix: Optional[str] = Field(
        default=None,
        description="卷册前缀（如 '卷一'）"
    )
    leaf_notation: bool = Field(
        default=False,
        description="是否使用叶（葉）记法（古籍常见）"
    )

    class Config:
        extra = "allow"


class LayoutTemplateConfig(BaseModel):
    """版面识别配置"""

    # 后端选择
    layout_backend: str = Field(
        default="surya",
        description="版面识别后端: surya, vlm, yolo, custom"
    )

    # 强制版面类型
    force_layout_block: Optional[str] = Field(
        default=None,
        description="强制所有页面使用指定的块类型（跳过版面识别）"
    )

    # 块类型扩展
    expand_block_types: List[str] = Field(
        default=["Picture", "Figure", "ComplexRegion"],
        description="需要扩展边界的块类型"
    )
    max_expand_frac: float = Field(
        default=0.05,
        description="最大扩展比例"
    )

    # 版面结构提示
    expected_block_types: List[str] = Field(
        default=[],
        description="预期的块类型列表（提示版面识别）"
    )
    column_layout: str = Field(
        default="auto",
        description="栏目布局: auto, single, double, multi"
    )
    reading_direction: str = Field(
        default="ltr",
        description="阅读方向: ltr(从左到右), rtl(从右到左), ttb(从上到下)"
    )

    # VLM 特定配置
    vlm_layout_prompt: Optional[str] = Field(
        default=None,
        description="VLM 版面识别自定义提示词"
    )
    vlm_layout_timeout: int = Field(
        default=120,
        description="VLM 版面识别超时时间（秒）"
    )

    # YOLO 特定配置
    yolo_base_url: str = Field(
        default="http://localhost:11900",
        description="YOLO 服务地址"
    )
    yolo_model: str = Field(
        default="doclayout_yolo",
        description="YOLO 模型名称"
    )
    yolo_confidence_threshold: float = Field(
        default=0.25,
        description="YOLO 检测置信度阈值"
    )

    class Config:
        extra = "allow"


class OcrTemplateConfig(BaseModel):
    """OCR 配置"""

    # 后端选择
    ocr_backend: str = Field(
        default="surya",
        description="OCR 后端: surya, vlm, calamari, none"
    )

    # 语言提示
    language_hints: List[str] = Field(
        default=[],
        description="语言提示列表（如 ['zh', 'en']）"
    )

    # 强制 OCR
    force_ocr: bool = Field(
        default=False,
        description="即使有 PDF 文本层也强制 OCR"
    )

    # Surya 特定配置
    ocr_batch_size: int = Field(
        default=32,
        description="Surya OCR 批处理大小"
    )

    # VLM 特定配置
    vlm_prompt_override: Optional[str] = Field(
        default=None,
        description="VLM OCR 自定义提示词"
    )
    vlm_response_mode: str = Field(
        default="text",
        description="VLM 响应模式: text, json"
    )

    # Calamari 特定配置
    calamari_base_url: str = Field(
        default="http://localhost:11800",
        description="Calamari 服务地址"
    )
    calamari_model: str = Field(
        default="gt4histocr",
        description="Calamari 模型名称"
    )
    calamari_sequential_mode: bool = Field(
        default=False,
        description="Calamari 串行模式"
    )

    class Config:
        extra = "allow"


class DocumentTemplate(BaseModel):
    """完整的文档处理模板"""

    # 基本信息
    name: str = Field(..., description="模板名称")
    scenario: str = Field(
        default="custom",
        description="文档场景"
    )
    description: str = Field(
        default="",
        description="模板描述"
    )
    version: str = Field(
        default="1.0",
        description="模板版本"
    )

    # 配置部分
    layout: LayoutTemplateConfig = Field(
        default_factory=LayoutTemplateConfig,
        description="版面识别配置"
    )
    ocr: OcrTemplateConfig = Field(
        default_factory=OcrTemplateConfig,
        description="OCR 配置"
    )
    page_numbering: PageNumberingConfig = Field(
        default_factory=PageNumberingConfig,
        description="页码配置"
    )

    # 额外元数据
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="额外的元数据"
    )

    # 作者信息
    author: Optional[str] = Field(
        default=None,
        description="模板作者"
    )
    tags: List[str] = Field(
        default_factory=list,
        description="标签列表"
    )

    class Config:
        extra = "allow"

    def to_config_dict(self) -> Dict[str, Any]:
        """
        将模板转换为 PdfConverter 可用的配置字典。

        Returns:
            配置字典
        """
        config = {}

        # 版面识别配置
        config["layout_backend"] = self.layout.layout_backend
        if self.layout.force_layout_block:
            config["force_layout_block"] = self.layout.force_layout_block
        if self.layout.expand_block_types:
            config["expand_block_types"] = self.layout.expand_block_types
        config["max_expand_frac"] = self.layout.max_expand_frac

        # VLM 版面识别配置
        if self.layout.layout_backend == "vlm":
            if self.layout.vlm_layout_prompt:
                config["vlm_layout_prompt"] = self.layout.vlm_layout_prompt
            config["vlm_layout_timeout"] = self.layout.vlm_layout_timeout

        # YOLO 版面识别配置
        if self.layout.layout_backend == "yolo":
            config["yolo_base_url"] = self.layout.yolo_base_url
            config["yolo_model"] = self.layout.yolo_model
            config["yolo_confidence_threshold"] = self.layout.yolo_confidence_threshold

        # OCR 配置
        config["ocr_backend"] = self.ocr.ocr_backend
        config["force_ocr"] = self.ocr.force_ocr
        config["ocr_batch_size"] = self.ocr.ocr_batch_size

        # VLM OCR 配置
        if self.ocr.ocr_backend == "vlm":
            if self.ocr.vlm_prompt_override:
                config["vlm_prompt"] = self.ocr.vlm_prompt_override
            config["vlm_response_mode"] = self.ocr.vlm_response_mode

        # Calamari OCR 配置
        if self.ocr.ocr_backend == "calamari":
            config["calamari_base_url"] = self.ocr.calamari_base_url
            config["calamari_model"] = self.ocr.calamari_model
            config["calamari_sequential_mode"] = self.ocr.calamari_sequential_mode

        # 页码配置
        config["page_numbering_enabled"] = self.page_numbering.enabled
        config["page_number_format"] = self.page_numbering.format
        config["use_printed_page_number"] = self.page_numbering.use_printed_page_number
        if self.page_numbering.custom_pattern:
            config["page_number_custom_pattern"] = self.page_numbering.custom_pattern

        # 阅读方向
        config["reading_direction"] = self.layout.reading_direction

        return config
