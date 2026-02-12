"""
Prompt Builder

Provides convenient methods to create VlmPromptTemplate instances
from built-in templates or custom parameters.
"""

from typing import Dict
from aih_contexture.prompts.base import VlmPromptTemplate
from aih_contexture.prompts.templates import BUILTIN_TEMPLATES


class PromptBuilder:
    """提示词构建器"""

    @staticmethod
    def from_template(template_name: str) -> VlmPromptTemplate:
        """
        从预置模板创建

        Args:
            template_name: 模板名称
                - "ancient_chinese" - 中文古籍
                - "archive_document" - 档案文献
                - "modern_publication" - 现代出版物（默认）
                - "gothic_german" - 哥特体德文
                - "manuscript" - 手稿
                - "academic_paper" - 学术论文
                - "mixed_content" - 混合内容

        Returns:
            VlmPromptTemplate 实例

        Raises:
            ValueError: 如果模板名称不存在
        """
        if template_name not in BUILTIN_TEMPLATES:
            available = ", ".join(BUILTIN_TEMPLATES.keys())
            raise ValueError(
                f"Unknown template: {template_name}. "
                f"Available templates: {available}"
            )

        template_config = BUILTIN_TEMPLATES[template_name]
        return VlmPromptTemplate(**template_config)

    @staticmethod
    def from_params(**params) -> VlmPromptTemplate:
        """
        从参数创建自定义模板

        Args:
            **params: 模板参数，支持所有 VlmPromptTemplate 的字段

        Returns:
            VlmPromptTemplate 实例

        Example:
            >>> template = PromptBuilder.from_params(
            ...     text_direction="vertical",
            ...     has_footnotes=True,
            ...     temperature=0.0,
            ...     top_p=0.1
            ... )
        """
        return VlmPromptTemplate(**params)

    @staticmethod
    def from_preset(preset: str) -> Dict:
        """
        获取 API 参数预设

        Args:
            preset: "high_accuracy" | "balanced" | "creative"

        Returns:
            API 参数字典

        Example:
            >>> params = PromptBuilder.from_preset("high_accuracy")
            >>> # {'temperature': 0.0, 'top_p': 0.1, 'max_tokens': 8192, ...}
        """
        presets = {
            "high_accuracy": {
                "temperature": 0.0,
                "top_p": 0.1,
                "max_tokens": 4096,
                "presence_penalty": 0.0,
                "frequency_penalty": 0.0,
            },
            "balanced": {
                "temperature": 0.2,
                "top_p": 0.3,
                "max_tokens": 4096,
            },
            "creative": {
                "temperature": 0.5,
                "top_p": 0.8,
                "max_tokens": 4096,
            }
        }

        if preset not in presets:
            available = ", ".join(presets.keys())
            raise ValueError(
                f"Unknown preset: {preset}. "
                f"Available presets: {available}"
            )

        return presets[preset]

    @staticmethod
    def list_templates() -> Dict[str, str]:
        """
        列出所有可用模板

        Returns:
            {template_name: description} 字典
        """
        from aih_contexture.prompts.templates import TEMPLATE_DISPLAY_NAMES
        return TEMPLATE_DISPLAY_NAMES

    @staticmethod
    def list_presets() -> Dict[str, str]:
        """
        列出所有可用预设

        Returns:
            {preset_name: description} 字典
        """
        return {
            "high_accuracy": "高准确性（temperature=0.0, 减少幻觉，提高可复现性）",
            "balanced": "平衡（temperature=0.2, 准确性和灵活性平衡）",
            "creative": "创意（temperature=0.5, 更灵活的解释能力）",
        }
