"""
配置管理模块 - 支持配置的保存、加载、导出和导入
"""

import json
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any


class ConfigManager:
    """配置管理器"""

    CONFIG_VERSION = "1.0.0"
    DEFAULT_CONFIG_NAME = "default"

    # API Key 相关的字段名
    API_KEY_FIELDS = [
        "api_key", "api_keys", "ocr_api_key",
        "vlm_direct_api_key", "vlm_gemini_api_key", "vlm_anthropic_api_key",
        "vlm_layout_api_key", "vlm_ocr_api_key", "llm_gemini_api_key"
    ]

    def __init__(self, config_dir: str = None):
        """
        初始化配置管理器

        Args:
            config_dir: 配置文件目录路径
        """
        if config_dir is None:
            # 默认使用项目根目录下的 configs 文件夹
            self.config_dir = Path(__file__).parent.parent.parent / "configs"
        else:
            self.config_dir = Path(config_dir)

        self._ensure_config_dir()

    def _ensure_config_dir(self):
        """确保配置目录存在"""
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_filename(self, name: str) -> str:
        """将配置名称转换为安全的文件名"""
        # 移除非法字符
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', name)
        # 限制长度
        return safe_name[:50]

    def _get_config_path(self, name: str) -> Path:
        """获取配置文件的完整路径"""
        safe_name = self._sanitize_filename(name)
        return self.config_dir / f"{safe_name}.json"

    def _mask_api_keys(self, data: Dict, mode: str = "placeholder") -> Dict:
        """
        处理 API Key

        Args:
            data: 配置数据
            mode: 处理模式 - "exclude"(删除), "placeholder"(占位符), "include"(保留)
        """
        if mode == "include":
            return data

        result = {}
        for key, value in data.items():
            if isinstance(value, dict):
                result[key] = self._mask_api_keys(value, mode)
            elif isinstance(value, list):
                if key in self.API_KEY_FIELDS:
                    if mode == "exclude":
                        result[key] = []
                    else:  # placeholder
                        result[key] = ["***MASKED***"] * len(value) if value else []
                else:
                    result[key] = [
                        self._mask_api_keys(item, mode) if isinstance(item, dict) else item
                        for item in value
                    ]
            elif key in self.API_KEY_FIELDS:
                if mode == "exclude":
                    result[key] = ""
                else:  # placeholder
                    result[key] = "***MASKED***" if value else ""
            else:
                result[key] = value

        return result

    def list_configs(self) -> List[Dict[str, Any]]:
        """
        列出所有已保存的配置

        Returns:
            配置元数据列表
        """
        configs = []
        for filepath in self.config_dir.glob("*.json"):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    meta = data.get("meta", {})
                    configs.append({
                        "name": meta.get("name", filepath.stem),
                        "description": meta.get("description", ""),
                        "mode": data.get("global", {}).get("conversion_mode", "unknown"),
                        "created_at": meta.get("created_at", ""),
                        "updated_at": meta.get("updated_at", ""),
                        "filename": filepath.name
                    })
            except (json.JSONDecodeError, IOError):
                continue

        # 按更新时间排序
        configs.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return configs

    def get_config_names(self) -> List[str]:
        """获取所有配置名称列表"""
        return [c["name"] for c in self.list_configs()]

    def save_config(
        self,
        name: str,
        config_data: Dict,
        description: str = "",
        api_key_mode: str = "placeholder",
        overwrite: bool = False
    ) -> bool:
        """
        保存配置

        Args:
            name: 配置名称
            config_data: 配置数据
            description: 配置描述
            api_key_mode: API Key 处理模式
            overwrite: 是否覆盖同名配置

        Returns:
            是否保存成功
        """
        filepath = self._get_config_path(name)

        if filepath.exists() and not overwrite:
            return False

        # 处理 API Key
        processed_data = self._mask_api_keys(config_data, api_key_mode)

        # 添加元数据
        now = datetime.now().isoformat()
        full_config = {
            "meta": {
                "version": self.CONFIG_VERSION,
                "name": name,
                "description": description,
                "created_at": now,
                "updated_at": now
            },
            **processed_data
        }

        # 如果是更新，保留原创建时间
        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    old_data = json.load(f)
                    full_config["meta"]["created_at"] = old_data.get("meta", {}).get("created_at", now)
            except (json.JSONDecodeError, IOError):
                pass

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(full_config, f, ensure_ascii=False, indent=2)

        return True

    def load_config(self, name: str) -> Optional[Dict]:
        """
        加载配置

        Args:
            name: 配置名称

        Returns:
            配置数据，如果不存在返回 None
        """
        filepath = self._get_config_path(name)

        if not filepath.exists():
            return None

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 移除 meta 字段，只返回配置数据
                data.pop("meta", None)
                return data
        except (json.JSONDecodeError, IOError):
            return None

    def delete_config(self, name: str) -> bool:
        """
        删除配置

        Args:
            name: 配置名称

        Returns:
            是否删除成功
        """
        filepath = self._get_config_path(name)

        if not filepath.exists():
            return False

        try:
            filepath.unlink()
            return True
        except IOError:
            return False

    def export_config(self, name: str, api_key_mode: str = "exclude") -> Optional[str]:
        """
        导出配置为 JSON 字符串

        Args:
            name: 配置名称
            api_key_mode: API Key 处理模式

        Returns:
            JSON 字符串，如果失败返回 None
        """
        filepath = self._get_config_path(name)

        if not filepath.exists():
            return None

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 处理 API Key
            if api_key_mode != "include":
                data = self._mask_api_keys(data, api_key_mode)

            return json.dumps(data, ensure_ascii=False, indent=2)
        except (json.JSONDecodeError, IOError):
            return None

    def import_config(self, json_str: str, overwrite: bool = False) -> tuple[bool, str]:
        """
        从 JSON 字符串导入配置

        Args:
            json_str: JSON 字符串
            overwrite: 是否覆盖同名配置

        Returns:
            (是否成功, 消息)
        """
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            return False, f"JSON 解析错误: {e}"

        # 获取配置名称
        name = data.get("meta", {}).get("name")
        if not name:
            return False, "配置文件缺少名称"

        filepath = self._get_config_path(name)

        if filepath.exists() and not overwrite:
            return False, f"配置 '{name}' 已存在"

        # 更新时间戳
        data["meta"]["updated_at"] = datetime.now().isoformat()

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return True, f"配置 '{name}' 导入成功"
