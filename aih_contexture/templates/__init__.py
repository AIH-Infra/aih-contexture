"""
Marker 模板系统

提供场景化的文档处理模板，支持人文学科社区使用。
"""

from aih_contexture.templates.template import (
    DocumentTemplate,
    LayoutTemplateConfig,
    OcrTemplateConfig,
    PageNumberingConfig,
    DocumentScenario,
)
from aih_contexture.templates.loader import TemplateLoader

__all__ = [
    "DocumentTemplate",
    "LayoutTemplateConfig",
    "OcrTemplateConfig",
    "PageNumberingConfig",
    "DocumentScenario",
    "TemplateLoader",
]
