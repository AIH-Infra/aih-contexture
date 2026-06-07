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
    APP_SETTINGS_NAME = "_app_settings"

    # API Key 相关的字段名
    API_KEY_FIELDS = [
        "api_key", "api_keys", "ocr_api_key",
        "vlm_direct_api_key", "vlm_gemini_api_key", "vlm_anthropic_api_key",
        "vlm_layout_api_key", "vlm_ocr_api_key", "llm_api_key",
        "llm_gemini_api_key", "llm_lmstudio_api_key", "llm_ollama_api_key",
        "llm_azure_api_key", "llm_claude_api_key", "openai_api_key",
        "gemini_api_key", "azure_api_key", "claude_api_key", "ollama_api_key",
        "lmstudio_api_key",
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
        self._get_api_profile_dir().mkdir(parents=True, exist_ok=True)

    def _get_api_profile_dir(self) -> Path:
        """获取 API 预设目录"""
        return self.config_dir / "api_profiles"

    def _get_api_profile_path(self, name: str) -> Path:
        """获取 API 预设文件路径"""
        safe_name = self._sanitize_filename(name)
        return self._get_api_profile_dir() / f"{safe_name}.json"

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

    def _get_app_settings_path(self) -> Path:
        """获取应用级设置文件路径"""
        return self.config_dir / f"{self.APP_SETTINGS_NAME}.json"

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

    def _infer_conversion_mode(self, config_data: Dict) -> str:
        global_mode = config_data.get("global", {}).get("conversion_mode")
        if global_mode:
            return global_mode

        for mode in ("pipeline", "vlm_generalized", "vlm_specialized"):
            if config_data.get(mode):
                return mode

        return "pipeline"

    def _build_summary(self, config_data: Dict) -> str:
        mode = self._infer_conversion_mode(config_data)
        global_config = config_data.get("global", {})
        printed_pages = "开" if global_config.get("extract_printed_pages_global", True) else "关"

        if mode == "pipeline":
            pipeline = config_data.get("pipeline", {})
            ocr_backend = pipeline.get("ocr_backend", "surya")
            layout_backend = pipeline.get("layout_backend", "surya")
            llm_enabled = "开" if pipeline.get("use_llm", False) else "关"
            return f"Pipeline / OCR:{ocr_backend} / Layout:{layout_backend} / 页码:{printed_pages} / LLM:{llm_enabled}"

        if mode == "vlm_generalized":
            generalized = config_data.get("vlm_generalized", {})
            provider = generalized.get("vlm_api_provider", "gemini")
            outputs = generalized.get("vlm_output_formats", [])
            output_text = ",".join(outputs) if outputs else "markdown"
            return f"VLM 泛化 / Provider:{provider} / 输出:{output_text} / 页码:{printed_pages}"

        specialized = config_data.get("vlm_specialized", {})
        backend = specialized.get("ocr_backend", "chandra")
        api_style = specialized.get("ocr_api_style", "lmstudio-native")
        return f"VLM 特化 / Backend:{backend} / API:{api_style} / 页码:{printed_pages}"

    def list_configs(self) -> List[Dict[str, Any]]:
        """
        列出所有已保存的配置

        Returns:
            配置元数据列表
        """
        configs = []
        for filepath in self.config_dir.glob("*.json"):
            if filepath.stem.startswith("_"):
                continue

            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    meta = data.get("meta", {})
                    if meta.get("category") == "app_settings":
                        continue

                    configs.append({
                        "name": meta.get("name", filepath.stem),
                        "description": meta.get("description", ""),
                        "mode": meta.get("conversion_mode", data.get("global", {}).get("conversion_mode", "unknown")),
                        "save_scope": meta.get("save_scope", "unknown"),
                        "summary": meta.get("summary", ""),
                        "created_at": meta.get("created_at", ""),
                        "updated_at": meta.get("updated_at", ""),
                        "filename": filepath.name
                    })
            except (json.JSONDecodeError, IOError):
                continue

        # 按更新时间排序
        configs.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return configs

    def list_api_profiles(self) -> List[Dict[str, Any]]:
        """列出所有已保存的 API 预设"""
        profiles = []
        for filepath in self._get_api_profile_dir().glob("*.json"):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    meta = data.get("meta", {})
                    profiles.append({
                        "name": meta.get("name", filepath.stem),
                        "description": meta.get("description", ""),
                        "provider": data.get("provider", ""),
                        "base_url": data.get("base_url", ""),
                        "model": data.get("model", ""),
                        "created_at": meta.get("created_at", ""),
                        "updated_at": meta.get("updated_at", ""),
                        "filename": filepath.name,
                    })
            except (json.JSONDecodeError, IOError):
                continue

        profiles.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return profiles

    def api_profile_exists(self, name: str) -> bool:
        """检查 API 预设是否已存在"""
        return self._get_api_profile_path(name).exists()

    def save_api_profile(
        self,
        name: str,
        provider: str,
        base_url: str,
        model: str,
        api_key: str = "",
        description: str = "",
        overwrite: bool = False,
    ) -> bool:
        """保存 API 预设"""
        filepath = self._get_api_profile_path(name)

        if filepath.exists() and not overwrite:
            return False

        now = datetime.now().isoformat()
        data = {
            "meta": {
                "version": self.CONFIG_VERSION,
                "name": name,
                "description": description,
                "category": "vlm_api_profile",
                "created_at": now,
                "updated_at": now,
            },
            "provider": provider,
            "base_url": base_url,
            "model": model,
            "api_key": api_key,
        }

        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    old_data = json.load(f)
                    data["meta"]["created_at"] = old_data.get("meta", {}).get("created_at", now)
            except (json.JSONDecodeError, IOError):
                pass

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return True

    def load_api_profile(self, name: str) -> Optional[Dict[str, Any]]:
        """加载 API 预设"""
        filepath = self._get_api_profile_path(name)
        if not filepath.exists():
            return None

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data.pop("meta", None)
                return data
        except (json.JSONDecodeError, IOError):
            return None

    def delete_api_profile(self, name: str) -> bool:
        """删除 API 预设"""
        filepath = self._get_api_profile_path(name)
        if not filepath.exists():
            return False

        try:
            filepath.unlink()
            return True
        except IOError:
            return False

    def get_config_names(self) -> List[str]:
        """获取所有配置名称列表"""
        return [c["name"] for c in self.list_configs()]

    def load_app_settings(self) -> Dict[str, Any]:
        """加载应用级设置"""
        filepath = self._get_app_settings_path()
        if not filepath.exists():
            return {}

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

        data.pop("meta", None)
        if not isinstance(data, dict):
            return {}
        return data

    def save_app_settings(self, settings_data: Dict[str, Any]) -> bool:
        """保存应用级设置"""
        filepath = self._get_app_settings_path()
        now = datetime.now().isoformat()
        full_settings = {
            "meta": {
                "version": self.CONFIG_VERSION,
                "name": self.APP_SETTINGS_NAME,
                "category": "app_settings",
                "updated_at": now,
            },
            **settings_data,
        }

        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    old_data = json.load(f)
                    full_settings["meta"]["created_at"] = old_data.get("meta", {}).get("created_at", now)
            except (json.JSONDecodeError, IOError):
                full_settings["meta"]["created_at"] = now
        else:
            full_settings["meta"]["created_at"] = now

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(full_settings, f, ensure_ascii=False, indent=2)
        except IOError:
            return False

        return True

    def config_exists(self, name: str) -> bool:
        """检查配置是否已存在"""
        return self._get_config_path(name).exists()

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
        conversion_mode = self._infer_conversion_mode(processed_data)
        full_config = {
            "meta": {
                "version": self.CONFIG_VERSION,
                "name": name,
                "description": description,
                "conversion_mode": conversion_mode,
                "save_scope": "current_mode",
                "summary": self._build_summary(processed_data),
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
