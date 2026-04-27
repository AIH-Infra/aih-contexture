"""
VLM Prompt Template Manager - 提示词模板管理器

负责加载、保存、管理预制模板和自定义模板。
"""

import json
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

from aih_contexture.logger import get_logger
from aih_contexture.prompts.presets import PRESET_PROMPTS

logger = get_logger()


class PromptTemplateManager:
    """提示词模板管理器"""

    def __init__(self, config_path: Optional[Path] = None):
        """
        初始化模板管理器

        Args:
            config_path: 自定义模板配置文件路径，默认为项目根目录/.claude/vlm_prompt_templates.json
        """
        self.config_path = config_path or self._default_config_path()
        self.presets = PRESET_PROMPTS
        self.custom = self._load_custom()

    def _default_config_path(self) -> Path:
        """获取默认配置文件路径"""
        # 项目根目录/.claude/vlm_prompt_templates.json
        project_root = Path.cwd()
        config_dir = project_root / ".claude"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "vlm_prompt_templates.json"

    def list_templates(self) -> Dict[str, Dict]:
        """
        列出所有模板（预制 + 自定义）

        Returns:
            {
                "default": {"name": "...", "description": "...", "builtin": True},
                "custom_xxx": {"name": "...", "description": "...", "builtin": False},
                ...
            }
        """
        all_templates = {}

        # 添加预制模板
        for tid, info in self.presets.items():
            all_templates[tid] = {
                "name": info["name"],
                "description": info["description"],
                "builtin": True
            }

        # 添加自定义模板
        for tid, info in self.custom.items():
            all_templates[tid] = {
                "name": info["name"],
                "description": info["description"],
                "builtin": False
            }

        return all_templates

    def get_template(self, template_id: str) -> str:
        """
        获取指定模板的 prompt 内容

        Args:
            template_id: 模板 ID

        Returns:
            prompt 字符串
        """
        # 优先从自定义模板查找
        if template_id in self.custom:
            return self.custom[template_id]["prompt"]

        # 从预制模板查找
        if template_id in self.presets:
            return self.presets[template_id]["prompt"]

        # 未找到，返回默认模板
        logger.warning(f"Template '{template_id}' not found, using default")
        return self.presets["default"]["prompt"]

    def get_template_info(self, template_id: str) -> Optional[Dict]:
        """获取模板完整信息"""
        if template_id in self.custom:
            return self.custom[template_id]
        if template_id in self.presets:
            return self.presets[template_id]
        return None

    def is_builtin(self, template_id: str) -> bool:
        """判断是否为内置模板"""
        return template_id in self.presets

    def save_custom_template(self, template_id: str, name: str, description: str, prompt: str):
        """
        保存自定义模板

        Args:
            template_id: 模板 ID（如 custom_20260331_015257）
            name: 模板名称
            description: 模板描述
            prompt: 提示词内容
        """
        self.custom[template_id] = {
            "name": name,
            "description": description,
            "prompt": prompt,
            "builtin": False,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        self._save_custom()
        logger.info(f"Saved custom template: {template_id}")

    def update_custom_template(self, template_id: str, prompt: str):
        """
        更新自定义模板的 prompt 内容

        Args:
            template_id: 模板 ID
            prompt: 新的提示词内容
        """
        if template_id not in self.custom:
            raise ValueError(f"Custom template '{template_id}' not found")

        self.custom[template_id]["prompt"] = prompt
        self.custom[template_id]["updated_at"] = datetime.now().isoformat()
        self._save_custom()
        logger.info(f"Updated custom template: {template_id}")

    def delete_custom_template(self, template_id: str):
        """
        删除自定义模板

        Args:
            template_id: 模板 ID
        """
        if template_id not in self.custom:
            raise ValueError(f"Custom template '{template_id}' not found")

        del self.custom[template_id]
        self._save_custom()
        logger.info(f"Deleted custom template: {template_id}")

    def generate_template_id(self) -> str:
        """生成新的模板 ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"custom_{timestamp}"

    def _load_custom(self) -> Dict:
        """从 JSON 文件加载自定义模板"""
        if not self.config_path.exists():
            return {}

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load custom templates: {e}")
            return {}

    def _save_custom(self):
        """保存自定义模板到 JSON 文件"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.custom, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save custom templates: {e}")

