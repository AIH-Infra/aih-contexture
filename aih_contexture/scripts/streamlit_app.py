import os
os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'expandable_segments:True'

import time
import io
import subprocess
import sys
import traceback
import gc
from datetime import datetime
from pathlib import Path
import tempfile
import zipfile

import streamlit as st
from pypdf import PdfReader
import torch

# 添加 marker 到系统路径
REPO_ROOT = str(Path(__file__).resolve().parents[2])
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import aih_contexture
import aih_contexture.converters.pdf
import aih_contexture.builders.vlm_ocr
import aih_contexture.services.ocr_vlm

# 调试输出已注释 - 避免重复打印
# print("aih_contexture.__file__ =", aih_contexture.__file__)
# print("aih_contexture.converters.pdf.__file__ =", aih_contexture.converters.pdf.__file__)

from aih_contexture.scripts.common import load_models
from aih_contexture.converters.pdf import PdfConverter
from aih_contexture.config.parser import ConfigParser
from aih_contexture.output import text_from_rendered, save_output

from aih_contexture.renderers.markdown import MarkdownRenderer
from aih_contexture.renderers.json import JSONRenderer
from aih_contexture.renderers.html import HTMLRenderer
from aih_contexture.renderers.chunk import ChunkRenderer

# 导入语言预设
from aih_contexture.prompts.templates import LANGUAGE_PRESETS, LANGUAGE_DISPLAY_NAMES

# 导入配置管理器
from aih_contexture.utils.config_manager import ConfigManager

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

# ==================== 页面配置 ====================
# Favicon 图标路径
FAVICON_PATH = Path(__file__).parent.parent.parent / "assets" / "logo.png"
_page_icon = str(FAVICON_PATH) if FAVICON_PATH.exists() else "📜"

st.set_page_config(
    page_title="經緯 · Contexture - 面向人文学科的文献结构化平台",
    layout="wide",
    page_icon=_page_icon
)

# ==================== 品牌头部 ====================
# Logo路径（如果存在则显示）
LOGO_PATH = Path(__file__).parent.parent.parent / "assets" / "logo.png"

col_logo, col_title = st.columns([1, 5])
with col_logo:
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), width=120)
    else:
        st.markdown("### 📜")

with col_title:
    st.markdown("""
    # 經緯 · Contexture
    **经纬万卷，结构古今** · *Weaving Data from History*

    <sub>将PDF转化为结构化知识，以页码锚点守护学术伦理<br>——面向下一代的人文学科材料基础设施建设</sub>

    <sub>🔗 仓库地址：<a href="https://github.com/AIH-Infra/aih-contexture" target="_blank">github.com/AIH-Infra/aih-contexture</a></sub>
    """, unsafe_allow_html=True)

# ==================== 文案常量定义 ====================

# 三个模式的介绍文案
MODE_DESCRIPTIONS = {
    "pipeline": """
**🔧 Pipeline模式** - 版面识别 + OCR 完整流程

经典的文档处理流水线，逻辑分支丰富（3×3组合）：
- **版面识别**: Surya / VLM / DocLayout-YOLO
- **OCR引擎**: Surya / Calamari / VLM
- **后处理**: 页码锚点 + 结构化处理 + 可选LLM增强

**典型组合**:
- Surya + 禁用OCR: 快速提取拥有良好文本层的PDF
- Surya + Surya: 近现代出版物通用方案
- Surya + Calamari: 欧洲历史文献专用

**适用场景**: 本地部署、离线处理、精细控制
    """,

    "vlm_generalized": """
**🌐 VLM 泛化模式** - 依赖通用大模型泛化能力

利用通用视觉语言模型的强大理解能力：
- **支持模型**: GPT、Gemini、Claude、Qwen-VL 等
- **处理方式**: 整页图像 → Markdown 文本
- **异步并发**: 多页并行处理，但受并发限制和网络延迟影响

**适用场景**: 困难文献、复杂排版、潦草手写等——尚无通用有效技术方案时的兜底模式
    """,

    "vlm_specialized": """
**🎯 VLM 特化模式** - 经过OCR任务微调的VLM

使用专门针对OCR任务微调的视觉语言模型（基于 Qwen-VL 架构）：
- **已支持**: Chandra（学术文档、复杂表格）
- **处理方式**: 整页图像 → 结构化文本
- **本地部署**: 支持 LM Studio / Ollama / vLLM

**敬请期待**: OlmOCR、PaddleOCR-VL、DeepSeek-OCR

**适用场景**: 特化训练所针对的特定文档类型
    """
}

# 版面识别后端介绍
LAYOUT_BACKEND_DESCRIPTIONS = {
    "surya": """
**Surya 版面识别** - Datalab 基础模型 🙏
- 自动检测文本块、图片、表格、公式等区域
- 近现代出版物通用方案
- 本地运行，无需网络连接
- 致敬 Datalab 团队的开源贡献
""",
    "vlm": """
**VLM 版面识别** - 视觉语言模型
- 理解复杂版面结构和阅读顺序
- 适合小众但元素较少的版面
- 需要配置 API 端点
""",
    "yolo": """
**DocLayout-YOLO** - 快速版面检测
- 基于 YOLOv10 的文档版面分析
- 检测速度快，适合批量处理
- 可调节置信度阈值

⚠️ **后续版本正式集成**（当前为实验性支持）
"""
}

# OCR后端介绍
OCR_BACKEND_DESCRIPTIONS = {
    "surya": """
**Surya OCR** - Datalab 基础模型 🙏
- 支持 90+ 语言的文字识别
- 近现代出版物通用方案
- 本地 GPU 加速，无需网络
- 致敬 Datalab 团队的开源贡献

⚠️ 本地资源消耗较高，建议配备独立显卡
""",
    "calamari": """
**Calamari OCR** - 欧洲历史文献专用 🙏
- 丰富的预训练模型: gt4histocr、fraktur_historical、antiqua_historical、fraktur_19th_century、historical_french、uw3-modern-english 等
- 支持自定义训练模型
- 致敬 Calamari 项目对历史文献 OCR 的贡献

⚠️ 当前仅支持 Docker 镜像通信，后续版本正式集成
""",
    "vlm": """
**VLM OCR** - 视觉语言模型
- 整页/分块/合并三种处理模式
- 理解上下文，减少识别错误
- 支持手写、印章等复杂内容
""",
    "kraken": """
**Kraken OCR** - 历史文献专用（敬请期待）
- 支持从右到左、双向文本
- 丰富的历史字体模型
""",
    "tesseract": """
**Tesseract OCR** - 多语言老牌方案 🙏
- Google 开源，支持 100+ 语言
- 轻量快速，资源占用低
- 成熟稳定，社区活跃
- 致敬 Tesseract 项目二十年的持续贡献

⚠️ 后续版本正式集成
"""
}

# VLM特化模式引擎介绍
SPECIALIZED_OCR_DESCRIPTIONS = {
    "chandra": """
**Chandra OCR** - Datalab 专业文档模型
- 基于 Qwen2-VL 架构微调
- 擅长学术文档、复杂表格、技术报告
- 支持 Markdown/JSON 结构化输出
- 兼容 OpenAI API 协议
- 可本地部署: LM Studio / Ollama / vLLM
""",
    "olmocr": """
**OlmOCR** - Allen AI 开源模型（敬请期待）
- 基于 Qwen2-VL 架构微调
- 专注学术论文和技术文档
- 公式、代码块识别优秀
""",
    "paddleocr": """
**PaddleOCR-VL** - 百度飞桨（敬请期待）
- 中文文档识别优势
- 轻量级部署方案
""",
    "deepseek": """
**DeepSeek-OCR** - DeepSeek（敬请期待）
- 多模态理解能力强
- 开源可商用
"""
}

os.environ["IN_STREAMLIT"] = "true"
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

DEFAULT_OUTPUT_DIR = os.environ.get("MARKER_OUTPUT_DIR", "output")
os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)

# ==================== Session State 初始化 ====================
if "processed_files" not in st.session_state:
    st.session_state.processed_files = {}
if "output_dir" not in st.session_state:
    st.session_state.output_dir = DEFAULT_OUTPUT_DIR
if "last_zip_path" not in st.session_state:
    st.session_state.last_zip_path = None
if "last_zip_name" not in st.session_state:
    st.session_state.last_zip_name = None

# 暂停-恢复机制的 session state
if "ocr_paused" not in st.session_state:
    st.session_state.ocr_paused = False
if "ocr_pause_info" not in st.session_state:
    st.session_state.ocr_pause_info = None  # 保存暂停时的状态信息
if "ocr_resume_batch_start" not in st.session_state:
    st.session_state.ocr_resume_batch_start = 0  # 恢复时从哪个文件开始


# ==================== 辅助函数 ====================

def collect_current_config() -> dict:
    """收集当前所有配置项"""
    config = {
        "global": {},
        "vlm_specialized": {},
        "vlm_generalized": {},
        "pipeline": {}
    }

    # 需要排除的内部key
    exclude_keys = {
        "config_selector", "load_config_btn", "save_config_btn", "export_config_btn",
        "import_config_btn", "config_uploader", "overwrite_config", "new_config_name",
        "new_config_desc", "api_key_mode", "file_uploader_global", "uploaded_id_file_global",
        "output_dir", "loaded_config"
    }

    # 收集所有 session_state 中的配置
    for key, value in st.session_state.items():
        if key in exclude_keys:
            continue
        # 跳过不可序列化的对象
        if hasattr(value, '__class__') and value.__class__.__name__ in ['UploadedFile', 'FormSubmitter']:
            continue

        if key.startswith("ocr_"):
            config["vlm_specialized"][key] = value
        elif key.startswith("vlm_"):
            config["vlm_generalized"][key] = value
        elif key.startswith("pipeline_") or key.startswith("layout_") or key.startswith("llm_") or key.startswith("calamari_") or key.startswith("yolo_"):
            config["pipeline"][key] = value
        elif key.endswith("_pipeline"):
            # 处理 *_pipeline 后缀的 key（如 line_merge_enabled_pipeline）
            config["pipeline"][key] = value
        elif key.endswith("_global"):
            config["global"][key] = value
        elif key in ["conversion_mode", "out_dir", "use_page_range", "start_page", "end_page"]:
            config["global"][key] = value
        elif key in ["ocr_backend", "force_ocr", "force_ocr_vlm", "ocr_batch_size", "use_llm", "llm_provider"]:
            config["pipeline"][key] = value

    return config


def apply_config_to_session(config: dict):
    """将配置应用到 session_state"""
    if not config:
        return

    # 应用全局配置
    for key, value in config.get("global", {}).items():
        st.session_state[key] = value

    # 应用各模式配置
    for key, value in config.get("vlm_specialized", {}).items():
        st.session_state[key] = value

    for key, value in config.get("vlm_generalized", {}).items():
        st.session_state[key] = value

    for key, value in config.get("pipeline", {}).items():
        st.session_state[key] = value


@st.cache_resource(show_spinner=False)
def get_artifacts():
    with st.spinner("正在加载模型..."):
        return load_models()


def build_config_dict(config_params: dict) -> dict:
    """构建配置字典"""

    # 检查转换模式
    conversion_mode = config_params.get("conversion_mode", "pipeline")

    # VLM 特化模式配置
    if conversion_mode == "vlm_specialized":
        cli = {
            "converter_cls": "aih_contexture.converters.ocr_direct_async.OcrDirectAsyncConverter",
            "ocr_endpoint": config_params.get("ocr_endpoint", "http://localhost:1234/v1"),
            "ocr_model": config_params.get("ocr_model", "chandra"),
            "ocr_api_key": config_params.get("ocr_api_key"),
            "ocr_output_format": config_params.get("ocr_output_format", "json"),
            "ocr_concurrency": int(config_params.get("ocr_concurrency", 5)),
            "ocr_batch_size": int(config_params.get("ocr_batch_size", 10)),
            "ocr_batch_rest": float(config_params.get("ocr_batch_rest", 2.0)),
            "ocr_max_retries": int(config_params.get("ocr_max_retries", 3)),
            "ocr_resize_max": int(config_params.get("ocr_resize_max", 1024)),
            "ocr_image_format": config_params.get("ocr_image_format", "JPEG"),
            "ocr_image_quality": int(config_params.get("ocr_image_quality", 60)),
            "ocr_page_anchor_enabled": bool(config_params.get("ocr_page_anchor_enabled", True)),
            "ocr_timeout": int(config_params.get("ocr_timeout", 120)),
            "ocr_max_tokens": 4096,
            "ocr_temperature": 0.1,
        }
        if config_params.get("page_range"):
            cli["page_range"] = config_params["page_range"]
        return cli

    # 传统模式和 VLM Direct 模式配置
    ocr_backend = config_params.get("ocr_backend", "surya")
    layout_backend = config_params.get("layout_backend", "surya")
    disable_ocr = (ocr_backend == "none")
    disable_layout = (layout_backend == "none")

    cli = {
        "ocr_batch_size": int(config_params.get("ocr_batch_size", 32)),
        "use_pdf_text_fallback": True,
        "use_pdf_objects": True,
        "use_fp16": bool(config_params.get("use_fp16", False)),
        "force_ocr": False if disable_ocr else bool(config_params.get("force_ocr", False)),
        "paginate_output": bool(config_params.get("paginate_output", True)),
        "page_separator": config_params.get("page_separator", "\n\n---\n\n"),
        "use_llm": bool(config_params.get("use_llm", False)),
        "ocr_backend": "surya" if disable_ocr else ocr_backend,
        "disable_ocr": disable_ocr,
        "layout_backend": "surya" if disable_layout else layout_backend,
        "disable_layout": disable_layout,
        # 🆕 基础处理器配置
        "printed_page_correction_enabled": bool(config_params.get("printed_page_correction_enabled", True)),
        "markdown_formatting_enabled": bool(config_params.get("markdown_formatting_enabled", True)),
        "markdown_noise_removal_enabled": bool(config_params.get("markdown_noise_removal_enabled", True)),
        "markdown_noise_cleaning_level": config_params.get("markdown_noise_cleaning_level", "basic"),
        "markdown_noise_custom_symbols": config_params.get("markdown_noise_custom_symbols", ""),
        "markdown_noise_line_start_only": bool(config_params.get("markdown_noise_line_start_only", True)),
        "blockquote_enabled": bool(config_params.get("blockquote_enabled", True)),
        "line_merge_enabled": bool(config_params.get("line_merge_enabled", True)),
        "code_enabled": bool(config_params.get("code_enabled", True)),
        "section_header_enabled": bool(config_params.get("section_header_enabled", True)),
        "list_enabled": bool(config_params.get("list_enabled", True)),
        "footnote_enabled": bool(config_params.get("footnote_enabled", True)),
        "reference_enabled": bool(config_params.get("reference_enabled", True)),
        "table_enabled": bool(config_params.get("table_enabled", True)),
    }

    if config_params.get("page_range"):
        cli["page_range"] = config_params["page_range"]

    # 印刷页码配置
    if config_params.get("page_numbering_enabled"):
        cli["page_numbering_enabled"] = True
        cli["use_printed_page_number"] = config_params.get("use_printed_page_number", True)
        cli["page_number_format"] = config_params.get("page_number_format", "auto")
        cli["printed_page_zones"] = config_params.get("printed_page_zones", ["footer", "header"])
        cli["printed_page_header_y_frac"] = config_params.get("printed_page_header_y_frac", 0.15)
        cli["printed_page_footer_y_frac"] = config_params.get("printed_page_footer_y_frac", 0.83)
        if config_params.get("page_number_custom_pattern"):
            cli["page_number_custom_pattern"] = config_params["page_number_custom_pattern"]

    # 版面识别 VLM 配置
    if layout_backend == "vlm":
        vlm_config = {
            "vlm_layout_timeout": int(config_params.get("vlm_layout_timeout", 120)),
        }

        # 提示词配置 - 确保至少有一个被设置
        has_prompt = False
        if config_params.get("vlm_layout_prompt"):
            vlm_config["vlm_layout_prompt"] = config_params["vlm_layout_prompt"]
            has_prompt = True
        if config_params.get("vlm_layout_prompt_template"):
            vlm_config["vlm_layout_prompt_template"] = config_params["vlm_layout_prompt_template"]
            has_prompt = True

        # 如果都没有设置，使用默认模板
        if not has_prompt:
            vlm_config["vlm_layout_prompt_template"] = "modern"

        # 独立的 VLM Layout API 配置
        if config_params.get("vlm_layout_base_url"):
            vlm_config["vlm_layout_base_url"] = config_params["vlm_layout_base_url"]
        if config_params.get("vlm_layout_model"):
            vlm_config["vlm_layout_model"] = config_params["vlm_layout_model"]
        if config_params.get("vlm_layout_api_key"):
            vlm_config["vlm_layout_api_key"] = config_params["vlm_layout_api_key"]
        if config_params.get("vlm_layout_image_format"):
            vlm_config["vlm_layout_image_format"] = config_params["vlm_layout_image_format"]
        if config_params.get("vlm_layout_max_image_dimension"):
            vlm_config["vlm_layout_max_image_dimension"] = int(config_params["vlm_layout_max_image_dimension"])
        if config_params.get("vlm_layout_jpeg_quality"):
            vlm_config["vlm_layout_jpeg_quality"] = int(config_params["vlm_layout_jpeg_quality"])

        cli.update(vlm_config)

    # 版面识别 YOLO 配置
    if layout_backend == "yolo":
        cli.update({
            "yolo_base_url": config_params.get("yolo_base_url", "http://localhost:11900"),
            "yolo_model": config_params.get("yolo_model", "doclayout_yolo"),
            "yolo_confidence_threshold": float(config_params.get("yolo_confidence_threshold", 0.25)),
        })

    # VLM 配置
    if ocr_backend == "vlm":
        vlm_mode = config_params.get("vlm_mode", "tile")
        cli.update({
            "openai_base_url": config_params.get("openai_base_url", "http://127.0.0.1:1234/v1"),
            "openai_model": config_params.get("openai_model", "churro-3b"),
            "openai_api_key": config_params.get("openai_api_key", "lm-studio"),
            "openai_image_format": config_params.get("openai_image_format", "jpeg"),
            "vlm_prompt": config_params.get("vlm_prompt", ""),
            "vlm_response_mode": config_params.get("vlm_response_mode", "text"),
            "openai_use_stop": bool(config_params.get("openai_use_stop", False)),
            "vlm_full_page_ocr": vlm_mode == "full_page",
            "vlm_full_page_max_tokens": int(config_params.get("vlm_full_page_max_tokens", 2048)),
            "vlm_merge_enabled": vlm_mode == "merge",
            "vlm_merge_y_threshold": int(config_params.get("vlm_merge_y_threshold", 80)),
            "vlm_merge_max_blocks": int(config_params.get("vlm_merge_max_blocks", 15)),
        })

    # Calamari 配置
    if ocr_backend == "calamari":
        cli.update({
            "calamari_base_url": config_params.get("calamari_base_url", "http://localhost:11800"),
            "calamari_model": config_params.get("calamari_model", "gt4histocr"),
            "calamari_batch_size": int(config_params.get("calamari_batch_size", 100)),
            "calamari_timeout": int(config_params.get("calamari_timeout", 120)),
            "calamari_sequential_mode": bool(config_params.get("calamari_sequential_mode", False)),
            "calamari_trust_batch_order": bool(config_params.get("calamari_trust_batch_order", True)),
            "calamari_require_ordering_info": bool(config_params.get("calamari_require_ordering_info", True)),
            "calamari_footnote_y_frac": float(config_params.get("calamari_footnote_y_frac", 0.83)),
            "calamari_fallback_to_sequential_on_ordering_failure": bool(config_params.get("calamari_fallback_to_sequential_on_ordering_failure", True)),
        })

    # LLM 配置
    if config_params.get("use_llm"):
        llm_provider = config_params.get("llm_provider", "gemini")

        # 通用 LLM 配置
        cli["use_llm"] = True
        cli["llm_max_concurrency"] = config_params.get("llm_max_concurrency", 3)

        # 模块开关
        cli["llm_table_enabled"] = config_params.get("llm_table_enabled", True)
        cli["llm_equation_enabled"] = config_params.get("llm_equation_enabled", True)
        cli["llm_image_description_enabled"] = config_params.get("llm_image_description_enabled", False)
        cli["llm_handwriting_enabled"] = config_params.get("llm_handwriting_enabled", False)
        cli["llm_page_correction_enabled"] = config_params.get("llm_page_correction_enabled", False)
        cli["llm_section_header_enabled"] = config_params.get("llm_section_header_enabled", False)
        cli["llm_form_enabled"] = config_params.get("llm_form_enabled", False)
        cli["llm_complex_region_enabled"] = config_params.get("llm_complex_region_enabled", False)
        cli["llm_noise_removal_enabled"] = config_params.get("llm_noise_removal_enabled", False)
        cli["llm_printed_page_correction_enabled"] = config_params.get("llm_printed_page_correction_enabled", False)
        cli["llm_heuristic_layout_enabled"] = config_params.get("llm_heuristic_layout_enabled", False)

        # 页面校正自定义提示词
        if config_params.get("llm_page_correction_prompt"):
            cli["llm_page_correction_prompt"] = config_params["llm_page_correction_prompt"]

        # 映射 llm_provider 到 llm_service 类路径
        provider_to_service = {
            "gemini": "marker.services.gemini.GoogleGeminiService",
            "azure": "marker.services.azure_openai.AzureOpenAIService",
            "claude": "marker.services.claude.ClaudeService",
            "ollama": "marker.services.ollama.OllamaService",
        }

        # 设置 llm_service 参数（ConfigParser 需要这个）
        if llm_provider in provider_to_service:
            cli["llm_service"] = provider_to_service[llm_provider]

        # 根据提供商配置
        if llm_provider == "gemini":
            cli["llm_provider"] = "gemini"
            if config_params.get("llm_api_key"):
                cli["gemini_api_key"] = config_params["llm_api_key"]
            if config_params.get("llm_model"):
                cli["gemini_model"] = config_params["llm_model"]
            # 🆕 支持 Gemini 中转接口
            if config_params.get("llm_base_url"):
                cli["gemini_base_url"] = config_params["llm_base_url"]

        elif llm_provider == "azure":
            cli["llm_provider"] = "azure"
            if config_params.get("llm_base_url"):
                cli["azure_endpoint"] = config_params["llm_base_url"]
            if config_params.get("llm_api_key"):
                cli["azure_api_key"] = config_params["llm_api_key"]
            if config_params.get("llm_model"):
                cli["azure_deployment"] = config_params["llm_model"]

        elif llm_provider == "claude":
            cli["llm_provider"] = "claude"
            if config_params.get("llm_api_key"):
                cli["claude_api_key"] = config_params["llm_api_key"]
            if config_params.get("llm_model"):
                cli["claude_model"] = config_params["llm_model"]

        elif llm_provider == "ollama":
            cli["llm_provider"] = "ollama"
            if config_params.get("llm_base_url"):
                cli["ollama_base_url"] = config_params["llm_base_url"]
            if config_params.get("llm_model"):
                cli["ollama_model"] = config_params["llm_model"]
            if config_params.get("llm_api_key"):
                cli["ollama_api_key"] = config_params["llm_api_key"]

    # 边码识别配置
    if config_params.get("enable_marginal_detection"):
        cli["enable_marginal_detection"] = True
        cli["left_margin_threshold"] = float(config_params.get("left_margin_threshold", 0.15))
        cli["right_margin_threshold"] = float(config_params.get("right_margin_threshold", 0.85))
        cli["top_margin_threshold"] = float(config_params.get("top_margin_threshold", 0.10))
        cli["bottom_margin_threshold"] = float(config_params.get("bottom_margin_threshold", 0.90))
        cli["vertical_center_tolerance"] = float(config_params.get("vertical_center_tolerance", 0.05))

    if config_params.get("enable_inline_detection"):
        cli["enable_inline_detection"] = True
        cli["font_size_ratio_threshold"] = float(config_params.get("font_size_ratio_threshold", 0.75))
        cli["max_inline_annotation_length"] = int(config_params.get("max_inline_annotation_length", 100))

    config_parser = ConfigParser(cli)
    config_dict = config_parser.generate_config_dict()
    config_dict["pdftext_workers"] = 1
    config_dict["disable_ocr"] = disable_ocr
    
    return config_dict


def get_output_basename(input_path_or_name: str, start_page=None, end_page=None) -> str:
    """
    生成输出文件的基础名称，始终包含时间戳以避免覆盖

    格式:
    - 默认: {文件名}_{时间戳}
    - 指定页码范围: {文件名}_p{起始}-{结束}_{时间戳}

    时间戳格式: YYYYMMDD_HHMMSS (便于排序和编程解析)
    """
    stem = Path(input_path_or_name).stem
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if start_page is not None and end_page is not None:
        # 有页码范围: document_p1-10_20260126_143022
        return f"{stem}_p{start_page}-{end_page}_{ts}"
    else:
        # 默认: document_20260126_143022
        return f"{stem}_{ts}"


def build_zip(paths: list, zip_path: str):
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in paths:
            if p and os.path.exists(p):
                zf.write(p, arcname=os.path.basename(p))


def scan_outputs_for_restore(out_dir: str):
    found = {}
    if not os.path.exists(out_dir):
        return found
    for f in os.listdir(out_dir):
        full = os.path.join(out_dir, f)
        if not os.path.isfile(full):
            continue
        base = Path(f).stem
        if base.endswith("_meta"):
            base = base[:-5]
        found.setdefault(base, [])
        found[base].append(full)
    return found


def check_calamari_health(base_url: str) -> tuple:
    """检查 Calamari 服务状态"""
    import requests
    try:
        resp = requests.get(f"{base_url}/health", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return True, data.get("cached_models", [])
        return False, []
    except Exception:
        return False, []


def get_calamari_models(base_url: str) -> list:
    """获取 Calamari 可用模型列表"""
    import requests
    try:
        resp = requests.get(f"{base_url}/models", timeout=5)
        if resp.status_code == 200:
            return resp.json().get("models", [])
        return []
    except Exception:
        return []


def safe_cleanup_temp_files(temp_files: list, max_retries: int = 3, delay: float = 1.0):
    """
    安全清理临时文件（带重试机制）

    解决批量处理时文件句柄未释放导致的权限错误

    Args:
        temp_files: 临时文件路径列表
        max_retries: 最大重试次数
        delay: 重试间隔（秒）
    """
    import time as time_module

    # 先强制垃圾回收，释放可能的文件句柄
    gc.collect()

    failed_files = []
    for tmp_path in temp_files:
        if not os.path.exists(tmp_path):
            continue

        success = False
        for attempt in range(max_retries):
            try:
                os.unlink(tmp_path)
                success = True
                break
            except PermissionError:
                # 文件可能还在被使用，等待后重试
                if attempt < max_retries - 1:
                    time_module.sleep(delay)
                    gc.collect()  # 再次尝试释放句柄
            except Exception as e:
                # 其他错误，记录但不重试
                break

        if not success and os.path.exists(tmp_path):
            failed_files.append(tmp_path)

    if failed_files:
        # 记录无法删除的文件，但不阻塞流程
        print(f"[警告] 以下临时文件无法删除（将在系统重启后自动清理）：{failed_files}")


# ==================== 应用已加载的配置 ====================
if "loaded_config" in st.session_state:
    apply_config_to_session(st.session_state["loaded_config"])
    del st.session_state["loaded_config"]


# ==================== 侧边栏 ====================
with st.sidebar:
    st.header("⚙️ 配置面板")
    st.caption("💡 成功处理某类文献的配置可保存为预设，便于经验交流和快速启动")

    # ==================== 配置管理 ====================
    config_manager = ConfigManager()

    with st.expander("📋 配置管理", expanded=False):
        # 获取已保存的配置列表
        saved_configs = config_manager.list_configs()
        config_names = ["-- 不使用预设 --"] + [c["name"] for c in saved_configs]

        # 配置选择器
        selected_config = st.selectbox(
            "选择配置",
            options=config_names,
            index=0,
            key="config_selector",
            help="选择已保存的配置快速加载"
        )

        # 加载配置按钮
        if selected_config != "-- 不使用预设 --":
            if st.button("📥 加载此配置", key="load_config_btn"):
                loaded = config_manager.load_config(selected_config)
                if loaded:
                    st.session_state["loaded_config"] = loaded
                    st.success(f"已加载配置: {selected_config}")
                    st.rerun()
                else:
                    st.error("加载配置失败")

        st.markdown("---")

        # 保存当前配置
        st.markdown("**保存当前配置**")
        new_config_name = st.text_input("配置名称", key="new_config_name", placeholder="例如: 德文-fraktur-印刷")
        new_config_desc = st.text_input("配置描述", key="new_config_desc", placeholder="可选")

        api_key_mode = st.radio(
            "API Key 处理",
            options=["exclude", "placeholder", "include"],
            format_func=lambda x: {"exclude": "不保存", "placeholder": "占位符", "include": "保留"}[x],
            index=1,
            horizontal=True,
            key="api_key_mode"
        )

        col_save, col_export = st.columns(2)
        with col_save:
            if st.button("💾 保存", key="save_config_btn"):
                if new_config_name:
                    # 收集当前配置
                    current_config = collect_current_config()
                    success = config_manager.save_config(
                        name=new_config_name,
                        config_data=current_config,
                        description=new_config_desc,
                        api_key_mode=api_key_mode,
                        overwrite=True
                    )
                    if success:
                        st.success(f"配置 '{new_config_name}' 已保存")
                        st.rerun()
                    else:
                        st.error("保存失败")
                else:
                    st.warning("请输入配置名称")

        with col_export:
            if st.button("📤 导出", key="export_config_btn"):
                if selected_config != "-- 不使用预设 --":
                    json_str = config_manager.export_config(selected_config, api_key_mode)
                    if json_str:
                        st.download_button(
                            "下载 JSON",
                            data=json_str,
                            file_name=f"{selected_config}.json",
                            mime="application/json"
                        )

        st.markdown("---")

        # 导入配置
        st.markdown("**导入配置**")
        uploaded_config = st.file_uploader("上传配置文件", type=["json"], key="config_uploader")
        if uploaded_config:
            overwrite = st.checkbox("覆盖同名配置", key="overwrite_config")
            if st.button("📥 导入", key="import_config_btn"):
                json_str = uploaded_config.read().decode("utf-8")
                success, msg = config_manager.import_config(json_str, overwrite)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    # ==================== 0. 关键：默认值初始化（防 NameError / rerun） ====================
    # Streamlit 会反复 rerun 脚本；下面这些变量在后续多个区块被引用，
    # 必须在任何分支之前先定义默认值，避免 use_llm / ocr_batch_size 等未定义。
    FORMAT_CHOICES = ["markdown", "json", "html", "chunks"]

    output_formats = FORMAT_CHOICES[:]  # 默认全选
    upload_mode = "上传文件"
    uploaded_files = []

    # 版面识别后端 defaults
    layout_backend = "surya"

    # OCR 后端 defaults
    ocr_backend = "surya"
    ocr_batch_size = 32
    force_ocr = False
    use_llm = False

    # VLM 版面识别 defaults (独立配置,不与OCR绑定)
    vlm_layout_base_url = os.environ.get("VLM_LAYOUT_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    vlm_layout_model = os.environ.get("VLM_LAYOUT_MODEL", "qwen-vl-max-2025-01-25")
    vlm_layout_api_key = os.environ.get("VLM_LAYOUT_API_KEY", "")
    vlm_layout_max_concurrent = int(os.environ.get("VLM_LAYOUT_MAX_CONCURRENT", "3"))
    vlm_layout_prompt_template = "modern"
    vlm_layout_prompt = ""
    vlm_layout_timeout = 120
    vlm_layout_image_format = "png"
    vlm_layout_max_image_dimension = 2048
    vlm_layout_jpeg_quality = 85

    # YOLO 版面识别 defaults
    yolo_base_url = os.environ.get("YOLO_BASE_URL", "http://localhost:11900")
    yolo_model = "doclayout_yolo"
    yolo_confidence_threshold = 0.25

    # Calamari defaults（确保即使不选 calamari 也不会 NameError）
    calamari_base_url = os.environ.get("CALAMARI_BASE_URL", "http://localhost:11800")
    calamari_model = os.environ.get("CALAMARI_MODEL", "gt4histocr")
    calamari_batch_size = 100
    calamari_timeout = 120
    calamari_sequential_mode = False
    calamari_trust_batch_order = False
    calamari_require_ordering_info = True
    calamari_fallback_to_sequential_on_ordering_failure = True

    # VLM defaults（确保即使不选 vlm 也不会 NameError）
    openai_base_url = os.environ.get("OPENAI_BASE_URL", "http://127.0.0.1:1234/v1")
    openai_model = os.environ.get("OPENAI_MODEL", "churro-3b")
    openai_api_key = os.environ.get("OPENAI_API_KEY", "lm-studio")
    openai_image_format = "png"
    vlm_mode = "tile"
    vlm_response_mode = "text"
    vlm_prompt = "Transcribe exactly as seen. Preserve line breaks. Do not repeat. Stop at the end of the block."
    openai_use_stop = False
    vlm_merge_y_threshold = 80
    vlm_merge_max_blocks = 15
    vlm_full_page_max_tokens = 2048

    st.divider()

    # ==================== 1. 输出设置 ====================
    st.subheader("📁 输出设置")
    col1, col2 = st.columns([4, 1])
    with col1:
        out_dir = st.text_input("输出文件夹", value=st.session_state.output_dir, label_visibility="collapsed", key="out_dir")
        if out_dir != st.session_state.output_dir:
            st.session_state.output_dir = out_dir
            os.makedirs(st.session_state.output_dir, exist_ok=True)
    with col2:
        if st.button("📂", help="打开输出文件夹"):
            if os.path.exists(st.session_state.output_dir):
                if sys.platform == "win32":
                    os.startfile(st.session_state.output_dir)
                elif sys.platform == "darwin":
                    subprocess.run(["open", st.session_state.output_dir])
                else:
                    subprocess.run(["xdg-open", st.session_state.output_dir])

    st.divider()

    # ==================== 2. 文件选择（全局） ====================
    st.subheader("📄 文件选择")
    upload_mode = st.radio("选择模式", ["上传文件", "选择文件夹"], index=0, horizontal=True, key="upload_mode_global")

    if upload_mode == "上传文件":
        uploaded_files = st.file_uploader(
            "上传 PDF 文件",
            type=["pdf"],
            accept_multiple_files=True,
            label_visibility="collapsed",
            key="file_uploader_global"
        )
    else:
        folder_path = st.text_input("文件夹路径", value="", label_visibility="collapsed", placeholder="输入文件夹路径...", key="folder_path_global")
        uploaded_files = []
        if folder_path:
            if os.path.exists(folder_path):
                for root, _, files in os.walk(folder_path):
                    for fn in files:
                        if fn.lower().endswith(".pdf"):
                            uploaded_files.append(os.path.join(root, fn))
                st.success(f"找到 {len(uploaded_files)} 个 PDF 文件")
            else:
                st.error("文件夹路径不存在")

    st.divider()

    # ==================== 3. 转换模式选择 ====================
    st.subheader("⚙️ 转换模式")
    conversion_mode = st.radio(
        "选择转换模式",
        options=["pipeline", "vlm_generalized", "vlm_specialized"],
        index=0,
        format_func=lambda x: {
            "pipeline": "🔧 Pipeline模式",
            "vlm_generalized": "🌐 VLM 泛化模式",
            "vlm_specialized": "🎯 VLM 特化模式",
        }.get(x, x),
        horizontal=True,
        help="Pipeline: 版面识别+OCR流水线 | VLM泛化: 通用大模型 | VLM特化: OCR微调模型",
        key="conversion_mode"
    )

    if conversion_mode == "vlm_generalized":
        st.info(MODE_DESCRIPTIONS["vlm_generalized"])
    elif conversion_mode == "vlm_specialized":
        st.warning(MODE_DESCRIPTIONS["vlm_specialized"])
    else:
        st.success(MODE_DESCRIPTIONS["pipeline"])

    st.divider()

    # ==================== 4. 统一页码锚点配置（全局） ====================
    st.subheader("📍 页码锚点配置")
    with st.expander("页码锚点设置", expanded=False):
        # ===== 1. PDF 页码锚点（强制启用） =====
        st.markdown("**📄 PDF 页码锚点**")
        st.success("✅ **已启用** - 格式：`{n}`（n = PDF 页序号）")
        st.caption("每页开头自动添加 PDF 页码锚点，便于引用和跳转")

        # 锚点位置（仅 VLM 泛化模式支持）
        if conversion_mode == "vlm_generalized":
            page_anchor_position = st.radio(
                "锚点位置",
                options=["before", "after", "both"],
                index=0,
                format_func=lambda x: {
                    "before": "页面前",
                    "after": "页面后",
                    "both": "页面前后"
                }.get(x, x),
                horizontal=True,
                help="锚点插入位置（仅 VLM 泛化模式支持）",
                key="page_anchor_position_global"
            )
        else:
            page_anchor_position = "before"

        # 强制启用页码锚点
        enable_page_anchors = True

        st.markdown("---")

        # ===== 2. 印刷页码提取 =====
        st.markdown("**📖 印刷页码提取**")
        extract_printed_pages = st.checkbox(
            "启用印刷页码提取",
            value=True,
            help="自动识别文档中的印刷页码，生成 `<!-- Page: X -->` 标签",
            key="extract_printed_pages_global"
        )

        # Pipeline 模式的印刷页码详细配置
        is_pipeline_with_extract = (extract_printed_pages and conversion_mode == "pipeline")
        is_direct_mode = conversion_mode in ["vlm_generalized", "vlm_specialized"]
        vlm_printed_page_patterns = None

        if extract_printed_pages:
            # Pipeline 模式配置
            if conversion_mode == "pipeline":
                st.caption("通过版面识别检测页眉/页脚区域提取页码")
                col1, col2 = st.columns(2)
                with col1:
                    printed_page_zones = st.multiselect(
                        "页码搜索区域",
                        options=["header", "footer"],
                        default=["footer", "header"],
                        help="页码可能出现的位置",
                        key="printed_page_zones_global"
                    )
                    printed_page_format = st.selectbox(
                        "页码格式",
                        options=["arabic", "roman", "chinese", "auto"],
                        index=3,
                        format_func=lambda x: {
                            "arabic": "阿拉伯数字",
                            "roman": "罗马数字",
                            "chinese": "中文数字",
                            "auto": "自动检测"
                        }.get(x, x),
                        key="printed_page_format_global"
                    )
                with col2:
                    printed_page_header_end = st.slider(
                        "页眉区域", 0.0, 0.3, 0.15, 0.01,
                        help="页面顶部 15% 为页眉区域",
                        key="printed_page_header_end_global"
                    )
                    printed_page_footer_start = st.slider(
                        "页脚区域", 0.7, 1.0, 0.83, 0.01,
                        help="页面底部 17% 为页脚区域",
                        key="printed_page_footer_start_global"
                    )
                printed_page_header_start = 0.0

                # 自定义正则表达式（Pipeline 模式）
                printed_page_custom_pattern = st.text_input(
                    "自定义正则表达式（可选）",
                    value="",
                    help="自定义页码匹配正则，优先级高于格式选择。留空则使用上方格式设置。示例：\\d{1,4} 匹配1-4位数字",
                    key="printed_page_custom_pattern_global"
                )
            # VLM 模式配置
            else:
                st.caption("通过正则表达式从 Markdown 输出中提取页码")

            # 正则预设选项
            regex_presets = {
                "default": {
                    "name": "默认（阿拉伯/罗马数字）",
                    "patterns": [
                        r"<!--\s*page-header:\s*(\d{1,4})\s*-->",
                        r"<!--\s*page-header:\s*([IVXLCDM]{1,8})\s*-->",
                        r"<!--\s*page-header:\s*([ivxlcdm]{1,8})\s*-->",
                        r"<!--\s*page-footer:\s*(\d{1,4})\s*-->",
                        r"^\s*[-—]?\s*(\d{1,4})\s*[-—]?\s*$",
                        r"(?:^|\s)([IVXLCDM]{2,8})(?:\s|$)",
                        r"(?:^|\s)([ivxlcdm]{2,8})(?:\s|$)",
                    ],
                    "description": "通用印刷页码：阿拉伯数字(1-9999)、罗马数字(I-MMMM)"
                },
                "sc_format": {
                    "name": "SC 档案编号",
                    "patterns": [
                        r"<!--\s*page-header:\s*([Ss][Cc]\s*\d{3})\s*-->",
                        r"\b([Ss5$][Cc0O(][Uu]?\s*[0Oo]?\d{3})(?!\d)",
                        r"\b([Ss][Cc][-\s]?\d{3})(?!\d)",
                    ],
                    "description": "档案编号 SC001~SC999（容忍 OCR 错误如 5C001, S0001）"
                },
                "chinese": {
                    "name": "中文页码",
                    "patterns": [
                        r"<!--\s*page-header:\s*([一二三四五六七八九十百千零〇]+)\s*-->",
                        r"第([一二三四五六七八九十百千零〇]+)[頁葉页叶]",
                        r"([一二三四五六七八九十百千零〇]+)[頁葉页叶]",
                        r"[頁葉页叶]([一二三四五六七八九十百千零〇]+)",
                    ],
                    "description": "中文数字页码（古籍、线装书）"
                },
                "custom": {
                    "name": "自定义正则",
                    "patterns": [],
                    "description": "手动输入正则表达式"
                }
            }

            regex_preset_key = st.selectbox(
                "正则预设",
                options=list(regex_presets.keys()),
                index=1,
                format_func=lambda x: regex_presets[x]["name"],
                disabled=not (is_direct_mode and extract_printed_pages),
                help="选择预设的正则表达式组合，或选择「自定义正则」手动输入",
                key="regex_preset_key_global"
            )

            if is_direct_mode and extract_printed_pages:
                st.caption(f"📝 {regex_presets[regex_preset_key]['description']}")

            if regex_preset_key == "custom":
                default_patterns_text = ""
            else:
                default_patterns_text = "\n".join(regex_presets[regex_preset_key]["patterns"])

            show_editor = (regex_preset_key == "custom") or st.checkbox(
                "编辑正则表达式",
                value=False,
                disabled=not (is_direct_mode and extract_printed_pages),
                help="展开编辑器查看或修改正则表达式",
                key="show_regex_editor_global"
            )

            if show_editor and is_direct_mode:
                vlm_patterns_text = st.text_area(
                    "正则表达式列表（每行一个）",
                    value=default_patterns_text,
                    height=120,
                    help="每行一个正则表达式，按顺序尝试匹配。捕获组 (...) 中的内容将作为页码。",
                    disabled=not extract_printed_pages,
                    key="vlm_patterns_text_global"
                )
            else:
                vlm_patterns_text = default_patterns_text

            # 处理 VLM 模式的正则表达式
            if is_direct_mode:
                vlm_printed_page_patterns = [
                    pattern.strip()
                    for pattern in vlm_patterns_text.split('\n')
                    if pattern.strip()
                ]
                st.success(f"✅ 正则提取已启用，共 {len(vlm_printed_page_patterns)} 条规则")
        else:
            # 禁用印刷页码提取时的默认值
            printed_page_zones = ["footer", "header"]
            printed_page_format = "auto"
            printed_page_custom_pattern = ""
            printed_page_header_start = 0.0
            printed_page_header_end = 0.15
            printed_page_footer_start = 0.83
            vlm_printed_page_patterns = None

        # ===== 3. 特殊-边码（古籍与经典文献） =====
        st.markdown("---")
        st.markdown("**📝 特殊-边码（古籍与经典文献）**")

        enable_marginal_detection = st.checkbox(
            "启用边码/页边注识别",
            value=False,
            help="识别版心叶码、Stephanus/Bekker编码、行号、书耳、眉批等",
            key="enable_marginal_detection_global"
        )

        if enable_marginal_detection:
            st.markdown("**位置阈值配置**")
            col1, col2 = st.columns(2)
            with col1:
                left_margin_threshold = st.slider(
                    "左边栏阈值", min_value=0.05, max_value=0.30, value=0.15, step=0.01,
                    help="左边栏区域宽度（页面宽度比例）",
                    key="left_margin_threshold_global"
                )
                right_margin_threshold = st.slider(
                    "右边栏阈值", min_value=0.70, max_value=0.95, value=0.85, step=0.01,
                    help="右边栏区域起始位置（页面宽度比例）",
                    key="right_margin_threshold_global"
                )
            with col2:
                top_margin_threshold = st.slider(
                    "上边栏阈值", min_value=0.05, max_value=0.20, value=0.10, step=0.01,
                    help="上边栏区域高度（页面高度比例）",
                    key="top_margin_threshold_global"
                )
                bottom_margin_threshold = st.slider(
                    "下边栏阈值", min_value=0.80, max_value=0.95, value=0.90, step=0.01,
                    help="下边栏区域起始位置（页面高度比例）",
                    key="bottom_margin_threshold_global"
                )
            vertical_center_tolerance = st.slider(
                "垂直中线容差", min_value=0.01, max_value=0.10, value=0.05, step=0.01,
                help="版心叶码检测的中线容差（页面宽度比例）",
                key="vertical_center_tolerance_global"
            )
        else:
            left_margin_threshold = 0.15
            right_margin_threshold = 0.85
            top_margin_threshold = 0.10
            bottom_margin_threshold = 0.90
            vertical_center_tolerance = 0.05

        enable_inline_detection = st.checkbox(
            "启用行内小字注识别",
            value=False,
            help="识别双行小字、夹注、割注、括号注等",
            key="enable_inline_detection_global"
        )

        if enable_inline_detection:
            font_size_ratio_threshold = st.slider(
                "字体比例阈值", min_value=0.50, max_value=0.90, value=0.75, step=0.05,
                help="相对于主文本的字体大小比例",
                key="font_size_ratio_threshold_global"
            )
            max_inline_annotation_length = st.number_input(
                "最大注释长度", min_value=50, max_value=200, value=100, step=10,
                help="行内注释的最大字符数",
                key="max_inline_annotation_length_global"
            )
        else:
            font_size_ratio_threshold = 0.75
            max_inline_annotation_length = 100

        # ===== 4. 自定义编号 =====
        st.markdown("---")
        st.markdown("**📋 自定义编号**")
        st.caption("为页面指定自定义编号（如档案编号 SC001），替代自动识别的印刷页码")

        custom_id_source = st.selectbox(
            "编号来源",
            options=["none", "file", "list", "auto"],
            index=0,
            format_func=lambda x: {
                "none": "无（使用印刷页码）",
                "file": "上传文件（CSV/JSON）",
                "list": "手动输入列表",
                "auto": "自动生成（SC 001, SC 002...）"
            }.get(x, x),
            help="选择自定义编号的来源方式",
            key="custom_id_source_global"
        )

        custom_id_data = None

        if custom_id_source == "file":
            st.info("💡 上传 CSV 或 JSON 文件，格式：页序,自定义编号")
            uploaded_id_file = st.file_uploader(
                "上传页码映射文件",
                type=["csv", "json"],
                help="CSV 格式：0,sc001\\n1,sc002\\nJSON 格式：{\"0\": \"sc001\", \"1\": \"sc002\"}",
                key="uploaded_id_file_global"
            )
            if uploaded_id_file:
                custom_id_data = uploaded_id_file

        elif custom_id_source == "list":
            st.info("💡 手动输入每页的自定义编号，用逗号或换行分隔")
            custom_id_list = st.text_area(
                "自定义编号列表",
                value="sc001, sc002, sc003",
                height=100,
                help="输入每页的自定义编号，按页序排列",
                key="custom_id_list_global"
            )
            if custom_id_list:
                ids = [id.strip() for id in custom_id_list.replace('\n', ',').split(',') if id.strip()]
                custom_id_data = ids

        elif custom_id_source == "auto":
            st.info("💡 自动生成连续编号（如 SC 001, SC 002...）")
            col1, col2, col3 = st.columns(3)
            with col1:
                auto_prefix = st.text_input(
                    "编号前缀",
                    value="SC",
                    help="自动生成编号的前缀",
                    key="auto_prefix_global"
                )
            with col2:
                auto_start = st.number_input(
                    "起始编号",
                    min_value=1,
                    value=1,
                    help="起始值",
                    key="auto_start_global"
                )
            with col3:
                auto_separator = st.selectbox(
                    "分隔符",
                    options=["", " ", "-", "_"],
                    index=1,
                    format_func=lambda x: {
                        "": "无（SC001）",
                        " ": "空格（SC 001）",
                        "-": "横线（SC-001）",
                        "_": "下划线（SC_001）"
                    }.get(x, x),
                    key="auto_separator_global"
                )
            auto_digits = st.slider(
                "编号位数",
                min_value=2,
                max_value=6,
                value=3,
                help="编号的位数（如 3 位：001, 002）",
                key="auto_digits_global"
            )
            custom_id_data = {
                "prefix": auto_prefix,
                "start": auto_start,
                "digits": auto_digits,
                "separator": auto_separator
            }

    st.divider()

    # ==================== 5. 配置区域（根据转换模式显示不同内容） ====================
    if conversion_mode == "vlm_specialized":
        # ==================== VLM 特化模式配置 ====================
        st.subheader("🎯 VLM 特化模式配置")

        # API 配置
        with st.expander("🔌 API 配置", expanded=True):
            ocr_endpoint = st.text_input(
                "API 端点",
                value="http://localhost:1234/v1",
                help="OCR API 端点（OpenAI 兼容格式）",
                key="ocr_endpoint"
            )
            ocr_model = st.text_input(
                "模型名称",
                value="chandra-ocr@f16",
                help="OCR 模型名称",
                key="ocr_model"
            )
            ocr_api_key = st.text_input(
                "API Key（可选）",
                value="",
                type="password",
                help="如果 API 需要认证",
                key="ocr_api_key"
            )
            # 输出格式选择（多选）
            ocr_output_formats = st.multiselect(
                "输出格式",
                options=["markdown", "json", "html"],
                default=["markdown", "json", "html"],
                help="选择要输出的格式（可多选，默认全选）",
                key="ocr_output_format"
            )

        # 图像预处理
        with st.expander("🖼️ 图像预处理", expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                ocr_image_format = st.selectbox(
                    "图像格式",
                    options=["jpeg", "png", "webp"],
                    index=1,
                    help="发送给 API 的图像格式（推荐 PNG）",
                    key="ocr_image_format"
                )
                ocr_resize_max = st.number_input(
                    "最大图像尺寸（像素）",
                    min_value=512,
                    max_value=4096,
                    value=2048,
                    step=128,
                    help="图像最大边长 - LM Studio 需要小图像",
                    key="ocr_resize_max"
                )
            with col2:
                ocr_image_quality = st.slider(
                    "JPEG 质量",
                    min_value=50,
                    max_value=100,
                    value=90,
                    help="JPEG 压缩质量",
                    key="ocr_image_quality"
                )

        # 高级选项（包含并发控制）
        with st.expander("⚙️ 高级选项", expanded=False):
            st.markdown("**📁 并发控制**")

            # 并发模式选择
            ocr_concurrency_mode = st.radio(
                "并发模式",
                options=["serial_file", "batch_single_page"],
                index=1,
                format_func=lambda x: {
                    "serial_file": "📄 串行文件处理（多页PDF推荐）",
                    "batch_single_page": "📑 单页多文件批次（扫描图片推荐）"
                }[x],
                help="串行模式：逐个文件处理，每个文件内可并行多页；批次模式：多个单页文件同时处理",
                key="ocr_concurrency_mode"
            )

            if ocr_concurrency_mode == "serial_file":
                # 串行文件处理模式
                col1, col2 = st.columns(2)
                with col1:
                    ocr_concurrency = st.number_input(
                        "页面并发数",
                        min_value=1,
                        max_value=20,
                        value=5,
                        help="单个文件内同时处理的页面数量",
                        key="ocr_concurrency"
                    )
                with col2:
                    ocr_batch_rest = st.number_input(
                        "批次休息时间（秒）",
                        min_value=0.0,
                        max_value=10.0,
                        value=1.0,
                        step=0.5,
                        help="每批页面处理完后的休息时间（帮助显卡散热）",
                        key="ocr_batch_rest"
                    )
                ocr_max_concurrent_files = 1
                ocr_batch_size = ocr_concurrency  # 批次大小等于并发数
                ocr_total_concurrent = ocr_concurrency  # 总并发数等于页面并发数
                st.caption(f"💡 串行模式：逐个文件处理，每 {ocr_concurrency} 页后休息 {ocr_batch_rest} 秒")
            else:
                # 单页多文件批次模式
                col1, col2 = st.columns(2)
                with col1:
                    ocr_file_batch_size = st.number_input(
                        "文件批次大小",
                        min_value=1,
                        max_value=20,
                        value=3,
                        help="每批同时处理的文件数量",
                        key="ocr_file_batch_size"
                    )
                with col2:
                    ocr_file_batch_rest = st.number_input(
                        "批次休息时间（秒）",
                        min_value=0.0,
                        max_value=10.0,
                        value=1.0,
                        step=0.5,
                        help="每批文件处理完后的休息时间（帮助显卡散热）",
                        key="ocr_file_batch_rest"
                    )
                ocr_max_concurrent_files = ocr_file_batch_size
                ocr_concurrency = 1
                ocr_batch_size = 1
                ocr_batch_rest = ocr_file_batch_rest
                ocr_total_concurrent = ocr_file_batch_size  # 总并发数等于文件批次大小
                st.caption(f"💡 批次模式：每批 {ocr_file_batch_size} 个文件，完成后休息 {ocr_file_batch_rest} 秒")

            st.markdown("---")
            st.markdown("**⚙️ 其他设置**")
            col1, col2 = st.columns(2)
            with col1:
                ocr_max_retries = st.number_input(
                    "最大重试次数",
                    min_value=1,
                    max_value=10,
                    value=3,
                    help="API 调用失败时的重试次数",
                    key="ocr_max_retries"
                )
            with col2:
                ocr_timeout = st.number_input(
                    "API 超时时间（秒）",
                    min_value=30,
                    max_value=300,
                    value=120,
                    help="单个 API 请求的超时时间",
                    key="ocr_timeout"
                )

            col3, col4 = st.columns(2)
            with col3:
                ocr_max_tokens = st.number_input(
                    "最大输出 Token 数",
                    min_value=1024,
                    max_value=32768,
                    value=8192,
                    step=1024,
                    help="单次 API 响应的最大 token 数量",
                    key="ocr_max_tokens"
                )

        # 📄 页码范围选择
        with st.expander("📄 页码范围", expanded=False):
            ocr_use_page_range = st.checkbox("指定页码范围", value=False, key="ocr_use_page_range")
            if ocr_use_page_range:
                col_start, col_end = st.columns(2)
                with col_start:
                    ocr_start_page = st.number_input("起始页", min_value=1, value=1, key="ocr_start_page")
                with col_end:
                    ocr_end_page = st.number_input("结束页", min_value=1, value=10, key="ocr_end_page")
            else:
                ocr_start_page = None
                ocr_end_page = None

        # 🆕 后处理配置
        with st.expander("🔧 后处理配置", expanded=False):
            st.markdown("**📝 文本后处理**")

            # 噪音过滤
            ocr_noise_removal = st.checkbox(
                "启用噪音过滤",
                value=True,
                help="移除水印、扫描标记等噪音",
                key="ocr_noise_removal"
            )

            if ocr_noise_removal:
                ocr_noise_patterns = st.text_area(
                    "自定义噪音模式（每行一个正则）",
                    value="Digitized by Google\nDigitized by the Internet Archive\nScanned by.*",
                    height=100,
                    help="支持正则表达式，每行一个模式",
                    key="ocr_noise_patterns"
                )
            else:
                ocr_noise_patterns = ""

            st.markdown("---")

            # 脚注修复
            ocr_footnote_fix = st.checkbox(
                "启用脚注修复",
                value=True,
                help="修复脚注格式（如重复括号、未标记脚注）",
                key="ocr_footnote_fix"
            )

            st.markdown("---")
            st.markdown("**🏷️ 页眉页脚过滤**")

            # 页眉过滤
            ocr_filter_page_header = st.checkbox(
                "过滤页眉语法标记",
                value=False,
                help="移除 <!-- page-header: --> 语法，保留内容。例如：<!-- page-header: 0115 --> → 0115",
                key="ocr_filter_page_header"
            )

            # 页脚过滤
            ocr_filter_page_footer = st.checkbox(
                "过滤页脚语法标记",
                value=False,
                help="移除 <!-- page-footer: --> 语法，保留内容。例如：<!-- page-footer: 123 --> → 123",
                key="ocr_filter_page_footer"
            )

    # VLM 泛化模式配置
    if conversion_mode == "vlm_generalized":
        # ==================== VLM 泛化模式配置 ====================
        st.subheader("🌐 VLM 泛化模式配置")

        # 🔌 API 配置
        with st.expander("🔌 API 配置", expanded=True):
            # 输出格式选择（多选）
            vlm_output_formats = st.multiselect(
                "输出格式",
                options=["markdown", "html"],
                default=["markdown"],
                help="选择要输出的格式（可多选）",
                key="vlm_output_format"
            )
            output_formats = vlm_output_formats if vlm_output_formats else ["markdown"]

            # API 提供商选择
            vlm_api_provider = st.selectbox(
                "API 提供商",
                options=["openai_compatible", "gemini", "anthropic"],
                format_func=lambda x: {
                    "openai_compatible": "OpenAI 兼容（通用）",
                    "gemini": "Google Gemini（原生）",
                    "anthropic": "Anthropic Claude（原生）"
                }.get(x, x),
                help="选择 API 提供商类型",
                key="vlm_api_provider"
            )

            if vlm_api_provider == "openai_compatible":
                # OpenAI 兼容配置
                vlm_direct_base_url = st.text_input(
                    "Base URL",
                    value=os.environ.get("OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
                    help="OpenAI 兼容 API 的基础 URL",
                    key="vlm_direct_base_url"
                )
                vlm_direct_model = st.text_input(
                    "模型名称",
                    value=os.environ.get("OPENAI_MODEL", "qwen-vl-max-2025-08-13"),
                    help="例如: gpt-4o, gpt-4o-mini, qwen-vl-max",
                    key="vlm_direct_model"
                )
                vlm_direct_api_key = st.text_area(
                    "API Keys (支持多个)",
                    value=os.environ.get("OPENAI_API_KEY", ""),
                    height=100,
                    help="支持多个API Key，每行一个或逗号分隔",
                    key="vlm_direct_api_key"
                )
            elif vlm_api_provider == "gemini":
                # Gemini 原生配置
                st.caption("📌 使用 Google Gemini 原生 API（支持中转）")
                vlm_direct_base_url = st.text_input(
                    "Gemini API 端点（可选）",
                    value=os.environ.get("GEMINI_BASE_URL", "https://code.newcli.com/gemini"),
                    help="留空使用官方API，或填写中转接口URL",
                    key="vlm_gemini_base_url"
                )
                vlm_direct_model = st.text_input(
                    "模型名称",
                    value=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
                    help="例如: gemini-2.5-flash, gemini-2.0-flash, gemini-1.5-pro",
                    key="vlm_gemini_model"
                )
                vlm_direct_api_key = st.text_area(
                    "Gemini API Keys (支持多个)",
                    value=os.environ.get("GEMINI_API_KEY", ""),
                    height=100,
                    help="支持多个API Key，每行一个或逗号分隔",
                    key="vlm_gemini_api_key"
                )
            elif vlm_api_provider == "anthropic":
                # Anthropic Claude 原生配置
                st.caption("📌 使用 Anthropic Claude 原生 API（支持中转）")
                vlm_direct_base_url = st.text_input(
                    "Anthropic API 端点（可选）",
                    value=os.environ.get("ANTHROPIC_BASE_URL", ""),
                    help="留空使用官方API (https://api.anthropic.com)，或填写中转接口URL",
                    key="vlm_anthropic_base_url"
                )
                vlm_direct_model = st.text_input(
                    "模型名称",
                    value=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
                    help="例如: claude-sonnet-4-20250514, claude-3-5-sonnet-20241022",
                    key="vlm_anthropic_model"
                )
                vlm_direct_api_key = st.text_area(
                    "Anthropic API Keys (支持多个)",
                    value=os.environ.get("ANTHROPIC_API_KEY", ""),
                    height=100,
                    help="支持多个API Key，每行一个或逗号分隔。格式: sk-ant-...",
                    key="vlm_anthropic_api_key"
                )

            # 显示Key数量和建议
            if vlm_direct_api_key:
                keys = [k.strip() for k in vlm_direct_api_key.replace('\n', ',').split(',') if k.strip()]
                key_count = len(keys)
                if key_count > 1:
                    st.success(f"✅ 检测到 {key_count} 个API Key")
                    suggested_concurrent = key_count * 3
                    st.info(f"💡 建议并发数: {suggested_concurrent} (Key数量 × 3)")

        # 🖼️ 图像预处理
        with st.expander("🖼️ 图像预处理", expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                vlm_direct_image_format = st.selectbox(
                    "图像格式",
                    options=["jpeg", "png", "webp"],
                    index=1,
                    help="发送给 API 的图像格式（推荐 PNG）",
                    key="vlm_direct_image_format"
                )
                vlm_direct_max_image_dimension = st.number_input(
                    "最大图像尺寸（像素）",
                    min_value=512,
                    max_value=4096,
                    value=2048,
                    step=128,
                    help="图像最大边长",
                    key="vlm_direct_max_image_dimension"
                )
            with col2:
                vlm_direct_jpeg_quality = st.slider(
                    "JPEG 质量",
                    min_value=50,
                    max_value=100,
                    value=90,
                    help="JPEG 压缩质量（推荐 85-95）",
                    key="vlm_direct_jpeg_quality"
                )

        # ⚙️ 高级选项
        with st.expander("⚙️ 高级选项", expanded=False):
            st.markdown("**📁 并发控制**")

            # 并发模式选择
            vlm_concurrency_mode = st.radio(
                "并发模式",
                options=["serial_file", "batch_single_page"],
                format_func=lambda x: {
                    "serial_file": "📄 串行文件处理（多页PDF推荐）",
                    "batch_single_page": "📑 单页多文件批次（扫描图片推荐）"
                }[x],
                help="串行模式：逐个文件处理，每个文件内可并行多页；批次模式：多个单页文件同时处理",
                key="vlm_concurrency_mode"
            )

            if vlm_concurrency_mode == "serial_file":
                # 串行文件处理模式
                col1, col2 = st.columns(2)
                with col1:
                    vlm_direct_max_concurrent = st.number_input(
                        "页面并发数",
                        min_value=1,
                        max_value=20,
                        value=5,
                        help="单个文件内同时处理的页面数量",
                        key="vlm_direct_max_concurrent"
                    )
                with col2:
                    vlm_batch_rest = st.number_input(
                        "批次休息时间（秒）",
                        min_value=0.0,
                        max_value=10.0,
                        value=1.0,
                        step=0.5,
                        help="每批页面处理完后的休息时间（帮助显卡散热）",
                        key="vlm_batch_rest"
                    )
                vlm_direct_max_concurrent_files = 1
                vlm_direct_total_concurrent = vlm_direct_max_concurrent
                st.caption(f"💡 串行模式：逐个文件处理，每 {vlm_direct_max_concurrent} 页后休息 {vlm_batch_rest} 秒")
            else:
                # 单页多文件批次模式
                col1, col2 = st.columns(2)
                with col1:
                    vlm_file_batch_size = st.number_input(
                        "文件批次大小",
                        min_value=1,
                        max_value=20,
                        value=6,
                        help="每批同时处理的文件数量",
                        key="vlm_file_batch_size"
                    )
                with col2:
                    vlm_file_batch_rest = st.number_input(
                        "批次休息时间（秒）",
                        min_value=0.0,
                        max_value=10.0,
                        value=1.0,
                        step=0.5,
                        help="每批文件处理完后的休息时间（帮助显卡散热）",
                        key="vlm_file_batch_rest"
                    )
                vlm_direct_max_concurrent_files = vlm_file_batch_size
                vlm_direct_max_concurrent = 1
                vlm_batch_rest = vlm_file_batch_rest
                vlm_direct_total_concurrent = vlm_file_batch_size
                st.caption(f"💡 批次模式：每批 {vlm_file_batch_size} 个文件，完成后休息 {vlm_file_batch_rest} 秒")

            st.markdown("---")
            st.markdown("**⚙️ 其他设置**")
            col1, col2 = st.columns(2)
            with col1:
                vlm_direct_timeout = st.number_input(
                    "超时时间（秒）",
                    min_value=30,
                    max_value=900,
                    value=600,
                    help="Gemini 等慢速 API 建议 600 秒以上",
                    key="vlm_direct_timeout"
                )
            with col2:
                vlm_direct_max_retries = st.number_input(
                    "最大重试次数",
                    min_value=0,
                    max_value=10,
                    value=3,
                    key="vlm_direct_max_retries"
                )

        # 📝 提示词模板配置
        with st.expander("📝 提示词模板配置", expanded=False):
            from aih_contexture.prompts import PromptBuilder

            # 模板选择
            template_options = {
                "通用模板（推荐）": "universal",
                "现代出版物": "modern_publication",
                "中文古籍": "ancient_chinese",
                "档案文献": "archive_document",
                "哥特体德文": "gothic_german",
                "手稿": "manuscript",
                "学术论文": "academic_paper",
                "混合内容": "mixed_content",
                "自定义": "custom"
            }

            selected_template = st.selectbox(
                "选择文档类型模板",
                list(template_options.keys()),
                index=0,
                help="根据文档类型选择合适的模板，包含针对性的识别指导",
                key="vlm_direct_template_select"
            )

            vlm_direct_prompt_template = template_options[selected_template]

            # API 参数预设
            st.markdown("**API 参数配置**")
            preset_options = {
                "高准确性（推荐）": "high_accuracy",
                "平衡": "balanced",
                "创意": "creative",
                "自定义": "custom"
            }

            selected_preset = st.selectbox(
                "API 参数预设",
                list(preset_options.keys()),
                index=0,
                help="高准确性：temperature=0.0, 减少幻觉，提高可复现性",
                key="vlm_direct_preset_select"
            )

            vlm_direct_api_preset = preset_options[selected_preset]

            # 自定义 API 参数
            if selected_preset == "自定义":
                col1, col2 = st.columns(2)
                with col1:
                    vlm_direct_temperature = st.slider(
                        "Temperature",
                        0.0, 1.0, 0.0, 0.1,
                        help="控制随机性，0.0=完全确定",
                        key="vlm_direct_temperature"
                    )
                    vlm_direct_top_p = st.slider(
                        "Top P",
                        0.0, 1.0, 0.1, 0.1,
                        help="核采样，限制候选词范围",
                        key="vlm_direct_top_p"
                    )
                with col2:
                    vlm_direct_top_k = st.number_input(
                        "Top K",
                        1, 100, 1,
                        help="Top-K采样（部分API支持）",
                        key="vlm_direct_top_k"
                    )
            else:
                vlm_direct_temperature = None
                vlm_direct_top_p = None
                vlm_direct_top_k = None

            # 自定义模板参数
            if selected_template == "自定义":
                st.markdown("**自定义模板参数**")
                col1, col2, col3 = st.columns(3)
                with col1:
                    text_direction = st.selectbox(
                        "文本方向",
                        ["horizontal", "vertical", "mixed"],
                        key="vlm_direct_text_direction"
                    )
                    has_footnotes = st.checkbox(
                        "包含脚注",
                        value=True,
                        key="vlm_direct_has_footnotes"
                    )
                    has_references = st.checkbox(
                        "包含引用",
                        value=True,
                        key="vlm_direct_has_references"
                    )

                with col2:
                    handwriting_mode = st.selectbox(
                        "手写识别模式",
                        ["none", "mixed", "pure"],
                        format_func=lambda x: {
                            "none": "不识别",
                            "mixed": "混合内容（标记手写）",
                            "pure": "纯手写（不标记）"
                        }[x],
                        help="none: 不特别处理; mixed: 印刷+手写混合，标记手写部分; pure: 全手写文档，不需要标记",
                        key="vlm_direct_handwriting_mode"
                    )
                    describe_images = st.checkbox(
                        "描述图片/印章",
                        value=False,
                        help="对印章、照片、图片等进行文字描述",
                        key="vlm_direct_describe_images"
                    )
                    language_mode = st.selectbox(
                        "语言模式",
                        ["monolingual", "multilingual"],
                        key="vlm_direct_language_mode"
                    )

                    # 使用17种语言预设
                    language_options = list(LANGUAGE_PRESETS.keys())
                    language_display = [LANGUAGE_DISPLAY_NAMES[code] for code in language_options]

                    # 创建显示名称到代码的映射
                    display_to_code = {display: code for code, display in zip(language_options, language_display)}

                    selected_language_display = st.selectbox(
                        "主要语言",
                        language_display,
                        index=0,  # 默认选择第一个（中文简体）
                        key="vlm_direct_primary_language"
                    )

                    # 获取对应的语言代码
                    primary_language = display_to_code[selected_language_display]

                with col3:
                    document_era = st.selectbox(
                        "文档年代",
                        ["ancient", "modern", "contemporary"],
                        key="vlm_direct_document_era"
                    )
                    has_page_numbers = st.checkbox(
                        "包含页码",
                        value=True,
                        key="vlm_direct_has_page_numbers"
                    )
                    has_headers_footers = st.checkbox(
                        "包含页眉页脚",
                        value=True,
                        key="vlm_direct_has_headers_footers"
                    )

                vlm_direct_prompt_params = {
                    "text_direction": text_direction,
                    "may_have_footnotes": has_footnotes,
                    "may_have_references": has_references,
                    "handwriting_mode": handwriting_mode,
                    "describe_images": describe_images,
                    "language_mode": language_mode,
                    "primary_language": primary_language,
                    "document_era": document_era,
                    "may_have_page_numbers": has_page_numbers,
                    "may_have_headers_footers": has_headers_footers,
                }
            else:
                # 非自定义模板时的常用选项
                st.markdown("**常用选项**")
                col1, col2, col3 = st.columns(3)
                with col1:
                    handwriting_mode = st.selectbox(
                        "手写识别",
                        ["none", "mixed"],
                        format_func=lambda x: {"none": "不标记", "mixed": "标记手写部分"}[x],
                        help="混合文档时开启，标记手写部分",
                        key="vlm_direct_handwriting_mode_simple"
                    )
                with col2:
                    describe_images = st.checkbox(
                        "详细描述图片",
                        value=False,
                        help="对印章、照片等进行详细描述（默认仅占位）",
                        key="vlm_direct_describe_images_simple"
                    )
                with col3:
                    has_page_numbers = st.checkbox(
                        "提取页码",
                        value=True,
                        help="提取页码为 <!-- page-header: X -->",
                        key="vlm_direct_has_page_numbers_simple"
                    )

                vlm_direct_prompt_params = {
                    "handwriting_mode": handwriting_mode,
                    "describe_images": describe_images,
                    "may_have_page_numbers": has_page_numbers,
                }

            # 旧的自定义提示词（向后兼容）
            st.markdown("**高级：自定义提示词（覆盖模板）**")
            vlm_direct_prompt = st.text_area(
                "自定义提示词（留空使用模板）",
                value="",
                height=150,
                help="如果填写，将覆盖模板系统，使用自定义提示词",
                key="vlm_direct_prompt"
            )

        # 📄 页码范围选择
        with st.expander("📄 页码范围", expanded=False):
            vlm_use_page_range = st.checkbox("指定页码范围", value=False, key="vlm_use_page_range")
            if vlm_use_page_range:
                col_start, col_end = st.columns(2)
                with col_start:
                    vlm_start_page = st.number_input("起始页", min_value=1, value=1, key="vlm_start_page")
                with col_end:
                    vlm_end_page = st.number_input("结束页", min_value=1, value=10, key="vlm_end_page")
            else:
                vlm_start_page = None
                vlm_end_page = None

        # 🔧 后处理配置
        with st.expander("🔧 后处理配置", expanded=False):
            st.markdown("**📝 文本后处理**")

            # 噪音过滤
            vlm_noise_removal = st.checkbox(
                "启用噪音过滤",
                value=True,
                help="移除水印、扫描标记等噪音",
                key="vlm_noise_removal"
            )

            if vlm_noise_removal:
                vlm_noise_patterns = st.text_area(
                    "自定义噪音模式（每行一个正则）",
                    value="Digitized by Google\nDigitized by the Internet Archive\nScanned by.*",
                    height=100,
                    help="支持正则表达式，每行一个模式",
                    key="vlm_noise_patterns"
                )
            else:
                vlm_noise_patterns = ""

            st.markdown("---")

            # 脚注修复
            vlm_footnote_fix = st.checkbox(
                "启用脚注修复",
                value=True,
                help="修复脚注格式（如重复括号、未标记脚注）",
                key="vlm_footnote_fix"
            )

            st.markdown("---")
            st.markdown("**🏷️ 页眉页脚过滤**")

            # 页眉过滤
            vlm_filter_page_header = st.checkbox(
                "过滤页眉语法标记",
                value=False,
                help="移除 <!-- page-header: --> 语法，保留内容",
                key="vlm_filter_page_header"
            )

            # 页脚过滤
            vlm_filter_page_footer = st.checkbox(
                "过滤页脚语法标记",
                value=False,
                help="移除 <!-- page-footer: --> 语法，保留内容",
                key="vlm_filter_page_footer"
            )

        # 映射统一配置到 VLM Direct 参数
        vlm_direct_enable_page_anchors = enable_page_anchors
        vlm_direct_page_anchor_position = page_anchor_position
        vlm_direct_extract_printed_pages = extract_printed_pages
        vlm_direct_custom_id_source = custom_id_source
        vlm_direct_custom_id_data = custom_id_data

        # 🆕 传递正则模式（独立于自定义编号）
        vlm_direct_printed_page_patterns = vlm_printed_page_patterns if 'vlm_printed_page_patterns' in locals() else None

    elif conversion_mode == "vlm_specialized":
        # ==================== VLM 特化模式配置（参数收集） ====================
        # VLM 特化模式的参数已经在前面的配置区域收集完毕
        # 这里只需要收集页码锚点相关的参数
        # VLM 特化模式使用自己的输出格式选择器 (ocr_output_formats)
        output_formats = ocr_output_formats if ocr_output_formats else ["markdown", "json", "html"]

    else:
        # ==================== 传统模式配置 ====================
        # 输出格式选择（仅 Pipeline 模式）
        st.markdown("**📄 输出格式**")
        output_formats = st.multiselect(
            "选择输出格式",
            FORMAT_CHOICES,
            default=FORMAT_CHOICES,
            help="选择需要生成的输出格式（markdown/json/html/chunks）",
            key="pipeline_output_formats"
        )
        st.divider()

        # ==================== 3. 版面识别后端选择 ====================
        st.subheader("📐 版面识别后端")
        layout_backend = st.selectbox(
            "选择版面识别引擎",
            options=["surya", "vlm", "yolo"],
            index=0,
            format_func=lambda x: {
                "surya": "🔮 Surya（内置深度学习，推荐）",
                "vlm": "🤖 VLM（视觉语言模型）",
                "yolo": "🎯 DocLayout-YOLO（实验性）",
            }.get(x, x),
            help="版面识别用于检测文档结构（文本块、图片、表格等）",
            key="layout_backend"
        )

        # 版面识别后端配置
        if layout_backend == "surya":
            st.success(LAYOUT_BACKEND_DESCRIPTIONS["surya"])

            # 🆕 基础处理器配置（只在 Pipeline 模式下显示）
            st.markdown("---")
            st.subheader("🔧 基础处理器配置")
            st.caption("配置 Pipeline 模式下的文本处理器（影响 Markdown 输出格式）")

            with st.expander("📋 文本处理器", expanded=False):
                markdown_noise_removal_enabled = st.checkbox(
                    "🧹 Markdown 噪音清理（推荐）",
                    value=True,
                    help="清理 OCR 识别出的 Markdown 特殊符号（如 #, >, *, - 等），防止与 Markdown 语法冲突。推荐启用！",
                    key="markdown_noise_removal_enabled_pipeline"
                )

                # 高级设置
                if markdown_noise_removal_enabled:
                    with st.expander("⚙️ 高级设置", expanded=False):
                        markdown_noise_cleaning_level = st.radio(
                            "清理级别",
                            options=["basic", "medium", "aggressive"],
                            index=0,
                            format_func=lambda x: {
                                "basic": "基础（只清理 # 标题符号）",
                                "medium": "中等（清理 #, >, -, * 等常见符号）",
                                "aggressive": "激进（清理所有 Markdown 符号）"
                            }.get(x, x),
                            help="选择清理强度。基础级别适合大多数文档。",
                            key="markdown_noise_cleaning_level_pipeline"
                        )

                        markdown_noise_custom_symbols = st.text_input(
                            "自定义符号列表（可选）",
                            value="",
                            placeholder="输入要过滤的符号，逗号分隔，如：#, >, -",
                            help="自定义要清理的符号，会覆盖清理级别设置。留空则使用清理级别。",
                        key="markdown_noise_custom_symbols_pipeline"
                        )

                        markdown_noise_line_start_only = st.checkbox(
                            "只清理行首符号（推荐）",
                            value=True,
                            help="只清理行首的符号，保护行中的合法内容。取消勾选会清理所有位置的符号。",
                            key="markdown_noise_line_start_only_pipeline"
                        )
                else:
                    # 如果未启用，设置默认值
                    markdown_noise_cleaning_level = "basic"
                    markdown_noise_custom_symbols = ""
                    markdown_noise_line_start_only = True

                line_merge_enabled = st.checkbox(
                    "行合并",
                    value=True,
                    help="将同一段落的多行文本合并。如果文档有特殊分行格式（如诗歌），建议禁用。",
                    key="line_merge_enabled_pipeline"
                )

                blockquote_enabled = st.checkbox(
                    "引用块检测",
                    value=True,
                    help="检测并标记缩进的引用块（使用 > 符号）。如果文档中有诗歌或特殊缩进格式，建议禁用。",
                    key="blockquote_enabled_pipeline"
                )

                code_enabled = st.checkbox(
                    "代码块检测",
                    value=True,
                    help="检测并标记代码块（使用 ``` 符号）。",
                    key="code_enabled_pipeline"
                )

            with st.expander("📚 结构处理器", expanded=False):
                section_header_enabled = st.checkbox(
                    "章节标题检测",
                    value=True,
                    help="检测并标记章节标题（使用 # 符号）。",
                    key="section_header_enabled_pipeline"
                )

                list_enabled = st.checkbox(
                    "列表检测",
                    value=True,
                    help="检测并标记列表项（使用 - 或数字）。",
                    key="list_enabled_pipeline"
                )

                footnote_enabled = st.checkbox(
                    "脚注检测",
                    value=True,
                    help="检测并标记脚注。",
                    key="footnote_enabled_pipeline"
                )

                reference_enabled = st.checkbox(
                    "参考文献检测",
                    value=True,
                    help="检测并标记参考文献。",
                    key="reference_enabled_pipeline"
                )

            with st.expander("📊 表格处理器", expanded=False):
                table_enabled = st.checkbox(
                    "表格处理",
                    value=True,
                    help="处理表格内容。",
                    key="table_enabled_pipeline"
                )

        elif layout_backend == "vlm":
            st.success(LAYOUT_BACKEND_DESCRIPTIONS["vlm"])
            with st.expander("VLM 版面识别配置", expanded=False):
                st.caption("📌 VLM Layout API 配置 (独立配置)")

                # API 配置
                vlm_layout_base_url = st.text_input(
                    "Base URL",
                    value=vlm_layout_base_url,
                    help="OpenAI 兼容 API 的基础 URL",
                    key="vlm_layout_base_url"
                )
                vlm_layout_model = st.text_input(
                    "模型名称",
                    value=vlm_layout_model,
                    help="例如: gpt-4o, gpt-4o-mini, qwen-vl-max",
                    key="vlm_layout_model"
                )

                # 多Key输入支持
                vlm_layout_api_key = st.text_area(
                    "API Keys (支持多个)",
                    value=vlm_layout_api_key,
                    height=100,
                    help="支持多个API Key，每行一个或逗号分隔。多Key可提高并发能力和容错性。",
                    key="vlm_layout_api_key"
                )

                # 显示Key数量和建议
                if vlm_layout_api_key:
                    keys = [k.strip() for k in vlm_layout_api_key.replace('\n', ',').split(',') if k.strip()]
                    key_count = len(keys)
                    if key_count > 1:
                        st.success(f"✅ 检测到 {key_count} 个API Key")
                        suggested_concurrent = key_count * 3
                        st.info(f"💡 建议并发数: {suggested_concurrent} (Key数量 × 3)")

                # 并发配置
                vlm_layout_max_concurrent = st.slider(
                    "最大并发数",
                    min_value=1,
                    max_value=50,  # 提高到50
                    value=int(vlm_layout_max_concurrent),
                    help="同时处理的页面数。多Key时可设置更高值。",
                    key="vlm_layout_max_concurrent"
                )

                col1, col2 = st.columns(2)
                with col1:
                    vlm_layout_image_format = st.selectbox(
                        "图像格式",
                        options=["jpeg", "png", "webp"],
                        index=["jpeg", "png", "webp"].index(vlm_layout_image_format),
                        key="vlm_layout_image_format"
                    )
                    vlm_layout_max_image_dimension = st.number_input(
                        "图像最大边长（像素）",
                        min_value=512,
                        max_value=4096,
                        value=int(vlm_layout_max_image_dimension),
                        step=128,
                        key="vlm_layout_max_image_dimension"
                    )
                with col2:
                    vlm_layout_jpeg_quality = st.number_input(
                        "JPEG 质量 (1-100)",
                        min_value=1,
                        max_value=100,
                        value=int(vlm_layout_jpeg_quality),
                        key="vlm_layout_jpeg_quality"
                    )
                    vlm_layout_timeout = st.number_input(
                        "超时时间（秒）",
                        min_value=30,
                        max_value=300,
                        value=int(vlm_layout_timeout),
                        key="vlm_layout_timeout"
                )

                # 提示词配置
                st.divider()
                st.caption("📝 版面识别提示词配置")

                prompt_config_mode = st.radio(
                    "提示词配置方式",
                    options=["使用预制模板", "自定义提示词"],
                    index=0,
                    horizontal=True,
                )

                if prompt_config_mode == "使用预制模板":
                    vlm_layout_prompt_template = st.selectbox(
                        "提示词模板",
                        options=[
                            "modern",
                            "chinese_ancient",
                            "gothic_german",
                            "archive",
                            "table_form",
                            "scientific",
                        ],
                        index=["modern", "chinese_ancient", "gothic_german", "archive", "table_form", "scientific"].index(vlm_layout_prompt_template),
                        format_func=lambda x: {
                            "modern": "现代出版物（默认）",
                            "chinese_ancient": "中文古籍（竖排、右到左）",
                            "gothic_german": "哥特体/德文古籍",
                            "archive": "档案文件（手写/印章）",
                            "table_form": "表格/表单密集",
                            "scientific": "科技论文（公式/代码/多栏）",
                        }.get(x, x),
                        help="选择适合您文档类型的提示词模板",
                    )
                    vlm_layout_prompt = ""  # 使用模板时清空自定义提示词
                else:
                    vlm_layout_prompt = st.text_area(
                        "自定义提示词",
                        value=vlm_layout_prompt if vlm_layout_prompt else "Analyze this document page and identify all layout regions...",
                        height=120,
                        help="直接指定提示词（优先级最高，会覆盖模板）",
                    )
                    vlm_layout_prompt_template = ""  # 自定义时清空模板选择

            # 🆕 VLM 模式下的处理器配置默认值
            markdown_noise_removal_enabled = True
            markdown_noise_cleaning_level = "basic"
            markdown_noise_custom_symbols = ""
            markdown_noise_line_start_only = True
            line_merge_enabled = True
            blockquote_enabled = True
            code_enabled = True
            section_header_enabled = True
            list_enabled = True
            footnote_enabled = True
            reference_enabled = True
            table_enabled = True

        elif layout_backend == "yolo":
            st.success(LAYOUT_BACKEND_DESCRIPTIONS["yolo"])

            st.warning("⚠️ 此功能为实验性支持，后续版本将正式集成本地推理能力")

            yolo_base_url = st.text_input(
                "YOLO 服务地址",
                value=yolo_base_url,
                help="DocLayout-YOLO 服务地址（当前需外部服务，后续支持本地推理）",
            )

            # YOLO 服务状态检查
            col_yolo_status, col_yolo_refresh = st.columns([3, 1])
            with col_yolo_refresh:
                _ = st.button("🔄", help="检查 YOLO 服务状态", key="yolo_refresh")

            try:
                import requests
                yolo_resp = requests.get(f"{yolo_base_url}/health", timeout=5)
                yolo_healthy = yolo_resp.status_code == 200
            except Exception:
                yolo_healthy = False

            with col_yolo_status:
                if yolo_healthy:
                    st.success("✅ YOLO 服务正常")
                else:
                    st.info("ℹ️ YOLO 服务未连接（可忽略，后续版本支持本地推理）")

            with st.expander("YOLO 高级设置", expanded=False):
                yolo_model = st.text_input("模型名称", value=yolo_model, key="yolo_model")
                yolo_confidence_threshold = st.slider(
                    "置信度阈值",
                    min_value=0.1,
                    max_value=0.9,
                    value=float(yolo_confidence_threshold),
                    step=0.05,
                    help="低于此阈值的检测结果将被过滤",
                )

            # 🆕 YOLO 模式下的处理器配置默认值
            markdown_noise_removal_enabled = True
            markdown_noise_cleaning_level = "basic"
            markdown_noise_custom_symbols = ""
            markdown_noise_line_start_only = True
            line_merge_enabled = True
            blockquote_enabled = True
            code_enabled = True
            section_header_enabled = True
            list_enabled = True
            footnote_enabled = True
            reference_enabled = True
            table_enabled = True

        st.divider()

        # ==================== 4. OCR 后端选择（核心） ====================
        st.subheader("🔍 OCR 后端")
        ocr_backend = st.selectbox(
            "选择 OCR 引擎",
            options=["none", "surya", "calamari", "vlm", "tesseract"],
            index=0,
            format_func=lambda x: {
                "none": "🚫 禁用 OCR（使用 PDF 内嵌文本，推荐现代出版物）",
                "surya": "🔮 Surya（内置深度学习 OCR）",
                "vlm": "🤖 VLM（视觉语言模型）",
                "calamari": "📜 Calamari（历史文档专用）",
                "tesseract": "🔤 Tesseract（多语言老牌方案）",
            }.get(x, x),
            help="现代出版物通常已有高质量文本层，可禁用OCR直接提取结构",
            key="ocr_backend"
        )

        # ==================== 3.1 后端说明与配置 ====================
        if ocr_backend == "none":
            st.info(
                "💡 **禁用 OCR 模式**\n\n"
                "将仅使用 PDF 内嵌文本层。适用于：\n"
                "- Google Books 等已有高质量 OCR 层的 PDF\n"
                "- 原生数字 PDF（非扫描件）"
            )
            force_ocr = False
            use_llm = False

        elif ocr_backend == "surya":
            st.success(OCR_BACKEND_DESCRIPTIONS["surya"])
            with st.expander("Surya 配置", expanded=False):
                ocr_batch_size = st.slider("OCR 批次大小", 1, 64, int(ocr_batch_size), help="每批处理的图像数量", key="ocr_batch_size")
                force_ocr = st.checkbox("强制 OCR", value=False, help="即使有文本层也强制进行 OCR", key="force_ocr")

            # LLM 增强配置移到独立区块

        # 在 "config_dict = build_config_dict(config_params)" 之后添加
        elif ocr_backend == "calamari":
            st.success(OCR_BACKEND_DESCRIPTIONS["calamari"])

            # 服务状态检查
            calamari_base_url = st.text_input("API 地址", value=calamari_base_url, help="Calamari Docker 服务地址", key="calamari_base_url")

            col_status, col_refresh = st.columns([3, 1])
            with col_refresh:
                _ = st.button("🔄", help="检查服务状态")

            is_healthy, cached_models = check_calamari_health(calamari_base_url)

            with col_status:
                if is_healthy:
                    st.success("✅ 服务正常")
                else:
                    st.error("❌ 服务不可用")
                    st.caption("请确保 Docker 容器已启动")

            # 获取可用模型
            available_models = get_calamari_models(calamari_base_url) if is_healthy else []
            if available_models:
                default_idx = available_models.index("gt4histocr") if "gt4histocr" in available_models else 0
                calamari_model = st.selectbox("OCR 模型", options=available_models, index=default_idx, key="calamari_model")
                if cached_models:
                    st.caption(f"已预热模型: {', '.join(cached_models)}")
            else:
                calamari_model = st.selectbox(
                    "OCR 模型",
                    options=["gt4histocr", "fraktur_19th_century", "antiqua_historical"],
                    index=0,
                    help="选择 Calamari 模型（服务离线时使用默认列表）",
                )

            with st.expander("⚙️ 高级设置", expanded=False):
                calamari_batch_size = st.number_input(
                    "批次大小",
                    min_value=10,
                    max_value=500,
                    value=int(calamari_batch_size),
                    help="每次发送的最大图片数",
                    key="calamari_batch_size_input"
                )
                calamari_timeout = st.number_input(
                    "超时时间（秒）",
                    min_value=30,
                    max_value=300,
                    value=int(calamari_timeout),
                    key="calamari_timeout_input"
                )

                st.markdown("---")
                st.markdown("---")
                st.markdown("**单栏页底(脚注)后置阈值**")
                calamari_footnote_y_frac = st.slider(
                    "页底区域阈值 (y_frac)",
                    min_value=0.60,
                    max_value=0.95,
                    value=0.83,
                    step=0.01,
                    help="将 y_center >= y_frac * page_height 的行视为页底区域(脚注/出处/页码)，在输出中后置以减少混入正文",
                    key="calamari_footnote_y_frac_slider"
                )
                st.markdown("**顺序保证设置**")

                calamari_sequential_mode = st.checkbox(
                    "使用串行模式（最稳，但慢）",
                    value=bool(calamari_sequential_mode),
                    help="逐张发送图片，天然保证 line->text 一一对应",
                    key="calamari_sequential_mode_checkbox"
                )

                calamari_require_ordering_info = st.checkbox(
                    "批量模式要求可重排信息（推荐）",
                    value=True,
                    help="要求 /ocr/batch 返回 filenames/results 且 filename 可解析出 image_000123 形式的索引；否则自动降级串行重试该批次",
                    key="calamari_require_ordering_info_checkbox"
                )

                calamari_fallback_to_sequential_on_ordering_failure = st.checkbox(
                    "批量失败自动降级串行重试（推荐）",
                    value=True,
                    help="当批量响应缺少/无法解析索引时，只对该 batch 串行重试，避免生成错位 Markdown",
                    key="calamari_fallback_checkbox"
                )

                if not calamari_sequential_mode:
                    calamari_trust_batch_order = st.checkbox(
                        "信任批量返回顺序（不推荐）",
                        value=False,
                        help="仅当服务端保证严格按请求顺序返回且你已验证无乱序时才开启",
                        key="calamari_trust_batch_order_checkbox"
                    )
                else:
                    calamari_trust_batch_order = False
                    # 串行模式下这两个开关没意义，关闭以减少误解
                    calamari_require_ordering_info = False
                    calamari_fallback_to_sequential_on_ordering_failure = False

            # Calamari 模式下，force_ocr 通常保持 False（Marker 内部仍会走 OCR 流程）
            force_ocr = False
            use_llm = False
            ocr_batch_size = 32  # 该值只影响 surya/vlm 的 batch size

        elif ocr_backend == "vlm":
            st.success(OCR_BACKEND_DESCRIPTIONS["vlm"])

            st.markdown("**API 配置**")
            openai_base_url = st.text_input(
                "Base URL",
                value=openai_base_url,
                help="OpenAI 兼容 API 地址（如 LM Studio）",
                key="vlm_ocr_base_url"
            )
            openai_model = st.text_input("模型名称", value=openai_model, key="vlm_ocr_model")

            # 多Key输入支持
            openai_api_key = st.text_area(
                "API Keys (支持多个)",
                value=openai_api_key,
                height=100,
                help="支持多个API Key，每行一个或逗号分隔。多Key可提高并发能力和容错性。",
                key="vlm_ocr_api_key"
            )

            # 显示Key数量和建议
            if openai_api_key:
                # 解析Key数量
                keys = [k.strip() for k in openai_api_key.replace('\n', ',').split(',') if k.strip()]
                key_count = len(keys)
                if key_count > 1:
                    st.success(f"✅ 检测到 {key_count} 个API Key")
                    suggested_concurrent = key_count * 3
                    st.info(f"💡 建议并发数: {suggested_concurrent} (Key数量 × 3)")

            # 并发配置
            openai_max_concurrent = st.slider(
                "最大并发数",
                min_value=1,
                max_value=50,  # 提高到50
                value=3,
                help="同时处理的OCR请求数。多Key时可设置更高值。",
                key="vlm_ocr_max_concurrent"
            )

            openai_image_format = st.selectbox(
                "图像格式",
                options=["jpeg", "png", "webp"],
                index=["jpeg", "png", "webp"].index(openai_image_format) if openai_image_format in ["jpeg", "png", "webp"] else 0,
                help="发送给 VLM 的图像格式",
                key="vlm_ocr_image_format"
            )

            st.markdown("---")
            st.markdown("**OCR 模式**")
            vlm_mode = st.radio(
                "处理模式",
                options=["tile", "merge", "full_page"],
                index=0,
                format_func=lambda x: {
                    "tile": "📦 逐块（推荐，按 Marker 原逻辑）",
                    "merge": "🔗 区域合并（相邻块合并处理）",
                    "full_page": "📄 整页（一次处理整页）",
                }.get(x, x),
                horizontal=False,
            )

            # 智能提示：整页模式的最佳配置
            if vlm_mode == "full_page":
                if layout_backend == "surya":
                    st.success(
                        "✅ **推荐配置！**\n\n"
                        "您已启用「Surya Layout + VLM 整页模式」\n\n"
                        "这是最佳方案：\n"
                        "- Surya 快速检测版面结构（~10秒）\n"
                        "- VLM 处理整页内容（利用大模型能力）\n"
                        "- 结合两者优势，获得最佳效果\n\n"
                        "适合：复杂文档、手写、古籍、多语言"
                    )
                elif layout_backend == "none":
                    st.warning(
                        "⚠️ **配置说明**\n\n"
                        "「禁用版面识别 + VLM 整页」暂不可用。\n\n"
                        "Marker 需要 layout 结构来组织 OCR 结果。\n\n"
                        "**建议**：将版面识别后端改为 **Surya**"
                    )
                else:
                    st.info(
                        "💡 **提示**\n\n"
                        "您选择了「整页模式」。\n\n"
                        "推荐配置：\n"
                        "- 版面识别后端：**Surya**（快速、稳定）\n"
                        "- OCR 后端：**VLM**\n"
                        "- VLM 模式：**整页**\n\n"
                        "这样可以获得最佳效果。"
                    )

            vlm_response_mode = st.radio(
                "返回格式",
                options=["text", "json"],
                index=0,
                horizontal=True,
                help="text 更稳定，json 可解析结构",
            )

            with st.expander("🎛️ 高级参数", expanded=False):
                vlm_prompt = st.text_area("自定义 Prompt", value=vlm_prompt, height=100, key="vlm_prompt")
                openai_use_stop = st.checkbox(
                    "启用 stop 参数",
                    value=bool(openai_use_stop),
                    help="LM Studio 下可能导致输出为空，默认关闭",
                    key="openai_use_stop"
                )

                if vlm_mode == "merge":
                    st.markdown("**区域合并参数**")
                    vlm_merge_y_threshold = st.slider("Y 合并阈值", 30, 200, int(vlm_merge_y_threshold))
                    vlm_merge_max_blocks = st.slider("单组最大块数", 3, 30, int(vlm_merge_max_blocks))
                else:
                    vlm_merge_y_threshold = 80
                    vlm_merge_max_blocks = 15

                if vlm_mode == "full_page":
                    vlm_full_page_max_tokens = st.number_input(
                        "整页 max_tokens",
                        min_value=512,
                        max_value=8192,
                        value=int(vlm_full_page_max_tokens),
                    )
                else:
                    vlm_full_page_max_tokens = 2048

                force_ocr = st.checkbox("强制 OCR", value=False, key="force_ocr_vlm")
                use_llm = False  # VLM 模式下不启用额外 LLM
                ocr_batch_size = 32

        elif ocr_backend == "tesseract":
            st.success(OCR_BACKEND_DESCRIPTIONS["tesseract"])
            st.warning("⚠️ Tesseract OCR 将在后续版本正式集成，当前为预留接口")

            with st.expander("Tesseract 配置（预留）", expanded=False):
                tesseract_lang = st.text_input(
                    "语言代码",
                    value="chi_sim+eng",
                    help="Tesseract 语言代码，多语言用 + 连接，如: chi_sim+eng, deu+fra",
                    key="tesseract_lang"
                )
                tesseract_psm = st.selectbox(
                    "页面分割模式 (PSM)",
                    options=[3, 4, 6, 11, 12],
                    index=0,
                    format_func=lambda x: {
                        3: "3 - 全自动页面分割（默认）",
                        4: "4 - 假设单列可变大小文本",
                        6: "6 - 假设单个统一文本块",
                        11: "11 - 稀疏文本，无特定顺序",
                        12: "12 - 带 OSD 的稀疏文本",
                    }.get(x, str(x)),
                    help="页面分割模式影响 Tesseract 如何分析页面布局",
                    key="tesseract_psm"
                )
                tesseract_oem = st.selectbox(
                    "OCR 引擎模式 (OEM)",
                    options=[1, 2, 3],
                    index=0,
                    format_func=lambda x: {
                        1: "1 - LSTM 神经网络（推荐）",
                        2: "2 - 传统引擎 + LSTM",
                        3: "3 - 默认（基于可用模型）",
                    }.get(x, str(x)),
                    help="OCR 引擎模式，LSTM 模式通常效果更好",
                    key="tesseract_oem"
                )

            force_ocr = False
            use_llm = False
            ocr_batch_size = 32

        # ==================== OCR 后端配置结束 ====================
        st.divider()

        # ==================== 5. LLM 增强配置 ====================
        st.subheader("🧠 LLM 增强")
        use_llm = st.checkbox("启用 LLM 增强", value=False, help="使用大语言模型优化文档结构和内容", key="use_llm")

        if use_llm:
            with st.expander("LLM 配置", expanded=True):
                # API 提供商选择
                llm_provider = st.selectbox(
                    "API 提供商",
                    options=["ollama", "gemini", "azure", "claude"],
                    index=0,
                    format_func=lambda x: {
                        "ollama": "OpenAI 兼容 API（推荐）",
                        "gemini": "Google Gemini",
                        "azure": "Azure OpenAI",
                        "claude": "Anthropic Claude"
                    }.get(x, x),
                    help="选择 LLM API 提供商。OpenAI 兼容可用于本地模型或远程 API。",
                    key="llm_provider"
                )

                # Gemini 配置
                if llm_provider == "gemini":
                    st.caption("📌 Google Gemini 配置")

                    # 多Key输入支持
                    llm_api_key = st.text_area(
                        "Gemini API Keys (支持多个)",
                        value=os.environ.get("GEMINI_API_KEY", ""),
                        height=100,
                        help="支持多个API Key，每行一个或逗号分隔。多Key可提高并发能力和容错性。",
                        key="llm_gemini_api_key"
                    )

                    # 🆕 Gemini 中转接口支持
                    llm_base_url = st.text_input(
                        "中转接口 URL（可选）",
                        value=os.environ.get("GEMINI_BASE_URL", ""),
                        help="留空使用官方API。填写中转接口URL（需支持Gemini官方格式）",
                        key="llm_gemini_base_url"
                    )

                    # 显示Key数量和建议
                    if llm_api_key:
                        keys = [k.strip() for k in llm_api_key.replace('\n', ',').split(',') if k.strip()]
                        key_count = len(keys)
                        if key_count > 1:
                                st.success(f"✅ 检测到 {key_count} 个API Key")
                                suggested_concurrent = key_count * 3
                                st.info(f"💡 建议并发数: {suggested_concurrent} (Key数量 × 3)")

                        llm_model = st.text_input(
                            "模型名称",
                            value=os.environ.get("GEMINI_MODEL", "gemini-2.0-flash-exp"),
                            help="例如: gemini-2.0-flash-exp, gemini-1.5-pro",
                            key="llm_gemini_model"
                        )
                        llm_max_concurrency = st.number_input(
                            "最大并发数",
                            min_value=1,
                            max_value=50,  # 提高到50
                            value=3,
                            help="同时处理的LLM请求数。多Key时可设置更高值。",
                            key="llm_gemini_max_concurrency"
                        )
                        llm_base_url = ""
                        llm_timeout = 120

                # Ollama 配置（支持 OpenAI 兼容 API）
                elif llm_provider == "ollama":
                    st.caption("📌 Ollama 配置")
                    st.info("💡 Ollama 支持本地模型和 OpenAI 兼容的远程 API（如 LM Studio、vLLM、OpenAI 等）")

                    llm_base_url = st.text_input(
                        "API URL",
                        value=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
                        help="Ollama 服务地址或 OpenAI 兼容 API 地址（如 http://localhost:1234/v1）",
                        key="llm_ollama_base_url"
                    )
                    llm_model = st.text_input(
                        "模型名称",
                        value=os.environ.get("OLLAMA_MODEL", "llama3.2-vision"),
                        help="本地模型: llama3.2-vision, qwen2-vl | OpenAI API: gpt-4o, gpt-4o-mini",
                        key="llm_ollama_model"
                    )
                    llm_api_key = st.text_input(
                        "API Key（可选）",
                        value=os.environ.get("OLLAMA_API_KEY", ""),
                        type="password",
                        help="本地 Ollama 不需要；远程 API 需要填写",
                        key="llm_ollama_api_key"
                    )
                    if not llm_api_key:
                        llm_api_key = "ollama"  # 默认值

                    llm_max_concurrency = st.number_input(
                        "最大并发数",
                        min_value=1,
                        max_value=20,
                        value=3,
                        key="llm_ollama_max_concurrency"
                    )
                    llm_timeout = 120

                # Azure OpenAI 配置
                elif llm_provider == "azure":
                    st.caption("📌 Azure OpenAI 配置")
                    llm_base_url = st.text_input(
                        "Azure Endpoint",
                        value=os.environ.get("AZURE_OPENAI_ENDPOINT", ""),
                        help="Azure OpenAI 端点 URL",
                        key="llm_azure_endpoint"
                    )
                    llm_api_key = st.text_input(
                        "API Key",
                        value=os.environ.get("AZURE_OPENAI_API_KEY", ""),
                        type="password",
                        key="llm_azure_api_key"
                    )
                    llm_model = st.text_input(
                        "Deployment Name",
                        value=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
                        help="Azure 部署名称",
                        key="llm_azure_deployment"
                    )
                    llm_max_concurrency = 3
                    llm_timeout = 120

                # Claude 配置
                elif llm_provider == "claude":
                    st.caption("📌 Anthropic Claude 配置")
                    llm_api_key = st.text_input(
                        "Claude API Key",
                        value=os.environ.get("CLAUDE_API_KEY", ""),
                        type="password",
                        key="llm_claude_api_key"
                    )
                    llm_model = st.selectbox(
                        "模型",
                        options=["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-haiku-20240307"],
                        index=0,
                        key="llm_claude_model"
                    )
                    llm_max_concurrency = 3
                    llm_base_url = ""
                    llm_timeout = 120

                st.divider()

                # LLM 处理模块配置
                st.caption("🔧 LLM 处理模块")
                st.markdown("选择要启用的 LLM 增强功能:")

                col1, col2 = st.columns(2)

                with col1:
                    llm_table_enabled = st.checkbox(
                        "表格优化",
                        value=True,
                        help="修正表格结构,确保列对齐正确"
                    )
                    llm_equation_enabled = st.checkbox(
                        "公式识别",
                        value=True,
                        help="识别和转换数学公式"
                    )
                    llm_image_description_enabled = st.checkbox(
                        "图片描述",
                        value=False,
                        help="为图片生成描述性文本"
                    )
                    llm_handwriting_enabled = st.checkbox(
                        "手写识别",
                        value=False,
                        help="识别手写内容"
                    )
                    llm_noise_removal_enabled = st.checkbox(
                        "智能降噪",
                        value=False,
                        help="识别并过滤无关符号和语言（与主要内容相差甚远的噪音）"
                    )

                with col2:
                    llm_page_correction_enabled = st.checkbox(
                        "页面校正",
                        value=False,
                        help="修正页面结构和阅读顺序"
                    )
                    llm_section_header_enabled = st.checkbox(
                        "章节识别",
                        value=False,
                        help="识别和标记章节标题"
                    )
                    llm_form_enabled = st.checkbox(
                        "表单识别",
                        value=False,
                        help="识别和提取表单内容"
                    )
                    llm_complex_region_enabled = st.checkbox(
                        "复杂区域处理",
                        value=False,
                        help="处理复杂布局区域"
                    )
                    llm_printed_page_correction_enabled = st.checkbox(
                        "印刷页码修正",
                        value=False,
                        help="启发式识别和修正印刷页码（跨块分析规律性页码）"
                    )
                    llm_heuristic_layout_enabled = st.checkbox(
                        "启发式版面增强",
                        value=False,
                        help="使用启发式规则优化版面检测结果"
                    )

                # 页面校正自定义提示词
                if llm_page_correction_enabled:
                    st.divider()
                    st.caption("📝 页面校正提示词（可选）")
                    llm_page_correction_prompt = st.text_area(
                        "自定义提示词",
                        value="",
                        height=100,
                        placeholder="留空使用默认提示词。可以自定义指导 LLM 如何修正页面结构...",
                        help="自定义页面校正的提示词,留空使用默认"
                    )
                else:
                    llm_page_correction_prompt = ""

            # 映射统一配置到 Pipeline 参数（LLM 启用时）
            printed_page_enabled = extract_printed_pages
        else:
            # 默认值（LLM 未启用时）
            llm_provider = "gemini"
            llm_base_url = ""
            llm_model = ""
            llm_api_key = ""
            llm_max_concurrency = 3
            llm_timeout = 120
            llm_table_enabled = False
            llm_equation_enabled = False
            llm_image_description_enabled = False
            llm_handwriting_enabled = False
            llm_page_correction_enabled = False
            llm_section_header_enabled = False
            llm_form_enabled = False
            llm_complex_region_enabled = False
            llm_noise_removal_enabled = False
            llm_printed_page_correction_enabled = False
            llm_page_correction_prompt = ""

            st.divider()

            # 映射统一配置到 Pipeline 参数
            printed_page_enabled = extract_printed_pages
            # printed_page_zones, printed_page_format 等已在统一配置中设置

            st.divider()

            # ==================== 6. 高级选项 ====================
            with st.expander("⚙️ 高级选项", expanded=False):
                st.markdown("**⚡ 处理设置**")

                # 批处理模式选择
                batch_mode = st.radio(
                    "处理模式",
                    options=["自动", "单批处理", "分批处理"],
                    index=0,
                    horizontal=True,
                    help="自动：根据页数自动决定；单批：一次性处理所有页面；分批：分批处理大文档"
                )

                # 根据选择显示相关设置
                if batch_mode == "分批处理" or batch_mode == "自动":
                    st.info("💡 分批处理说明：分批是为了本地部署后端时降低性能压力，批次间冷却是为了改善散热")

                    col_a, col_b = st.columns(2)
                    with col_a:
                        batch_threshold = st.number_input(
                            "分批阈值（页）",
                            min_value=10,
                            max_value=2000,
                            value=50,
                            help="超过此页数自动分批（仅自动模式生效）",
                        )
                        pages_per_batch = st.number_input(
                            "每批页数",
                            min_value=5,
                            max_value=1000,
                            value=25,
                            help="每批处理的页面数量"
                        )
                    with col_b:
                        cooling_seconds = st.number_input(
                            "批次间冷却（秒）",
                            min_value=0,
                            max_value=30,
                            value=3,
                            help="每批处理后等待时间，用于显存回收和散热",
                        )
                else:
                    # 单批处理模式，使用默认值
                    batch_threshold = 50
                    pages_per_batch = 25
                    cooling_seconds = 0

                # 映射到原有的 process_mode 变量
                if batch_mode == "自动":
                    process_mode = "自动"
                elif batch_mode == "单批处理":
                    process_mode = "强制单批"
                else:
                    process_mode = "强制分批"

                st.markdown("---")

                # 页码范围选择
                use_page_range = st.checkbox("指定页码范围", value=False, key="use_page_range")
                if use_page_range:
                    col_start, col_end = st.columns(2)
                    with col_start:
                        start_page_1based = st.number_input("起始页", min_value=1, value=1, key="start_page")
                    with col_end:
                        end_page_1based = st.number_input("结束页", min_value=1, value=10, key="end_page")
                else:
                    start_page_1based = None
                    end_page_1based = None

                st.markdown("---")
                st.markdown("**🔧 其他设置**")

                use_fp16 = st.checkbox(
                    "使用 FP16",
                    value=os.environ.get("USE_FP16", "false").lower() == "true",
                    help="半精度推理，减少显存占用",
                )

            st.divider()

    # ==================== 6. 操作按钮 ====================
    if st.button("🔄 恢复历史记录", help="从输出目录恢复之前的处理记录"):
        restored = scan_outputs_for_restore(st.session_state.output_dir)
        st.session_state.processed_files = {
            k: [{"format": "file", "path": p, "name": os.path.basename(p)} for p in v]
            for k, v in restored.items()
        }
        st.success(f"已恢复 {len(restored)} 组文件")

    start_button = st.button("🚀 开始转换", type="primary", use_container_width=True)

# ==================== 主区域：历史下载 ====================
if st.session_state.last_zip_path and os.path.exists(st.session_state.last_zip_path):
    st.subheader("⬇️ 上次任务下载")
    with open(st.session_state.last_zip_path, "rb") as f:
        st.download_button(
            "📦 下载所有结果（ZIP）",
            data=f.read(),
            file_name=st.session_state.last_zip_name or os.path.basename(st.session_state.last_zip_path),
            mime="application/zip",
            key="download_all_persist",
        )

if st.session_state.processed_files:
    with st.expander("📌 已处理文件记录", expanded=False):
        for group, items in st.session_state.processed_files.items():
            st.write(f"**{group}**")
            for it in items:
                st.caption(f"  └─ {it.get('name')}")


# ==================== 主处理逻辑 ====================
if uploaded_files and len(uploaded_files) > 0:
    st.write(f"### 📋 待处理文件：{len(uploaded_files)} 个")

    if start_button:
        if not output_formats:
            st.error("请至少选择一种输出格式。")
            st.stop()

        # ==================== VLM 泛化模式处理 ====================
        if conversion_mode == "vlm_generalized":
            # 检查必要配置
            if not vlm_direct_api_key:
                st.error("❌ 请配置 API Key")
                st.stop()

            from aih_contexture.converters.vlm_direct_async import VlmDirectAsyncConverter

            # 构建配置
            vlm_direct_config = {
                "vlm_api_provider": vlm_api_provider,  # 🆕 API 提供商
                "vlm_direct_base_url": vlm_direct_base_url,
                "vlm_direct_model": vlm_direct_model,
                "vlm_direct_api_key": vlm_direct_api_key,
                "vlm_direct_max_concurrent": vlm_direct_max_concurrent,
                "vlm_direct_image_format": vlm_direct_image_format,
                "vlm_direct_max_image_dimension": vlm_direct_max_image_dimension,
                "vlm_direct_jpeg_quality": vlm_direct_jpeg_quality,
                "vlm_direct_timeout": vlm_direct_timeout,
                "vlm_direct_max_tokens": 0,  # 不限制，让模型自然停止
                "vlm_direct_max_retries": vlm_direct_max_retries,
                # 页码锚点配置
                "vlm_direct_enable_page_anchors": vlm_direct_enable_page_anchors,
                "vlm_direct_page_anchor_wrapper": "{{{}}}",  # 标准格式（固定 {n}）
                "vlm_direct_page_anchor_position": vlm_direct_page_anchor_position,
                "vlm_direct_extract_printed_pages": vlm_direct_extract_printed_pages,
                "vlm_direct_printed_page_patterns": vlm_direct_printed_page_patterns,  # 🆕 正则模式
                "vlm_direct_custom_id_source": vlm_direct_custom_id_source,
                "vlm_direct_custom_id_data": vlm_direct_custom_id_data,
                # 提示词模板配置（新增）
                "vlm_direct_prompt_template": vlm_direct_prompt_template,
                "vlm_direct_api_preset": vlm_direct_api_preset,
            }

            # 添加自定义模板参数
            if vlm_direct_prompt_params:
                vlm_direct_config["vlm_direct_prompt_params"] = vlm_direct_prompt_params

            # 添加自定义 API 参数
            if vlm_direct_temperature is not None:
                vlm_direct_config["vlm_direct_temperature"] = vlm_direct_temperature
            if vlm_direct_top_p is not None:
                vlm_direct_config["vlm_direct_top_p"] = vlm_direct_top_p
            if vlm_direct_top_k is not None:
                vlm_direct_config["vlm_direct_top_k"] = vlm_direct_top_k

            # 只在用户实际填写了自定义提示词时才传递（避免覆盖模板）
            if vlm_direct_prompt and vlm_direct_prompt.strip():
                vlm_direct_config["vlm_direct_prompt"] = vlm_direct_prompt

            # 页码范围
            if vlm_use_page_range and vlm_start_page and vlm_end_page:
                start0 = max(0, int(vlm_start_page) - 1)
                end0 = int(vlm_end_page) - 1
                vlm_direct_config["page_range"] = f"{start0}-{end0}"

            # 创建 converter
            converter = VlmDirectAsyncConverter(vlm_direct_config)

            all_output_paths_for_zip = []
            start_time = time.time()

            # 多文件并发处理
            import asyncio

            # 创建全局信号量
            global_semaphore = asyncio.Semaphore(vlm_direct_total_concurrent)
            file_semaphore = asyncio.Semaphore(vlm_direct_max_concurrent_files)

            # 🆕 预先读取所有文件内容到内存（避免 Streamlit 长时间运行后清理文件缓存）
            # 这是解决批处理后期失败的关键修复
            if upload_mode == "上传文件":
                st.write("📥 预读取文件内容到内存...")
                file_objects = []
                for file_obj in uploaded_files:
                    # 立即读取文件内容到内存，避免后续被 Streamlit 清理
                    file_content = file_obj.getvalue()
                    file_objects.append((file_content, file_obj.name))
                st.write(f"✅ 已预读取 {len(file_objects)} 个文件")
            else:
                file_objects = [(file_obj, os.path.basename(file_obj)) for file_obj in uploaded_files]

            st.info(f"🚀 使用 VLM Direct 模式（{'串行文件' if vlm_concurrency_mode == 'serial_file' else '单页批次'}：{vlm_direct_max_concurrent_files}文件 × {vlm_direct_max_concurrent}页并发）")
            st.write(f"📋 待处理文件：{len(file_objects)} 个")

            # 定义文件可访问性检查函数
            def check_file_accessible(file_path):
                """检查文件是否可以被读取（未被其他程序锁定）"""
                try:
                    with open(file_path, 'rb') as f:
                        f.read(1024)  # 尝试读取前1KB
                    return True
                except (PermissionError, IOError):
                    return False

            # 定义单文件处理函数（异步版本，避免 pypdfium2 多线程问题）
            async def process_single_file_async(file_path, file_name, file_idx):
                try:
                    # 先检查文件是否可访问
                    if not check_file_accessible(file_path):
                        return (file_idx, file_name, None, "文件被锁定（可能被PDF阅读器打开）")

                    markdown = await converter.convert_async(file_path, global_semaphore)
                    return (file_idx, file_name, markdown, None)
                except Exception as e:
                    return (file_idx, file_name, None, str(e))

            # 使用严格批次模式处理（避免 LM Studio promote 问题）
            # 🆕 使用 asyncio 而不是 ThreadPoolExecutor（避免 pypdfium2 多线程问题）
            import time as time_module
            batch_size = vlm_direct_max_concurrent_files
            total_batches = (len(file_objects) + batch_size - 1) // batch_size
            success_count = [0]  # 使用列表以便在嵌套函数中修改

            async def process_all_vlm_batches():
                for batch_start in range(0, len(file_objects), batch_size):
                    batch_objects = file_objects[batch_start:batch_start + batch_size]
                    batch_num = batch_start // batch_size + 1
                    st.write(f"📦 处理批次 {batch_num}/{total_batches}（{len(batch_objects)} 个文件）")

                    # 为当前批次创建临时文件
                    batch_file_list = []
                    batch_temp_files = []
                    for file_content, file_name in batch_objects:
                        if upload_mode == "上传文件":
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                                tmp.write(file_content)
                                tmp.flush()
                                os.fsync(tmp.fileno())
                                batch_file_list.append((tmp.name, file_name))
                                batch_temp_files.append(tmp.name)
                        else:
                            batch_file_list.append((file_content, file_name))

                    # 使用 asyncio.gather 并行处理（单线程异步，避免 pypdfium2 问题）
                    tasks = [
                        process_single_file_async(fp, fn, batch_start + idx)
                        for idx, (fp, fn) in enumerate(batch_file_list)
                    ]
                    batch_results = await asyncio.gather(*tasks)

                    # 立即清理当前批次的临时文件
                    safe_cleanup_temp_files(batch_temp_files)

                    # 强制释放资源
                    gc.collect()

                    # 立即保存当前批次的结果
                    batch_saved = 0
                    for file_idx, file_name, markdown, error in batch_results:
                        if error:
                            st.error(f"❌ {file_name} 转换失败：{error}")
                            continue

                        success_count[0] += 1
                        batch_saved += 1
                        fname_base = get_output_basename(
                            file_name,
                            vlm_start_page if vlm_use_page_range else None,
                            vlm_end_page if vlm_use_page_range else None,
                        )
                        output_files = []

                        # 1. Markdown 输出
                        if "markdown" in output_formats:
                            md_path = os.path.join(st.session_state.output_dir, f"{fname_base}.md")
                            with open(md_path, "w", encoding="utf-8") as f:
                                f.write(markdown)
                            output_files.append(md_path)

                        # 2. HTML 输出
                        if "html" in output_formats:
                            try:
                                import markdown as md_lib
                                html_content = md_lib.markdown(markdown, extensions=['tables', 'fenced_code'])
                            except ImportError:
                                html_content = f"<pre>{markdown}</pre>"

                            html_full = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{file_name}</title>
    <style>
        body {{ font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
        pre {{ background: #f5f5f5; padding: 10px; overflow-x: auto; }}
    </style>
</head>
<body>
{html_content}
</body>
</html>"""
                            html_path = os.path.join(st.session_state.output_dir, f"{fname_base}.html")
                            with open(html_path, "w", encoding="utf-8") as f:
                                f.write(html_full)
                            output_files.append(html_path)

                        all_output_paths_for_zip.extend(output_files)
                        st.write(f"  💾 {file_name} 已保存")

                    st.write(f"✅ 批次 {batch_num} 完成，已保存 {batch_saved} 个文件")

                    # 批次间休息
                    if batch_num < total_batches and vlm_batch_rest > 0:
                        st.write(f"💤 休息 {vlm_batch_rest} 秒...")
                        await asyncio.sleep(vlm_batch_rest)

            # 运行异步批处理
            asyncio.run(process_all_vlm_batches())

            # 创建 ZIP
            if all_output_paths_for_zip:
                elapsed_time = time.time() - start_time
                st.success(f"🎉 所有文件处理完成！总耗时：{elapsed_time:.1f} 秒")

                zip_path = os.path.join(st.session_state.output_dir, "vlm_direct_results.zip")
                with zipfile.ZipFile(zip_path, "w") as zf:
                    for p in all_output_paths_for_zip:
                        zf.write(p, os.path.basename(p))

                st.session_state.last_zip_path = zip_path
                st.session_state.last_zip_name = "vlm_direct_results.zip"

                with open(zip_path, "rb") as f:
                    st.download_button(
                        "📦 下载所有结果（ZIP）",
                        data=f.read(),
                        file_name="vlm_direct_results.zip",
                        mime="application/zip",
                        key="download_vlm_direct_results"
                    )

            st.stop()

        # ==================== VLM 特化模式处理 ====================
        if conversion_mode == "vlm_specialized":
            # 检查必要配置
            if not ocr_endpoint:
                st.error("❌ 请配置 OCR API Endpoint")
                st.stop()

            from aih_contexture.converters.ocr_direct_async import OcrDirectAsyncConverter

            # 构建配置
            ocr_direct_config = {
                "ocr_endpoint": ocr_endpoint,
                "ocr_model": ocr_model,
                "ocr_api_key": ocr_api_key if ocr_api_key else None,
                "ocr_output_format": "html",  # Chandra always outputs HTML with data-bbox and data-label
                "ocr_concurrency": ocr_concurrency,
                "ocr_batch_size": ocr_batch_size,
                "ocr_batch_rest": ocr_batch_rest,
                "ocr_max_retries": ocr_max_retries,
                "ocr_resize_max": ocr_resize_max,
                "ocr_image_format": ocr_image_format,
                "ocr_image_quality": ocr_image_quality,
                "ocr_timeout": ocr_timeout,
                "ocr_max_tokens": ocr_max_tokens,
                "ocr_temperature": 0.1,
                # 页码锚点配置（使用统一配置）
                "ocr_page_anchor_enabled": enable_page_anchors,
                "ocr_page_anchor_wrapper": "{{{}}}",  # 固定格式 {n}
                "ocr_page_anchor_position": page_anchor_position if 'page_anchor_position' in locals() else "before",
                "ocr_extract_printed_pages": extract_printed_pages if 'extract_printed_pages' in locals() else True,
                "ocr_printed_page_patterns": vlm_printed_page_patterns if 'vlm_printed_page_patterns' in locals() else None,
                "ocr_custom_id_source": custom_id_source if 'custom_id_source' in locals() else "none",
                "ocr_custom_id_data": custom_id_data if 'custom_id_data' in locals() else None,
                # 🆕 后处理配置
                "ocr_noise_removal": ocr_noise_removal if 'ocr_noise_removal' in locals() else True,
                "ocr_noise_patterns": ocr_noise_patterns if 'ocr_noise_patterns' in locals() else "",
                "ocr_footnote_fix": ocr_footnote_fix if 'ocr_footnote_fix' in locals() else True,
                "ocr_filter_page_header": ocr_filter_page_header if 'ocr_filter_page_header' in locals() else False,
                "ocr_filter_page_footer": ocr_filter_page_footer if 'ocr_filter_page_footer' in locals() else False,
            }

            # 页码范围
            if ocr_use_page_range and ocr_start_page and ocr_end_page:
                start0 = max(0, int(ocr_start_page) - 1)
                end0 = int(ocr_end_page) - 1
                ocr_direct_config["page_range"] = f"{start0}-{end0}"

            # 创建 converter
            converter = OcrDirectAsyncConverter(ocr_direct_config)

            all_output_paths_for_zip = []
            start_time = time.time()

            # 多文件并发处理
            import asyncio

            # 创建全局信号量（用于API请求限制）
            global_semaphore = asyncio.Semaphore(ocr_total_concurrent)
            file_semaphore = asyncio.Semaphore(ocr_max_concurrent_files)

            # 🆕 改为按批次创建临时文件（避免被系统清理）
            if upload_mode == "上传文件":
                file_objects = [(file_obj, file_obj.name) for file_obj in uploaded_files]
            else:
                file_objects = [(file_obj, os.path.basename(file_obj)) for file_obj in uploaded_files]

            st.info(f"📚 使用 OCR Direct 模式（{'串行文件' if ocr_concurrency_mode == 'serial_file' else '单页批次'}：{ocr_max_concurrent_files}文件 × {ocr_concurrency}页并发）")
            st.write(f"📋 待处理文件：{len(file_objects)} 个")

            # 检查是否从暂停状态恢复
            resume_from_batch = 0
            if st.session_state.ocr_paused and st.session_state.ocr_pause_info:
                resume_from_batch = st.session_state.ocr_resume_batch_start
                # 恢复之前保存的输出路径
                if st.session_state.ocr_pause_info.get("all_output_paths_for_zip"):
                    all_output_paths_for_zip = st.session_state.ocr_pause_info["all_output_paths_for_zip"]
                st.info(f"🔄 从批次 {resume_from_batch // ocr_max_concurrent_files + 1} 恢复处理...")
                # 清除暂停状态
                st.session_state.ocr_paused = False
                st.session_state.ocr_pause_info = None

            # 导入 ModelCrashError
            from aih_contexture.services.ocr_chandra import ModelCrashError

            # 定义文件可访问性检查函数
            def check_file_accessible(file_path):
                """检查文件是否可以被读取（未被其他程序锁定）"""
                try:
                    with open(file_path, 'rb') as f:
                        f.read(1024)
                    return True
                except (PermissionError, IOError):
                    return False

            # 定义单文件处理函数（带文件锁定检查）
            async def process_single_file(file_path, file_name, file_idx):
                try:
                    # 先检查文件是否可访问
                    if not check_file_accessible(file_path):
                        return (file_idx, file_name, None, "文件被锁定（可能被PDF阅读器打开）", False)

                    markdown = await converter(file_path, global_semaphore)
                    return (file_idx, file_name, markdown, None, False)
                except ModelCrashError as e:
                    return (file_idx, file_name, None, str(e), True)
                except Exception as e:
                    return (file_idx, file_name, None, str(e), False)

            # 使用严格批次模式处理（避免 LM Studio promote 问题）
            # 🆕 每个批次处理前才创建临时文件，处理后立即清理
            batch_size = ocr_max_concurrent_files
            total_batches = (len(file_objects) + batch_size - 1) // batch_size
            success_count = [0]  # 使用列表以便在嵌套函数中修改

            async def process_batch_and_save(batch_file_list, batch_num, batch_start):
                # 创建当前批次的任务
                tasks = [
                    process_single_file(fp, fn, batch_start + idx)
                    for idx, (fp, fn) in enumerate(batch_file_list)
                ]

                # 等待当前批次所有任务完成
                batch_results = await asyncio.gather(*tasks)

                # 检测是否有模型崩溃
                model_crashed = False
                crash_error = None

                # 立即保存当前批次的结果
                saved_count = 0
                for file_idx, file_name, markdown, error, is_crash in batch_results:
                    if is_crash:
                        model_crashed = True
                        crash_error = error
                        st.error(f"🚨 {file_name} 模型崩溃：{error}")
                        continue
                    if error:
                        st.error(f"❌ {file_name} 转换失败：{error}")
                        continue

                    success_count[0] += 1
                    saved_count += 1
                    fname_base = get_output_basename(
                        file_name,
                        ocr_start_page if ocr_use_page_range else None,
                        ocr_end_page if ocr_use_page_range else None,
                    )
                    output_files = []

                    # 1. Markdown 输出
                    if "markdown" in ocr_output_formats:
                        md_path = os.path.join(st.session_state.output_dir, f"{fname_base}.md")
                        with open(md_path, "w", encoding="utf-8") as f:
                            f.write(markdown)
                        output_files.append(md_path)

                    # 2. JSON 输出
                    if "json" in ocr_output_formats:
                        import json as json_module
                        json_data = {
                            "filename": file_name,
                            "markdown": markdown,
                            "format": "vlm_specialized",
                            "page_count": markdown.count("{") - 1
                        }
                        json_str = json_module.dumps(json_data, ensure_ascii=False, indent=2)
                        json_path = os.path.join(st.session_state.output_dir, f"{fname_base}.json")
                        with open(json_path, "w", encoding="utf-8") as f:
                            f.write(json_str)
                        output_files.append(json_path)

                    # 3. HTML 输出
                    if "html" in ocr_output_formats:
                        try:
                            import markdown as md_lib
                            html_content = md_lib.markdown(markdown, extensions=['tables', 'fenced_code'])
                        except ImportError:
                            html_content = f"<pre>{markdown}</pre>"

                        html_full = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{file_name}</title>
    <style>
        body {{ font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
        pre {{ background: #f5f5f5; padding: 10px; overflow-x: auto; }}
    </style>
</head>
<body>
{html_content}
</body>
</html>"""
                        html_path = os.path.join(st.session_state.output_dir, f"{fname_base}.html")
                        with open(html_path, "w", encoding="utf-8") as f:
                            f.write(html_full)
                        output_files.append(html_path)

                    all_output_paths_for_zip.extend(output_files)
                    st.write(f"  💾 {file_name} 已保存")

                return saved_count, model_crashed, crash_error

            async def process_all_batches(resume_from=0):
                for batch_start in range(resume_from, len(file_objects), batch_size):
                    batch_objects = file_objects[batch_start:batch_start + batch_size]
                    batch_num = batch_start // batch_size + 1

                    st.write(f"📦 处理批次 {batch_num}/{total_batches}（{len(batch_objects)} 个文件）")

                    # 🆕 为当前批次创建临时文件
                    batch_file_list = []
                    batch_temp_files = []
                    for file_obj, file_name in batch_objects:
                        if upload_mode == "上传文件":
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                                tmp.write(file_obj.getvalue())
                                tmp.flush()
                                os.fsync(tmp.fileno())
                                batch_file_list.append((tmp.name, file_name))
                                batch_temp_files.append(tmp.name)
                        else:
                            batch_file_list.append((file_obj, file_name))

                    saved_count, model_crashed, crash_error = await process_batch_and_save(batch_file_list, batch_num, batch_start)

                    # 🆕 立即清理当前批次的临时文件
                    safe_cleanup_temp_files(batch_temp_files)

                    st.write(f"✅ 批次 {batch_num} 完成，已保存 {saved_count} 个文件")

                    # 检测模型崩溃
                    if model_crashed:
                        return {
                            "crashed": True,
                            "batch_start": batch_start,
                            "batch_num": batch_num,
                            "error": crash_error
                        }

                    # 批次间休息（帮助显卡散热）
                    if batch_num < total_batches and ocr_batch_rest > 0:
                        st.write(f"💤 休息 {ocr_batch_rest} 秒...")
                        await asyncio.sleep(ocr_batch_rest)

                return {"crashed": False}

            # 执行批次处理
            batch_result = asyncio.run(process_all_batches(resume_from=resume_from_batch))

            # 检测模型崩溃，进入暂停状态
            if batch_result.get("crashed", False):
                st.session_state.ocr_paused = True
                st.session_state.ocr_pause_info = {
                    "batch_start": batch_result["batch_start"],
                    "batch_num": batch_result["batch_num"],
                    "error": batch_result["error"],
                    "file_objects": file_objects,  # 🆕 改为保存原始文件对象
                    "all_output_paths_for_zip": all_output_paths_for_zip,
                    "start_time": start_time,
                }
                st.session_state.ocr_resume_batch_start = batch_result["batch_start"]

                # 显示暂停 UI
                st.error(f"⚠️ 模型崩溃检测！批次 {batch_result['batch_num']} 处理失败")
                st.warning(batch_result["error"])
                st.info("📋 已处理的文件已保存到磁盘，不会丢失")

                if st.button("🔄 重启 LM Studio 后点击继续", key="resume_ocr_btn"):
                    st.session_state.ocr_paused = False
                    st.rerun()

                st.stop()

            # 🆕 临时文件已在每个批次处理后立即清理，无需全局清理

            # 创建 ZIP
            if all_output_paths_for_zip:
                elapsed_time = time.time() - start_time
                st.success(f"🎉 所有文件处理完成！总耗时：{elapsed_time:.1f} 秒")

                zip_path = os.path.join(st.session_state.output_dir, "ocr_direct_results.zip")
                with zipfile.ZipFile(zip_path, "w") as zf:
                    for p in all_output_paths_for_zip:
                        zf.write(p, os.path.basename(p))

                st.session_state.last_zip_path = zip_path
                st.session_state.last_zip_name = "ocr_direct_results.zip"

                with open(zip_path, "rb") as f:
                    st.download_button(
                        "📦 下载所有结果（ZIP）",
                        data=f.read(),
                        file_name="ocr_direct_results.zip",
                        mime="application/zip",
                        key="download_ocr_direct_results"
                    )

            st.stop()

        # ==================== 传统模式处理 ====================
        artifacts = get_artifacts()
        all_output_paths_for_zip = []
        start_time = time.time()

        for file_idx, file_obj in enumerate(uploaded_files):
            progress_bar = st.progress(0.0)

            if upload_mode == "上传文件":
                file_name = file_obj.name
                st.write(f"### 处理文件 {file_idx+1}/{len(uploaded_files)}: {file_name}")
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(file_obj.getvalue())
                    file_path = tmp.name
            else:
                file_path = file_obj
                file_name = os.path.basename(file_path)
                st.write(f"### 处理文件 {file_idx+1}/{len(uploaded_files)}: {file_name}")

            try:
                total_pages = len(PdfReader(file_path).pages)
                st.write(f"📊 检测到 {total_pages} 页")

                if process_mode == "强制单批":
                    should_batch = False
                elif process_mode == "强制分批":
                    should_batch = True
                else:
                    should_batch = total_pages > batch_threshold

                if use_page_range and start_page_1based and end_page_1based:
                    start0 = max(0, int(start_page_1based) - 1)
                    end0 = min(total_pages - 1, int(end_page_1based) - 1)
                    target_ranges = [(start0, end0 + 1)]
                else:
                    target_ranges = [(0, total_pages)]

                page_ranges = []
                for (rs, re_) in target_ranges:
                    if (not should_batch) or (re_ - rs) <= pages_per_batch:
                        page_ranges.append((rs, re_))
                    else:
                        cur = rs
                        while cur < re_:
                            nxt = min(cur + int(pages_per_batch), re_)
                            page_ranges.append((cur, nxt))
                            cur = nxt

                file_outputs = []
                fname_base = get_output_basename(
                    file_name if upload_mode == "上传文件" else file_path,
                    start_page_1based if use_page_range else None,
                    end_page_1based if use_page_range else None,
                )

                merged_rendered = {fmt: None for fmt in output_formats}
                merged_text = {fmt: "" for fmt in output_formats}
                merged_images = {fmt: {} for fmt in output_formats}
                merged_metadata = {}

                total_batches = len(page_ranges)

                for bidx, (start, end) in enumerate(page_ranges):
                    st.write(f"📄 批次 {bidx+1}/{total_batches}: 处理页 {start+1}-{end}")
                    page_range_str = f"{start}-{end-1}"

                    # 构建配置参数
                    config_params = {
                        "ocr_batch_size": ocr_batch_size if ocr_backend in ["surya", "vlm"] else 32,
                        "use_fp16": use_fp16,
                        "force_ocr": force_ocr,
                        "use_llm": use_llm,
                        "page_range": page_range_str,
                        "paginate_output": True,
                        "page_separator": "\n\n---\n\n",
                        "ocr_backend": ocr_backend,
                        "layout_backend": layout_backend,
                    }

                    # 版面识别 VLM 配置
                    if layout_backend == "vlm":
                        vlm_layout_config = {
                            "vlm_layout_timeout": vlm_layout_timeout,
                        }

                        # 提示词配置：优先使用直接指定的 prompt，否则使用模板
                        # 确保至少有一个被设置（不能都为空）
                        if vlm_layout_prompt and vlm_layout_prompt.strip():
                            vlm_layout_config["vlm_layout_prompt"] = vlm_layout_prompt
                        elif vlm_layout_prompt_template and vlm_layout_prompt_template.strip():
                            vlm_layout_config["vlm_layout_prompt_template"] = vlm_layout_prompt_template
                        else:
                            # 如果都为空，使用默认模板
                            vlm_layout_config["vlm_layout_prompt_template"] = "modern"

                        # VLM Layout 始终使用独立配置
                        vlm_layout_config.update({
                            "vlm_layout_base_url": vlm_layout_base_url,
                            "vlm_layout_model": vlm_layout_model,
                            "vlm_layout_api_key": vlm_layout_api_key,
                            "vlm_layout_max_concurrent": vlm_layout_max_concurrent,
                            "vlm_layout_image_format": vlm_layout_image_format,
                            "vlm_layout_max_image_dimension": vlm_layout_max_image_dimension,
                            "vlm_layout_jpeg_quality": vlm_layout_jpeg_quality,
                        })

                        config_params.update(vlm_layout_config)

                    # 版面识别 YOLO 配置
                    if layout_backend == "yolo":
                        config_params.update({
                            "yolo_base_url": yolo_base_url,
                            "yolo_model": yolo_model,
                            "yolo_confidence_threshold": yolo_confidence_threshold,
                        })

                    # 页码配置
                    config_params.update({
                        "custom_id_source": custom_id_source,
                        "custom_id_data": custom_id_data,
                    })

                    if printed_page_enabled:
                        config_params.update({
                            "use_printed_page_number": True,
                            "page_numbering_enabled": True,
                            "printed_page_zones": printed_page_zones,
                            "page_number_format": printed_page_format,
                            "printed_page_header_y_frac": printed_page_header_end,
                            "printed_page_footer_y_frac": printed_page_footer_start,
                            "page_number_custom_pattern": printed_page_custom_pattern if printed_page_custom_pattern else None,
                        })
                    else:
                        config_params.update({
                            "page_numbering_enabled": False,
                        })

                    # 边码识别配置
                    if enable_marginal_detection:
                        config_params.update({
                            "enable_marginal_detection": True,
                            "left_margin_threshold": left_margin_threshold,
                            "right_margin_threshold": right_margin_threshold,
                            "top_margin_threshold": top_margin_threshold,
                            "bottom_margin_threshold": bottom_margin_threshold,
                            "vertical_center_tolerance": vertical_center_tolerance,
                        })
                    else:
                        config_params.update({
                            "enable_marginal_detection": False,
                        })

                    if enable_inline_detection:
                        config_params.update({
                            "enable_inline_detection": True,
                            "font_size_ratio_threshold": font_size_ratio_threshold,
                            "max_inline_annotation_length": max_inline_annotation_length,
                        })
                    else:
                        config_params.update({
                            "enable_inline_detection": False,
                        })

                    # VLM 特定配置
                    if ocr_backend == "vlm":
                        config_params.update({
                            "openai_base_url": openai_base_url,
                            "openai_model": openai_model,
                            "openai_api_key": openai_api_key,
                            "openai_image_format": openai_image_format,
                            "vlm_prompt": vlm_prompt,
                            "vlm_response_mode": vlm_response_mode,
                            "openai_use_stop": openai_use_stop,
                            "vlm_mode": vlm_mode,
                            "vlm_full_page_max_tokens": vlm_full_page_max_tokens,
                            "vlm_merge_y_threshold": vlm_merge_y_threshold,
                            "vlm_merge_max_blocks": vlm_merge_max_blocks,
                        })
                    
                    # Calamari 特定配置
                    if ocr_backend == "calamari":
                        config_params.update({
                            "calamari_base_url": calamari_base_url,
                            "calamari_model": calamari_model,
                            "calamari_batch_size": calamari_batch_size,
                            "calamari_timeout": calamari_timeout,
                            "calamari_sequential_mode": calamari_sequential_mode,
                            "calamari_trust_batch_order": calamari_trust_batch_order,
                            "calamari_footnote_y_frac": calamari_footnote_y_frac,
                            "calamari_require_ordering_info": calamari_require_ordering_info,
                            "calamari_fallback_to_sequential_on_ordering_failure": calamari_fallback_to_sequential_on_ordering_failure,
                        })

                    # LLM 配置
                    if use_llm:
                        config_params.update({
                            "llm_provider": llm_provider,
                            "llm_base_url": llm_base_url if llm_provider in ["azure", "ollama", "gemini"] else None,
                            "llm_model": llm_model,
                            "llm_api_key": llm_api_key,
                            "llm_max_concurrency": llm_max_concurrency,
                            "llm_timeout": llm_timeout,
                            "llm_table_enabled": llm_table_enabled,
                            "llm_equation_enabled": llm_equation_enabled,
                            "llm_image_description_enabled": llm_image_description_enabled,
                            "llm_handwriting_enabled": llm_handwriting_enabled,
                            "llm_page_correction_enabled": llm_page_correction_enabled,
                            "llm_section_header_enabled": llm_section_header_enabled,
                            "llm_form_enabled": llm_form_enabled,
                            "llm_complex_region_enabled": llm_complex_region_enabled,
                            "llm_noise_removal_enabled": llm_noise_removal_enabled,
                            "llm_page_correction_prompt": llm_page_correction_prompt,
                        })

                        # 🆕 非 LLM 增强功能配置（在 LLM 启用时从 UI 获取）
                        config_params.update({
                            "printed_page_correction_enabled": llm_printed_page_correction_enabled,
                            "markdown_formatting_enabled": llm_heuristic_layout_enabled,
                        })
                    else:
                        # 🆕 非 LLM 增强功能配置（在 LLM 未启用时使用默认值）
                        config_params.update({
                            "printed_page_correction_enabled": False,
                            "markdown_formatting_enabled": True,  # 默认启用 Markdown 格式化
                        })

                    # 🆕 基础处理器配置（所有模式通用，从主配置区域获取）
                    config_params.update({
                        "markdown_noise_removal_enabled": markdown_noise_removal_enabled,
                        "markdown_noise_cleaning_level": markdown_noise_cleaning_level,
                        "markdown_noise_custom_symbols": markdown_noise_custom_symbols,
                        "markdown_noise_line_start_only": markdown_noise_line_start_only,
                        "blockquote_enabled": blockquote_enabled,
                        "line_merge_enabled": line_merge_enabled,
                        "code_enabled": code_enabled,
                        "section_header_enabled": section_header_enabled,
                        "list_enabled": list_enabled,
                        "footnote_enabled": footnote_enabled,
                        "reference_enabled": reference_enabled,
                        "table_enabled": table_enabled,
                    })

                    config_dict = build_config_dict(config_params)

                    # 记录处理开始时间
                    import time as time_module
                    processing_start_time = time_module.time()

                    # Clear GPU cache to free memory
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()

                    st.write("⏱️ **开始文档构建...**")
                    converter = PdfConverter(config=config_dict, artifact_dict=artifacts)
                    document = converter.build_document(file_path)

                    build_elapsed = time_module.time() - processing_start_time
                    st.write(f"✅ **文档构建完成** (耗时: {build_elapsed:.2f}秒)")


                    renderer_map = {
                        "markdown": MarkdownRenderer,
                        "json": JSONRenderer,
                        "html": HTMLRenderer,
                        "chunks": ChunkRenderer,
                    }

                    for fmt in output_formats:
                        renderer = renderer_map[fmt](config_dict)
                        rendered = renderer(document)
                        text, _, images = text_from_rendered(rendered)

                        if not merged_metadata and getattr(rendered, "metadata", None) is not None:
                            merged_metadata = rendered.metadata

                        if fmt in ("markdown", "html"):
                            merged_text[fmt] += text
                            merged_images[fmt].update(images)
                        elif fmt == "json":
                            if merged_rendered[fmt] is None:
                                merged_rendered[fmt] = rendered
                            else:
                                merged_rendered[fmt].children.extend(rendered.children)
                        elif fmt == "chunks":
                            if merged_rendered[fmt] is None:
                                merged_rendered[fmt] = rendered
                            else:
                                merged_rendered[fmt].blocks.extend(rendered.blocks)
                                merged_rendered[fmt].page_info.update(rendered.page_info)

                    progress_bar.progress((bidx + 1) / total_batches)

                    if bidx < total_batches - 1 and cooling_seconds > 0:
                        time.sleep(int(cooling_seconds))
                        gc.collect()
                        if HAS_TORCH and torch.cuda.is_available():
                            torch.cuda.empty_cache()

                out_dir_final = st.session_state.output_dir
                os.makedirs(out_dir_final, exist_ok=True)

                def write_text_with_meta_and_images(main_ext: str, main_text: str, images_dict: dict, meta: dict):
                    main_path = os.path.join(out_dir_final, f"{fname_base}.{main_ext}")

                    with open(main_path, "w", encoding="utf-8") as f:
                        f.write(main_text)

                    meta_path = os.path.join(out_dir_final, f"{fname_base}_meta.json")
                    if meta and (not os.path.exists(meta_path)):
                        import json as _json
                        with open(meta_path, "w", encoding="utf-8") as f:
                            f.write(_json.dumps(meta, ensure_ascii=False, indent=2))

                    from aih_contexture.output import convert_if_not_rgb
                    from aih_contexture.settings import settings as _settings

                    for img_name, img in images_dict.items():
                        try:
                            img = convert_if_not_rgb(img)
                            img.save(os.path.join(out_dir_final, img_name), _settings.OUTPUT_IMAGE_FORMAT)
                        except Exception:
                            pass
                    return main_path

                if "markdown" in output_formats:
                    p = write_text_with_meta_and_images("md", merged_text["markdown"], merged_images["markdown"], merged_metadata)
                    file_outputs.append({"format": "markdown", "path": p, "name": os.path.basename(p)})
                    all_output_paths_for_zip.append(p)

                if "html" in output_formats:
                    p = write_text_with_meta_and_images("html", merged_text["html"], merged_images["html"], merged_metadata)
                    file_outputs.append({"format": "html", "path": p, "name": os.path.basename(p)})
                    all_output_paths_for_zip.append(p)

                if "json" in output_formats:
                    json_text, _, _ = text_from_rendered(merged_rendered["json"])
                    jp = os.path.join(out_dir_final, f"{fname_base}.json")
                    with open(jp, "w", encoding="utf-8") as f:
                        f.write(json_text)
                    file_outputs.append({"format": "json", "path": jp, "name": os.path.basename(jp)})
                    all_output_paths_for_zip.append(jp)

                if "chunks" in output_formats:
                    chunks_text, _, _ = text_from_rendered(merged_rendered["chunks"])
                    cp = os.path.join(out_dir_final, f"{fname_base}_chunks.json")
                    with open(cp, "w", encoding="utf-8") as f:
                        f.write(chunks_text)
                    file_outputs.append({"format": "chunks", "path": cp, "name": os.path.basename(cp)})
                    all_output_paths_for_zip.append(cp)

                # 使用唯一的键来存储处理结果，避免覆盖
                # 格式: {文件名}_{时间戳}
                result_key = f"{file_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                st.session_state.processed_files[result_key] = file_outputs

                # 显示处理结果
                total_elapsed = time_module.time() - processing_start_time
                st.info(f"⏱️ 处理耗时: {total_elapsed:.2f}秒")

                st.success(f"✅ 《{file_name}》处理完成")

            except Exception as e:
                st.error(f"处理《{file_name}》失败: {str(e)}")
                st.error(traceback.format_exc())

            finally:
                if upload_mode == "上传文件":
                    try:
                        os.unlink(file_path)
                    except Exception:
                        pass

        elapsed = time.time() - start_time
        st.success(f"🎉 全部完成！总用时 {elapsed:.2f} 秒")

        zip_name = f"marker_output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        zip_path = os.path.join(st.session_state.output_dir, zip_name)
        build_zip(all_output_paths_for_zip, zip_path)

        st.session_state.last_zip_path = zip_path
        st.session_state.last_zip_name = zip_name

        with open(zip_path, "rb") as f:
            st.download_button(
                "📦 下载所有结果（ZIP）",
                data=f.read(),
                file_name=zip_name,
                mime="application/zip",
                key="download_all",
            )
else:
    st.info("👆 请在侧边栏上传 PDF 文件或选择包含 PDF 的文件夹")