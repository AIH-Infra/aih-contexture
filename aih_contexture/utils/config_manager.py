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
    MASKED_API_KEY = "***MASKED***"
    CONFIG_SECTIONS = (
        "global",
        "pipeline",
        "vlm_generalized",
        "vlm_specialized",
        "markdown_postprocess",
        "structured_source",
    )
    CONVERSION_MODES = CONFIG_SECTIONS[1:]
    API_KEY_MODES = ("exclude", "placeholder", "include")

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

    def _normalize_config_name(self, name: Any) -> Optional[str]:
        if not isinstance(name, str):
            return None
        normalized = name.strip()
        if not normalized or not self._sanitize_filename(normalized).strip(" ."):
            return None
        if normalized.casefold() == self.APP_SETTINGS_NAME.casefold():
            return None
        windows_reserved = {"CON", "PRN", "AUX", "NUL"}
        windows_reserved.update(f"COM{index}" for index in range(1, 10))
        windows_reserved.update(f"LPT{index}" for index in range(1, 10))
        if normalized.split(".", 1)[0].rstrip(" .").upper() in windows_reserved:
            return None
        return normalized

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
                if self._is_api_key_field(key):
                    if mode == "exclude":
                        result[key] = []
                    else:  # placeholder
                        result[key] = [self.MASKED_API_KEY] * len(value) if value else []
                else:
                    result[key] = [
                        self._mask_api_keys(item, mode) if isinstance(item, dict) else item
                        for item in value
                    ]
            elif self._is_api_key_field(key):
                if mode == "exclude":
                    result[key] = ""
                else:  # placeholder
                    result[key] = self.MASKED_API_KEY if value else ""
            else:
                result[key] = value

        return result

    def _is_api_key_field(self, key: str) -> bool:
        normalized = str(key).lower()
        if normalized.endswith("_widget"):
            normalized = normalized[:-len("_widget")]
        known_fields = {field.lower() for field in self.API_KEY_FIELDS}
        return (
            normalized in known_fields
            or normalized.endswith("_api_key")
            or normalized.endswith("_api_keys")
        )

    def _restore_api_key_placeholders(self, imported: Dict, existing: Dict) -> None:
        """Keep local secrets when an imported file contains mask markers."""
        for key, value in list(imported.items()):
            previous = existing.get(key)
            if self._is_api_key_field(key):
                if value == self.MASKED_API_KEY and isinstance(previous, str) and previous and previous != self.MASKED_API_KEY:
                    imported[key] = previous
                elif (
                    isinstance(value, list)
                    and value
                    and all(item == self.MASKED_API_KEY for item in value)
                    and isinstance(previous, list)
                    and previous
                    and not any(item == self.MASKED_API_KEY for item in previous)
                ):
                    imported[key] = previous
            elif isinstance(value, dict) and isinstance(previous, dict):
                self._restore_api_key_placeholders(value, previous)
            elif isinstance(value, list) and isinstance(previous, list):
                for index, item in enumerate(value):
                    if index < len(previous) and isinstance(item, dict) and isinstance(previous[index], dict):
                        self._restore_api_key_placeholders(item, previous[index])

    def _clear_api_key_placeholders(self, data: Dict) -> Dict:
        """Never expose a serialized mask marker to a backend as a credential."""
        result = {}
        for key, value in data.items():
            if isinstance(value, dict):
                result[key] = self._clear_api_key_placeholders(value)
            elif self._is_api_key_field(key) and value == self.MASKED_API_KEY:
                result[key] = ""
            elif self._is_api_key_field(key) and isinstance(value, list):
                result[key] = [item for item in value if item != self.MASKED_API_KEY and item]
            elif isinstance(value, list):
                result[key] = [
                    self._clear_api_key_placeholders(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    def _infer_conversion_mode(self, config_data: Dict) -> str:
        global_config = config_data.get("global")
        global_mode = global_config.get("conversion_mode") if isinstance(global_config, dict) else None
        if global_mode in self.CONVERSION_MODES:
            return global_mode

        for mode in self.CONVERSION_MODES:
            if isinstance(config_data.get(mode), dict) and config_data[mode]:
                return mode

        for mode in self.CONVERSION_MODES:
            if isinstance(config_data.get(mode), dict):
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

        if mode == "vlm_specialized":
            specialized = config_data.get("vlm_specialized", {})
            backend = specialized.get("ocr_backend", "chandra")
            api_style = specialized.get("ocr_api_style", "lmstudio-native")
            return f"VLM 特化 / Backend:{backend} / API:{api_style} / 页码:{printed_pages}"

        if mode == "markdown_postprocess":
            postprocess = config_data.get("markdown_postprocess", {})
            input_kind = postprocess.get("markdown_postprocess_input_kind", "markdown")
            return f"Markdown 后处理 / 功能:{input_kind} / 页码:{printed_pages}"

        if mode == "structured_source":
            return f"结构化源导入 / 页码:{printed_pages}"
        return f"配置 / 页码:{printed_pages}"

    def _is_valid_config_data(self, config_data: Any, *, allow_meta: bool = False) -> bool:
        if not isinstance(config_data, dict):
            return False
        if not any(section in config_data for section in self.CONFIG_SECTIONS):
            return False
        if not allow_meta and "meta" in config_data:
            return False
        for key, value in config_data.items():
            if key == "meta" and allow_meta:
                if not isinstance(value, dict):
                    return False
            elif key not in self.CONFIG_SECTIONS or not isinstance(value, dict):
                return False
        global_config = config_data.get("global", {})
        if isinstance(global_config, dict):
            mode = global_config.get("conversion_mode")
            if mode is not None and mode not in self.CONVERSION_MODES:
                return False
        return True

    def _is_valid_config_document(self, data: Any) -> bool:
        if not isinstance(data, dict) or not isinstance(data.get("meta"), dict):
            return False
        meta = data["meta"]
        if not self._normalize_config_name(meta.get("name")):
            return False
        for key in (
            "version", "description", "conversion_mode", "save_scope", "summary",
            "created_at", "updated_at", "category",
        ):
            if key in meta and not isinstance(meta[key], str):
                return False
        config_data = {key: value for key, value in data.items() if key != "meta"}
        return self._is_valid_config_data(config_data)

    def _build_config_document(
        self,
        name: str,
        config_data: Dict,
        description: str,
        api_key_mode: str,
        *,
        created_at: str | None = None,
    ) -> Dict[str, Any]:
        processed_data = self._mask_api_keys(config_data, api_key_mode)
        now = datetime.now().isoformat()
        conversion_mode = self._infer_conversion_mode(processed_data)
        return {
            "meta": {
                "version": self.CONFIG_VERSION,
                "name": name,
                "description": description,
                "conversion_mode": conversion_mode,
                "save_scope": "current_mode",
                "summary": self._build_summary(processed_data),
                "created_at": created_at or now,
                "updated_at": now,
            },
            **processed_data,
        }

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
                    if not self._is_valid_config_document(data):
                        continue
                    meta = data["meta"]
                    if meta.get("category") == "app_settings":
                        continue

                    configs.append({
                        "name": meta.get("name", filepath.stem),
                        "description": meta.get("description", ""),
                        "mode": meta.get("conversion_mode", self._infer_conversion_mode(data)),
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
                    if not isinstance(data, dict) or not isinstance(data.get("meta", {}), dict):
                        continue
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
                    old_meta = old_data.get("meta") if isinstance(old_data, dict) else None
                    if isinstance(old_meta, dict):
                        data["meta"]["created_at"] = old_meta.get("created_at", now)
            except (json.JSONDecodeError, IOError):
                pass

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            return False

        return True

    def load_api_profile(self, name: str) -> Optional[Dict[str, Any]]:
        """加载 API 预设"""
        filepath = self._get_api_profile_path(name)
        if not filepath.exists():
            return None

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if not isinstance(data, dict) or not isinstance(data.get("meta", {}), dict):
                    return None
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

        if not isinstance(data, dict):
            return {}
        data.pop("meta", None)
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
                    old_meta = old_data.get("meta") if isinstance(old_data, dict) else None
                    full_settings["meta"]["created_at"] = (
                        old_meta.get("created_at", now) if isinstance(old_meta, dict) else now
                    )
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
        name = self._normalize_config_name(name)
        if name is None:
            return False
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
        name = self._normalize_config_name(name)
        if name is None or not self._is_valid_config_data(config_data) or api_key_mode not in self.API_KEY_MODES:
            return False
        filepath = self._get_config_path(name)

        if filepath.exists() and not overwrite:
            return False

        created_at = None
        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    old_data = json.load(f)
                    old_meta = old_data.get("meta") if isinstance(old_data, dict) else None
                    if isinstance(old_meta, dict):
                        created_at = old_meta.get("created_at")
            except (json.JSONDecodeError, IOError):
                pass

        full_config = self._build_config_document(
            name, config_data, description, api_key_mode, created_at=created_at
        )
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(full_config, f, ensure_ascii=False, indent=2)
        except OSError:
            return False

        return True

    def load_config(self, name: str) -> Optional[Dict]:
        """
        加载配置

        Args:
            name: 配置名称

        Returns:
            配置数据，如果不存在返回 None
        """
        name = self._normalize_config_name(name)
        if name is None:
            return None
        filepath = self._get_config_path(name)

        if not filepath.exists():
            return None

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if not self._is_valid_config_document(data):
                    return None
                data.pop("meta", None)
                return self._clear_api_key_placeholders(data)
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
        name = self._normalize_config_name(name)
        if name is None:
            return False
        filepath = self._get_config_path(name)

        if not filepath.exists():
            return False

        try:
            filepath.unlink()
            return True
        except IOError:
            return False

    def export_current_config(
        self,
        name: str,
        config_data: Dict,
        description: str = "",
        api_key_mode: str = "exclude",
    ) -> str:
        """Export the current unsaved configuration in the importable format."""
        normalized_name = self._normalize_config_name(name)
        if normalized_name is None:
            raise ValueError("配置名称无效或使用了保留名称")
        if not self._is_valid_config_data(config_data):
            raise ValueError("配置数据结构无效")
        if api_key_mode not in self.API_KEY_MODES:
            raise ValueError("API Key 处理方式无效")
        document = self._build_config_document(
            normalized_name, config_data, description, api_key_mode
        )
        return json.dumps(document, ensure_ascii=False, indent=2)

    def export_config(self, name: str, api_key_mode: str = "exclude") -> Optional[str]:
        """
        导出配置为 JSON 字符串

        Args:
            name: 配置名称
            api_key_mode: API Key 处理模式

        Returns:
            JSON 字符串，如果失败返回 None
        """
        name = self._normalize_config_name(name)
        if name is None or api_key_mode not in self.API_KEY_MODES:
            return None
        filepath = self._get_config_path(name)

        if not filepath.exists():
            return None

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not self._is_valid_config_document(data):
                return None

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

        if not self._is_valid_config_document(data):
            return False, "配置文件结构无效，需包含有效名称及配置分区"

        name = self._normalize_config_name(data["meta"].get("name"))
        data["meta"]["name"] = name

        filepath = self._get_config_path(name)

        if filepath.exists() and not overwrite:
            return False, f"配置 '{name}' 已存在"

        now = datetime.now().isoformat()
        old_data = None
        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    candidate = json.load(f)
                if self._is_valid_config_document(candidate):
                    old_data = candidate
            except (json.JSONDecodeError, IOError):
                pass

        if old_data is not None:
            self._restore_api_key_placeholders(data, old_data)
            data["meta"]["created_at"] = old_data["meta"].get(
                "created_at", data["meta"].get("created_at", now)
            )
        else:
            data["meta"].setdefault("created_at", now)

        config_data = {key: value for key, value in data.items() if key != "meta"}
        inferred_mode = self._infer_conversion_mode(config_data)
        data["meta"]["conversion_mode"] = inferred_mode
        data["meta"]["summary"] = self._build_summary(config_data)
        data["meta"]["updated_at"] = now

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            return False, f"配置写入失败: {e}"

        return True, f"配置 '{name}' 导入成功"
