"""
模板加载器

负责加载、管理和缓存文档处理模板。
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Any

import yaml

from aih_contexture.logger import get_logger
from aih_contexture.templates.template import DocumentTemplate

logger = get_logger()


class TemplateLoader:
    """
    模板加载器。

    支持从内置模板目录和自定义路径加载模板。
    """

    # 内置模板目录
    BUILTIN_TEMPLATES_DIR = Path(__file__).parent / "builtin"

    # 模板缓存
    _cache: Dict[str, DocumentTemplate] = {}

    @classmethod
    def load(cls, name_or_path: str) -> DocumentTemplate:
        """
        加载模板。

        优先级：
        1. 缓存
        2. 内置模板（按名称）
        3. 自定义路径（文件路径）

        Args:
            name_or_path: 模板名称或文件路径

        Returns:
            DocumentTemplate 实例

        Raises:
            ValueError: 模板不存在
        """
        # 检查缓存
        if name_or_path in cls._cache:
            logger.debug(f"[TemplateLoader] Loading from cache: {name_or_path}")
            return cls._cache[name_or_path]

        # 尝试内置模板
        builtin_path = cls.BUILTIN_TEMPLATES_DIR / f"{name_or_path}.yaml"
        if builtin_path.exists():
            logger.info(f"[TemplateLoader] Loading builtin template: {name_or_path}")
            template = cls._load_yaml(builtin_path)
            cls._cache[name_or_path] = template
            return template

        # 尝试 yml 扩展名
        builtin_path_yml = cls.BUILTIN_TEMPLATES_DIR / f"{name_or_path}.yml"
        if builtin_path_yml.exists():
            logger.info(f"[TemplateLoader] Loading builtin template: {name_or_path}")
            template = cls._load_yaml(builtin_path_yml)
            cls._cache[name_or_path] = template
            return template

        # 尝试自定义路径
        custom_path = Path(name_or_path)
        if custom_path.exists():
            logger.info(f"[TemplateLoader] Loading custom template: {name_or_path}")
            template = cls._load_yaml(custom_path)
            cls._cache[name_or_path] = template
            return template

        raise ValueError(f"Template not found: {name_or_path}")

    @classmethod
    def _load_yaml(cls, path: Path) -> DocumentTemplate:
        """
        从 YAML 文件加载模板。

        Args:
            path: YAML 文件路径

        Returns:
            DocumentTemplate 实例
        """
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if data is None:
            data = {}

        return DocumentTemplate(**data)

    @classmethod
    def to_config(cls, template: DocumentTemplate) -> Dict[str, Any]:
        """
        将模板转换为配置字典。

        这是 template.to_config_dict() 的便捷方法。

        Args:
            template: 模板实例

        Returns:
            配置字典
        """
        return template.to_config_dict()

    @classmethod
    def list_builtin(cls) -> List[str]:
        """
        列出所有内置模板。

        Returns:
            内置模板名称列表
        """
        templates = []
        if cls.BUILTIN_TEMPLATES_DIR.exists():
            for f in cls.BUILTIN_TEMPLATES_DIR.iterdir():
                if f.suffix in (".yaml", ".yml"):
                    templates.append(f.stem)
        return sorted(templates)

    @classmethod
    def get_template_info(cls, name_or_path: str) -> Dict[str, Any]:
        """
        获取模板的基本信息（不完全加载）。

        Args:
            name_or_path: 模板名称或路径

        Returns:
            包含名称、描述、场景等基本信息的字典
        """
        template = cls.load(name_or_path)
        return {
            "name": template.name,
            "scenario": template.scenario,
            "description": template.description,
            "version": template.version,
            "author": template.author,
            "tags": template.tags,
            "layout_backend": template.layout.layout_backend,
            "ocr_backend": template.ocr.ocr_backend,
        }

    @classmethod
    def clear_cache(cls):
        """清空模板缓存"""
        cls._cache.clear()
        logger.debug("[TemplateLoader] Cache cleared")

    @classmethod
    def save_template(
        cls,
        template: DocumentTemplate,
        path: str,
        overwrite: bool = False
    ):
        """
        保存模板到文件。

        Args:
            template: 模板实例
            path: 保存路径
            overwrite: 是否覆盖现有文件

        Raises:
            FileExistsError: 文件已存在且 overwrite=False
        """
        path = Path(path)
        if path.exists() and not overwrite:
            raise FileExistsError(f"Template file already exists: {path}")

        # 确保目录存在
        path.parent.mkdir(parents=True, exist_ok=True)

        # 转换为字典
        data = template.model_dump(exclude_none=True)

        # 写入 YAML
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False
            )

        logger.info(f"[TemplateLoader] Template saved: {path}")

    @classmethod
    def create_from_config(cls, config: Dict[str, Any], name: str) -> DocumentTemplate:
        """
        从配置字典创建模板。

        Args:
            config: 配置字典
            name: 模板名称

        Returns:
            DocumentTemplate 实例
        """
        from aih_contexture.templates.template import (
            LayoutTemplateConfig,
            OcrTemplateConfig,
            PageNumberingConfig,
        )

        # 提取各部分配置
        layout_config = LayoutTemplateConfig(
            layout_backend=config.get("layout_backend", "surya"),
            force_layout_block=config.get("force_layout_block"),
            expand_block_types=config.get("expand_block_types", ["Picture", "Figure", "ComplexRegion"]),
            max_expand_frac=config.get("max_expand_frac", 0.05),
            reading_direction=config.get("reading_direction", "ltr"),
            vlm_layout_prompt=config.get("vlm_layout_prompt"),
            vlm_layout_timeout=config.get("vlm_layout_timeout", 120),
            yolo_base_url=config.get("yolo_base_url", "http://localhost:11900"),
            yolo_model=config.get("yolo_model", "doclayout_yolo"),
            yolo_confidence_threshold=config.get("yolo_confidence_threshold", 0.25),
        )

        ocr_config = OcrTemplateConfig(
            ocr_backend=config.get("ocr_backend", "surya"),
            force_ocr=config.get("force_ocr", False),
            ocr_batch_size=config.get("ocr_batch_size", 32),
            vlm_prompt_override=config.get("vlm_prompt"),
            vlm_response_mode=config.get("vlm_response_mode", "text"),
            calamari_base_url=config.get("calamari_base_url", "http://localhost:11800"),
            calamari_model=config.get("calamari_model", "gt4histocr"),
            calamari_sequential_mode=config.get("calamari_sequential_mode", False),
        )

        page_numbering_config = PageNumberingConfig(
            enabled=config.get("page_numbering_enabled", True),
            format=config.get("page_number_format", "arabic"),
            use_printed_page_number=config.get("use_printed_page_number", False),
            custom_pattern=config.get("page_number_custom_pattern"),
        )

        return DocumentTemplate(
            name=name,
            scenario="custom",
            layout=layout_config,
            ocr=ocr_config,
            page_numbering=page_numbering_config,
        )
