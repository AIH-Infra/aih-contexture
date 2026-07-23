import os
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "max_split_size_mb:512")

import time
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import threading
import json
import shutil

import streamlit as st

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
from aih_contexture.config.vlm_model_presets import (
    VLM_SPECIALIZED_BACKEND_LABELS,
    default_quant,
    default_version,
    quant_options,
    resolve_vlm_model,
    version_label,
    version_options,
)
from aih_contexture.converters.pdf import PdfConverter
from aih_contexture.config.marginal_output import normalize_marginal_output_mode
from aih_contexture.models import create_model_dict
from aih_contexture.output import text_from_rendered
from aih_contexture.renderers.chunk import ChunkRenderer
from aih_contexture.renderers.html import HTMLRenderer
from aih_contexture.renderers.json import JSONRenderer
from aih_contexture.renderers.markdown import MarkdownRenderer
from aih_contexture.runtime.artifacts import (
    append_text,
    merge_chunk_batches,
    merge_json_batches,
    save_images,
    write_meta_once,
)
from aih_contexture.runtime.vlm_repair import (
    extract_failed_pages,
    load_vlm_generalized_json,
    repair_vlm_json,
    rerender_vlm_json,
)
from aih_contexture.scripts.ui.backend_selectors import (
    render_layout_backend_selector,
    render_ocr_backend_selector,
)
from aih_contexture.scripts.ui.batch_inputs import (
    check_file_accessible,
    input_file_objects,
    validate_single_page_batch,
)
from aih_contexture.scripts.ui.pipeline_output_settings import (
    default_pipeline_output_formats,
    render_pipeline_output_settings,
)
from aih_contexture.scripts.ui.pipeline_file_runner import run_pipeline_file
from aih_contexture.scripts.ui.pipeline_run_settings import render_pipeline_run_settings
from aih_contexture.scripts.ui.middle_debug_settings import render_middle_artifact_settings
from aih_contexture.scripts.ui.dpi_settings import (
    render_pipeline_layout_dpi_settings,
    render_pipeline_ocr_dpi_settings,
)
from aih_contexture.scripts.ui.markdown_postprocess_runner import (
    run_markdown_postprocess_batch,
)
from aih_contexture.scripts.ui.vlm_generalized_runner import (
    run_vlm_generalized_batch,
)
from aih_contexture.scripts.ui.vlm_specialized_runner import (
    run_vlm_specialized_batch,
)
from aih_contexture.scripts.ui.result_panel import (
    render_process_controls,
    render_result_history,
)
from aih_contexture.scripts.ui.task_outputs import (
    finalize_zip_outputs,
    get_output_basename,
    record_processed_outputs,
)
from aih_contexture.scripts.ui.task_state import (
    attach_preread_files,
    cleanup_staged_uploads,
    initial_proc_context,
    sync_proc_context_to_session,
)
from aih_contexture.scripts.ui.task_thread import run_proc_body_with_streamlit_log
from aih_contexture.scripts.ui.vlm_output_saver import (
    save_vlm_generalized_outputs,
)
from aih_contexture.scripts.ui.vlm_config import (
    build_vlm_generalized_config,
)
from aih_contexture.scripts.ui.pipeline_config_sections import snapshot_pipeline_ui_values
from aih_contexture.scripts.ui.vlm_progress import (
    finish_vlm_progress,
    make_vlm_progress_callback,
    render_vlm_progress,
    update_vlm_batch_progress,
)
from aih_contexture.scripts.ui.ocr_calamari_settings import render_calamari_ocr_settings
from aih_contexture.builders.ocr_line_crops import (
    DEFAULT_OCR_CROP_PADDING_FRAC,
    DEFAULT_OCR_CROP_PADDING_PX,
    DEFAULT_OCR_CROP_UPSCALE_MIN_HEIGHT,
)
from aih_contexture.scripts.ui.paddle_ocr_settings import render_paddle_ocr_settings
from aih_contexture.scripts.ui.ocr_surya_settings import render_surya_ocr_settings
from aih_contexture.scripts.ui.ocr_tesseract_settings import render_tesseract_ocr_settings
from aih_contexture.scripts.ui.ocr_vlm_settings import (
    render_paddleocr_vl_ocr_settings,
    render_vlm_ocr_settings,
)
from aih_contexture.scripts.ui.external_layout_sidecar_settings import render_external_layout_sidecar_settings
from aih_contexture.scripts.ui.file_input import render_file_input_selector
from aih_contexture.scripts.ui.mineru_layout_settings import (
    render_mineru_direct_layout_settings,
    render_mineru_ocr_settings,
)
from aih_contexture.scripts.ui.mineru_vl_layout_settings import render_mineru_vl_layout_settings
from aih_contexture.scripts.ui.paddle_layout_settings import render_paddle_layout_settings
from aih_contexture.scripts.ui.page_margin_settings import render_pipeline_page_margin_settings
from aih_contexture.scripts.ui.pipeline_processor_settings import render_pipeline_processor_settings
from aih_contexture.scripts.ui.surya_layout_settings import render_surya_layout_settings
from aih_contexture.scripts.ui.surya2_vlm_settings import render_surya2_vlm_settings
from aih_contexture.scripts.ui.vlm_layout_settings import render_vlm_layout_settings
from aih_contexture.settings import settings
from aih_contexture.runtime.ui_config import build_config_dict

# 导入语言预设
from aih_contexture.prompts.templates import LANGUAGE_PRESETS, LANGUAGE_DISPLAY_NAMES

# 导入配置管理器
from aih_contexture.utils.config_manager import ConfigManager


def _local_folder_uri(path: str) -> str | None:
    try:
        folder = Path(path).expanduser().resolve()
        folder.mkdir(parents=True, exist_ok=True)
        return folder.as_uri()
    except Exception:
        return None


def _middle_settings_from_value(value):
    """Normalize Middle settings across hot-reloaded Streamlit module versions."""
    if hasattr(value, "emit_middle_json"):
        if hasattr(value, "emit_middle_full_json"):
            return value
        return SimpleNamespace(
            emit_middle_json=bool(value.emit_middle_json),
            emit_middle_report=bool(getattr(value, "emit_middle_report", False)),
            emit_middle_debug=bool(getattr(value, "emit_middle_debug", False)),
            emit_middle_scholarly=bool(getattr(value, "emit_middle_scholarly", False)),
            emit_middle_scholarly_report=bool(getattr(value, "emit_middle_scholarly_report", False)),
            emit_layout_overlay=bool(getattr(value, "emit_layout_overlay", False)),
            emit_span_overlay=bool(getattr(value, "emit_span_overlay", False)),
            emit_middle_full_json=False,
        )
    if isinstance(value, (tuple, list)):
        if len(value) == 3:
            emit_middle_json, emit_layout_overlay, emit_span_overlay = value
            return SimpleNamespace(
                emit_middle_json=bool(emit_middle_json),
                emit_middle_report=False,
                emit_middle_debug=False,
                emit_middle_scholarly=False,
                emit_middle_scholarly_report=False,
                emit_layout_overlay=bool(emit_layout_overlay),
                emit_span_overlay=bool(emit_span_overlay),
                emit_middle_full_json=False,
            )
        if len(value) == 7:
            (
                emit_middle_json,
                emit_middle_report,
                emit_middle_debug,
                emit_middle_scholarly,
                emit_middle_scholarly_report,
                emit_layout_overlay,
                emit_span_overlay,
            ) = value
            return SimpleNamespace(
                emit_middle_json=bool(emit_middle_json),
                emit_middle_report=bool(emit_middle_report),
                emit_middle_debug=bool(emit_middle_debug),
                emit_middle_scholarly=bool(emit_middle_scholarly),
                emit_middle_scholarly_report=bool(emit_middle_scholarly_report),
                emit_layout_overlay=bool(emit_layout_overlay),
                emit_span_overlay=bool(emit_span_overlay),
                emit_middle_full_json=False,
            )
    return SimpleNamespace(
        emit_middle_json=bool(value),
        emit_middle_report=False,
        emit_middle_debug=False,
        emit_middle_scholarly=False,
        emit_middle_scholarly_report=False,
        emit_layout_overlay=False,
        emit_span_overlay=False,
        emit_middle_full_json=False,
    )


def _pipeline_output_settings_from_value(value):
    """Normalize Pipeline output settings across new/old helper return shapes."""
    if isinstance(value, (tuple, list)):
        if len(value) == 2:
            output_formats, middle_settings = value
            return output_formats, _middle_settings_from_value(middle_settings)
        if len(value) == 4:
            output_formats, emit_middle_json, emit_layout_overlay, emit_span_overlay = value
            return output_formats, _middle_settings_from_value(
                (emit_middle_json, emit_layout_overlay, emit_span_overlay)
            )
    raise ValueError("Invalid Pipeline output settings return value")


def _migrate_multiselect_default(key: str, *, old_defaults: list[list[str]], new_default: list[str]) -> None:
    current = st.session_state.get(key)
    if current is not None and list(current) in old_defaults:
        st.session_state[key] = list(new_default)

try:
    import torch
    HAS_TORCH = True
    TORCH_IMPORT_ERROR = None
except (ImportError, OSError) as exc:
    torch = None
    HAS_TORCH = False
    TORCH_IMPORT_ERROR = exc

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

if TORCH_IMPORT_ERROR is not None:
    st.warning(
        "当前环境的 PyTorch DLL 无法加载，本地 Surya/PyTorch 后端暂不可用；"
        "不依赖本地 torch 的后端、API 后端和已有 JSON 重渲染仍可继续使用。"
    )

# ==================== 文案常量定义 ====================

# 模式介绍文案
MODE_DESCRIPTIONS = {
    "pipeline": """
**Pipeline 模式** - 版面识别 + OCR + 后处理

把版面检测、文字识别和结构后处理拆开配置：
- **版面识别**: Surya / Paddle / MinerU / Sidecar
- **OCR 引擎**: PDF 文本层 / Surya / Paddle / Tesseract / Calamari / VLM
- **后处理**: 页码锚点、结构识别、页眉页脚、可选 LLM 增强

适用于需要本地运行、离线处理或精细控制的任务。
    """,

    "vlm_generalized": """
**VLM 泛化模式** - 通用视觉语言模型

整页图像直接交给通用 VLM，输出 Markdown 或结构化文本。

适用于小批量困难页面、复杂排版和常规 OCR 难以处理的材料。质量和成本取决于模型与服务稳定性。
    """,

    "vlm_specialized": """
**VLM 特化模式** - 文档 OCR/解析微调模型

调用已挂载的 OCR/VLM 专用模型，尽量贴近各模型官方任务格式，再标准化为 Contexture 输出。

已接入 Chandra、Churro、PaddleOCR-VL、MinerU-VL。适用于这些模型覆盖的文档类型。
    """,

    "markdown_postprocess": """
**Markdown 后处理**

对已有 Markdown 或 JSON 结果做二次整理与重渲染，不重新跑 PDF/OCR。
    """
}

_VLM_LAYOUT_DESCRIPTION = """
**VLM 版面识别** - 视觉语言模型
- 通过 OpenAI 兼容 API 识别版面
- 适用于小批量、特殊版式测试
- 结果质量取决于模型和提示词
"""

_VLM_OCR_DESCRIPTION = """
**VLM OCR** - 视觉语言模型
- 通过 OpenAI 兼容 API 调用视觉语言模型识别文字
- 支持逐块、区域合并和整页模式
- 适用于复杂页面、低结构化材料或传统 OCR 表现不佳的实验场景
"""

# 版面识别后端介绍
LAYOUT_BACKEND_DESCRIPTIONS = {
    "surya": """
**Surya 版面分析** - 内置通用版面模型
- 默认版面分析后端，覆盖常见论文、图书、报告和扫描页
- 本地运行，首次使用会下载模型并缓存
- 常作为稳定基线，也可与任意 OCR 后端组合
""",
    "vlm": _VLM_LAYOUT_DESCRIPTION,
    "vlm_layout": _VLM_LAYOUT_DESCRIPTION,
    "external_layout_sidecar": """
**External Layout Sidecar** - 外部版面识别 JSON
- 读取已经生成好的 layout JSON 或 Contexture Middle JSON
- 不启动版面模型，适用于复用离线识别结果
- 用于对比 MinerU、Paddle 或其他外部版面输出
""",
    "mineru_pp_doclayout_v2_direct": """
**MinerU PP-DocLayoutV2 Direct** - 高精度文档版面检测
- 直接调用 MinerU 的 PP-DocLayoutV2 模型
- 只输出版面区域和置信度，不执行 MinerU 完整 pipeline
- 适用于复杂文档版面、论文、书页和多类型区域识别
""",
    "mineru_vl_layout": """
**MinerU-VL Layout** - API/VLM 版面检测
- 调用 MinerU-VL 2.5 Pro 2605 的 Layout Detection 协议
- 只生成 layout block，不执行后续块级文字识别
- 可与 Pipeline 的 OCR 后端自由组合，适合旁注/复杂书页版面测试
""",
    "surya2_layout": """
**Surya 2 Layout** - API/VLM 版面检测
- 调用 Surya 2 官方 layout JSON 协议，bbox 使用 0-1000 归一化坐标
- 只生成 layout block，不执行块级 OCR
- 推荐通过 LM Studio/OpenAI-compatible 服务调用；layout 并发可从 4-6 起试
""",
    "paddle_pp_doclayout_plus_l": """
**Paddle PP-DocLayout Plus-L** - 通用文档版面检测
- 调用 PaddleOCR LayoutDetection 的 Plus-L 模型
- 只做版面区域检测，不做文字识别
- 适用于通用扫描件和常见文档版式
""",
    "paddle_pp_doclayout_v3": """
**Paddle PP-DocLayoutV3** - 新一代文档版面检测
- 调用 PaddleOCR LayoutDetection 的 V3 模型
- 只做版面区域检测，不启动 PP-StructureV3
- 可与 Plus-L 对照，用于观察新版模型在复杂版式上的差异
""",
}

# OCR后端介绍
OCR_BACKEND_DESCRIPTIONS = {
    "surya": """
**Surya OCR** - 内置通用 OCR
- Contexture 默认 OCR 后端，可与 Surya 版面分析直接配合
- 支持多语言印刷文本，适用于现代出版物和一般扫描件
- 本地运行，首次使用会下载模型；资源占用相对较高
""",
    "calamari": """
**Calamari OCR** - 欧洲历史文献 OCR
- 面向 Fraktur、Antiqua 等欧洲历史印刷文本
- 通过外部 Calamari 服务调用指定历史模型
- 适用于已有专门训练模型的德文、拉丁文、早期现代印刷材料
""",
    "paddle_ocr_v5": """
**PaddleOCR PP-OCRv5** - 本地通用 OCR
- PaddleOCR 的本地文字检测与识别后端
- 适用于中文、CJK、多语种混排和常见现代印刷材料
- 可使用独立 Paddle/GPU 环境，适用于批量处理和本地部署
""",
    "paddleocr_vl_ocr": """
**PaddleOCR-VL OCR** - 块级文档 VLM OCR
- 使用已有 Pipeline layout block 裁切，不重复做版面识别
- 通过 PaddleOCR-VL 的 OCR/Table/Formula VLRecognition 任务识别块内容
- 适用于 Surya、MinerU 或 Paddle layout 已经切好区域后的表格、公式、脚注和正文识别
""",
    "surya2_ocr": """
**Surya 2 OCR** - 块级 HTML OCR
- 使用已有 Pipeline layout block 裁切，不重复做版面识别
- 通过 Surya 2 官方 `OCR this block image to HTML.` 协议识别块内容
- 适合与 Surya2/MinerU/Paddle/Surya layout 组合，用作轻量文档 VLM OCR 后端
""",
    "mineru_pytorch_paddle_ocr": """
**MinerU PaddleOCR-Torch** - MinerU 内部 OCR 后端
- 调用 MinerU 内部封装的 PytorchPaddleOCR，不启动 MinerU 完整 pipeline
- 可与任意 layout 后端组合，适合需要 MinerU OCR 行为但不想锁死 layout 的场景
- 设备通过 MinerU 外部虚拟环境和 MINERU_DEVICE_MODE 控制
""",
    "tesseract": """
**Tesseract OCR** - 传统 CPU OCR
- 调用系统 Tesseract，可使用丰富的 tessdata 语言包
- 适用于清晰扫描、规则印刷文本和可解释的 CPU 工作流
- 支持语言组合，如 eng、chi_sim+eng、deu_frak+eng
""",
    "vlm": _VLM_OCR_DESCRIPTION,
    "vlm_ocr": _VLM_OCR_DESCRIPTION,
    "kraken": """
**Kraken OCR** - 历史文献专用（未启用）
- 支持从右到左、双向文本
- 丰富的历史字体模型
""",
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
    "chrome_screenai": """
**Chrome ScreenAI** - 本地原生 OCR
- 直接调用 Chrome ScreenAI 组件
- 默认走 PDF 原生通道；仅在显式选择时才做去文本层或栅格化预处理
- 支持页面切分并行与 searchable PDF 输出
""",
    "olmocr": """
**OlmOCR** - Allen AI 开源模型（未启用）
- 基于 Qwen2-VL 架构微调
- 专注学术论文和技术文档
- 公式、代码块识别优秀
""",
    "paddleocr": """
**PaddleOCR-VL** - 文档解析 VLM
- 已在 VLM 特化模式中接入
- 按官方任务提示调用并标准化输出
""",
    "deepseek": """
**DeepSeek-OCR** - DeepSeek（未启用）
- 多模态理解能力强
- 开源可商用
"""
}

os.environ["IN_STREAMLIT"] = "true"
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

config_manager = ConfigManager()
_app_settings = config_manager.load_app_settings()
DEFAULT_OUTPUT_DIR = os.environ.get("MARKER_OUTPUT_DIR") or _app_settings.get("output_dir") or "output"
DEFAULT_ALWAYS_SAVE_MIDDLE_JSON = bool(_app_settings.get("always_save_middle_json", True))
os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)

# ==================== Session State 初始化 ====================
if "processed_files" not in st.session_state:
    st.session_state.processed_files = {}
if "output_dir" not in st.session_state:
    st.session_state.output_dir = DEFAULT_OUTPUT_DIR
if "always_save_middle_json" not in st.session_state:
    st.session_state.always_save_middle_json = DEFAULT_ALWAYS_SAVE_MIDDLE_JSON
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

# 后台处理上下文（线程安全，不依赖 st.session_state）
if "proc_ctx" not in st.session_state:
    st.session_state.proc_ctx = initial_proc_context()
if "proc_cancel" not in st.session_state:
    st.session_state.proc_cancel = None
if "proc_thread" not in st.session_state:
    st.session_state.proc_thread = None
if "pending_vlm_repair_job" not in st.session_state:
    st.session_state.pending_vlm_repair_job = None


# ==================== 辅助函数 ====================

GLOBAL_STATE_EXCLUDE_KEYS = {
    "config_selector", "load_config_btn", "delete_config_btn", "confirm_delete_config",
    "save_config_btn", "export_config_btn", "import_config_btn", "config_uploader",
    "overwrite_config", "overwrite_save_config", "new_config_name", "new_config_desc",
    "api_key_mode", "file_uploader_global", "uploaded_id_file_global", "upload_mode_global",
    "folder_path_global", "show_regex_editor_global", "out_dir", "output_dir", "loaded_config",
    "processed_files", "last_zip_path", "last_zip_name", "proc_ctx", "proc_cancel", "proc_thread",
    "ocr_paused", "ocr_pause_info", "ocr_resume_batch_start", "download_all_persist",
    "download_proc_results", "vlm_api_profile_selector", "vlm_api_profile_name",
    "vlm_api_profile_desc", "save_api_profile_btn", "load_api_profile_btn", "delete_api_profile_btn",
    "overwrite_api_profile", "confirm_delete_api_profile",
}

GLOBAL_STATE_INCLUDE_KEYS = {
    "conversion_mode", "use_page_range", "start_page", "end_page",
    "page_anchor_position_global", "extract_printed_pages_global", "printed_page_format_global",
    "printed_page_custom_pattern_global", "regex_preset_key_global", "vlm_patterns_text_global",
    "custom_id_source_global", "custom_id_list_global", "auto_prefix_global", "auto_start_global",
    "auto_separator_global", "auto_digits_global", "enable_marginal_detection_global",
    "native_marginalia_enabled_global", "heuristic_marginal_detection_enabled_global",
    "marginal_output_mode_global",
    "left_margin_threshold_global", "right_margin_threshold_global", "top_margin_threshold_global",
    "bottom_margin_threshold_global", "vertical_center_tolerance_global", "enable_inline_detection_global",
    "font_size_ratio_threshold_global", "max_inline_annotation_length_global",
}

MODE_STATE_RULES = {
    "vlm_specialized": {
        "prefixes": ("ocr_", "chandra_"),
        "include": {
            "ocr_backend",
            "vlm_specialized_emit_middle_json",
            "vlm_specialized_emit_middle_report",
            "vlm_specialized_emit_middle_debug",
            "vlm_specialized_emit_middle_scholarly",
            "vlm_specialized_emit_middle_scholarly_report",
            "vlm_specialized_emit_layout_overlay",
            "vlm_specialized_emit_span_overlay",
            "vlm_specialized_emit_middle_full_json",
        },
        "exclude": {"ocr_paused", "ocr_pause_info", "ocr_resume_batch_start"},
    },
    "vlm_generalized": {
        "prefixes": ("vlm_",),
        "include": set(),
        "exclude": set(),
    },
    "pipeline": {
        "prefixes": ("pipeline_", "llm_", "calamari_", "vlm_layout_", "mineru_vl_", "vlm_ocr_", "tesseract_", "ocr_crop_", "markdown_postprocess_"),
        "include": {
            "ocr_backend", "ocr_batch_size", "ocr_quality", "ocr_dpi_override",
            "force_ocr", "force_ocr_vlm", "layout_backend", "surya_layout_quality",
            "layout_dpi_override",
            "use_llm", "llm_provider", "vlm_prompt", "openai_use_stop",
            "markdown_postprocess_enabled", "markdown_postprocess_review_only",
            "markdown_postprocess_enable_cleanup", "markdown_postprocess_enable_printed_page_repair",
            "markdown_postprocess_enable_llm",
        },
        "exclude": set(),
    },
    "markdown_postprocess": {
        "prefixes": ("markdown_postprocess_",),
        "include": set(),
        "exclude": set(),
    },
}


def _is_persistable_global_key(key: str) -> bool:
    if key in GLOBAL_STATE_EXCLUDE_KEYS:
        return False
    return key.endswith("_global") or key in GLOBAL_STATE_INCLUDE_KEYS


def _is_persistable_mode_key(key: str, mode: str) -> bool:
    rules = MODE_STATE_RULES.get(mode)
    if not rules:
        return False
    if key in GLOBAL_STATE_EXCLUDE_KEYS or key in rules["exclude"]:
        return False
    if key in rules["include"]:
        return True
    if any(key.startswith(prefix) for prefix in rules["prefixes"]):
        return True
    return False


def _infer_config_mode(config: dict) -> str:
    global_mode = config.get("global", {}).get("conversion_mode")
    if global_mode in MODE_STATE_RULES:
        return global_mode

    for mode in ("pipeline", "vlm_generalized", "vlm_specialized", "markdown_postprocess"):
        if config.get(mode):
            return mode

    return "pipeline"


def _clear_persisted_keys_for_mode(mode: str):
    for key in list(st.session_state.keys()):
        if _is_persistable_global_key(key) or _is_persistable_mode_key(key, mode):
            st.session_state.pop(key, None)


def _build_config_save_scope_text(mode: str) -> str:
    return {
        "pipeline": "当前 Pipeline 模式配置",
        "vlm_generalized": "当前 VLM 泛化模式配置",
        "vlm_specialized": "当前 VLM 特化模式配置",
        "markdown_postprocess": "当前 Markdown 后处理模式配置",
    }.get(mode, "当前模式配置")


def _render_proc_log():
    """渲染后台处理日志"""
    _dispatch = {"write": st.write, "info": st.info, "error": st.error,
                 "success": st.success, "warning": st.warning}
    for level, msg in list(st.session_state.proc_ctx["log"]):
        _dispatch.get(level, st.write)(msg)


def collect_current_config() -> dict:
    """按当前模式收集可复现配置项"""
    current_mode = st.session_state.get("conversion_mode", "pipeline")
    config = {
        "global": {},
        "vlm_specialized": {},
        "vlm_generalized": {},
        "pipeline": {},
        "markdown_postprocess": {},
    }

    # 收集真正参与复现的全局配置和当前模式配置
    for key, value in st.session_state.items():
        if key in GLOBAL_STATE_EXCLUDE_KEYS:
            continue
        if hasattr(value, "__class__") and value.__class__.__name__ in ["UploadedFile", "FormSubmitter"]:
            continue

        if _is_persistable_global_key(key):
            config["global"][key] = value
        elif _is_persistable_mode_key(key, current_mode):
            config[current_mode][key] = value

    config["global"]["conversion_mode"] = current_mode

    # VLM 泛化模式的模板与 prompt 参数属于核心复现项
    if current_mode == "vlm_generalized":
        config["vlm_generalized"]["vlm_direct_prompt_template"] = st.session_state.get(
            "vlm_prompt_template_selector",
            st.session_state.get("vlm_direct_prompt_template", "default"),
        )

    if current_mode == "vlm_generalized" and "vlm_direct_preset_select" in st.session_state:
        preset_mapping = {
            "高准确性（默认）": "high_accuracy",
            "高准确性（推荐）": "high_accuracy",
            "平衡": "balanced",
            "创意": "creative",
        }
        display_name = st.session_state["vlm_direct_preset_select"]
        if display_name in preset_mapping:
            config["vlm_generalized"]["vlm_direct_api_preset"] = preset_mapping[display_name]

    if current_mode == "vlm_generalized":
        prompt_params = {}
        if "vlm_direct_text_direction_simple" in st.session_state:
            prompt_params["text_direction"] = st.session_state["vlm_direct_text_direction_simple"]
        if "vlm_direct_primary_language_simple" in st.session_state:
            primary_language = st.session_state["vlm_direct_primary_language_simple"]
            if primary_language and primary_language != "auto":
                prompt_params["primary_language"] = primary_language
        if "vlm_direct_handwriting_mode_simple" in st.session_state:
            prompt_params["handwriting_mode"] = st.session_state["vlm_direct_handwriting_mode_simple"]
        if "vlm_direct_describe_images_simple" in st.session_state:
            prompt_params["describe_images"] = st.session_state["vlm_direct_describe_images_simple"]
        if "vlm_direct_anti_hallucination_simple" in st.session_state:
            prompt_params["anti_hallucination"] = st.session_state["vlm_direct_anti_hallucination_simple"]
        if "vlm_direct_extract_bboxes_simple" in st.session_state:
            prompt_params["extract_bboxes"] = st.session_state["vlm_direct_extract_bboxes_simple"]
        if "vlm_direct_include_confidence_simple" in st.session_state:
            prompt_params["include_confidence"] = st.session_state["vlm_direct_include_confidence_simple"]
        if "vlm_direct_enhance_tables_equations_simple" in st.session_state:
            prompt_params["enhance_tables_equations"] = st.session_state["vlm_direct_enhance_tables_equations_simple"]
        if "vlm_direct_has_page_numbers_simple" in st.session_state:
            prompt_params["may_have_page_numbers"] = st.session_state["vlm_direct_has_page_numbers_simple"]
        if "vlm_direct_enable_marginalia_simple" in st.session_state:
            prompt_params["enable_marginalia"] = st.session_state["vlm_direct_enable_marginalia_simple"]
        if "vlm_direct_enable_footnotes_simple" in st.session_state:
            prompt_params["may_have_footnotes"] = st.session_state["vlm_direct_enable_footnotes_simple"]
        if prompt_params:
            config["vlm_generalized"]["vlm_direct_prompt_params"] = prompt_params

        if "vlm_output_formats" in st.session_state:
            config["vlm_generalized"]["final_output_formats"] = st.session_state["vlm_output_formats"]

        if "vlm_direct_enable_marginalia_simple" in st.session_state:
            config["vlm_generalized"]["vlm_direct_marginal_note_enabled"] = st.session_state["vlm_direct_enable_marginalia_simple"]
        else:
            config["vlm_generalized"]["vlm_direct_marginal_note_enabled"] = False
        config["vlm_generalized"]["vlm_direct_use_markdown_footnotes"] = False
        config["vlm_generalized"]["vlm_direct_footnote_backlink"] = False

    return config


def apply_config_to_session(config: dict):
    """将配置应用到 session_state"""
    if not config:
        return

    target_mode = _infer_config_mode(config)
    _clear_persisted_keys_for_mode(target_mode)

    for key, value in config.get("global", {}).items():
        if _is_persistable_global_key(key):
            st.session_state[key] = value

    for key, value in config.get(target_mode, {}).items():
        if _is_persistable_mode_key(key, target_mode):
            st.session_state[key] = value

    legacy_pipeline_to_global = {
        "printed_page_format_pipeline": "printed_page_format_global",
        "printed_page_custom_pattern_pipeline": "printed_page_custom_pattern_global",
    }
    for legacy_key, global_key in legacy_pipeline_to_global.items():
        if global_key not in st.session_state and legacy_key in st.session_state:
            st.session_state[global_key] = st.session_state[legacy_key]


@st.cache_resource(show_spinner=False)
def get_artifacts():
    with st.spinner("正在加载模型..."):
        return load_models()



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


# ==================== 应用已加载的配置 ====================
if "loaded_config" in st.session_state:
    apply_config_to_session(st.session_state["loaded_config"])
    del st.session_state["loaded_config"]


# ==================== 侧边栏 ====================
with st.sidebar:
    st.header("⚙️ 配置面板")
    st.caption("可将稳定配置保存为预设；页码锚点等核心配置会一并保存。")

    # ==================== 配置管理 ====================
    api_profiles = config_manager.list_api_profiles()
    api_profile_map = {p["name"]: p for p in api_profiles}

    # 兼容迁移：把旧 key 挪到新的 widget key，避免 Streamlit 对已实例化 widget key 的写入冲突
    legacy_to_widget_keys = {
        "markdown_postprocess_llm_provider": "markdown_postprocess_llm_provider_widget",
        "markdown_postprocess_llm_base_url": "markdown_postprocess_llm_base_url_widget",
        "markdown_postprocess_llm_model": "markdown_postprocess_llm_model_widget",
        "markdown_postprocess_llm_api_key": "markdown_postprocess_llm_api_key_widget",
        "markdown_postprocess_llm_timeout": "markdown_postprocess_llm_timeout_widget",
        "markdown_postprocess_llm_max_retries": "markdown_postprocess_llm_max_retries_widget",
    }
    for legacy_key, widget_key in legacy_to_widget_keys.items():
        if legacy_key in st.session_state:
            if widget_key not in st.session_state:
                st.session_state[widget_key] = st.session_state[legacy_key]
            del st.session_state[legacy_key]

    pending_markdown_postprocess_api_profile = st.session_state.pop("pending_markdown_postprocess_api_profile", None)
    if pending_markdown_postprocess_api_profile:
        profile = config_manager.load_api_profile(pending_markdown_postprocess_api_profile)
        if profile:
            st.session_state["markdown_postprocess_llm_provider_widget"] = profile.get("provider", "openai")
            st.session_state["markdown_postprocess_llm_base_url_widget"] = profile.get("base_url", "")
            st.session_state["markdown_postprocess_llm_model_widget"] = profile.get("model", "")
            st.session_state["markdown_postprocess_llm_api_key_widget"] = profile.get("api_key", "")
            st.session_state["markdown_postprocess_api_profile_loaded_message"] = pending_markdown_postprocess_api_profile

    pending_vlm_api_profile = st.session_state.pop("pending_vlm_api_profile", None)
    if pending_vlm_api_profile:
        profile = config_manager.load_api_profile(pending_vlm_api_profile)
        if profile:
            provider = profile.get("provider", "openai_compatible")
            provider = {
                "openai": "openai_compatible",
                "lmstudio_native": "openai_compatible",
                "claude": "anthropic",
            }.get(provider, provider)
            if provider not in {"openai_compatible", "gemini", "anthropic"}:
                provider = "openai_compatible"
            st.session_state["vlm_api_provider"] = provider
            if provider == "openai_compatible":
                st.session_state["vlm_direct_base_url"] = profile.get("base_url", "")
                st.session_state["vlm_direct_model"] = profile.get("model", "")
                st.session_state["vlm_direct_api_key"] = profile.get("api_key", "")
            elif provider == "gemini":
                st.session_state["vlm_gemini_base_url"] = profile.get("base_url", "")
                st.session_state["vlm_gemini_model"] = profile.get("model", "")
                st.session_state["vlm_gemini_api_key"] = profile.get("api_key", "")
            elif provider == "anthropic":
                st.session_state["vlm_anthropic_base_url"] = profile.get("base_url", "")
                st.session_state["vlm_anthropic_model"] = profile.get("model", "")
                st.session_state["vlm_anthropic_api_key"] = profile.get("api_key", "")
            st.session_state["vlm_api_profile_loaded_message"] = pending_vlm_api_profile

    with st.expander("📋 配置管理", expanded=False):
        # 获取已保存的配置列表
        saved_configs = config_manager.list_configs()
        saved_config_map = {c["name"]: c for c in saved_configs}
        config_names = ["-- 不使用预设 --"] + [c["name"] for c in saved_configs]

        # 配置选择器
        selected_config = st.selectbox(
            "选择配置",
            options=config_names,
            index=0,
            key="config_selector",
            help="选择已保存的配置快速加载"
        )

        if selected_config != "-- 不使用预设 --":
            selected_meta = saved_config_map.get(selected_config, {})
            summary_parts = [
                selected_meta.get("mode", "unknown"),
                selected_meta.get("summary", "").strip(),
            ]
            summary_parts = [part for part in summary_parts if part]
            if summary_parts:
                st.caption(" | ".join(summary_parts))
            if selected_meta.get("description"):
                st.caption(selected_meta["description"])

        # 加载配置按钮
        if selected_config != "-- 不使用预设 --":
            col_load, col_delete = st.columns(2)
            with col_load:
                if st.button("📥 加载此配置", key="load_config_btn"):
                    loaded = config_manager.load_config(selected_config)
                    if loaded:
                        st.session_state["loaded_config"] = loaded
                        st.success(f"已加载配置: {selected_config}")
                        st.rerun()
                    else:
                        st.error("加载配置失败")
            with col_delete:
                confirm_delete = st.checkbox("确认删除", key="confirm_delete_config")
                if st.button("🗑️ 删除此配置", key="delete_config_btn", disabled=not confirm_delete):
                    if config_manager.delete_config(selected_config):
                        st.success(f"已删除配置: {selected_config}")
                        st.rerun()
                    else:
                        st.error("删除失败")

        st.markdown("---")

        # 保存当前配置
        st.markdown("**保存当前配置**")
        new_config_name = st.text_input("配置名称", key="new_config_name", placeholder="例如: 德文-fraktur-印刷")
        new_config_desc = st.text_input("配置描述", key="new_config_desc", placeholder="可选")
        current_save_mode = st.session_state.get("conversion_mode", "pipeline")
        st.caption(f"将保存为“{_build_config_save_scope_text(current_save_mode)}”，不会混入其他主分支的残留状态。")

        api_key_mode = st.radio(
            "API Key 处理",
            options=["exclude", "placeholder", "include"],
            format_func=lambda x: {"exclude": "不保存", "placeholder": "占位符", "include": "保留"}[x],
            index=1,
            horizontal=True,
            key="api_key_mode"
        )

        config_already_exists = bool(new_config_name and config_manager.config_exists(new_config_name.strip()))
        overwrite_save = st.checkbox(
            "覆盖同名配置",
            value=False,
            key="overwrite_save_config",
            disabled=not config_already_exists,
            help="仅当存在同名配置时生效。"
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
                        overwrite=overwrite_save
                    )
                    if success:
                        st.success(f"配置 '{new_config_name}' 已保存")
                        st.rerun()
                    else:
                        if config_manager.config_exists(new_config_name.strip()):
                            st.warning("同名配置已存在。勾选“覆盖同名配置”或更换名称后再保存。")
                        else:
                            st.error("保存失败")
                else:
                    st.warning("需要输入配置名称")

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
    output_formats = default_pipeline_output_formats()
    emit_middle_json = False
    emit_middle_report = False
    emit_middle_debug = False
    emit_middle_scholarly = False
    emit_middle_scholarly_report = False
    emit_layout_overlay = False
    emit_span_overlay = False
    emit_middle_full_json = False
    upload_mode = "上传文件"
    uploaded_files = []
    markdown_postprocess_input_kind = "markdown"
    middle_rerender_include_provenance = False
    middle_rerender_include_printed_page_comments = True
    middle_rerender_include_page_header_comments = True
    middle_rerender_include_page_footer_comments = True
    middle_rerender_include_margin_comments = True
    middle_rerender_include_page_separators = True
    middle_rerender_marginal_output_mode = "line_markers"
    middle_rerender_equation_output_mode = "humanities_safe"
    middle_rerender_apply_postprocess = False
    markdown_postprocess_enabled = False
    markdown_postprocess_enable_printed_page_repair = False
    markdown_postprocess_enable_llm = False
    markdown_postprocess_enable_cleanup = False
    markdown_postprocess_review_only = True
    markdown_postprocess_llm_provider = "lmstudio_native"
    markdown_postprocess_llm_base_url = "http://localhost:1234/api/v1/chat"
    markdown_postprocess_llm_model = ""
    markdown_postprocess_llm_api_key = ""
    markdown_postprocess_llm_timeout = 60
    markdown_postprocess_llm_max_retries = 1

    st.markdown("### 🧭 全局输出偏好")
    always_save_middle_json = st.checkbox(
        "始终保存 Middle JSON",
        help="对 Pipeline、VLM 泛化、VLM 特化统一生效：每次任务都会额外保存 *_middle.json 核心中间层，方便后续重渲染。",
        key="always_save_middle_json",
    )
    if always_save_middle_json != bool(_app_settings.get("always_save_middle_json", True)):
        next_settings = dict(_app_settings)
        next_settings["always_save_middle_json"] = bool(always_save_middle_json)
        if config_manager.save_app_settings(next_settings):
            _app_settings["always_save_middle_json"] = bool(always_save_middle_json)
    if always_save_middle_json:
        st.caption("已开启：正式输出之外会自动保留统一 Middle JSON；报告和调试文件仍按高级开关生成。")

    # 版面识别后端 defaults
    layout_backend = "surya"
    surya_layout_quality = st.session_state.get("surya_layout_quality", "fast")
    layout_dpi_override = st.session_state.get("layout_dpi_override")

    # OCR 后端 defaults
    ocr_backend = "surya"
    ocr_quality = st.session_state.get("ocr_quality", "auto")
    ocr_dpi_override = st.session_state.get("ocr_dpi_override")
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

    # Calamari defaults（确保即使不选 calamari 也不会 NameError）
    calamari_base_url = os.environ.get("CALAMARI_BASE_URL", "http://localhost:11800")
    calamari_model = os.environ.get("CALAMARI_MODEL", "gt4histocr")
    calamari_batch_size = 100
    calamari_timeout = 120
    calamari_sequential_mode = False
    calamari_trust_batch_order = False
    calamari_require_ordering_info = True
    calamari_fallback_to_sequential_on_ordering_failure = True
    calamari_preprocess = "otsu"
    calamari_crop_padding_px = 5
    calamari_crop_padding_frac = 0.08
    calamari_upscale_min_height = 0
    calamari_split_large_batches = True

    # Tesseract defaults（外部 CPU 可执行后端）
    tesseract_profile = "printed_latin"
    tesseract_cmd = os.environ.get("CONTEXTURE_TESSERACT_CMD", "")
    tesseract_lang = "eng"
    tesseract_oem = 1
    tesseract_psm = 7
    tesseract_timeout = 30
    tesseract_omp_thread_limit = 1
    tesseract_tessdata_prefix = os.environ.get("TESSDATA_PREFIX", "")
    tesseract_user_words = ""
    tesseract_user_patterns = ""
    tesseract_extra_config = ""
    tesseract_line_psm = 1
    tesseract_line_preprocess = "otsu"
    tesseract_line_upscale_min_height = 0
    tesseract_thresholding_method = "auto"
    ocr_crop_padding_px = DEFAULT_OCR_CROP_PADDING_PX
    ocr_crop_padding_frac = DEFAULT_OCR_CROP_PADDING_FRAC
    ocr_crop_preprocess = "otsu"
    ocr_crop_upscale_min_height = DEFAULT_OCR_CROP_UPSCALE_MIN_HEIGHT

    # VLM defaults（确保即使不选 vlm 也不会 NameError）
    openai_base_url = os.environ.get("OPENAI_BASE_URL", "http://127.0.0.1:1234/v1")
    openai_model = os.environ.get("OPENAI_MODEL", "churro-3b")
    openai_api_key = os.environ.get("OPENAI_API_KEY", "lm-studio")
    openai_max_concurrent = int(os.environ.get("OPENAI_MAX_CONCURRENT", "3"))
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
    col1, col2, col3 = st.columns([4, 1, 1.4])
    with col1:
        out_dir = st.text_input("输出文件夹", value=st.session_state.output_dir, label_visibility="collapsed", key="out_dir")
        if out_dir != st.session_state.output_dir:
            normalized_out_dir = os.path.normpath(out_dir.strip()) if out_dir.strip() else st.session_state.output_dir
            os.makedirs(normalized_out_dir, exist_ok=True)
            st.session_state.output_dir = normalized_out_dir
    with col2:
        folder_uri = _local_folder_uri(st.session_state.output_dir)
        if folder_uri:
            st.link_button("📂", folder_uri, help="打开输出文件夹", use_container_width=True)
        else:
            st.button("📂", help="输出文件夹路径无效", disabled=True, use_container_width=True)
    with col3:
        if st.button("保存默认值", key="save_output_dir_default_btn", help="将当前输出目录保存为应用默认值"):
            normalized_out_dir = os.path.normpath(st.session_state.output_dir.strip()) if st.session_state.output_dir.strip() else "output"
            os.makedirs(normalized_out_dir, exist_ok=True)
            st.session_state.output_dir = normalized_out_dir
            st.session_state.out_dir = normalized_out_dir
            if config_manager.save_app_settings({"output_dir": normalized_out_dir}):
                st.success("已保存为默认输出目录")
            else:
                st.error("默认输出目录保存失败")
    st.caption("修改输入框会立即作用于当前会话；点击“保存默认值”后，后续启动应用会继续使用该目录。")

    st.divider()

    # ==================== 3. 转换模式选择 ====================
    st.subheader("⚙️ 转换模式")
    conversion_mode = st.radio(
        "选择转换模式",
        options=["pipeline", "vlm_generalized", "vlm_specialized", "markdown_postprocess"],
        index=0,
        format_func=lambda x: {
            "pipeline": "🔧 Pipeline模式",
            "vlm_generalized": "🌐 VLM 泛化模式",
            "vlm_specialized": "🎯 VLM 特化模式",
            "markdown_postprocess": "📝 Markdown 后处理",
        }.get(x, x),
        horizontal=True,
        help="Pipeline 拆分版面、OCR 和后处理；VLM 泛化整页调用通用模型；VLM 特化调用文档解析专用模型。",
        key="conversion_mode"
    )

    if conversion_mode == "vlm_generalized":
        st.info(MODE_DESCRIPTIONS["vlm_generalized"])
    elif conversion_mode == "vlm_specialized":
        st.warning(MODE_DESCRIPTIONS["vlm_specialized"])
    elif conversion_mode == "markdown_postprocess":
        pass
    else:
        st.success(MODE_DESCRIPTIONS["pipeline"])
        st.info("首次使用 Pipeline 中的 Surya 版面识别或 OCR 时，程序需要联网下载模型并写入本地缓存；首次运行通常耗时更长。")

    st.divider()

    if conversion_mode == "markdown_postprocess":
        st.subheader("🧰 后处理工具")
        markdown_postprocess_input_kind = st.radio(
            "功能",
            options=["markdown", "middle_json", "mineru_json"],
            index=0,
            format_func=lambda x: {
                "markdown": "Markdown 页码修正",
                "middle_json": "Contexture Middle JSON 重渲染",
                "mineru_json": "MinerU 官方 JSON 转换",
            }.get(x, x),
            horizontal=True,
            key="markdown_postprocess_input_kind",
            help="三项功能相互独立。MinerU 官方 JSON 先导入为 Contexture Middle，再按学术版规则渲染 Markdown。",
        )
        markdown_postprocess_enabled = True
        middle_rerender_include_provenance = False
        middle_rerender_include_printed_page_comments = True
        middle_rerender_include_page_header_comments = True
        middle_rerender_include_page_footer_comments = True
        middle_rerender_include_margin_comments = True
        middle_rerender_include_page_separators = True
        middle_rerender_marginal_output_mode = "line_markers"
        middle_rerender_equation_output_mode = "humanities_safe"
        middle_rerender_apply_postprocess = False

        if markdown_postprocess_input_kind == "middle_json":
            st.markdown("**🧱 Contexture Middle JSON 重渲染**")
            st.info("读取 Contexture Middle JSON，按当前学术版 Markdown 规则重新渲染；不会调用模型或 API。")
            with st.expander("渲染配置", expanded=True):
                col_render_1, col_render_2 = st.columns(2)
                with col_render_1:
                    middle_rerender_include_printed_page_comments = st.checkbox(
                        "输出印刷页码注释",
                        value=True,
                        key="middle_rerender_include_printed_page_comments",
                        help="输出形如 `<!-- Page: 35 -->` 的印刷页码注释。",
                    )
                    middle_rerender_include_page_header_comments = st.checkbox(
                        "输出页眉注释",
                        value=True,
                        key="middle_rerender_include_page_header_comments",
                    )
                    middle_rerender_include_page_separators = st.checkbox(
                        "输出页面分隔线",
                        value=True,
                        key="middle_rerender_include_page_separators",
                        help="在页码锚点后输出 `---`，保持与主转换链路一致。",
                    )
                with col_render_2:
                    middle_rerender_include_page_footer_comments = st.checkbox(
                        "输出页脚注释",
                        value=True,
                        key="middle_rerender_include_page_footer_comments",
                    )
                    middle_rerender_include_margin_comments = st.checkbox(
                        "输出边注语法标记",
                        value=True,
                        key="middle_rerender_include_margin_comments",
                        help="输出 `<!-- Margin:left/right -->` 边注块；关闭后边注内容以普通文本保留。",
                    )
                    middle_rerender_include_provenance = st.checkbox(
                        "输出块级 provenance 注释",
                        value=False,
                        key="middle_rerender_include_provenance",
                        help="用于调试 block 来源、置信度和锚点；正式阅读版通常保持关闭。",
                    )
                middle_rerender_marginal_output_mode = st.selectbox(
                    "边注输出方式",
                    options=["line_markers", "margin_comments", "plain", "drop"],
                    index=0,
                    format_func=lambda x: {
                        "line_markers": "旁注注释（纯数字简写为行号）",
                        "margin_comments": "旁注注释（全部保持旁注）",
                        "plain": "普通文本",
                        "drop": "丢弃",
                    }.get(x, x),
                    key="middle_rerender_marginal_output_mode",
                    help="只影响已识别为 MarginalNote 的块；纯数字旁注可简写为 `<!-- Line: n -->`。",
                )
                middle_rerender_equation_output_mode = st.selectbox(
                    "公式输出方式",
                    options=["humanities_safe", "plain", "math"],
                    index=0,
                    format_func=lambda x: {
                        "humanities_safe": "人文学术安全（疑似校勘索引转普通文本）",
                        "plain": "全部公式按普通文本",
                        "math": "保留全部公式块",
                    }.get(x, x),
                    key="middle_rerender_equation_output_mode",
                    help="用于处理 `1065_{3}`、`\\parallel~1072_{38}` 这类被误识别为公式的校勘索引。",
                )
            st.caption("输出包含重渲染 Markdown、Contexture Middle 校验报告、debug Markdown 和 scholarly report。")
            st.divider()
        elif markdown_postprocess_input_kind == "mineru_json":
            st.markdown("**⛏️ MinerU 官方 JSON 转换**")
            st.info("支持 MinerU 官方 `*_content_list.json`、`*_content_list_v2.json` 和 `*_middle.json`。导入流程先转换为 Contexture Middle JSON，再生成标准学术版 Markdown；不会调用 MinerU API 或模型。")
            with st.expander("渲染配置", expanded=True):
                col_render_1, col_render_2 = st.columns(2)
                with col_render_1:
                    middle_rerender_include_printed_page_comments = st.checkbox(
                        "输出印刷页码注释",
                        value=True,
                        key="mineru_import_include_printed_page_comments",
                        help="输出形如 `<!-- Page: 35 -->` 的印刷页码注释。",
                    )
                    middle_rerender_include_page_header_comments = st.checkbox(
                        "输出页眉注释",
                        value=True,
                        key="mineru_import_include_page_header_comments",
                    )
                    middle_rerender_include_page_separators = st.checkbox(
                        "输出页面分隔线",
                        value=True,
                        key="mineru_import_include_page_separators",
                        help="在页码锚点后输出 `---`，保持与主转换链路一致。",
                    )
                with col_render_2:
                    middle_rerender_include_page_footer_comments = st.checkbox(
                        "输出页脚注释",
                        value=True,
                        key="mineru_import_include_page_footer_comments",
                    )
                    middle_rerender_include_margin_comments = st.checkbox(
                        "输出边注语法标记",
                        value=True,
                        key="mineru_import_include_margin_comments",
                        help="输出 `<!-- Margin:left/right -->` 边注块；关闭后边注内容以普通文本保留。",
                    )
                    middle_rerender_include_provenance = st.checkbox(
                        "输出块级 provenance 注释",
                        value=False,
                        key="mineru_import_include_provenance",
                        help="用于检查 MinerU 原始类型、bbox 与 Contexture Middle 块之间的映射关系。",
                    )
                middle_rerender_marginal_output_mode = st.selectbox(
                    "边注输出方式",
                    options=["line_markers", "margin_comments", "plain", "drop"],
                    index=0,
                    format_func=lambda x: {
                        "line_markers": "旁注注释（纯数字简写为行号）",
                        "margin_comments": "旁注注释（全部保持旁注）",
                        "plain": "普通文本",
                        "drop": "丢弃",
                    }.get(x, x),
                    key="mineru_import_marginal_output_mode",
                    help="只影响已识别为 MarginalNote 的块；纯数字旁注可简写为 `<!-- Line: n -->`。",
                )
                middle_rerender_equation_output_mode = st.selectbox(
                    "公式输出方式",
                    options=["humanities_safe", "plain", "math"],
                    index=0,
                    format_func=lambda x: {
                        "humanities_safe": "人文学术安全（疑似校勘索引转普通文本）",
                        "plain": "全部公式按普通文本",
                        "math": "保留全部公式块",
                    }.get(x, x),
                    key="mineru_import_equation_output_mode",
                    help="用于处理 `1065_{3}`、`\\parallel~1072_{38}` 这类被误识别为公式的校勘索引。",
                )
            st.caption("导入后的 Contexture Middle JSON 会随结果保存，便于复查和再次重渲染。")
            st.divider()
        else:
            markdown_postprocess_enable_printed_page_repair = True
            st.markdown("**📖 印刷页码修正**")
            page_repair_mode = st.radio(
                "修正方式",
                options=["llm", "rules"],
                index=0,
                format_func=lambda x: {
                    "llm": "LLM 稀疏修正",
                    "rules": "规则保守修正（兜底）",
                }.get(x, x),
                horizontal=True,
                key="markdown_postprocess_page_repair_mode",
            )
            markdown_postprocess_enable_llm = page_repair_mode == "llm"
            markdown_postprocess_enable_cleanup = False
            st.caption("只处理已有 Markdown 的印刷页码问题；不会重新解析 PDF 或 Middle JSON。")
            markdown_postprocess_review_only = st.checkbox(
                "稀疏 review 模式",
                value=True,
                key="markdown_postprocess_review_only",
                help="开启后只输出 review 报告；关闭后写入 validator 接受的局部修正。",
            )

            if page_repair_mode == "llm":
                if markdown_postprocess_review_only:
                    st.info("当前使用 LLM 稀疏 review：保留原 Markdown，只输出 review 报告。")
                else:
                    st.info("当前使用 LLM 稀疏 apply：仅写入 validator 接受的局部页码修正。")
            else:
                st.info("当前使用规则保守修正兜底方案：无需 LLM，但修正能力更弱。")

            if markdown_postprocess_enable_llm:
                st.markdown("**🔌 API 配置**")
                st.caption("仅 Markdown 页码修正选择 LLM 时调用；JSON 重渲染与转换不会使用这里。")
                markdown_postprocess_llm_provider = st.radio(
                    "接口类型",
                    options=["lmstudio_native", "openai"],
                    index=0,
                    format_func=lambda x: {
                        "lmstudio_native": "LM Studio 兼容接口",
                        "openai": "OpenAI 兼容接口",
                    }.get(x, x),
                    horizontal=True,
                    key="markdown_postprocess_llm_provider_widget",
                )
                default_base_url = (
                    "http://localhost:1234/api/v1/chat"
                    if markdown_postprocess_llm_provider == "lmstudio_native"
                    else "http://localhost:1234/v1/chat/completions"
                )
                markdown_postprocess_llm_base_url = st.text_input(
                    "Base URL",
                    value=st.session_state.get("markdown_postprocess_llm_base_url_widget", default_base_url),
                    key="markdown_postprocess_llm_base_url_widget",
                )
                markdown_postprocess_llm_model = st.text_input(
                    "模型名称",
                    value=st.session_state.get("markdown_postprocess_llm_model_widget", ""),
                    key="markdown_postprocess_llm_model_widget",
                )
                markdown_postprocess_llm_api_key = st.text_input(
                    "API Key（可选）",
                    value=st.session_state.get(
                        "markdown_postprocess_llm_api_key_widget",
                        "lm-studio" if markdown_postprocess_llm_provider == "lmstudio_native" else "",
                    ),
                    type="password",
                    key="markdown_postprocess_llm_api_key_widget",
                )
                col_llm_1, col_llm_2 = st.columns(2)
                with col_llm_1:
                    markdown_postprocess_llm_timeout = st.number_input(
                        "超时（秒）",
                        min_value=10,
                        max_value=600,
                        value=int(st.session_state.get("markdown_postprocess_llm_timeout_widget", 60)),
                        key="markdown_postprocess_llm_timeout_widget",
                    )
                with col_llm_2:
                    markdown_postprocess_llm_max_retries = st.number_input(
                        "重试次数",
                        min_value=0,
                        max_value=5,
                        value=int(st.session_state.get("markdown_postprocess_llm_max_retries_widget", 1)),
                        key="markdown_postprocess_llm_max_retries_widget",
                    )

                st.markdown("**💾 API 配置保存**")
                if st.session_state.get("markdown_postprocess_api_profile_loaded_message"):
                    st.success(f"已载入 API 预设: {st.session_state['markdown_postprocess_api_profile_loaded_message']}")
                    del st.session_state["markdown_postprocess_api_profile_loaded_message"]
                markdown_postprocess_api_profiles = config_manager.list_api_profiles()
                markdown_postprocess_api_options = ["不使用预设"] + [p["name"] for p in markdown_postprocess_api_profiles]
                selected_markdown_postprocess_api_profile = st.selectbox(
                    "API 预设",
                    markdown_postprocess_api_options,
                    key="markdown_postprocess_api_profile_select",
                )
                col_mp_api_load, col_mp_api_save = st.columns(2)
                with col_mp_api_load:
                    if st.button(
                        "📥 载入 API 预设",
                        key="load_markdown_postprocess_api_profile_btn",
                        disabled=selected_markdown_postprocess_api_profile == "不使用预设",
                    ):
                        st.session_state["pending_markdown_postprocess_api_profile"] = selected_markdown_postprocess_api_profile
                        st.rerun()
                with col_mp_api_save:
                    markdown_postprocess_api_profile_name = st.text_input(
                        "预设名称",
                        key="markdown_postprocess_api_profile_name",
                        placeholder="例如: kimi-openai / lmstudio-local",
                    )
                    markdown_postprocess_api_profile_exists = bool(
                        markdown_postprocess_api_profile_name
                        and config_manager.api_profile_exists(markdown_postprocess_api_profile_name.strip())
                    )
                    overwrite_markdown_postprocess_api_profile = st.checkbox(
                        "覆盖同名",
                        value=False,
                        key="overwrite_markdown_postprocess_api_profile",
                        disabled=not markdown_postprocess_api_profile_exists,
                    )
                    if st.button("💾 保存 API 预设", key="save_markdown_postprocess_api_profile_btn"):
                        if markdown_postprocess_api_profile_name:
                            success = config_manager.save_api_profile(
                                name=markdown_postprocess_api_profile_name,
                                provider=st.session_state.get("markdown_postprocess_llm_provider_widget", markdown_postprocess_llm_provider),
                                base_url=st.session_state.get("markdown_postprocess_llm_base_url_widget", markdown_postprocess_llm_base_url),
                                model=st.session_state.get("markdown_postprocess_llm_model_widget", markdown_postprocess_llm_model),
                                api_key=st.session_state.get("markdown_postprocess_llm_api_key_widget", markdown_postprocess_llm_api_key),
                                description="markdown postprocess api preset",
                                overwrite=overwrite_markdown_postprocess_api_profile,
                            )
                            if success:
                                st.success(f"API 预设 '{markdown_postprocess_api_profile_name}' 已保存")
                                st.rerun()
                            else:
                                if config_manager.api_profile_exists(markdown_postprocess_api_profile_name.strip()):
                                    st.warning("同名 API 预设已存在。勾选“覆盖同名”或更换名称后再保存。")
                                else:
                                    st.error("API 预设保存失败")
                        else:
                            st.warning("需要输入 API 预设名称")

        st.caption("后处理默认另存为新文件并输出报告；三项功能相互独立，重渲染与 JSON 导入不会调用模型。")
        st.divider()

    # ==================== 4. 统一页码锚点配置（全局） ====================
    page_anchor_position = "before"
    enable_page_anchors = True
    extract_printed_pages = True
    emit_page_header_comment = False
    emit_page_footer_comment = False
    keep_pageheader_in_output = False
    keep_pagefooter_in_output = False
    printed_page_zones = ["footer", "header"]
    printed_page_format = "auto"
    printed_page_custom_pattern = ""
    printed_page_header_start = 0.0
    printed_page_header_end = 0.15
    printed_page_footer_start = 0.83
    vlm_printed_page_patterns = None
    enable_marginal_detection = False
    native_marginalia_enabled = False
    heuristic_marginal_detection_enabled = False
    marginal_output_mode = "drop"
    left_margin_threshold = 0.15
    right_margin_threshold = 0.85
    top_margin_threshold = 0.10
    bottom_margin_threshold = 0.90
    vertical_center_tolerance = 0.05
    enable_inline_detection = False
    font_size_ratio_threshold = 0.75
    max_inline_annotation_length = 100
    custom_id_source = "none"
    custom_id_data = None

    if conversion_mode != "markdown_postprocess":
        st.subheader("📍 页码锚点配置")
        st.caption("PDF 页码锚点默认启用，当前区块的关键设置会参与配置保存/加载；不同主分支对印刷页码的提取机制各不相同。")
        with st.expander("页码锚点设置", expanded=False):
            st.markdown("**📄 PDF 页码锚点**")
            st.success("已启用 - 格式：`{n}`（n = PDF 页序号）")
            st.caption("每页开头自动添加 PDF 页码锚点，便于引用和跳转")

            if conversion_mode == "vlm_generalized":
                page_anchor_position = st.radio(
                    "锚点位置",
                    options=["before", "after", "both"],
                    index=0,
                    format_func=lambda x: {
                        "before": "页面前",
                        "after": "页面后",
                        "both": "页面前后",
                    }.get(x, x),
                    horizontal=True,
                    help="锚点插入位置（仅 VLM 泛化模式支持）",
                    key="page_anchor_position_global",
                )
            else:
                page_anchor_position = "before"

            enable_page_anchors = True

            st.markdown("---")
            st.markdown("**📖 印刷页码提取**")
            extract_printed_pages = st.checkbox(
                "启用印刷页码提取",
                value=True,
                help="自动识别文档中的印刷页码，生成 `<!-- Page: X -->` 标签",
                key="extract_printed_pages_global",
            )

            emit_page_header_comment = False
            emit_page_footer_comment = False
            keep_pageheader_in_output = False
            keep_pagefooter_in_output = False
            printed_page_zones = ["footer", "header"]
            printed_page_format_options = ["arabic", "roman", "chinese", "auto"]
            current_printed_page_format = st.session_state.get("printed_page_format_global", "auto")
            if current_printed_page_format not in printed_page_format_options:
                current_printed_page_format = "auto"
            printed_page_format = st.selectbox(
                "页码格式",
                options=printed_page_format_options,
                index=printed_page_format_options.index(current_printed_page_format),
                format_func=lambda x: {
                    "arabic": "阿拉伯数字",
                    "roman": "罗马数字",
                    "chinese": "中文数字",
                    "auto": "自动检测",
                }.get(x, x),
                disabled=not extract_printed_pages,
                help="跨模式共享的印刷页码解释规则。Pipeline、VLM 泛化和 VLM 特化均使用这里的页码语义。",
                key="printed_page_format_global",
            )
            printed_page_custom_pattern = st.text_input(
                "自定义页码正则（可选）",
                value=st.session_state.get("printed_page_custom_pattern_global", ""),
                disabled=not extract_printed_pages,
                help="跨模式共享的自定义页码匹配正则。留空则使用上方格式设置。VLM 模式仍可在下方补充正则提取规则。",
                key="printed_page_custom_pattern_global",
            )
            printed_page_header_start = 0.0
            printed_page_header_end = 0.15
            printed_page_footer_start = 0.83

            is_direct_mode = conversion_mode in ["vlm_generalized", "vlm_specialized"]
            vlm_printed_page_patterns = None

            if conversion_mode == "pipeline":
                st.caption("Pipeline 模式的页眉页脚与页码区域设置已移至下方“Pipeline 后处理配置 > 页眉页脚处理”。")

            if is_direct_mode and extract_printed_pages:
                st.caption("通过正则表达式从 Markdown 输出中提取页码。")

                regex_presets = {
                    "default": {
                        "name": "默认（阿拉伯/罗马数字）",
                        "patterns": [
                            r"<!--\s*(?:PageHeader|page-header):\s*(\d{1,4})\s*-->",
                            r"<!--\s*(?:PageHeader|page-header):\s*([IVXLCDM]{1,8})\s*-->",
                            r"<!--\s*(?:PageHeader|page-header):\s*([ivxlcdm]{1,8})\s*-->",
                            r"<!--\s*(?:PageFooter|page-footer):\s*(\d{1,4})\s*-->",
                            r"^\s*[-—]?\s*(\d{1,4})\s*[-—]?\s*$",
                            r"(?:^|\s)([IVXLCDM]{2,8})(?:\s|$)",
                            r"(?:^|\s)([ivxlcdm]{2,8})(?:\s|$)",
                        ],
                        "description": "通用印刷页码：阿拉伯数字(1-9999)、罗马数字(I-MMMM)",
                    },
                    "chinese": {
                        "name": "中文页码",
                        "patterns": [
                            r"<!--\s*(?:PageHeader|page-header):\s*([一二三四五六七八九十百千零〇]+)\s*-->",
                            r"第([一二三四五六七八九十百千零〇]+)[頁葉页叶]",
                            r"([一二三四五六七八九十百千零〇]+)[頁葉页叶]",
                            r"[頁葉页叶]([一二三四五六七八九十百千零〇]+)",
                        ],
                        "description": "中文数字页码（古籍、线装书）",
                    },
                    "custom": {
                        "name": "自定义正则",
                        "patterns": [],
                        "description": "手动输入正则表达式",
                    },
                }
                if st.session_state.get("regex_preset_key_global") not in regex_presets:
                    st.session_state["regex_preset_key_global"] = "default"

                regex_preset_key = st.selectbox(
                    "正则预设",
                    options=list(regex_presets.keys()),
                    index=0,
                    format_func=lambda x: regex_presets[x]["name"],
                    disabled=not (is_direct_mode and extract_printed_pages),
                    help="选择预设的正则表达式组合，或选择“自定义正则”手动输入。",
                    key="regex_preset_key_global",
                )

                st.caption(f"📝 {regex_presets[regex_preset_key]['description']}")

                if regex_preset_key == "custom":
                    default_patterns_text = ""
                else:
                    default_patterns_text = "\n".join(regex_presets[regex_preset_key]["patterns"])

                show_editor = (regex_preset_key == "custom") or st.checkbox(
                    "编辑正则表达式",
                    value=False,
                    disabled=not (is_direct_mode and extract_printed_pages),
                    help="展开编辑器查看或修改正则表达式。",
                    key="show_regex_editor_global",
                )

                if show_editor:
                    vlm_patterns_text = st.text_area(
                        "正则表达式列表（每行一个）",
                        value=default_patterns_text,
                        height=120,
                        help="每行一个正则表达式，按顺序尝试匹配。捕获组 (...) 中的内容将作为页码。",
                        disabled=not extract_printed_pages,
                        key="vlm_patterns_text_global",
                    )
                else:
                    vlm_patterns_text = default_patterns_text

                vlm_printed_page_patterns = [
                    pattern.strip()
                    for pattern in vlm_patterns_text.split("\n")
                    if pattern.strip()
                ]
                st.success(f"正则提取已启用，共 {len(vlm_printed_page_patterns)} 条规则")

            st.markdown("---")
            st.markdown("**📝 特殊-边码（古籍与经典文献）**")
            st.caption("后端原生边注、坐标启发式恢复和 Markdown 输出方式分开控制。MinerU/MinerU-VL/Paddle/VLM 等后端的原生标签会优先保留。")

            legacy_marginal_detection = bool(st.session_state.get("enable_marginal_detection_global", False))
            native_marginalia_enabled = st.checkbox(
                "接收后端原生页边注",
                value=bool(st.session_state.get("native_marginalia_enabled_global", legacy_marginal_detection)),
                help="保留后端原生识别出的 aside_text/page_aside_text/marginal_note。不会把页眉页脚改成旁注。",
                key="native_marginalia_enabled_global",
            )
            heuristic_marginal_detection_enabled = st.checkbox(
                "启用坐标启发式恢复",
                value=bool(st.session_state.get("heuristic_marginal_detection_enabled_global", legacy_marginal_detection)),
                help="只从 Text 块中按坐标和内容恢复漏检边码/行号；不会处理后端原生 PageHeader/PageFooter/Footnote。",
                key="heuristic_marginal_detection_enabled_global",
            )
            enable_marginal_detection = native_marginalia_enabled or heuristic_marginal_detection_enabled
            st.session_state["enable_marginal_detection_global"] = enable_marginal_detection
            st.caption(f"兼容总开关：{'已启用' if enable_marginal_detection else '已关闭'}")
            marginal_mode_options = ["line_markers", "margin_comments", "plain", "drop"]
            current_marginal_output_mode = normalize_marginal_output_mode(
                st.session_state.get("marginal_output_mode_global"),
                enable_marginal_detection=enable_marginal_detection,
            )
            marginal_output_mode = st.selectbox(
                "边码输出方式",
                options=marginal_mode_options,
                index=marginal_mode_options.index(current_marginal_output_mode),
                format_func=lambda x: {
                    "line_markers": "旁注注释（纯数字简写为行号）",
                    "margin_comments": "旁注注释（全部保持旁注）",
                    "plain": "普通文本",
                    "drop": "丢弃",
                }.get(x, x),
                help="控制已识别页边旁注在 Markdown 中的表现；只有纯数字旁注会在第一档输出为 `<!-- Line: n -->`。",
                key="marginal_output_mode_global",
            )

            if heuristic_marginal_detection_enabled:
                st.markdown("**位置阈值配置**")
                col1, col2 = st.columns(2)
                with col1:
                    left_margin_threshold = st.slider(
                        "左边栏阈值",
                        min_value=0.05,
                        max_value=0.30,
                        value=0.15,
                        step=0.01,
                        help="左边栏区域宽度（页面宽度比例）",
                        key="left_margin_threshold_global",
                    )
                    right_margin_threshold = st.slider(
                        "右边栏阈值",
                        min_value=0.70,
                        max_value=0.95,
                        value=0.85,
                        step=0.01,
                        help="右边栏区域起始位置（页面宽度比例）",
                        key="right_margin_threshold_global",
                    )
                with col2:
                    top_margin_threshold = st.slider(
                        "上边栏阈值",
                        min_value=0.05,
                        max_value=0.20,
                        value=0.10,
                        step=0.01,
                        help="上边栏区域高度（页面高度比例）",
                        key="top_margin_threshold_global",
                    )
                    bottom_margin_threshold = st.slider(
                        "下边栏阈值",
                        min_value=0.80,
                        max_value=0.95,
                        value=0.90,
                        step=0.01,
                        help="下边栏区域起始位置（页面高度比例）",
                        key="bottom_margin_threshold_global",
                    )
                vertical_center_tolerance = st.slider(
                    "垂直中线容差",
                    min_value=0.01,
                    max_value=0.10,
                    value=0.05,
                    step=0.01,
                    help="版心叶码检测的中线容差（页面宽度比例）",
                    key="vertical_center_tolerance_global",
                )

            enable_inline_detection = st.checkbox(
                "启用行内小字注识别",
                value=False,
                help="识别正文中的小字注释（如夹注、双行小字等）。",
                key="enable_inline_detection_global",
            )

            if enable_inline_detection:
                font_size_ratio_threshold = st.slider(
                    "字体比例阈值",
                    min_value=0.50,
                    max_value=0.90,
                    value=0.75,
                    step=0.05,
                    help="相对于主文本的字体大小比例。",
                    key="font_size_ratio_threshold_global",
                )
                max_inline_annotation_length = st.number_input(
                    "最大注释长度",
                    min_value=50,
                    max_value=200,
                    value=100,
                    step=10,
                    help="行内注释的最大字符数。",
                    key="max_inline_annotation_length_global",
                )

            st.markdown("---")
            st.markdown("**📋 自定义编号**")
            st.caption("为页面指定自定义编号（如档案编号 SC001），替代自动识别的印刷页码。")

            custom_id_source = st.selectbox(
                "编号来源",
                options=["none", "file", "list", "auto"],
                index=0,
                format_func=lambda x: {
                    "none": "无（使用印刷页码）",
                    "file": "上传文件（CSV/JSON）",
                    "list": "手动输入列表",
                    "auto": "自动生成（SC 001, SC 002...）",
                }.get(x, x),
                help="选择自定义编号的来源方式。",
                key="custom_id_source_global",
            )

            custom_id_data = None

            if custom_id_source == "file":
                st.info("上传 CSV 或 JSON 文件，格式：页序,自定义编号。")
                uploaded_id_file = st.file_uploader(
                    "上传页码映射文件",
                    type=["csv", "json"],
                    help="CSV 格式：0,sc001；JSON 格式：{\"0\": \"sc001\", \"1\": \"sc002\"}",
                    key="uploaded_id_file_global",
                )
                if uploaded_id_file:
                    custom_id_data = uploaded_id_file
            elif custom_id_source == "list":
                st.info("手动输入每页的自定义编号，用逗号或换行分隔。")
                custom_id_list = st.text_area(
                    "自定义编号列表",
                    value="sc001, sc002, sc003",
                    height=100,
                    help="输入每页的自定义编号，按页序排列。",
                    key="custom_id_list_global",
                )
                if custom_id_list:
                    custom_id_data = [
                        item.strip()
                        for item in custom_id_list.replace("\n", ",").split(",")
                        if item.strip()
                    ]
            elif custom_id_source == "auto":
                st.info("自动生成连续编号，如 SC 001、SC 002。")
                col1, col2, col3 = st.columns(3)
                with col1:
                    auto_prefix = st.text_input(
                        "编号前缀",
                        value="SC",
                        help="自动生成编号的前缀。",
                        key="auto_prefix_global",
                    )
                with col2:
                    auto_start = st.number_input(
                        "起始编号",
                        min_value=1,
                        value=1,
                        help="起始值。",
                        key="auto_start_global",
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
                            "_": "下划线（SC_001）",
                        }.get(x, x),
                        key="auto_separator_global",
                    )
                auto_digits = st.slider(
                    "编号位数",
                    min_value=2,
                    max_value=6,
                    value=3,
                    help="编号的位数（如 3 位：001, 002）。",
                    key="auto_digits_global",
                )
                custom_id_data = {
                    "prefix": auto_prefix,
                    "start": auto_start,
                    "digits": auto_digits,
                    "separator": auto_separator,
                }

        st.divider()

    # ==================== 5. 配置区域（根据转换模式显示不同内容） ====================
    if conversion_mode == "vlm_specialized":
        # ==================== VLM 特化模式配置 ====================
        st.subheader("🎯 VLM 特化模式配置")

        # OCR 后端选择
        specialized_ocr_backend_options = ["chandra", "churro", "chrome_screenai", "paddleocr_vl", "mineru_vl", "surya2"]
        current_specialized_ocr_backend = st.session_state.get("ocr_backend", "churro")
        if current_specialized_ocr_backend not in specialized_ocr_backend_options:
            current_specialized_ocr_backend = "churro"
        ocr_backend = st.selectbox(
            "OCR 后端",
            options=specialized_ocr_backend_options,
            index=specialized_ocr_backend_options.index(current_specialized_ocr_backend),
            format_func=lambda x: VLM_SPECIALIZED_BACKEND_LABELS[x],
            help="选择 OCR 后端模型",
            key="ocr_backend"
        )

        if ocr_backend == "churro":
            st.info("""
**Churro OCR** - 历史文档专用模型
- 基于 Qwen2-VL 架构微调（3B 参数）
- 专注历史手稿、古籍、档案文献
- 自动生成 XML/JSON/Markdown/HTML 四种格式
- 本地推理通常需要低并发运行
            """)
            chandra_version = None
            chandra_quant = None
            churro_version = default_version("churro")
            churro_quant_options = quant_options("churro", churro_version)
            churro_quant = st.selectbox(
                "Churro 量化",
                options=churro_quant_options,
                index=churro_quant_options.index(default_quant("churro")),
                key="churro_quant",
            )
            paddleocr_vl_prompt_label = "ocr"
            paddleocr_vl_version = None
            paddleocr_vl_mode = "auto"
            paddleocr_vl_layout_parsing_url = None
            mineru_vl_version = None
            mineru_vl_quant = None
            surya2_version = None
        elif ocr_backend == "paddleocr_vl":
            st.info("""
**PaddleOCR-VL** - 文档解析 VLM/Pipeline
- 配置官方 `/layout-parsing` 时优先使用完整文档解析结构
- 未配置官方服务时使用 `Layout Detection:` 获取整页文本与 LOC 坐标
- Contexture 会按现代印刷物规则保守恢复页码、页眉页脚、标题、正文和脚注
- 输出保留模型原始结果，并标准化为 Contexture 结构
            """)
            st.warning(
                "LM Studio 当前可能把 PaddleOCR-VL GGUF 条目标记为 text-only；"
                "如出现“不支持 image inputs”，需要换用支持图片输入的 PaddleOCR-VL runtime/service。"
            )
            chandra_version = None
            chandra_quant = None
            churro_version = None
            churro_quant = None
            paddleocr_vl_versions = version_options("paddleocr_vl")
            paddleocr_vl_default_version = default_version("paddleocr_vl")
            paddleocr_vl_version = st.selectbox(
                "PaddleOCR-VL 版本",
                options=paddleocr_vl_versions,
                index=paddleocr_vl_versions.index(paddleocr_vl_default_version),
                format_func=lambda x: version_label("paddleocr_vl", x),
                key="paddleocr_vl_version",
            )
            paddleocr_vl_mode = st.selectbox(
                "PaddleOCR-VL 调用模式",
                options=["auto", "layout_parsing", "vl_prompt"],
                index=0,
                format_func=lambda x: {
                    "auto": "自动：优先官方 /layout-parsing",
                    "layout_parsing": "官方 /layout-parsing",
                    "vl_prompt": "Prompt-only VLRecognition",
                }[x],
                help="官方 /layout-parsing 返回结构化 layoutParsingResults；Prompt-only 返回 LOC/OCR 文本，由 Contexture 做轻量结构恢复。",
                key="paddleocr_vl_mode",
            )
            paddleocr_vl_layout_parsing_url = st.text_input(
                "官方 /layout-parsing URL",
                value="",
                help="填写后 auto 模式会优先调用官方 PaddleOCR-VL 文档解析接口；留空则走 prompt fallback。",
                key="paddleocr_vl_layout_parsing_url",
            )
            mineru_vl_version = None
            mineru_vl_quant = None
            surya2_version = None
            paddleocr_vl_prompt_label = "layout_detection"
            st.caption("Prompt fallback：Layout Detection:（固定默认，用于整页坐标 OCR 与保守结构恢复）")
        elif ocr_backend == "mineru_vl":
            st.info("""
**MinerU-VL** - 文档理解 VLM
- 当前按 OpenAI 兼容接口挂载云端或 LM Studio 模型
- 使用官方兼容结构化解析：先 Layout Detection，再按块调用官方识别提示词
- 输出保留模型原始结果，先归一化 MinerU 协议，再标准化为 Contexture Middle
            """)
            chandra_version = None
            chandra_quant = None
            churro_version = None
            churro_quant = None
            paddleocr_vl_prompt_label = "ocr"
            paddleocr_vl_version = None
            paddleocr_vl_mode = "auto"
            paddleocr_vl_layout_parsing_url = None
            mineru_vl_versions = version_options("mineru_vl")
            mineru_vl_default_version = default_version("mineru_vl")
            mineru_vl_version = st.selectbox(
                "MinerU-VL 版本",
                options=mineru_vl_versions,
                index=mineru_vl_versions.index(mineru_vl_default_version),
                format_func=lambda x: version_label("mineru_vl", x),
                key="mineru_vl_version",
            )
            mineru_vl_quant_options = quant_options("mineru_vl", mineru_vl_version)
            mineru_vl_quant = st.selectbox(
                "MinerU-VL 量化",
                options=mineru_vl_quant_options,
                index=mineru_vl_quant_options.index(default_quant("mineru_vl")),
                key="mineru_vl_quant",
            )
            mineru_vl_col_a, mineru_vl_col_b, mineru_vl_col_c = st.columns(3)
            with mineru_vl_col_a:
                mineru_vl_request_concurrency = st.number_input(
                    "API 请求并发",
                    min_value=1,
                    max_value=8,
                    value=int(st.session_state.get("mineru_vl_request_concurrency", 1)),
                    help="MinerU-VL 专属 API 请求上限。Layout 和块识别请求共用此值；LM Studio 通常使用 1，显存充足时可试 2。",
                    key="mineru_vl_request_concurrency",
                )
            with mineru_vl_col_b:
                mineru_vl_block_concurrency = st.number_input(
                    "块调度上限",
                    min_value=1,
                    max_value=16,
                    value=int(st.session_state.get("mineru_vl_block_concurrency", 4)),
                    help="单页内部块抽取的调度上限；实际后端请求并发仍受“API 请求并发”限制。",
                    key="mineru_vl_block_concurrency",
                )
            with mineru_vl_col_c:
                mineru_vl_layout_image_size_value = st.number_input(
                    "Layout 输入边长",
                    min_value=512,
                    max_value=2048,
                    value=int(st.session_state.get("mineru_vl_layout_image_size_value", 1036)),
                    step=4,
                    help="发送给 Layout Detection 的方形缩放边长。默认 1036 对齐 MinerU-VL 常见坐标协议。",
                    key="mineru_vl_layout_image_size_value",
                )
            mineru_vl_layout_image_size = (
                int(mineru_vl_layout_image_size_value),
                int(mineru_vl_layout_image_size_value),
            )
            st.session_state["mineru_vl_layout_image_size"] = mineru_vl_layout_image_size
            surya2_version = None
        elif ocr_backend == "surya2":
            st.info("""
**Surya 2** - 轻量文档 VLM
- 使用官方 layout JSON 协议，再按块调用 HTML OCR
- Contexture 会保留原始 bbox/HTML/protocol，并标准化为 Middle JSON
- 本地 LM Studio 测试中 layout-only 并发 4-6 较稳
            """)
            chandra_version = None
            chandra_quant = None
            churro_version = None
            churro_quant = None
            paddleocr_vl_prompt_label = "ocr"
            paddleocr_vl_version = None
            paddleocr_vl_mode = "auto"
            paddleocr_vl_layout_parsing_url = None
            mineru_vl_version = None
            mineru_vl_quant = None
            surya2_settings = render_surya2_vlm_settings(
                st,
                description="",
                key_prefix="specialized_surya2",
            )
            surya2_endpoint = surya2_settings["surya2_endpoint"]
            surya2_api_key = surya2_settings["surya2_api_key"]
            surya2_api_style = surya2_settings["surya2_api_style"]
            surya2_version = surya2_settings["surya2_version"]
            surya2_model = surya2_settings["surya2_model"]
            surya2_request_concurrency = surya2_settings["surya2_request_concurrency"]
            surya2_block_concurrency = surya2_settings["surya2_block_concurrency"]
            surya2_image_format = surya2_settings["surya2_image_format"]
            surya2_image_quality = surya2_settings["surya2_image_quality"]
        elif ocr_backend == "chrome_screenai":
            st.info("""
**Chrome ScreenAI** - 本地原生 OCR
- 默认直接走 PDF 原生通道
- 仅在你选择“去除已有文本层”或“栅格化 PDF”时做额外预处理
- 支持页面切分并行和 searchable PDF 输出
            """)
            chandra_version = None
            chandra_quant = None
            churro_version = None
            churro_quant = None
            paddleocr_vl_prompt_label = "ocr"
            paddleocr_vl_version = None
            paddleocr_vl_mode = "auto"
            paddleocr_vl_layout_parsing_url = None
            mineru_vl_version = None
            mineru_vl_quant = None
            surya2_version = None
        else:
            paddleocr_vl_prompt_label = "ocr"
            paddleocr_vl_version = None
            paddleocr_vl_mode = "auto"
            paddleocr_vl_layout_parsing_url = None
            churro_version = None
            churro_quant = None
            mineru_vl_version = None
            mineru_vl_quant = None
            surya2_version = None
            chandra_versions = version_options("chandra")
            chandra_default_version = default_version("chandra")
            chandra_version = st.selectbox(
                "Chandra 版本",
                options=chandra_versions,
                index=chandra_versions.index(chandra_default_version),
                format_func=lambda x: version_label("chandra", x),
                help="在同一个 Chandra 后端下切换 1.0 / 2.0 profile。",
                key="chandra_version"
            )
            chandra_quant_options = quant_options("chandra", chandra_version)
            chandra_quant = st.selectbox(
                "Chandra 量化",
                options=chandra_quant_options,
                index=chandra_quant_options.index(default_quant("chandra")),
                key="chandra_quant",
            )

        # API 配置
        with st.expander("🔌 API 配置", expanded=True):
            if ocr_backend == "chrome_screenai":
                ocr_api_style = "native"
                ocr_endpoint = None
                ocr_model = "chrome-screenai-local"
                ocr_api_key = ""
                st.caption("Chrome ScreenAI 走本地直通，不需要 API 端点或密钥。")
            else:
                default_ocr_api_style = "openai" if ocr_backend in {"churro", "surya2"} else "lmstudio-native"
                if st.session_state.get("_last_ocr_api_backend") != ocr_backend:
                    st.session_state["ocr_api_style"] = default_ocr_api_style
                    st.session_state["_last_ocr_api_backend"] = ocr_backend
                ocr_api_style_options = ["lmstudio-native", "openai"]
                current_ocr_api_style = st.session_state.get("ocr_api_style", default_ocr_api_style)
                if current_ocr_api_style == "openai-compatible":
                    current_ocr_api_style = "openai"
                elif current_ocr_api_style not in ocr_api_style_options:
                    current_ocr_api_style = default_ocr_api_style
                ocr_api_style = st.selectbox(
                    "协议风格",
                    options=ocr_api_style_options,
                    index=ocr_api_style_options.index(current_ocr_api_style),
                    format_func=lambda x: {
                        "lmstudio-native": "LM Studio 原生协议",
                        "openai": "OpenAI 兼容协议"
                    }[x],
                    help="Churro 在 LM Studio 中使用 OpenAI 兼容协议更稳定；原生协议使用 /api/v1/chat。",
                    key="ocr_api_style"
                )

                default_endpoint = (
                    "http://localhost:1234/api/v1/chat"
                    if ocr_api_style == "lmstudio-native"
                    else "http://localhost:1234/v1/chat/completions"
                )
                if (
                    "ocr_endpoint" not in st.session_state
                    or st.session_state.get("_last_ocr_api_style") != ocr_api_style
                    or st.session_state.get("_last_ocr_endpoint_backend") != ocr_backend
                ):
                    st.session_state["ocr_endpoint"] = default_endpoint
                    st.session_state["_last_ocr_api_style"] = ocr_api_style
                    st.session_state["_last_ocr_endpoint_backend"] = ocr_backend

                ocr_endpoint = st.text_input(
                    "API 端点",
                    help="LM Studio 原生协议使用 /api/v1/chat；OpenAI 兼容协议使用 /v1/chat/completions。",
                    key="ocr_endpoint"
                )

                if ocr_backend == "chandra":
                    model_version = chandra_version
                    model_quant = chandra_quant
                elif ocr_backend == "churro":
                    model_version = churro_version
                    model_quant = churro_quant
                elif ocr_backend == "paddleocr_vl":
                    model_version = paddleocr_vl_version
                    model_quant = None
                elif ocr_backend == "surya2":
                    model_version = surya2_version
                    model_quant = None
                else:
                    model_version = mineru_vl_version
                    model_quant = mineru_vl_quant

                default_model = resolve_vlm_model(
                    ocr_backend,
                    version=model_version,
                    quant=model_quant,
                )

                if (
                    "ocr_model" not in st.session_state
                    or st.session_state.get("_last_ocr_backend") != ocr_backend
                    or st.session_state.get("_last_chandra_version") != chandra_version
                    or st.session_state.get("_last_vlm_model_version") != model_version
                    or st.session_state.get("_last_vlm_model_quant") != model_quant
                ):
                    st.session_state["ocr_model"] = default_model
                    st.session_state["_last_ocr_backend"] = ocr_backend
                    st.session_state["_last_chandra_version"] = chandra_version
                    st.session_state["_last_vlm_model_version"] = model_version
                    st.session_state["_last_vlm_model_quant"] = model_quant

                ocr_model = st.text_input(
                    "模型名称",
                    help="由后端家族、版本和量化自动生成；如 LM Studio 中使用了带 namespace 的模型名，可在这里覆盖。",
                    key="ocr_model"
                )
                ocr_api_key = st.text_input(
                    "API Key（可选）",
                    value="",
                    type="password",
                    help="仅在服务端要求认证时填写。",
                    key="ocr_api_key"
                )
            # 输出格式选择（根据后端动态调整）
            if ocr_backend == "chandra":
                _migrate_multiselect_default(
                    "ocr_output_format",
                    old_defaults=[["markdown", "html"]],
                    new_default=["markdown", "json", "html"],
                )
                ocr_output_formats = st.multiselect(
                    "输出格式",
                    options=["markdown", "json", "html"],
                    default=["markdown", "json", "html"],
                    help="选择需要保存的输出格式。",
                    key="ocr_output_format"
                )
            elif ocr_backend == "churro":
                _migrate_multiselect_default(
                    "ocr_output_format",
                    old_defaults=[["markdown", "xml"]],
                    new_default=["markdown", "xml", "json", "html"],
                )
                ocr_output_formats = st.multiselect(
                    "输出格式",
                    options=["markdown", "xml", "json", "html"],
                    default=["markdown", "xml", "json", "html"],
                    help="XML 是 Churro 官方原始输出；JSON/HTML 默认保留，方便后处理和浏览器查看。",
                    key="ocr_output_format"
                )
            else:
                _migrate_multiselect_default(
                    "ocr_output_format",
                    old_defaults=[["markdown", "json"]],
                    new_default=["markdown", "json", "html"],
                )
                ocr_output_formats = st.multiselect(
                    "输出格式",
                    options=["markdown", "json", "html"],
                    default=["markdown", "json", "html"],
                    help="JSON 保存标准化后的 page/block 结构。",
                    key="ocr_output_format"
                )
            middle_settings = _middle_settings_from_value(
                render_middle_artifact_settings(
                    st,
                    key_prefix="vlm_specialized",
                    force_middle_json=always_save_middle_json,
                )
            )
            emit_middle_json = middle_settings.emit_middle_json
            emit_middle_report = middle_settings.emit_middle_report
            emit_middle_debug = middle_settings.emit_middle_debug
            emit_middle_scholarly = middle_settings.emit_middle_scholarly
            emit_middle_scholarly_report = middle_settings.emit_middle_scholarly_report
            emit_layout_overlay = middle_settings.emit_layout_overlay
            emit_span_overlay = middle_settings.emit_span_overlay
            emit_middle_full_json = middle_settings.emit_middle_full_json

        # 图像预处理
        with st.expander("🖼️ 图像预处理", expanded=False):
            if ocr_backend == "chrome_screenai":
                st.caption("默认原生直通；只有在你主动选择重做或栅格化时，才会对 PDF 页面做额外预处理。")
                chrome_screenai_light = st.checkbox(
                    "轻量模式",
                    value=bool(st.session_state.get("chrome_screenai_light", False)),
                    help="速度更快，精度略低。",
                    key="chrome_screenai_light",
                )
                chrome_preprocess_mode = st.selectbox(
                    "处理模式",
                    options=["native", "strip_existing_ocr", "rasterize_pdf", "strip_then_rasterize"],
                    index=["native", "strip_existing_ocr", "rasterize_pdf", "strip_then_rasterize"].index(
                        st.session_state.get("chrome_preprocess_mode", "native")
                    ),
                    format_func=lambda x: {
                        "native": "直通（保留原页面）",
                        "strip_existing_ocr": "重做（删除旧 OCR 层重新识别）",
                        "rasterize_pdf": "栅格化（整页渲染后识别）",
                        "strip_then_rasterize": "重做 + 栅格化",
                    }[x],
                    key="chrome_preprocess_mode",
                )
                if chrome_preprocess_mode in {"rasterize_pdf", "strip_then_rasterize"}:
                    chrome_rasterize_dpi = st.number_input(
                        "栅格化 DPI",
                        min_value=72,
                        max_value=300,
                        value=int(st.session_state.get("chrome_rasterize_dpi", 144)),
                        step=12,
                        key="chrome_rasterize_dpi",
                    )
                else:
                    chrome_rasterize_dpi = int(st.session_state.get("chrome_rasterize_dpi", 144))
                chrome_model_dir = st.text_input(
                    "模型目录（可选）",
                    value=st.session_state.get("chrome_model_dir", ""),
                    help="留空时自动发现 Chrome ScreenAI 组件目录。",
                    key="chrome_model_dir",
                )
                ocr_image_format = "png"
                ocr_resize_max = 2048
                ocr_image_quality = 90
            else:
                default_ocr_image_format = "png" if ocr_backend == "churro" else "jpeg"
                default_ocr_resize_max = 2500 if ocr_backend == "churro" else 2048
                default_ocr_image_quality = 95 if ocr_backend == "churro" else 90
                col1, col2 = st.columns(2)
                with col1:
                    image_format_options = ["jpeg", "png", "webp"]
                    ocr_image_format = st.selectbox(
                        "图像格式",
                        options=image_format_options,
                        index=image_format_options.index(default_ocr_image_format),
                        help="发送给 API 的图像格式；PNG 更稳，JPEG 更省流量。",
                        key="ocr_image_format"
                    )
                    ocr_resize_max = st.number_input(
                        "最大图像尺寸（像素）",
                        min_value=512,
                        max_value=4096,
                        value=default_ocr_resize_max,
                        step=128,
                        help="发送前的图像最大边长；本地模型显存有限时可调低。",
                        key="ocr_resize_max"
                    )
                with col2:
                    ocr_image_quality = st.slider(
                        "JPEG 质量",
                        min_value=50,
                        max_value=100,
                        value=default_ocr_image_quality,
                        help="JPEG 压缩质量",
                        key="ocr_image_quality"
                    )

        # 高级选项（包含并发控制）
        with st.expander("高级选项", expanded=False):
            st.markdown("**并发控制**")

            # 并发模式选择
            _specialized_mode_value = str(st.session_state.get("ocr_concurrency_mode", "page_parallel"))
            if _specialized_mode_value == "serial_file":
                _specialized_mode_value = "page_parallel"
            elif _specialized_mode_value == "batch_single_page":
                _specialized_mode_value = "file_parallel"
            ocr_concurrency_mode = st.radio(
                "并发模式",
                options=["page_parallel", "file_parallel"],
                index=["page_parallel", "file_parallel"].index(_specialized_mode_value),
                format_func=lambda x: {
                    "page_parallel": "单本书页内并行",
                    "file_parallel": "多本书整本并行",
                }[x],
                help="两种模式互斥：要么把线程集中给一本书的页面，要么把线程分散给多本书。",
                key="ocr_concurrency_mode"
            )

            if ocr_concurrency_mode == "page_parallel":
                # 单本书页内并行
                col1, col2 = st.columns(2)
                with col1:
                    if ocr_backend == "chrome_screenai":
                        chrome_workers = st.number_input(
                            "Chrome 并行数",
                            min_value=1,
                            max_value=20,
                            value=int(st.session_state.get("chrome_workers", st.session_state.get("ocr_concurrency", 2))),
                            help="单本书内部同时运行的 Chrome ScreenAI worker 数。Chrome 默认建议从 1-2 开始。",
                            key="chrome_workers",
                        )
                        ocr_concurrency = int(chrome_workers)
                    else:
                        default_ocr_concurrency = 2
                        ocr_concurrency = st.number_input(
                            "页面并发数",
                            min_value=1,
                            max_value=20,
                            value=default_ocr_concurrency,
                            help="单个文件内同时处理的页面数。本地 LM Studio 通常从低并发开始更稳。",
                            key="ocr_concurrency"
                        )
                with col2:
                    ocr_batch_rest = st.number_input(
                        "批次休息时间（秒）",
                        min_value=0.0,
                        max_value=10.0,
                        value=1.0,
                        step=0.5,
                        help="每批页面处理完后的等待时间。",
                        key="ocr_batch_rest"
                    )
                if ocr_backend == "chrome_screenai":
                    chrome_chunk_pages = max(1, int(ocr_concurrency))
                    st.session_state["chrome_chunk_pages"] = chrome_chunk_pages
                ocr_batch_size = ocr_concurrency
                ocr_max_concurrent_files = 1
                ocr_total_concurrent = ocr_concurrency
                if ocr_backend == "chrome_screenai":
                    st.caption(
                        f"Chrome 页内并行：一次只处理 1 本书，并行数={ocr_concurrency}，批间等待 {ocr_batch_rest} 秒。"
                    )
                else:
                    st.caption(f"页内并行：一次只处理 1 本书，每批 {ocr_concurrency} 页，批间等待 {ocr_batch_rest} 秒。")
            else:
                # 多本书整本并行
                col1, col2 = st.columns(2)
                with col1:
                    ocr_file_batch_size = st.number_input(
                        "并行书本数",
                        min_value=1,
                        max_value=20,
                        value=3,
                        help="同时处理的文件数；每本书内部按单线程顺序处理页面。",
                        key="ocr_file_batch_size"
                    )
                with col2:
                    ocr_file_batch_rest = st.number_input(
                        "批次休息时间（秒）",
                        min_value=0.0,
                        max_value=10.0,
                        value=1.0,
                        step=0.5,
                        help="每批文件处理完后的等待时间。",
                        key="ocr_file_batch_rest"
                    )
                ocr_max_concurrent_files = ocr_file_batch_size
                ocr_concurrency = 1
                ocr_batch_size = 1
                ocr_batch_rest = ocr_file_batch_rest
                ocr_total_concurrent = ocr_file_batch_size
                if ocr_backend == "chrome_screenai":
                    chrome_workers = 1
                    chrome_chunk_pages = 1
                    st.session_state["chrome_chunk_pages"] = 1
                    st.caption(
                        f"Chrome 整本并行：同时跑 {ocr_file_batch_size} 本书；每本书固定页内串行，批间等待 {ocr_file_batch_rest} 秒。"
                    )
                else:
                    st.caption(f"整本并行：同时跑 {ocr_file_batch_size} 本书，每本书页内串行，批间等待 {ocr_file_batch_rest} 秒。")
            if ocr_backend == "chrome_screenai":
                chrome_emit_searchable_pdf = st.checkbox(
                    "输出 searchable PDF",
                    value=bool(st.session_state.get("chrome_emit_searchable_pdf", True)),
                    key="chrome_emit_searchable_pdf",
                )
                st.info(
                    "\n".join(
                        [
                            "**Chrome ScreenAI 实际执行摘要**",
                            f"- 调度模式：{'单本书页内并行' if ocr_concurrency_mode == 'page_parallel' else '多本书整本并行'}",
                            f"- 文件并发：{int(ocr_max_concurrent_files)}",
                            f"- 页内并行数：{int(chrome_workers)}",
                            f"- 预处理：{chrome_preprocess_mode}",
                            f"- searchable PDF：{'开启' if chrome_emit_searchable_pdf else '关闭'}",
                        ]
                    )
                )

            st.markdown("---")
            st.markdown("**其他设置**")
            col1, col2 = st.columns(2)
            with col1:
                ocr_max_retries = st.number_input(
                    "最大重试次数",
                    min_value=1,
                    max_value=10,
                    value=3,
                    help="单页或单请求失败后的重试次数。",
                    key="ocr_max_retries"
                )
            with col2:
                default_ocr_timeout = 600 if ocr_backend == "mineru_vl" else 120
                ocr_timeout = st.number_input(
                    "超时时间（秒）",
                    min_value=30,
                    max_value=1800,
                    value=default_ocr_timeout,
                    help="MinerU-VL 等远端服务是单请求超时；Chrome ScreenAI 用作单页处理保护超时。",
                    key="ocr_timeout"
                )
                if ocr_backend == "mineru_vl" and int(ocr_timeout) < 600:
                    st.caption("MinerU-VL + LM Studio 运行时会将有效超时提升到 600 秒。")

            col3, col4 = st.columns(2)
            with col3:
                # 根据后端设置默认值和限制
                if ocr_backend == "chandra":
                    default_max_tokens = 4096
                    max_limit = 16384
                    help_text = "Chandra 默认 4096；复杂页面可提高到 8192。"
                elif ocr_backend == "churro":
                    default_max_tokens = 20000
                    max_limit = 32768
                    help_text = "Churro 默认 20000；本地推理通常需要低并发。"
                elif ocr_backend == "paddleocr_vl":
                    default_max_tokens = 8192
                    max_limit = 32768
                    help_text = "PaddleOCR-VL 默认 8192；复杂表格或长页可提高。"
                elif ocr_backend == "mineru_vl":
                    default_max_tokens = 8192
                    max_limit = 32768
                    help_text = "MinerU-VL 官方兼容结构化解析默认 8192；块级表格、公式或长引用可提高。"
                elif ocr_backend == "chrome_screenai":
                    default_max_tokens = 0
                    max_limit = 0
                    help_text = "Chrome ScreenAI 为本地模型，不使用 Token 限制。"
                else:
                    default_max_tokens = 8192
                    max_limit = 32768
                    help_text = "特化 VLM 默认 8192；复杂页面可提高。"
                if ocr_backend == "chrome_screenai":
                    st.caption(help_text)
                    ocr_max_tokens = 0
                else:
                    ocr_max_tokens = st.number_input(
                        "最大输出 Token 数",
                        min_value=1024,
                        max_value=max_limit,
                        value=default_max_tokens,
                        step=1024,
                        help=help_text,
                        key="ocr_max_tokens"
                    )

            # Churro 并发配置警告
            if ocr_backend == "churro":
                theoretical_max = ocr_max_tokens * ocr_concurrency
                if theoretical_max > 32000:
                    st.warning(f"""
**配置提示**：
- 理论最大输出：{theoretical_max:,} tokens
- 32K 上下文窗口：通常保持在 25,000 tokens 以下
- 本地推理通常需要降低页面并发
                    """)

            st.markdown("---")
            st.markdown("**页码范围**")
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
                help="修复Unicode上标脚注（¹) → <sup>1</sup>）",
                key="ocr_footnote_fix"
            )

            # 断行修复
            ocr_hyphenation_fix = st.checkbox(
                "启用断行修复",
                value=True,
                help="合并断行的单词（Philo-\\nsophen → Philosophen）",
                key="ocr_hyphenation_fix"
            )

            st.markdown("---")
            st.markdown("**🏷️ 页眉页脚与边注过滤**")

            # 页眉过滤
            ocr_filter_page_header = st.checkbox(
                "过滤页眉语法标记",
                value=False,
                help="移除 <!-- PageHeader: --> 语法，保留内容；历史 <!-- page-header: --> 也兼容。",
                key="ocr_filter_page_header"
            )

            # 页脚过滤
            ocr_filter_page_footer = st.checkbox(
                "过滤页脚语法标记",
                value=False,
                help="移除 <!-- PageFooter: --> 语法，保留内容；历史 <!-- page-footer: --> 也兼容。",
                key="ocr_filter_page_footer"
            )

            ocr_filter_margin_notes = st.checkbox(
                "过滤边注语法标记",
                value=False,
                help="移除 <!-- Margin:left/right --> 与 <!-- /Margin --> 语法，并将边注引用行转为普通文本。",
                key="ocr_filter_margin_notes"
            )

            ocr_filter_blockquote_markers = st.checkbox(
                "过滤引用块语法标记",
                value=False,
                help="将识别为引用块的 Markdown > 或 HTML blockquote 包装转为普通文本，不处理普通文本中的 > 字符。",
                key="ocr_filter_blockquote_markers"
            )

    # VLM 泛化模式配置
    if conversion_mode == "vlm_generalized":
        # ==================== VLM 泛化模式配置 ====================
        st.subheader("🌐 VLM 泛化模式配置")

        # 🔌 API 配置
        with st.expander("🔌 API 配置", expanded=True):
            # 输出格式选择（多选）
            _migrate_multiselect_default(
                "vlm_output_formats",
                old_defaults=[["markdown", "json"]],
                new_default=["markdown", "json", "html"],
            )
            vlm_output_formats = st.multiselect(
                "导出文件格式",
                options=["markdown", "json", "html"],
                default=["markdown", "json", "html"],
                help="选择要保存的结果文件格式（可多选），仅影响导出保存，不改变内部 JSON 识别流程",
                key="vlm_output_formats"
            )
            st.caption("ℹ️ 生效级别：仅影响导出保存，参与配置保存/加载。")
            output_formats = vlm_output_formats if vlm_output_formats else ["markdown"]
            middle_settings = _middle_settings_from_value(
                render_middle_artifact_settings(
                    st,
                    key_prefix="vlm_generalized",
                    force_middle_json=always_save_middle_json,
                )
            )
            emit_middle_json = middle_settings.emit_middle_json
            emit_middle_report = middle_settings.emit_middle_report
            emit_middle_debug = middle_settings.emit_middle_debug
            emit_middle_scholarly = middle_settings.emit_middle_scholarly
            emit_middle_scholarly_report = middle_settings.emit_middle_scholarly_report
            emit_layout_overlay = middle_settings.emit_layout_overlay
            emit_span_overlay = middle_settings.emit_span_overlay
            emit_middle_full_json = middle_settings.emit_middle_full_json

            # API 提供商选择
            vlm_api_provider = st.selectbox(
                "API 提供商",
                options=["openai_compatible", "gemini", "anthropic"],
                index=0,  # 默认选择 openai_compatible
                format_func=lambda x: {
                    "openai_compatible": "OpenAI 兼容",
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
                    value=os.environ.get("OPENAI_BASE_URL", ""),
                    help="OpenAI 兼容 API 的基础 URL",
                    key="vlm_direct_base_url"
                )
                vlm_direct_model = st.text_input(
                    "模型名称",
                    value=os.environ.get("OPENAI_MODEL", ""),
                    help="填写当前服务端实际可用的模型名；不同服务商升级较快，以控制台或官方文档为准。",
                    key="vlm_direct_model"
                )
                vlm_direct_api_key = st.text_area(
                    "API Keys (支持多个)",
                    value=os.environ.get("OPENAI_API_KEY", ""),
                    height=100,
                    help="可填写 1 个或多个 API Key。多 key 时，后端会按英文逗号 , 或换行分隔并轮换使用。",
                    key="vlm_direct_api_key"
                )
            elif vlm_api_provider == "gemini":
                # Gemini 原生配置
                st.caption("使用 Google Gemini 原生 API（支持中转）。")
                vlm_direct_base_url = st.text_input(
                    "Gemini API 端点",
                    value=os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com"),
                    help="Google Gemini 原生 API 端点；也可替换为兼容中转地址",
                    key="vlm_gemini_base_url"
                )
                vlm_direct_model = st.text_input(
                    "模型名称",
                    value=os.environ.get("GEMINI_MODEL", "gemini-3.0-flash"),
                    help="例如: gemini-3.0-flash, gemini-2.5-pro, gemini-2.0-flash",
                    key="vlm_gemini_model"
                )
                vlm_direct_api_key = st.text_area(
                    "Gemini API Keys (支持多个)",
                    value=os.environ.get("GEMINI_API_KEY", ""),
                    height=100,
                    help="可填写 1 个或多个 API Key。多 key 时，后端会按英文逗号 , 或换行分隔并轮换使用。",
                    key="vlm_gemini_api_key"
                )
            elif vlm_api_provider == "anthropic":
                # Anthropic Claude 原生配置
                st.caption("使用 Anthropic Claude 原生 API（支持中转）。")
                vlm_direct_base_url = st.text_input(
                    "Anthropic API 端点",
                    value=os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
                    help="Anthropic Claude 原生 API 端点；也可替换为兼容中转地址",
                    key="vlm_anthropic_base_url"
                )
                vlm_direct_model = st.text_input(
                    "模型名称",
                    value=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5"),
                    help="例如: claude-sonnet-4-5, claude-opus-4-1, claude-3-7-sonnet-latest",
                    key="vlm_anthropic_model"
                )
                vlm_direct_api_key = st.text_area(
                    "Anthropic API Keys (支持多个)",
                    value=os.environ.get("ANTHROPIC_API_KEY", ""),
                    height=100,
                    help="可填写 1 个或多个 API Key。多 key 时，后端会按英文逗号 , 或换行分隔并轮换使用。单个 key 通常形如 sk-ant-...",
                    key="vlm_anthropic_api_key"
                )

            # 显示Key数量和建议
            if vlm_direct_api_key:
                keys = [k.strip() for k in vlm_direct_api_key.replace('\n', ',').split(',') if k.strip()]
                key_count = len(keys)
                if key_count > 1:
                    st.success(f"已检测到 {key_count} 个 API Key")
                    suggested_concurrent = key_count * 3
                    st.caption(f"可将并发数逐步提高到 {suggested_concurrent} 左右，具体取决于服务限流。")

            st.markdown("---")
            if st.session_state.get("vlm_api_profile_loaded_message"):
                st.success(f"已载入 API 预设: {st.session_state['vlm_api_profile_loaded_message']}")
                del st.session_state["vlm_api_profile_loaded_message"]
            api_profile_names = ["-- 不使用预设 --"] + [p["name"] for p in api_profiles]
            selected_api_profile = st.selectbox(
                "API 预设",
                options=api_profile_names,
                index=0,
                key="vlm_api_profile_selector",
                help="可将当前 provider、端点、模型和 API key 保存为本地预设"
            )

            if selected_api_profile != "-- 不使用预设 --":
                selected_api_meta = api_profile_map.get(selected_api_profile, {})
                summary_parts = [
                    selected_api_meta.get("provider", ""),
                    selected_api_meta.get("model", ""),
                ]
                summary_parts = [part for part in summary_parts if part]
                if summary_parts:
                    st.caption(" | ".join(summary_parts))
                if selected_api_meta.get("base_url"):
                    st.caption(selected_api_meta["base_url"])
                col_api_load, col_api_delete = st.columns(2)
                with col_api_load:
                    if st.button("📥 载入 API 预设", key="load_api_profile_btn"):
                        if config_manager.load_api_profile(selected_api_profile):
                            st.session_state["pending_vlm_api_profile"] = selected_api_profile
                            st.rerun()
                        else:
                            st.error("载入 API 预设失败")
                with col_api_delete:
                    confirm_delete_api_profile = st.checkbox("确认删除", key="confirm_delete_api_profile")
                    if st.button("🗑️ 删除 API 预设", key="delete_api_profile_btn", disabled=not confirm_delete_api_profile):
                        if config_manager.delete_api_profile(selected_api_profile):
                            st.success(f"已删除 API 预设: {selected_api_profile}")
                            st.rerun()
                        else:
                            st.error("删除 API 预设失败")

            st.markdown("**保存当前 API 为预设**")
            api_profile_name = st.text_input("预设名称", key="vlm_api_profile_name", placeholder="例如: gemini-官方 / qwen-兼容 / kimi-中转")
            api_profile_exists = bool(api_profile_name and config_manager.api_profile_exists(api_profile_name.strip()))
            overwrite_api_profile = st.checkbox(
                "覆盖同名 API 预设",
                value=False,
                key="overwrite_api_profile",
                disabled=not api_profile_exists,
            )
            st.caption("ℹ️ 保存内容包括 provider、端点、模型和 API key，仅保存在本地配置目录中。")
            if st.button("💾 保存 API 预设", key="save_api_profile_btn"):
                if api_profile_name:
                    current_provider = st.session_state.get("vlm_api_provider", "gemini")
                    if current_provider == "openai_compatible":
                        current_base_url = st.session_state.get("vlm_direct_base_url", "")
                        current_model = st.session_state.get("vlm_direct_model", "")
                        current_api_key = st.session_state.get("vlm_direct_api_key", "")
                    elif current_provider == "gemini":
                        current_base_url = st.session_state.get("vlm_gemini_base_url", "")
                        current_model = st.session_state.get("vlm_gemini_model", "")
                        current_api_key = st.session_state.get("vlm_gemini_api_key", "")
                    else:
                        current_base_url = st.session_state.get("vlm_anthropic_base_url", "")
                        current_model = st.session_state.get("vlm_anthropic_model", "")
                        current_api_key = st.session_state.get("vlm_anthropic_api_key", "")

                    success = config_manager.save_api_profile(
                        name=api_profile_name,
                        provider=current_provider,
                        base_url=current_base_url,
                        model=current_model,
                        api_key=current_api_key,
                        description="",
                        overwrite=overwrite_api_profile,
                    )
                    if success:
                        st.success(f"API 预设 '{api_profile_name}' 已保存")
                        st.rerun()
                    else:
                        if config_manager.api_profile_exists(api_profile_name.strip()):
                            st.warning("同名 API 预设已存在。勾选“覆盖同名 API 预设”或更换名称后再保存。")
                        else:
                            st.error("API 预设保存失败")
                else:
                    st.warning("需要输入 API 预设名称")

        # 🖼️ 图像预处理
        with st.expander("🖼️ 图像预处理", expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                vlm_direct_image_format = st.selectbox(
                    "图像格式",
                    options=["jpeg", "png", "webp"],
                    index=1,
                    help="发送给 API 的图像格式；PNG 更稳，JPEG 更省流量。",
                    key="vlm_direct_image_format"
                )
                vlm_direct_max_image_dimension = st.number_input(
                    "最大图像尺寸（像素）",
                    min_value=0,
                    max_value=4096,
                    value=0,
                    step=128,
                    help="图像最大边长，0 表示不缩放并保持原始尺寸",
                    key="vlm_direct_max_image_dimension"
                )
            with col2:
                vlm_direct_jpeg_quality = st.slider(
                    "JPEG 质量",
                    min_value=50,
                    max_value=100,
                    value=90,
                    help="JPEG 压缩质量；仅选择 JPEG 时生效。",
                    key="vlm_direct_jpeg_quality"
                )

        # ⚙️ 高级选项
        with st.expander("高级选项", expanded=False):
            st.markdown("**并发控制**")

            # 并发模式选择
            vlm_concurrency_mode = st.radio(
                "并发模式",
                options=["serial_file", "batch_single_page"],
                format_func=lambda x: {
                    "serial_file": "串行文件处理（多页 PDF）",
                    "batch_single_page": "单页多文件批次（扫描图片）"
                }[x],
                help="串行模式逐个文件处理；批次模式用于多个单页 PDF 或图片。",
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
                        help="单个文件内同时处理的页面数量。",
                        key="vlm_direct_max_concurrent"
                    )
                with col2:
                    vlm_batch_rest = st.number_input(
                        "批次休息时间（秒）",
                        min_value=0.0,
                        max_value=10.0,
                        value=1.0,
                        step=0.5,
                        help="每批页面处理完后的等待时间。",
                        key="vlm_batch_rest"
                    )
                vlm_direct_max_concurrent_files = 1
                vlm_direct_total_concurrent = vlm_direct_max_concurrent
                st.caption(f"串行模式：逐个文件处理，每 {vlm_direct_max_concurrent} 页后等待 {vlm_batch_rest} 秒。")
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
                st.caption(f"批次模式：每批 {vlm_file_batch_size} 个文件，完成后等待 {vlm_file_batch_rest} 秒。")

            st.markdown("---")
            st.markdown("**其他设置**")
            col1, col2 = st.columns(2)
            with col1:
                vlm_direct_timeout = st.number_input(
                    "超时时间（秒）",
                    min_value=30,
                    max_value=900,
                    value=600,
                    help="Gemini 等慢速 API 通常需要 600 秒以上。",
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

            st.markdown("**失败页自动补跑**")
            vlm_auto_repair_failed_pages = st.checkbox(
                "任务结束前自动低并发补跑失败页",
                value=True,
                help="主批次结束后，根据逐页 diagnostics 找出失败页，用更低并发补跑，最后再整书拼接输出。",
                key="vlm_auto_repair_failed_pages",
            )
            col_repair_1, col_repair_2 = st.columns(2)
            with col_repair_1:
                vlm_repair_max_concurrent = st.number_input(
                    "补跑页并发数",
                    min_value=1,
                    max_value=8,
                    value=2,
                    help="通常低于主跑并发；LM Studio/local VLM 一般从 1-2 开始。",
                    key="vlm_repair_max_concurrent",
                )
            with col_repair_2:
                vlm_repair_rounds = st.number_input(
                    "补跑轮数",
                    min_value=0,
                    max_value=5,
                    value=2,
                    help="每轮只补跑上一轮仍失败的页。",
                    key="vlm_repair_rounds",
                )

            st.markdown("---")
            st.markdown("**📄 页码范围**")
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

        # 🧭 识别策略与提示词
        with st.expander("🧭 识别策略与提示词", expanded=False):
            # ===== 1. API 参数预设 =====
            st.markdown("**API 参数配置**")
            preset_options = {
                "高准确性（默认）": "high_accuracy",
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

            # 自定义 API 参数
            if selected_preset == "自定义":
                col1, col2 = st.columns(2)
                with col1:
                    vlm_direct_temperature = st.slider(
                        "Temperature", 0.0, 1.0, 0.0, 0.1,
                        help="控制随机性，0.0=完全确定",
                        key="vlm_direct_temperature"
                    )
                    vlm_direct_top_p = st.slider(
                        "Top P", 0.0, 1.0, 0.1, 0.1,
                        help="核采样，限制候选词范围",
                        key="vlm_direct_top_p"
                    )
                with col2:
                    vlm_direct_top_k = st.number_input(
                        "Top K", 1, 100, 1,
                        help="Top-K采样（部分API支持）",
                        key="vlm_direct_top_k"
                    )
            else:
                vlm_direct_temperature = None
                vlm_direct_top_p = None
                vlm_direct_top_k = None

            st.markdown("---")

            # ===== 2. 字段开关 =====
            st.markdown("**文档理解偏好**")
            st.caption("以下设置用于调整模板提示词的生成内容。仅在未手动覆盖提示词时生效；若直接编辑提示词文本，则以编辑后的提示词为准。")

            col1, col2, col3 = st.columns(3)
            with col1:
                text_direction = st.selectbox(
                    "文字方向",
                    ["horizontal", "vertical", "mixed"],
                    format_func=lambda x: {"horizontal": "横排", "vertical": "竖排", "mixed": "混合"}[x],
                    help="文档的主要文字排列方向",
                    key="vlm_direct_text_direction_simple"
                )
            with col2:
                primary_language = st.selectbox(
                    "主要语言",
                    ["auto", "zh-Hans", "zh-Hant", "en", "de", "fr", "ja", "ko", "la", "ar"],
                    format_func=lambda x: {
                        "auto": "自动识别（默认）",
                        "zh-Hans": "中文简体", "zh-Hant": "中文繁体", "en": "英语",
                        "de": "德语", "fr": "法语", "ja": "日语", "ko": "韩语",
                        "la": "拉丁语", "ar": "阿拉伯语"
                    }[x],
                    help="仅作为模板提示偏好；选择自动识别时不强行向提示词注入特定语言",
                    key="vlm_direct_primary_language_simple"
                )
            with col3:
                handwriting_mode = st.selectbox(
                    "手写识别",
                    ["none", "mixed"],
                    format_func=lambda x: {"none": "关闭：忽略手写", "mixed": "开启：识别并标记手写"}[x],
                    help="关闭时要求模型忽略手写笔记/批注；开启时识别手写并标记为 **[handwritten]**。",
                    key="vlm_direct_handwriting_mode_simple"
                )

            col4, col5, col6 = st.columns(3)
            with col4:
                describe_images = st.checkbox(
                    "生成图片描述",
                    value=False,
                    help="非强制：仅当 PDF 页面中明确包含插图、照片、印章、图表等非文本内容时，尝试生成与文档主语言一致的简短描述；纯文本页通常关闭。",
                    key="vlm_direct_describe_images_simple"
                )
            with col5:
                has_page_numbers = st.checkbox(
                    "提取页码",
                    value=True,
                    help="从页眉或页脚区域识别并提取印刷页码",
                    key="vlm_direct_has_page_numbers_simple"
                )
            with col6:
                enable_marginalia = st.checkbox(
                    "识别边注",
                    value=False,
                    help="识别页边注释（左侧、右侧、顶部边注）；普通文档通常关闭，边注/眉批明显时再开启。",
                    key="vlm_direct_enable_marginalia_simple"
                )

            col7, col8, col9 = st.columns(3)
            with col7:
                enable_footnotes = st.checkbox(
                    "识别脚注",
                    value=True,
                    help="识别页面底部的脚注",
                    key="vlm_direct_enable_footnotes_simple"
                )
            with col8:
                anti_hallucination = st.checkbox(
                    "缺失信息不猜测",
                    value=True,
                    help="无法判断的页码、文本、坐标、标签或描述使用 null/空值，不诱导模型硬填",
                    key="vlm_direct_anti_hallucination_simple"
                )
            with col9:
                enhance_tables_equations = st.checkbox(
                    "表格/公式结构增强",
                    value=True,
                    help="尽量保留表格和公式结构；关闭后不确定时更倾向普通正文区域",
                    key="vlm_direct_enhance_tables_equations_simple"
                )

            with st.expander("🔬 高级 / 科学参数", expanded=False):
                sci_col1, sci_col2 = st.columns(2)
                with sci_col1:
                    extract_bboxes = st.checkbox(
                        "提取区域坐标 bbox",
                        value=True,
                        help="默认开启；坐标不确定时提示模型使用 null，而不是硬编坐标",
                        key="vlm_direct_extract_bboxes_simple"
                    )
                with sci_col2:
                    include_confidence = st.checkbox(
                        "输出置信度 confidence",
                        value=False,
                        help="VLM 置信度不是传统 OCR 概率，默认关闭并提示模型输出 null",
                        key="vlm_direct_include_confidence_simple"
                    )
                st.caption("JSON 严格输出和请求级关闭 thinking 固定开启，不作为普通开关。")

            st.markdown("---")

            # ===== 提示词模板选择器 =====
            st.markdown("**📝 提示词模板**")

            # 初始化模板管理器
            from aih_contexture.prompts.manager import PromptTemplateManager
            template_manager = PromptTemplateManager()
            templates = template_manager.list_templates()

            # 构建下拉选项
            template_options = []
            for tid, info in templates.items():
                label = f"{info['name']}"
                if info['builtin']:
                    label += " (内置)"
                else:
                    label += " (自定义)"
                template_options.append((tid, label))

            # 模板选择下拉框
            col_select, col_new, col_delete = st.columns([6, 1, 1])
            with col_select:
                selected_template_id = st.selectbox(
                    "选择模板",
                    options=[t[0] for t in template_options],
                    format_func=lambda tid: next(t[1] for t in template_options if t[0] == tid),
                    index=0,
                    help="选择接近当前文档类型的提示词模板。",
                    key="vlm_prompt_template_selector"
                )

            with col_new:
                st.write("")  # 占位对齐
                st.write("")
                if st.button("➕", help="新建模板"):
                    st.session_state['show_new_template_dialog'] = True

            with col_delete:
                st.write("")  # 占位对齐
                st.write("")
                is_builtin = template_manager.is_builtin(selected_template_id)
                if st.button("🗑️", disabled=is_builtin, help="删除自定义模板" if not is_builtin else "内置模板不可删除"):
                    try:
                        template_manager.delete_custom_template(selected_template_id)
                        st.success(f"✅ 已删除模板")
                        st.rerun()
                    except Exception as e:
                        st.error(f"删除失败: {e}")

            # 编辑区
            current_prompt = template_manager.get_template(selected_template_id)
            edited_prompt = st.text_area(
                "编辑提示词",
                value=current_prompt,
                height=300,
                help="可以直接修改提示词内容",
                key="vlm_prompt_editor"
            )

            # 修改状态提示
            if edited_prompt != current_prompt:
                st.caption("⚠️ 提示词已修改（临时生效，需保存才能永久保留）")
            else:
                st.caption("ℹ️ 当前使用模板原始内容")

            # 按钮行
            col_save, col_saveas, col_reset = st.columns(3)

            with col_save:
                if st.button("💾 保存修改", use_container_width=True):
                    if is_builtin:
                        # 内置模板自动打开另存为对话框
                        st.session_state['show_saveas_dialog'] = True
                        st.rerun()
                    else:
                        try:
                            template_manager.update_custom_template(selected_template_id, edited_prompt)
                            st.success("✅ 已保存")
                            st.rerun()
                        except Exception as e:
                            st.error(f"保存失败: {e}")

            with col_saveas:
                if st.button("📋 另存为新模板", use_container_width=True):
                    st.session_state['show_saveas_dialog'] = True

            with col_reset:
                if st.button("🔄 恢复默认", use_container_width=True):
                    # 清除编辑器状态，强制重新加载模板内容
                    if 'vlm_prompt_editor' in st.session_state:
                        del st.session_state['vlm_prompt_editor']
                    st.rerun()

            # 另存为对话框
            if st.session_state.get('show_saveas_dialog', False):
                with st.form("saveas_form"):
                    st.markdown("### 另存为新模板")
                    new_name = st.text_input("模板名称", value="自定义模板")
                    new_desc = st.text_input("描述", value="")

                    col_submit, col_cancel = st.columns(2)
                    with col_submit:
                        if st.form_submit_button("保存", use_container_width=True):
                            try:
                                new_id = template_manager.generate_template_id()
                                template_manager.save_custom_template(new_id, new_name, new_desc, edited_prompt)
                                st.success(f"✅ 已创建新模板：{new_name}")
                                st.session_state['show_saveas_dialog'] = False
                                st.rerun()
                            except Exception as e:
                                st.error(f"保存失败: {e}")

                    with col_cancel:
                        if st.form_submit_button("取消", use_container_width=True):
                            st.session_state['show_saveas_dialog'] = False
                            st.rerun()

            # 新建模板对话框
            if st.session_state.get('show_new_template_dialog', False):
                with st.form("new_template_form"):
                    st.markdown("### 新建模板")
                    new_name = st.text_input("模板名称", value="")
                    new_desc = st.text_input("描述", value="")
                    new_prompt = st.text_area("提示词内容", value="", height=200)

                    col_submit, col_cancel = st.columns(2)
                    with col_submit:
                        if st.form_submit_button("创建", use_container_width=True):
                            if not new_name.strip():
                                st.error("❌ 模板名称不能为空")
                            elif not new_prompt.strip():
                                st.error("❌ 提示词内容不能为空")
                            else:
                                try:
                                    new_id = template_manager.generate_template_id()
                                    template_manager.save_custom_template(new_id, new_name, new_desc, new_prompt)
                                    st.success(f"✅ 已创建新模板：{new_name}")
                                    st.session_state['show_new_template_dialog'] = False
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"创建失败: {e}")

                    with col_cancel:
                        if st.form_submit_button("取消", use_container_width=True):
                            st.session_state['show_new_template_dialog'] = False
                            st.rerun()

        # 🔧 后处理配置
        with st.expander("🔧 后处理配置", expanded=False):
            st.markdown("**📝 文本后处理**")

            # 噪音过滤
            st.caption("ℹ️ 生效级别：当前次 generalized 运行生效，按下方正则在后处理阶段清理 Markdown 文本。")
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
                help="修复Unicode上标脚注（¹) → <sup>1</sup>）",
                key="vlm_footnote_fix"
            )

            # 断行修复
            vlm_hyphenation_fix = st.checkbox(
                "启用断行修复",
                value=True,
                help="合并断行的单词（Philo-\\nsophen → Philosophen）",
                key="vlm_hyphenation_fix"
            )

            st.markdown("---")
            st.markdown("**🏷️ 页眉页脚与边注过滤**")
            st.caption("ℹ️ 生效级别：当前次 generalized 运行生效，仅移除页眉、页脚或边注语法标记并保留内容文本。")

            # 页眉过滤
            vlm_filter_page_header = st.checkbox(
                "过滤页眉语法标记",
                value=False,
                help="移除 <!-- PageHeader: --> 语法，保留内容；历史 <!-- page-header: --> 也兼容。",
                key="vlm_filter_page_header"
            )

            # 页脚过滤
            vlm_filter_page_footer = st.checkbox(
                "过滤页脚语法标记",
                value=False,
                help="移除 <!-- PageFooter: --> 语法，保留内容；历史 <!-- page-footer: --> 也兼容。",
                key="vlm_filter_page_footer"
            )

            vlm_filter_margin_notes = st.checkbox(
                "过滤边注语法标记",
                value=False,
                help="移除 <!-- Margin:left/right --> 包裹和引用符号，保留边注文本。",
                key="vlm_filter_margin_notes"
            )

            vlm_filter_blockquote_markers = st.checkbox(
                "过滤引用块语法标记",
                value=False,
                help="将识别为引用块的 Markdown > 或 HTML blockquote 包装转为普通文本，不处理普通文本中的 > 字符。",
                key="vlm_filter_blockquote_markers"
            )

        with st.expander("🛠️ VLM JSON 重渲染 / 失败页补跑", expanded=False):
            st.caption("上传已有 VLM 泛化 JSON 后，可只按当前侧边栏规则重新渲染；如需补跑失败页，再额外上传原始 PDF。")
            repair_pdf_file = st.file_uploader(
                "原始 PDF",
                type=["pdf"],
                key="vlm_repair_pdf_file",
            )
            repair_json_file = st.file_uploader(
                "已有 VLM 泛化 JSON",
                type=["json"],
                key="vlm_repair_json_file",
            )
            repair_json_path = st.text_input(
                "或填写已有 VLM 泛化 JSON 路径",
                value="",
                placeholder=r"output\xxx.json",
                key="vlm_repair_json_path",
            )

            if st.button("🔎 分析失败页", key="vlm_repair_analyze_btn"):
                try:
                    if repair_json_file is not None:
                        data = json.loads(repair_json_file.getvalue().decode("utf-8"))
                    elif repair_json_path.strip():
                        data = load_vlm_generalized_json(repair_json_path.strip())
                    else:
                        raise ValueError("需要上传 JSON 或填写 JSON 路径")
                    failed_pages = extract_failed_pages(data)
                    st.session_state["vlm_repair_failed_pages"] = failed_pages
                    if failed_pages:
                        st.warning(f"检测到 {len(failed_pages)} 个失败页：{', '.join(map(str, failed_pages[:80]))}")
                    else:
                        st.success("未检测到失败页")
                except Exception as exc:
                    st.error(f"分析失败：{exc}")

            failed_pages_preview = st.session_state.get("vlm_repair_failed_pages")
            if failed_pages_preview:
                st.caption(f"当前待修复页数：{len(failed_pages_preview)}")

            vlm_json_reprocess_values = dict(locals())

            def _prepare_vlm_json_reprocess_job(*, action: str) -> None:
                if action == "repair" and repair_pdf_file is None:
                    raise ValueError("补跑失败页需要上传原始 PDF")
                if repair_json_file is None and not repair_json_path.strip():
                    raise ValueError("需要上传 VLM JSON 或填写 JSON 路径")

                repair_output_dir = st.session_state.output_dir
                repair_tmp_dir = Path(repair_output_dir) / "_vlm_repair_inputs"
                repair_tmp_dir.mkdir(parents=True, exist_ok=True)

                repair_pdf_path = None
                if repair_pdf_file is not None:
                    repair_pdf_path = repair_tmp_dir / repair_pdf_file.name
                    repair_pdf_path.write_bytes(repair_pdf_file.getvalue())

                if repair_json_file is not None:
                    repair_old_json_path = repair_tmp_dir / repair_json_file.name
                    repair_old_json_path.write_bytes(repair_json_file.getvalue())
                    source_json_name = repair_json_file.name
                else:
                    repair_old_json_path = Path(repair_json_path.strip())
                    source_json_name = repair_old_json_path.name

                repair_values = dict(vlm_json_reprocess_values)
                repair_values.update(
                    {
                        "handwriting_mode": st.session_state.get("vlm_direct_handwriting_mode_simple", handwriting_mode),
                        "enable_marginalia": st.session_state.get("vlm_direct_enable_marginalia_simple", enable_marginalia),
                        "vlm_direct_max_concurrent": vlm_repair_max_concurrent,
                        "vlm_direct_max_retries": vlm_direct_max_retries,
                        "vlm_auto_repair_failed_pages": False,
                        "vlm_repair_max_concurrent": vlm_repair_max_concurrent,
                        "vlm_repair_rounds": 0,
                    }
                )
                repair_config, _ = build_vlm_generalized_config(
                    repair_values,
                    output_formats=output_formats,
                    template_manager=template_manager,
                )
                st.session_state.pending_vlm_repair_job = {
                    "action": action,
                    "pdf_path": str(repair_pdf_path) if repair_pdf_path is not None else None,
                    "json_path": str(repair_old_json_path),
                    "file_name": repair_pdf_file.name if repair_pdf_file is not None else source_json_name,
                    "converter_config": repair_config,
                    "output_formats": list(output_formats),
                    "emit_middle_json": bool(emit_middle_json),
                    "emit_middle_report": bool(emit_middle_report),
                    "emit_middle_debug": bool(emit_middle_debug),
                    "emit_middle_scholarly": bool(emit_middle_scholarly),
                    "emit_middle_scholarly_report": bool(emit_middle_scholarly_report),
                    "emit_layout_overlay": bool(emit_layout_overlay),
                    "emit_span_overlay": bool(emit_span_overlay),
                    "emit_middle_full_json": bool(emit_middle_full_json),
                    "output_dir": repair_output_dir,
                }

            col_rerender, col_repair = st.columns(2)
            with col_rerender:
                if st.button("🎛️ 按当前规则重新渲染 JSON", key="vlm_rerender_run_btn", use_container_width=True):
                    try:
                        _prepare_vlm_json_reprocess_job(action="rerender")
                        st.success("已提交 JSON 重渲染任务，正在后台启动。")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"重渲染失败：{exc}")
            with col_repair:
                repair_clicked = st.button(
                    "🚑 补跑失败页并生成完整结果",
                    key="vlm_repair_run_btn",
                    use_container_width=True,
                )

            if repair_clicked:
                try:
                    _prepare_vlm_json_reprocess_job(action="repair")
                    st.success("已提交失败页修复任务，正在后台启动。")
                    st.rerun()
                except Exception as exc:
                    st.error(f"补跑失败：{exc}")

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
        output_formats = ocr_output_formats if ocr_output_formats else ["markdown"]

    elif conversion_mode == "pipeline":
        # ==================== 传统模式配置 ====================
        # 输出格式选择（仅 Pipeline 模式）
        output_formats, middle_settings = _pipeline_output_settings_from_value(
            render_pipeline_output_settings(
                st,
                force_middle_json=always_save_middle_json,
            )
        )
        emit_middle_json = middle_settings.emit_middle_json
        emit_middle_report = middle_settings.emit_middle_report
        emit_middle_debug = middle_settings.emit_middle_debug
        emit_middle_scholarly = middle_settings.emit_middle_scholarly
        emit_middle_scholarly_report = middle_settings.emit_middle_scholarly_report
        emit_layout_overlay = middle_settings.emit_layout_overlay
        emit_span_overlay = middle_settings.emit_span_overlay
        emit_middle_full_json = middle_settings.emit_middle_full_json
        st.divider()

        # ==================== 3. 版面识别后端选择 ====================
        st.subheader("📐 版面识别后端")
        layout_backend = render_layout_backend_selector(st)
        layout_dpi_settings = render_pipeline_layout_dpi_settings(
            st,
            layout_backend=layout_backend,
            surya_layout_quality=surya_layout_quality,
            layout_dpi_override=layout_dpi_override,
        )
        surya_layout_quality = layout_dpi_settings["surya_layout_quality"]
        layout_dpi_override = layout_dpi_settings["layout_dpi_override"]

        # 版面识别后端配置
        if layout_backend == "surya":
            render_surya_layout_settings(
                st,
                description=LAYOUT_BACKEND_DESCRIPTIONS["surya"],
                extract_printed_pages=extract_printed_pages,
            )

        elif layout_backend in ("vlm", "vlm_layout"):
            vlm_layout_settings = render_vlm_layout_settings(
                st,
                description=LAYOUT_BACKEND_DESCRIPTIONS["vlm_layout"],
                base_url=vlm_layout_base_url,
                model=vlm_layout_model,
                api_key=vlm_layout_api_key,
                max_concurrent=vlm_layout_max_concurrent,
                image_format=vlm_layout_image_format,
                max_image_dimension=vlm_layout_max_image_dimension,
                jpeg_quality=vlm_layout_jpeg_quality,
                timeout=vlm_layout_timeout,
                prompt_template=vlm_layout_prompt_template,
                prompt=vlm_layout_prompt,
            )
            vlm_layout_base_url = vlm_layout_settings["vlm_layout_base_url"]
            vlm_layout_model = vlm_layout_settings["vlm_layout_model"]
            vlm_layout_api_key = vlm_layout_settings["vlm_layout_api_key"]
            vlm_layout_max_concurrent = vlm_layout_settings["vlm_layout_max_concurrent"]
            vlm_layout_image_format = vlm_layout_settings["vlm_layout_image_format"]
            vlm_layout_max_image_dimension = vlm_layout_settings["vlm_layout_max_image_dimension"]
            vlm_layout_jpeg_quality = vlm_layout_settings["vlm_layout_jpeg_quality"]
            vlm_layout_timeout = vlm_layout_settings["vlm_layout_timeout"]
            vlm_layout_prompt_template = vlm_layout_settings["vlm_layout_prompt_template"]
            vlm_layout_prompt = vlm_layout_settings["vlm_layout_prompt"]

            # 🆕 VLM 模式下的处理器配置默认值
            markdown_noise_removal_enabled = locals().get("markdown_noise_removal_enabled", True)
            markdown_noise_cleaning_level = locals().get("markdown_noise_cleaning_level", "basic")
            markdown_noise_custom_symbols = locals().get("markdown_noise_custom_symbols", "")
            markdown_noise_line_start_only = locals().get("markdown_noise_line_start_only", True)
            line_merge_enabled = locals().get("line_merge_enabled", True)
            blockquote_enabled = locals().get("blockquote_enabled", True)
            code_enabled = locals().get("code_enabled", True)
            section_header_enabled = locals().get("section_header_enabled", True)
            list_enabled = locals().get("list_enabled", True)
            footnote_enabled = locals().get("footnote_enabled", True)
            reference_enabled = locals().get("reference_enabled", True)
            equation_enabled = locals().get("equation_enabled", True)
            table_enabled = locals().get("table_enabled", True)

        elif layout_backend == "external_layout_sidecar":
            external_layout_settings = render_external_layout_sidecar_settings(
                st,
                description=LAYOUT_BACKEND_DESCRIPTIONS["external_layout_sidecar"],
            )
            external_layout_json = external_layout_settings["external_layout_json"]
            external_layout_block_source = external_layout_settings["external_layout_block_source"]
            external_layout_backend_name = external_layout_settings["external_layout_backend_name"]
            external_layout_model = external_layout_settings["external_layout_model"]
            external_layout_allow_missing_pages = external_layout_settings["external_layout_allow_missing_pages"]

            markdown_noise_removal_enabled = locals().get("markdown_noise_removal_enabled", True)
            markdown_noise_cleaning_level = locals().get("markdown_noise_cleaning_level", "basic")
            markdown_noise_custom_symbols = locals().get("markdown_noise_custom_symbols", "")
            markdown_noise_line_start_only = locals().get("markdown_noise_line_start_only", True)
            line_merge_enabled = locals().get("line_merge_enabled", True)
            blockquote_enabled = locals().get("blockquote_enabled", True)
            code_enabled = locals().get("code_enabled", True)
            section_header_enabled = locals().get("section_header_enabled", True)
            list_enabled = locals().get("list_enabled", True)
            footnote_enabled = locals().get("footnote_enabled", True)
            reference_enabled = locals().get("reference_enabled", True)
            equation_enabled = locals().get("equation_enabled", True)
            table_enabled = locals().get("table_enabled", True)

        elif layout_backend == "mineru_pp_doclayout_v2_direct":
            mineru_direct_layout_settings = render_mineru_direct_layout_settings(
                st,
                description=LAYOUT_BACKEND_DESCRIPTIONS["mineru_pp_doclayout_v2_direct"],
            )
            mineru_layout_python = mineru_direct_layout_settings["mineru_layout_python"]
            mineru_layout_model_dir = mineru_direct_layout_settings["mineru_layout_model_dir"]
            mineru_layout_device = mineru_direct_layout_settings["mineru_layout_device"]
            mineru_layout_batch_size = mineru_direct_layout_settings["mineru_layout_batch_size"]
            mineru_layout_timeout = mineru_direct_layout_settings["mineru_layout_timeout"]
            mineru_layout_use_paddlex_filter_boxes = mineru_direct_layout_settings[
                "mineru_layout_use_paddlex_filter_boxes"
            ]

            markdown_noise_removal_enabled = locals().get("markdown_noise_removal_enabled", True)
            markdown_noise_cleaning_level = locals().get("markdown_noise_cleaning_level", "basic")
            markdown_noise_custom_symbols = locals().get("markdown_noise_custom_symbols", "")
            markdown_noise_line_start_only = locals().get("markdown_noise_line_start_only", True)
            line_merge_enabled = locals().get("line_merge_enabled", True)
            blockquote_enabled = locals().get("blockquote_enabled", True)
            code_enabled = locals().get("code_enabled", True)
            section_header_enabled = locals().get("section_header_enabled", True)
            list_enabled = locals().get("list_enabled", True)
            footnote_enabled = locals().get("footnote_enabled", True)
            reference_enabled = locals().get("reference_enabled", True)
            equation_enabled = locals().get("equation_enabled", True)
            table_enabled = locals().get("table_enabled", True)

        elif layout_backend == "mineru_vl_layout":
            mineru_vl_layout_settings = render_mineru_vl_layout_settings(
                st,
                description=LAYOUT_BACKEND_DESCRIPTIONS["mineru_vl_layout"],
            )
            mineru_vl_endpoint = mineru_vl_layout_settings["mineru_vl_endpoint"]
            mineru_vl_api_key = mineru_vl_layout_settings["mineru_vl_api_key"]
            mineru_vl_api_style = mineru_vl_layout_settings["mineru_vl_api_style"]
            mineru_vl_version = mineru_vl_layout_settings["mineru_vl_version"]
            mineru_vl_quant = mineru_vl_layout_settings["mineru_vl_quant"]
            mineru_vl_model = mineru_vl_layout_settings["mineru_vl_model"]
            mineru_vl_layout_image_size = mineru_vl_layout_settings["mineru_vl_layout_image_size"]
            mineru_vl_layout_timeout = mineru_vl_layout_settings["mineru_vl_layout_timeout"]
            mineru_vl_layout_max_tokens = mineru_vl_layout_settings["mineru_vl_layout_max_tokens"]
            mineru_vl_layout_concurrency = mineru_vl_layout_settings["mineru_vl_layout_concurrency"]
            mineru_vl_request_concurrency = mineru_vl_layout_settings["mineru_vl_request_concurrency"]
            mineru_vl_image_quality = mineru_vl_layout_settings["mineru_vl_image_quality"]

            markdown_noise_removal_enabled = locals().get("markdown_noise_removal_enabled", True)
            markdown_noise_cleaning_level = locals().get("markdown_noise_cleaning_level", "basic")
            markdown_noise_custom_symbols = locals().get("markdown_noise_custom_symbols", "")
            markdown_noise_line_start_only = locals().get("markdown_noise_line_start_only", True)
            line_merge_enabled = locals().get("line_merge_enabled", True)
            blockquote_enabled = locals().get("blockquote_enabled", True)
            code_enabled = locals().get("code_enabled", True)
            section_header_enabled = locals().get("section_header_enabled", True)
            list_enabled = locals().get("list_enabled", True)
            footnote_enabled = locals().get("footnote_enabled", True)
            reference_enabled = locals().get("reference_enabled", True)
            equation_enabled = locals().get("equation_enabled", True)
            table_enabled = locals().get("table_enabled", True)

        elif layout_backend == "surya2_layout":
            surya2_layout_settings = render_surya2_vlm_settings(
                st,
                description=LAYOUT_BACKEND_DESCRIPTIONS["surya2_layout"],
                layout_mode=True,
                key_prefix="layout_surya2",
            )
            surya2_endpoint = surya2_layout_settings["surya2_endpoint"]
            surya2_api_key = surya2_layout_settings["surya2_api_key"]
            surya2_api_style = surya2_layout_settings["surya2_api_style"]
            surya2_version = surya2_layout_settings["surya2_version"]
            surya2_model = surya2_layout_settings["surya2_model"]
            surya2_layout_timeout = surya2_layout_settings["surya2_layout_timeout"]
            surya2_layout_max_tokens = surya2_layout_settings["surya2_layout_max_tokens"]
            surya2_layout_batch_size = surya2_layout_settings["surya2_layout_batch_size"]
            surya2_layout_concurrency = surya2_layout_settings["surya2_layout_concurrency"]
            surya2_request_concurrency = surya2_layout_settings["surya2_request_concurrency"]
            surya2_block_concurrency = surya2_layout_settings["surya2_block_concurrency"]
            surya2_image_format = surya2_layout_settings["surya2_image_format"]
            surya2_image_quality = surya2_layout_settings["surya2_image_quality"]

            markdown_noise_removal_enabled = locals().get("markdown_noise_removal_enabled", True)
            markdown_noise_cleaning_level = locals().get("markdown_noise_cleaning_level", "basic")
            markdown_noise_custom_symbols = locals().get("markdown_noise_custom_symbols", "")
            markdown_noise_line_start_only = locals().get("markdown_noise_line_start_only", True)
            line_merge_enabled = locals().get("line_merge_enabled", True)
            blockquote_enabled = locals().get("blockquote_enabled", True)
            code_enabled = locals().get("code_enabled", True)
            section_header_enabled = locals().get("section_header_enabled", True)
            list_enabled = locals().get("list_enabled", True)
            footnote_enabled = locals().get("footnote_enabled", True)
            reference_enabled = locals().get("reference_enabled", True)
            equation_enabled = locals().get("equation_enabled", True)
            table_enabled = locals().get("table_enabled", True)

        elif layout_backend in ("paddle_pp_doclayout_plus_l", "paddle_pp_doclayout_v3"):
            default_paddle_model = "PP-DocLayoutV3" if layout_backend == "paddle_pp_doclayout_v3" else "PP-DocLayout_plus-L"
            paddle_layout_settings = render_paddle_layout_settings(
                st,
                description=LAYOUT_BACKEND_DESCRIPTIONS[layout_backend],
                default_model_name=default_paddle_model,
            )
            paddle_layout_model_name = paddle_layout_settings["paddle_layout_model_name"]
            paddle_layout_model_dir = paddle_layout_settings["paddle_layout_model_dir"]
            paddle_layout_device = paddle_layout_settings["paddle_layout_device"]
            paddle_layout_engine = paddle_layout_settings["paddle_layout_engine"]
            paddle_layout_enable_mkldnn = paddle_layout_settings["paddle_layout_enable_mkldnn"]
            paddle_layout_cpu_threads = paddle_layout_settings["paddle_layout_cpu_threads"]
            paddle_layout_threshold = paddle_layout_settings["paddle_layout_threshold"]
            paddle_layout_img_size = paddle_layout_settings["paddle_layout_img_size"]
            paddle_layout_batch_size = paddle_layout_settings["paddle_layout_batch_size"]

            markdown_noise_removal_enabled = locals().get("markdown_noise_removal_enabled", True)
            markdown_noise_cleaning_level = locals().get("markdown_noise_cleaning_level", "basic")
            markdown_noise_custom_symbols = locals().get("markdown_noise_custom_symbols", "")
            markdown_noise_line_start_only = locals().get("markdown_noise_line_start_only", True)
            line_merge_enabled = locals().get("line_merge_enabled", True)
            blockquote_enabled = locals().get("blockquote_enabled", True)
            code_enabled = locals().get("code_enabled", True)
            section_header_enabled = locals().get("section_header_enabled", True)
            list_enabled = locals().get("list_enabled", True)
            footnote_enabled = locals().get("footnote_enabled", True)
            reference_enabled = locals().get("reference_enabled", True)
            equation_enabled = locals().get("equation_enabled", True)
            table_enabled = locals().get("table_enabled", True)

        st.markdown("---")
        st.subheader("🔧 Pipeline 后处理配置")
        st.caption(
            "适用于 Pipeline 模式下的所有版面后端。版面后端先产生区域框，随后这些处理器统一负责文本清理、结构识别、页眉页脚与输出行为。"
        )
        processor_settings = render_pipeline_processor_settings(st)
        page_margin_settings = render_pipeline_page_margin_settings(
            st,
            extract_printed_pages=extract_printed_pages,
        )
        markdown_noise_removal_enabled = processor_settings["markdown_noise_removal_enabled"]
        markdown_noise_cleaning_level = processor_settings["markdown_noise_cleaning_level"]
        markdown_noise_custom_symbols = processor_settings["markdown_noise_custom_symbols"]
        markdown_noise_line_start_only = processor_settings["markdown_noise_line_start_only"]
        line_merge_enabled = processor_settings["line_merge_enabled"]
        blockquote_enabled = processor_settings["blockquote_enabled"]
        code_enabled = processor_settings["code_enabled"]
        section_header_enabled = processor_settings["section_header_enabled"]
        equation_enabled = processor_settings["equation_enabled"]
        equation_output_mode = processor_settings["equation_output_mode"]
        list_enabled = processor_settings["list_enabled"]
        footnote_enabled = processor_settings["footnote_enabled"]
        reference_enabled = processor_settings["reference_enabled"]
        table_enabled = processor_settings["table_enabled"]
        emit_page_header_comment = page_margin_settings["emit_page_header_comment"]
        emit_page_footer_comment = page_margin_settings["emit_page_footer_comment"]
        keep_pageheader_in_output = page_margin_settings["keep_pageheader_in_output"]
        keep_pagefooter_in_output = page_margin_settings["keep_pagefooter_in_output"]
        marginal_output_mode = page_margin_settings.get("marginal_output_mode", marginal_output_mode)
        printed_page_zones = page_margin_settings["printed_page_zones"]
        printed_page_header_end = page_margin_settings["printed_page_header_end"]
        printed_page_footer_start = page_margin_settings["printed_page_footer_start"]

        st.divider()

        # ==================== 4. OCR 后端选择（核心） ====================
        st.subheader("🔍 OCR 后端")
        chrome_screenai_light = bool(st.session_state.get("chrome_screenai_light", False))
        chrome_preprocess_mode = st.session_state.get("chrome_preprocess_mode", "native")
        chrome_workers = int(st.session_state.get("chrome_workers", 2))
        chrome_chunk_pages = int(st.session_state.get("chrome_chunk_pages", 4))
        chrome_emit_searchable_pdf = bool(st.session_state.get("chrome_emit_searchable_pdf", False))
        chrome_rasterize_dpi = int(st.session_state.get("chrome_rasterize_dpi", 144))
        chrome_model_dir = st.session_state.get("chrome_model_dir", "")
        legacy_preprocess_backend = (
            str(st.session_state.get("ocr_preprocess_backend", "none") or "none")
            .strip()
            .lower()
            .replace("-", "_")
        )
        if legacy_preprocess_backend == "chrome_screenai_searchable_pdf" and st.session_state.get("ocr_backend") != "chrome_screenai":
            st.session_state["ocr_backend"] = "chrome_screenai"
            st.session_state["ocr_preprocess_backend"] = "none"
            st.info("已将旧版 ScreenAI 预处理配置迁移为 OCR 后端 `chrome_screenai`。")

        ocr_backend = render_ocr_backend_selector(st)
        ocr_preprocess_backend = "chrome_screenai_searchable_pdf" if ocr_backend == "chrome_screenai" else "none"
        st.session_state["ocr_preprocess_backend"] = ocr_preprocess_backend

        if ocr_backend == "chrome_screenai":
            ocr_quality = "auto"
            ocr_dpi_override = None
        else:
            ocr_dpi_settings = render_pipeline_ocr_dpi_settings(
                st,
                ocr_backend=ocr_backend,
                ocr_quality=ocr_quality,
                ocr_dpi_override=ocr_dpi_override,
            )
            ocr_quality = ocr_dpi_settings["ocr_quality"]
            ocr_dpi_override = ocr_dpi_settings["ocr_dpi_override"]

        # ==================== 3.1 后端说明与配置 ====================
        if ocr_backend == "chrome_screenai":
            st.caption(
                "先用 Chrome ScreenAI 处理整本 PDF，写回 searchable PDF，"
                "随后继续使用当前 layout backend，并直接读取回流后的内嵌文本层。"
            )
            chrome_workers = int(
                st.number_input(
                    "ScreenAI 并行数",
                    min_value=1,
                    max_value=16,
                    value=chrome_workers,
                    step=1,
                    key="chrome_workers",
                )
            )
            chrome_emit_searchable_pdf = st.checkbox(
                "导出 searchable PDF 中间件",
                value=chrome_emit_searchable_pdf,
                key="chrome_emit_searchable_pdf",
            )
            chrome_chunk_pages = max(1, int(chrome_workers))
            st.session_state["chrome_chunk_pages"] = chrome_chunk_pages
            st.info("本次不会执行常规块级 OCR。内部顺序为 ScreenAI -> searchable PDF -> layout + embedded text。")
            force_ocr = False
            use_llm = False

        elif ocr_backend == "none":
            st.caption(
                "使用 PDF 内嵌文本层，适用于已有高质量 OCR 层或原生文本层的 PDF。"
                " 清晰的主流印刷物可先经 OCRmyPDF-AIH 等工具补齐高精度文本层，再结合 Surya 做版面识别，通常效果更稳且性能开销更低。"
            )
            force_ocr = False
            use_llm = False

        elif ocr_backend == "surya":
            surya_ocr_settings = render_surya_ocr_settings(
                st,
                description=OCR_BACKEND_DESCRIPTIONS["surya"],
                batch_size=ocr_batch_size,
                force_ocr=force_ocr,
            )
            ocr_batch_size = surya_ocr_settings["ocr_batch_size"]
            force_ocr = surya_ocr_settings["force_ocr"]

        # 在 "config_dict = build_config_dict(config_params)" 之后添加
        elif ocr_backend == "calamari":
            calamari_settings = render_calamari_ocr_settings(
                st,
                description=OCR_BACKEND_DESCRIPTIONS["calamari"],
                base_url=calamari_base_url,
                model=calamari_model,
                batch_size=calamari_batch_size,
                timeout=calamari_timeout,
                sequential_mode=calamari_sequential_mode,
                trust_batch_order=calamari_trust_batch_order,
                require_ordering_info=calamari_require_ordering_info,
                fallback_to_sequential_on_ordering_failure=calamari_fallback_to_sequential_on_ordering_failure,
                footnote_y_frac=0.83,
                binarize_lines=True,
                check_health=check_calamari_health,
                get_models=get_calamari_models,
                preprocess=calamari_preprocess,
                crop_padding_px=calamari_crop_padding_px,
                crop_padding_frac=calamari_crop_padding_frac,
                upscale_min_height=calamari_upscale_min_height,
                split_large_batches=calamari_split_large_batches,
            )
            calamari_base_url = calamari_settings["calamari_base_url"]
            calamari_model = calamari_settings["calamari_model"]
            calamari_batch_size = calamari_settings["calamari_batch_size"]
            calamari_timeout = calamari_settings["calamari_timeout"]
            calamari_sequential_mode = calamari_settings["calamari_sequential_mode"]
            calamari_trust_batch_order = calamari_settings["calamari_trust_batch_order"]
            calamari_require_ordering_info = calamari_settings["calamari_require_ordering_info"]
            calamari_fallback_to_sequential_on_ordering_failure = calamari_settings["calamari_fallback_to_sequential_on_ordering_failure"]
            calamari_footnote_y_frac = calamari_settings["calamari_footnote_y_frac"]
            calamari_binarize_lines = calamari_settings["calamari_binarize_lines"]
            calamari_preprocess = calamari_settings["calamari_preprocess"]
            calamari_crop_padding_px = calamari_settings["calamari_crop_padding_px"]
            calamari_crop_padding_frac = calamari_settings["calamari_crop_padding_frac"]
            calamari_upscale_min_height = calamari_settings["calamari_upscale_min_height"]
            calamari_split_large_batches = calamari_settings["calamari_split_large_batches"]
            tesseract_line_psm = calamari_settings["tesseract_line_psm"]
            tesseract_line_preprocess = calamari_settings["tesseract_line_preprocess"]
            tesseract_thresholding_method = calamari_settings["tesseract_thresholding_method"]
            force_ocr = calamari_settings["force_ocr"]
            use_llm = calamari_settings["use_llm"]
            ocr_batch_size = calamari_settings["ocr_batch_size"]

        elif ocr_backend == "paddle_ocr_v5":
            paddle_ocr_settings = render_paddle_ocr_settings(
                st,
                description=OCR_BACKEND_DESCRIPTIONS.get("paddle_ocr_v5", "PaddleOCR PP-OCRv5"),
            )
            paddle_ocr_lang = paddle_ocr_settings["paddle_ocr_lang"]
            paddle_ocr_version = paddle_ocr_settings["paddle_ocr_version"]
            paddle_ocr_device = paddle_ocr_settings["paddle_ocr_device"]
            paddle_ocr_engine = paddle_ocr_settings["paddle_ocr_engine"]
            paddle_ocr_enable_mkldnn = paddle_ocr_settings["paddle_ocr_enable_mkldnn"]
            paddle_ocr_cpu_threads = paddle_ocr_settings["paddle_ocr_cpu_threads"]
            paddle_ocr_use_doc_orientation_classify = paddle_ocr_settings["paddle_ocr_use_doc_orientation_classify"]
            paddle_ocr_use_doc_unwarping = paddle_ocr_settings["paddle_ocr_use_doc_unwarping"]
            paddle_ocr_use_textline_orientation = paddle_ocr_settings["paddle_ocr_use_textline_orientation"]
            force_ocr = paddle_ocr_settings["force_ocr"]
            use_llm = paddle_ocr_settings["use_llm"]
            ocr_batch_size = paddle_ocr_settings["ocr_batch_size"]

        elif ocr_backend == "paddleocr_vl_ocr":
            paddle_vl_default_version = default_version("paddleocr_vl")
            paddle_vl_default_model = resolve_vlm_model(
                "paddleocr_vl",
                version=paddle_vl_default_version,
            )
            paddle_vl_ocr_settings = render_paddleocr_vl_ocr_settings(
                st,
                description=OCR_BACKEND_DESCRIPTIONS["paddleocr_vl_ocr"],
                endpoint=os.environ.get("PADDLEOCR_VL_ENDPOINT", "http://127.0.0.1:1234/v1/chat/completions"),
                model=os.environ.get("PADDLEOCR_VL_MODEL", paddle_vl_default_model),
                api_key=os.environ.get("PADDLEOCR_VL_API_KEY", "lm-studio"),
                api_style=os.environ.get("PADDLEOCR_VL_API_STYLE", "openai"),
                block_concurrency=4,
                image_format="JPEG",
                image_quality=90,
                crop_padding_px=4,
                crop_padding_frac=0.02,
            )
            paddleocr_vl_version = paddle_vl_default_version
            paddleocr_vl_endpoint = paddle_vl_ocr_settings["paddleocr_vl_endpoint"]
            paddleocr_vl_version = paddle_vl_ocr_settings["paddleocr_vl_version"]
            paddleocr_vl_model = paddle_vl_ocr_settings["paddleocr_vl_model"]
            paddleocr_vl_api_key = paddle_vl_ocr_settings["paddleocr_vl_api_key"]
            paddleocr_vl_api_style = paddle_vl_ocr_settings["paddleocr_vl_api_style"]
            paddleocr_vl_request_concurrency = paddle_vl_ocr_settings["paddleocr_vl_request_concurrency"]
            paddleocr_vl_block_concurrency = paddle_vl_ocr_settings["paddleocr_vl_block_concurrency"]
            paddleocr_vl_prompt_label = paddle_vl_ocr_settings["paddleocr_vl_prompt_label"]
            paddleocr_vl_image_format = paddle_vl_ocr_settings["paddleocr_vl_image_format"]
            paddleocr_vl_image_quality = paddle_vl_ocr_settings["paddleocr_vl_image_quality"]
            paddleocr_vl_crop_padding_px = paddle_vl_ocr_settings["paddleocr_vl_crop_padding_px"]
            paddleocr_vl_crop_padding_frac = paddle_vl_ocr_settings["paddleocr_vl_crop_padding_frac"]
            force_ocr = paddle_vl_ocr_settings["force_ocr"]
            use_llm = paddle_vl_ocr_settings["use_llm"]
            ocr_batch_size = paddle_vl_ocr_settings["ocr_batch_size"]

        elif ocr_backend == "surya2_ocr":
            surya2_ocr_settings = render_surya2_vlm_settings(
                st,
                description=OCR_BACKEND_DESCRIPTIONS["surya2_ocr"],
                pipeline_ocr=True,
                key_prefix="ocr_surya2",
            )
            surya2_endpoint = surya2_ocr_settings["surya2_endpoint"]
            surya2_api_key = surya2_ocr_settings["surya2_api_key"]
            surya2_api_style = surya2_ocr_settings["surya2_api_style"]
            surya2_version = surya2_ocr_settings["surya2_version"]
            surya2_model = surya2_ocr_settings["surya2_model"]
            surya2_layout_timeout = surya2_ocr_settings["surya2_layout_timeout"]
            surya2_layout_max_tokens = surya2_ocr_settings["surya2_layout_max_tokens"]
            surya2_request_concurrency = surya2_ocr_settings["surya2_request_concurrency"]
            surya2_block_concurrency = surya2_ocr_settings["surya2_block_concurrency"]
            surya2_image_format = surya2_ocr_settings["surya2_image_format"]
            surya2_image_quality = surya2_ocr_settings["surya2_image_quality"]
            surya2_crop_padding_px = surya2_ocr_settings["surya2_crop_padding_px"]
            surya2_crop_padding_frac = surya2_ocr_settings["surya2_crop_padding_frac"]
            force_ocr = surya2_ocr_settings["force_ocr"]
            use_llm = surya2_ocr_settings["use_llm"]
            ocr_batch_size = surya2_ocr_settings["ocr_batch_size"]

        elif ocr_backend == "mineru_pytorch_paddle_ocr":
            mineru_ocr_settings = render_mineru_ocr_settings(
                st,
                description=OCR_BACKEND_DESCRIPTIONS["mineru_pytorch_paddle_ocr"],
            )
            mineru_ocr_python = mineru_ocr_settings["mineru_ocr_python"]
            mineru_ocr_device = mineru_ocr_settings["mineru_ocr_device"]
            mineru_ocr_lang = mineru_ocr_settings["mineru_ocr_lang"]
            mineru_ocr_timeout = mineru_ocr_settings["mineru_ocr_timeout"]
            mineru_ocr_det_db_box_thresh = mineru_ocr_settings["mineru_ocr_det_db_box_thresh"]
            mineru_ocr_det_db_unclip_ratio = mineru_ocr_settings["mineru_ocr_det_db_unclip_ratio"]
            mineru_ocr_enable_merge_det_boxes = mineru_ocr_settings["mineru_ocr_enable_merge_det_boxes"]
            force_ocr = mineru_ocr_settings["force_ocr"]
            use_llm = mineru_ocr_settings["use_llm"]
            ocr_batch_size = mineru_ocr_settings["ocr_batch_size"]

        elif ocr_backend == "tesseract":
            tesseract_settings = render_tesseract_ocr_settings(
                st,
                description=OCR_BACKEND_DESCRIPTIONS["tesseract"],
            )
            tesseract_profile = tesseract_settings["tesseract_profile"]
            tesseract_cmd = tesseract_settings["tesseract_cmd"]
            tesseract_lang = tesseract_settings["tesseract_lang"]
            tesseract_oem = tesseract_settings["tesseract_oem"]
            tesseract_psm = tesseract_settings["tesseract_psm"]
            tesseract_timeout = tesseract_settings["tesseract_timeout"]
            tesseract_omp_thread_limit = tesseract_settings["tesseract_omp_thread_limit"]
            tesseract_tessdata_prefix = tesseract_settings["tesseract_tessdata_prefix"]
            tesseract_user_words = tesseract_settings["tesseract_user_words"]
            tesseract_user_patterns = tesseract_settings["tesseract_user_patterns"]
            tesseract_extra_config = tesseract_settings["tesseract_extra_config"]
            tesseract_line_psm = tesseract_settings["tesseract_line_psm"]
            tesseract_line_preprocess = tesseract_settings["tesseract_line_preprocess"]
            tesseract_line_upscale_min_height = tesseract_settings["tesseract_line_upscale_min_height"]
            tesseract_thresholding_method = tesseract_settings["tesseract_thresholding_method"]
            ocr_crop_padding_px = tesseract_settings["ocr_crop_padding_px"]
            ocr_crop_padding_frac = tesseract_settings["ocr_crop_padding_frac"]
            ocr_crop_preprocess = tesseract_settings["ocr_crop_preprocess"]
            ocr_crop_upscale_min_height = tesseract_settings["ocr_crop_upscale_min_height"]
            force_ocr = tesseract_settings["force_ocr"]
            use_llm = tesseract_settings["use_llm"]
            ocr_batch_size = tesseract_settings["ocr_batch_size"]

        elif ocr_backend in ("vlm", "vlm_ocr"):
            vlm_ocr_settings = render_vlm_ocr_settings(
                st,
                description=OCR_BACKEND_DESCRIPTIONS["vlm_ocr"],
                layout_backend=layout_backend,
                base_url=openai_base_url,
                model=openai_model,
                api_key=openai_api_key,
                max_concurrent=openai_max_concurrent,
                image_format=openai_image_format,
                mode=vlm_mode,
                response_mode=vlm_response_mode,
                prompt=vlm_prompt,
                use_stop=openai_use_stop,
                merge_y_threshold=vlm_merge_y_threshold,
                merge_max_blocks=vlm_merge_max_blocks,
                full_page_max_tokens=vlm_full_page_max_tokens,
            )
            openai_base_url = vlm_ocr_settings["openai_base_url"]
            openai_model = vlm_ocr_settings["openai_model"]
            openai_api_key = vlm_ocr_settings["openai_api_key"]
            openai_max_concurrent = vlm_ocr_settings["openai_max_concurrent"]
            openai_image_format = vlm_ocr_settings["openai_image_format"]
            vlm_mode = vlm_ocr_settings["vlm_mode"]
            vlm_response_mode = vlm_ocr_settings["vlm_response_mode"]
            vlm_prompt = vlm_ocr_settings["vlm_prompt"]
            openai_use_stop = vlm_ocr_settings["openai_use_stop"]
            vlm_merge_y_threshold = vlm_ocr_settings["vlm_merge_y_threshold"]
            vlm_merge_max_blocks = vlm_ocr_settings["vlm_merge_max_blocks"]
            vlm_full_page_max_tokens = vlm_ocr_settings["vlm_full_page_max_tokens"]
            force_ocr = vlm_ocr_settings["force_ocr"]
            use_llm = vlm_ocr_settings["use_llm"]
            ocr_batch_size = vlm_ocr_settings["ocr_batch_size"]

        # ==================== OCR 后端配置结束 ====================
        st.divider()

        # ==================== 5. LLM 增强配置 ====================
        llm_provider = "lmstudio_native"
        llm_base_url = ""
        llm_model = ""
        llm_api_key = ""
        llm_api_version = "2024-08-01-preview"
        llm_max_concurrency = 3
        llm_timeout = 120
        llm_table_enabled = False
        llm_equation_enabled = False
        llm_image_description_enabled = False
        llm_image_description_language = "auto"
        llm_handwriting_enabled = False
        llm_page_correction_enabled = False
        llm_section_header_enabled = False
        llm_form_enabled = False
        llm_complex_region_enabled = False
        llm_noise_removal_enabled = False
        llm_printed_page_correction_enabled = False
        llm_heuristic_layout_enabled = False
        llm_page_correction_prompt = ""
        llm_thinking_mode = "off"

        st.subheader("🧠 LLM 增强")
        st.caption(
            "适用于 Pipeline 模式下的所有版面后端。LLM 在基础流水线结果之上追加结构与内容增强；"
            "实际效果取决于前置 layout/OCR 是否产生了对应块类型和文本内容。"
        )
        use_llm = st.checkbox(
            "启用 LLM 增强",
            value=False,
            help="使用大语言模型优化 Pipeline 结果。不是 Surya 专属；Paddle、MinerU Direct、External Sidecar 等后端也可组合使用。",
            key="use_llm",
        )

        if use_llm:
            with st.expander("LLM 配置", expanded=True):
                # 服务协议选择
                llm_provider = st.selectbox(
                    "服务协议",
                    options=["lmstudio_native", "openai_compatible", "ollama", "gemini", "azure", "claude"],
                    index=0,
                    format_func=lambda x: {
                        "lmstudio_native": "LM Studio 原生（本地）",
                        "openai_compatible": "OpenAI 兼容",
                        "ollama": "Ollama（本地原生）",
                        "gemini": "Google Gemini（原生）",
                        "azure": "Azure OpenAI",
                        "claude": "Anthropic Claude",
                    }.get(x, x),
                    help="LM Studio 原生使用 /api/v1/chat；OpenAI 兼容使用 /v1/chat/completions；云端服务可选择对应原生协议。",
                    key="llm_provider"
                )

                if llm_provider == "lmstudio_native":
                    st.caption("使用 LM Studio 原生协议（/api/v1/chat）。")
                    llm_base_url = st.text_input(
                        "LM Studio 端点",
                        value=os.environ.get("LMSTUDIO_BASE_URL", "http://localhost:1234/api/v1/chat"),
                        help="若只填写到 /v1，系统会自动补成 /api/v1/chat。",
                        key="llm_lmstudio_base_url"
                    )
                    llm_model = st.text_input(
                        "模型名称",
                        value=os.environ.get("LMSTUDIO_MODEL", os.environ.get("OPENAI_MODEL", "")),
                        help="例如：qwen2.5-vl、kimi-vl、gemma3 等本地已加载模型。",
                        key="llm_lmstudio_model"
                    )
                    llm_api_key = st.text_input(
                        "API Key（可选）",
                        value=os.environ.get("LMSTUDIO_API_KEY", "lm-studio"),
                        type="password",
                        help="LM Studio 通常接受任意值；留默认即可。",
                        key="llm_lmstudio_api_key"
                    )
                    llm_thinking_mode = st.radio(
                        "思考模式",
                        options=["off", "on"],
                        index=0,
                        horizontal=True,
                        format_func=lambda x: {
                            "off": "不思考（默认）",
                            "on": "启用思考"
                        }.get(x, x),
                        help="启用思考可能提升复杂判断，但会增加延迟。当前为原生模式优先支持的实验选项。",
                        key="llm_thinking_mode"
                    )
                    llm_max_concurrency = st.number_input(
                        "最大并发数",
                        min_value=1,
                        max_value=20,
                        value=3,
                        help="本地 LM Studio 通常从 1-3 开始。",
                        key="llm_lmstudio_max_concurrency"
                    )
                    llm_timeout = 120

                elif llm_provider == "openai_compatible":
                    st.caption("使用 OpenAI 兼容 Chat Completions 协议。适用于 OpenAI、vLLM、One API、LiteLLM、LM Studio 兼容端点等。")
                    llm_base_url = st.text_input(
                        "Base URL",
                        value=os.environ.get("OPENAI_BASE_URL", "http://localhost:1234/v1"),
                        help="OpenAI 兼容 API 根地址，例如 http://localhost:1234/v1 或 https://api.openai.com/v1。",
                        key="llm_openai_compatible_base_url"
                    )
                    llm_model = st.text_input(
                        "模型名称",
                        value=os.environ.get("OPENAI_MODEL", ""),
                        help="例如 gpt-4o-mini、qwen2.5-vl、本地兼容端点中的模型名。",
                        key="llm_openai_compatible_model"
                    )
                    llm_api_key = st.text_input(
                        "API Key",
                        value=os.environ.get("OPENAI_API_KEY", "lm-studio"),
                        type="password",
                        help="本地兼容服务通常接受任意值；云端服务需填写真实 key。",
                        key="llm_openai_compatible_api_key"
                    )
                    llm_max_concurrency = st.number_input(
                        "最大并发数",
                        min_value=1,
                        max_value=50,
                        value=3,
                        help="本地服务通常从 1-3 开始；云端按限流逐步提高。",
                        key="llm_openai_compatible_max_concurrency"
                    )
                    llm_timeout = 120
                    llm_thinking_mode = "off"

                # Gemini 配置
                elif llm_provider == "gemini":
                    st.caption("Google Gemini 配置。")

                    # 多Key输入支持
                    llm_api_key = st.text_area(
                        "Gemini API Keys (支持多个)",
                        value=os.environ.get("GEMINI_API_KEY", ""),
                        height=100,
                        help="每行一个或用英文逗号分隔。多 key 可轮换请求。",
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
                                st.success(f"已检测到 {key_count} 个 API Key")
                                suggested_concurrent = key_count * 3
                                st.caption(f"可将并发数逐步提高到 {suggested_concurrent} 左右，具体取决于服务限流。")

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
                            help="同时处理的 LLM 请求数。多 key 时可逐步提高。",
                            key="llm_gemini_max_concurrency"
                        )
                        llm_base_url = ""
                        llm_timeout = 120

                # Ollama 配置（支持 OpenAI 兼容 API）
                    llm_thinking_mode = "off"

                elif llm_provider == "ollama":
                    st.caption("Ollama 配置。")
                    st.info("Ollama 使用本地原生 `/api/generate` 协议；LM Studio 对应上方“LM Studio 原生”。")

                    llm_base_url = st.text_input(
                        "API URL",
                        value=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
                        help="Ollama 服务地址，例如 http://localhost:11434",
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
                    llm_thinking_mode = "off"

                # Azure OpenAI 配置
                elif llm_provider == "azure":
                    st.caption("Azure OpenAI 配置。")
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
                    llm_api_version = st.text_input(
                        "API Version",
                        value=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-08-01-preview"),
                        help="Azure OpenAI API 版本。",
                        key="llm_azure_api_version"
                    )
                    llm_max_concurrency = 3
                    llm_timeout = 120
                    llm_thinking_mode = "off"

                # Claude 配置
                elif llm_provider == "claude":
                    st.caption("Anthropic Claude 配置。")
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
                    llm_thinking_mode = "off"

                st.divider()

                # LLM 处理模块配置
                st.caption("🔧 LLM 处理模块")
                st.markdown("选择要启用的 LLM 增强功能。区域类能力需要前置 layout 后端识别出对应块。")

                col1, col2 = st.columns(2)

                with col1:
                    llm_table_enabled = st.checkbox(
                        "表格优化",
                        value=False,
                        help="修正表格结构，确保列对齐正确。需要前置 layout/processor 产生 Table 块或表格结构。"
                    )
                    llm_equation_enabled = st.checkbox(
                        "公式识别",
                        value=False,
                        help="识别和转换数学公式。需要公式区域、公式块或可裁剪图像；非 Surya 后端也可用，但取决于块映射质量。"
                    )
                    llm_image_description_enabled = st.checkbox(
                        "图片描述（替代图片输出）",
                        value=False,
                        help="将图片/插图转换为文字描述写入输出，而不是保留图片链接。需要 Picture/Figure 类块和可裁剪图像。"
                    )
                    if llm_image_description_enabled:
                        llm_image_description_language = st.selectbox(
                            "描述语言",
                            options=["auto", "zh", "en", "ja", "fr", "de"],
                            index=0,
                            format_func=lambda x: {
                                "auto": "自动（跟随文档）",
                                "zh": "中文（简体）",
                                "en": "English",
                                "ja": "日本語",
                                "fr": "Français",
                                "de": "Deutsch",
                            }.get(x, x),
                            help="只影响图片描述模块的输出语言，不影响其他 LLM 增强功能。",
                            key="llm_image_description_language"
                        )
                    llm_handwriting_enabled = st.checkbox(
                        "手写识别",
                        value=False,
                        help="识别手写内容。需要前置 layout 将手写区域保留下来，或存在可裁剪的复杂区域。"
                    )
                    llm_noise_removal_enabled = st.checkbox(
                        "智能降噪",
                        value=False,
                        help="识别并过滤无关符号和语言。主要依赖文本内容，对 layout 后端依赖较弱。"
                    )

                with col2:
                    llm_page_correction_enabled = st.checkbox(
                        "页面校正",
                        value=False,
                        help="修正页面结构和阅读顺序。适用于 Surya、Paddle、MinerU Direct、External Sidecar 等 Pipeline layout 后端。"
                    )
                    llm_section_header_enabled = st.checkbox(
                        "章节识别",
                        value=False,
                        help="识别和标记章节标题。需要文本块或候选标题块；若前置后端已产生 SectionHeader，效果通常更稳。"
                    )
                    llm_form_enabled = st.checkbox(
                        "表单识别",
                        value=False,
                        help="识别和提取表单内容。需要 Form、Table 或复杂区域块；对前置 layout 质量依赖较强。"
                    )
                    llm_complex_region_enabled = st.checkbox(
                        "复杂区域处理",
                        value=False,
                        help="处理复杂布局区域。需要 ComplexRegion 或其他未充分结构化的区域块。"
                    )
                    llm_printed_page_correction_enabled = st.checkbox(
                        "印刷页码修正",
                        value=False,
                        help="跨块分析规律性页码并修正印刷页码。依赖页眉页脚、页边区域或文本块中的页码候选。"
                    )
                    llm_heuristic_layout_enabled = st.checkbox(
                        "Markdown 格式修正",
                        value=False,
                        help="修正 Markdown 输出中的标题、列表、代码块、表格等格式细节，不改变版面检测结果。对 layout 后端依赖较弱。"
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

        printed_page_enabled = extract_printed_pages

        st.divider()

        # ==================== 6. 高级选项 ====================
        pipeline_run_settings = render_pipeline_run_settings(st)
        batch_mode = pipeline_run_settings["batch_mode"]
        batch_threshold = pipeline_run_settings["batch_threshold"]
        pages_per_batch = pipeline_run_settings["pages_per_batch"]
        cooling_seconds = pipeline_run_settings["cooling_seconds"]
        process_mode = pipeline_run_settings["process_mode"]
        use_page_range = pipeline_run_settings["use_page_range"]
        start_page_1based = pipeline_run_settings["start_page_1based"]
        end_page_1based = pipeline_run_settings["end_page_1based"]
        use_fp16 = pipeline_run_settings["use_fp16"]

# ==================== 主区域：文件选择 + 操作按钮 ====================
upload_mode, uploaded_files = render_file_input_selector(
    st,
    conversion_mode,
    markdown_postprocess_input_kind if conversion_mode == "markdown_postprocess" else None,
)

start_button = render_process_controls(st, conversion_mode, st.session_state.output_dir)
pipeline_values = snapshot_pipeline_ui_values(locals())
vlm_generalized_values = dict(locals()) if conversion_mode == "vlm_generalized" else {}
vlm_specialized_values = dict(locals()) if conversion_mode == "vlm_specialized" else {}

st.divider()

# ==================== 主区域：历史下载 ====================
render_result_history(st)


# ==================== 主处理逻辑 ====================
def _run_vlm_repair_job(_ctx, _cancel, _output_dir):
    job = dict(_ctx.get("vlm_repair_job") or {})
    if not job:
        _ctx["status"] = "error"
        st.error("缺少 VLM 修复任务参数")
        return

    file_name = job["file_name"]
    action = job.get("action") or "repair"
    progress_callback = make_vlm_progress_callback(
        _ctx,
        mode="vlm_generalized",
        file_name=file_name,
        file_index=0,
        total_files=1,
    )
    update_vlm_batch_progress(
        _ctx,
        mode="vlm_generalized",
        stage="重渲染中" if action == "rerender" else "修复中",
        total_batches=1,
        total_files=1,
        message=f"正在按当前规则重渲染：{file_name}" if action == "rerender" else f"正在补跑失败页：{file_name}",
    )
    if action == "rerender":
        markdown, repaired_converter, failed_before = rerender_vlm_json(
            json_path=job["json_path"],
            converter_config=job["converter_config"],
            progress_callback=progress_callback,
        )
        failed_after = failed_before
        output_suffix = "rerendered"
    else:
        markdown, repaired_converter, failed_before, failed_after = repair_vlm_json(
            pdf_path=job["pdf_path"],
            json_path=job["json_path"],
            converter_config=job["converter_config"],
            progress_callback=progress_callback,
        )
        output_suffix = "repaired"

    repair_base = f"{get_output_basename(file_name)}_{output_suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_files = save_vlm_generalized_outputs(
        converter=repaired_converter,
        markdown_text=markdown,
        output_dir=job.get("output_dir") or _output_dir,
        fname_base=repair_base,
        file_name=file_name,
        output_formats=job.get("output_formats") or ["markdown", "json"],
        emit_middle_json=bool(job.get("emit_middle_json")),
        emit_middle_report=bool(job.get("emit_middle_report")),
        emit_middle_debug=bool(job.get("emit_middle_debug")),
        emit_middle_scholarly=bool(job.get("emit_middle_scholarly")),
        emit_middle_scholarly_report=bool(job.get("emit_middle_scholarly_report")),
        emit_layout_overlay=bool(job.get("emit_layout_overlay")),
        emit_span_overlay=bool(job.get("emit_span_overlay")),
        emit_middle_full_json=bool(job.get("emit_middle_full_json")),
        warn=st.warning,
    )
    record_processed_outputs(_ctx, repair_base, output_files)
    finalize_zip_outputs(
        _ctx,
        output_files,
        job.get("output_dir") or _output_dir,
        "vlm_rerender_results.zip" if action == "rerender" else "vlm_repair_results.zip",
    )

    if action == "rerender":
        st.success(f"重渲染完成：原 JSON 中记录 {len(failed_before)} 个失败页，未调用模型补跑")
    elif failed_after:
        st.warning(f"补跑完成，但仍有 {len(failed_after)} 页失败：{', '.join(map(str, failed_after[:80]))}")
    else:
        st.success(f"补跑完成：原失败 {len(failed_before)} 页，当前 0 页失败")
    finish_vlm_progress(
        _ctx,
        mode="vlm_generalized",
        stage="完成",
        message=(
            f"JSON 重渲染完成：原 JSON 中记录 {len(failed_before)} 个失败页"
            if action == "rerender"
            else f"失败页修复完成：原失败 {len(failed_before)} 页，剩余 {len(failed_after)} 页"
        ),
    )
    _ctx["status"] = "done"


pending_vlm_repair_job = st.session_state.get("pending_vlm_repair_job")
if pending_vlm_repair_job and st.session_state.proc_ctx.get("status") in ("idle", "done", "error", "cancelled"):
    st.session_state.pending_vlm_repair_job = None
    st.session_state.proc_ctx = initial_proc_context(status="running")
    st.session_state.proc_ctx["vlm_repair_job"] = pending_vlm_repair_job
    _ctx = st.session_state.proc_ctx
    _cancel = threading.Event()
    st.session_state.proc_cancel = _cancel
    _out_dir = pending_vlm_repair_job.get("output_dir") or st.session_state.output_dir

    def _repair_proc_thread():
        run_proc_body_with_streamlit_log(
            st=st,
            ctx=_ctx,
            cancel=_cancel,
            output_dir=_out_dir,
            proc_body=_run_vlm_repair_job,
        )

    _thread = threading.Thread(target=_repair_proc_thread, daemon=True)
    _thread.start()
    st.session_state.proc_thread = _thread
    time.sleep(0.3)
    st.rerun()


if uploaded_files and len(uploaded_files) > 0:
    st.write(f"### 📋 待处理文件：{len(uploaded_files)} 个")

    # --- 后台处理函数（闭包，捕获所有侧边栏变量）---
    def _proc_body(_ctx, _cancel, _output_dir):
        """在后台线程中执行，st.write 等已被重定向到 _ctx["log"]"""

        if conversion_mode == "markdown_postprocess":
            mp_llm_provider = st.session_state.get("markdown_postprocess_llm_provider_widget", markdown_postprocess_llm_provider)
            mp_llm_base_url = st.session_state.get("markdown_postprocess_llm_base_url_widget", markdown_postprocess_llm_base_url)
            mp_llm_model = st.session_state.get("markdown_postprocess_llm_model_widget", markdown_postprocess_llm_model)
            mp_llm_api_key = st.session_state.get("markdown_postprocess_llm_api_key_widget", markdown_postprocess_llm_api_key)
            mp_llm_timeout = st.session_state.get("markdown_postprocess_llm_timeout_widget", markdown_postprocess_llm_timeout)
            mp_llm_max_retries = st.session_state.get("markdown_postprocess_llm_max_retries_widget", markdown_postprocess_llm_max_retries)

            all_output_paths_for_zip = run_markdown_postprocess_batch(
                st=st,
                uploaded_files=uploaded_files,
                upload_mode=upload_mode,
                output_dir=_output_dir,
                input_kind=markdown_postprocess_input_kind,
                review_only=markdown_postprocess_review_only,
                enable_llm=markdown_postprocess_enable_llm,
                enable_cleanup=markdown_postprocess_enable_cleanup,
                enable_printed_page_repair=markdown_postprocess_enable_printed_page_repair,
                llm_provider=mp_llm_provider,
                llm_base_url=mp_llm_base_url,
                llm_model=mp_llm_model,
                llm_api_key=mp_llm_api_key,
                llm_timeout=mp_llm_timeout,
                llm_max_retries=mp_llm_max_retries,
                middle_rerender_include_provenance=middle_rerender_include_provenance,
                middle_rerender_include_printed_page_comments=middle_rerender_include_printed_page_comments,
                middle_rerender_include_page_header_comments=middle_rerender_include_page_header_comments,
                middle_rerender_include_page_footer_comments=middle_rerender_include_page_footer_comments,
                middle_rerender_include_margin_comments=middle_rerender_include_margin_comments,
                middle_rerender_include_page_separators=middle_rerender_include_page_separators,
                middle_rerender_marginal_output_mode=middle_rerender_marginal_output_mode,
                middle_rerender_equation_output_mode=middle_rerender_equation_output_mode,
                middle_rerender_apply_postprocess=middle_rerender_apply_postprocess,
                cancel=_cancel,
                ctx=_ctx,
            )

            if _ctx.get("status") == "cancelled":
                return

            if all_output_paths_for_zip:
                zip_name = f"markdown_postprocess_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
                finalize_zip_outputs(_ctx, all_output_paths_for_zip, _output_dir, zip_name)
            _ctx["status"] = "done"
            return

        # ==================== VLM 泛化模式处理 ====================
        if conversion_mode == "vlm_generalized":
            run_vlm_generalized_batch(
                st=st,
                uploaded_files=uploaded_files,
                upload_mode=upload_mode,
                output_dir=_output_dir,
                config_values=vlm_generalized_values,
                output_formats=output_formats,
                vlm_use_page_range=vlm_use_page_range,
                vlm_start_page=vlm_start_page,
                vlm_end_page=vlm_end_page,
                vlm_concurrency_mode=vlm_concurrency_mode,
                vlm_direct_total_concurrent=vlm_direct_total_concurrent,
                vlm_direct_max_concurrent_files=vlm_direct_max_concurrent_files,
                vlm_batch_rest=vlm_batch_rest,
                emit_middle_json=emit_middle_json,
                emit_middle_report=emit_middle_report,
                emit_middle_debug=emit_middle_debug,
                emit_middle_scholarly=emit_middle_scholarly,
                emit_middle_scholarly_report=emit_middle_scholarly_report,
                emit_layout_overlay=emit_layout_overlay,
                emit_span_overlay=emit_span_overlay,
                emit_middle_full_json=emit_middle_full_json,
                cancel=_cancel,
                ctx=_ctx,
            )
            return

        # ==================== VLM 特化模式处理 ====================
        if conversion_mode == "vlm_specialized":
            # 检查必要配置
            if ocr_backend != "chrome_screenai" and not ocr_endpoint:
                st.error("❌ 需要配置 OCR API Endpoint")
                return
            run_vlm_specialized_batch(
                st=st,
                uploaded_files=uploaded_files,
                upload_mode=upload_mode,
                output_dir=_output_dir,
                config_values=vlm_specialized_values,
                output_formats=ocr_output_formats,
                vlm_use_page_range=ocr_use_page_range,
                vlm_start_page=ocr_start_page,
                vlm_end_page=ocr_end_page,
                vlm_concurrency_mode=ocr_concurrency_mode,
                ocr_total_concurrent=ocr_total_concurrent,
                ocr_max_concurrent_files=ocr_max_concurrent_files,
                ocr_batch_rest=ocr_batch_rest,
                emit_middle_json=emit_middle_json,
                emit_middle_report=emit_middle_report,
                emit_middle_debug=emit_middle_debug,
                emit_middle_scholarly=emit_middle_scholarly,
                emit_middle_scholarly_report=emit_middle_scholarly_report,
                emit_layout_overlay=emit_layout_overlay,
                emit_span_overlay=emit_span_overlay,
                emit_middle_full_json=emit_middle_full_json,
                cancel=_cancel,
                ctx=_ctx,
            )
            return

        # ==================== 传统模式处理 ====================
        all_output_paths_for_zip = []
        failed_pipeline_files = []
        start_time = time.time()

        _pipe_files = input_file_objects(upload_mode, uploaded_files, _ctx)
        for file_idx, file_obj in enumerate(_pipe_files):
            if _cancel.is_set():
                st.warning("⏹ 任务已取消")
                _ctx["status"] = "cancelled"
                break
            _ctx["progress"] = file_idx / len(_pipe_files)

            file_result = run_pipeline_file(
                file_obj,
                file_idx=file_idx,
                total_files=len(_pipe_files),
                upload_mode=upload_mode,
                ctx=_ctx,
                cancel=_cancel,
                values=pipeline_values,
                output_dir=_output_dir,
                output_formats=output_formats,
                repo_root=REPO_ROOT,
                config_builder=build_config_dict,
                write=st.write,
                info=st.info,
                warning=st.warning,
                error=st.error,
            )
            all_output_paths_for_zip.extend(file_result.get("output_paths", []))
            if file_result.get("status") == "failed":
                failed_pipeline_files.append(file_result.get("file_name") or "未知文件")
            if file_result.get("status") == "cancelled" or _ctx.get("status") == "cancelled":
                break

        elapsed = time.time() - start_time
        if failed_pipeline_files:
            st.warning(
                f"处理结束，但有 {len(failed_pipeline_files)} 个文件失败；总用时 {elapsed:.2f} 秒。"
            )
        elif _ctx.get("status") == "cancelled":
            st.warning(f"任务已取消；已用时 {elapsed:.2f} 秒")
        else:
            st.success(f"🎉 全部完成！总用时 {elapsed:.2f} 秒")

        zip_name = f"marker_output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        finalize_zip_outputs(_ctx, all_output_paths_for_zip, _output_dir, zip_name)

    # --- _proc_body 结束 ---

    # --- 启动后台线程 ---
    if start_button:
        if not output_formats:
            st.error("需要至少选择一种输出格式。")
            st.stop()
        # VLM 泛化模式验证
        if conversion_mode == "vlm_generalized" and not vlm_direct_api_key:
            st.error("❌ 需要配置 API Key")
            st.stop()
        # VLM 特化模式验证
        if conversion_mode == "vlm_specialized" and ocr_backend != "chrome_screenai" and not ocr_endpoint:
            st.error("❌ 需要配置 OCR API Endpoint")
            st.stop()
        # Markdown 后处理 LLM 模式验证
        if conversion_mode == "markdown_postprocess" and markdown_postprocess_enable_llm:
            mp_llm_base_url = st.session_state.get("markdown_postprocess_llm_base_url_widget", markdown_postprocess_llm_base_url)
            mp_llm_model = st.session_state.get("markdown_postprocess_llm_model_widget", markdown_postprocess_llm_model)
            if not (mp_llm_base_url or "").strip():
                st.error("❌ LLM 修正模式必须配置 Base URL")
                st.stop()
            if not (mp_llm_model or "").strip():
                st.error("❌ LLM 修正模式必须配置模型名称")
                st.stop()
        if conversion_mode == "markdown_postprocess" and markdown_postprocess_input_kind in {"middle_json", "mineru_json"}:
            bad_json_inputs = [
                getattr(file_obj, "name", str(file_obj))
                for file_obj in uploaded_files
                if not str(getattr(file_obj, "name", file_obj)).lower().endswith(".json")
            ]
            if bad_json_inputs:
                st.error("❌ JSON 后处理工具只能处理 .json 文件")
                st.stop()

        # 初始化后台处理上下文
        cleanup_staged_uploads(st.session_state.proc_ctx)
        st.session_state.proc_ctx = initial_proc_context(
            status="running",
            ocr_paused=st.session_state.ocr_paused,
            ocr_pause_info=st.session_state.ocr_pause_info,
            ocr_resume_batch_start=st.session_state.ocr_resume_batch_start,
        )
        _ctx = st.session_state.proc_ctx
        _cancel = threading.Event()
        st.session_state.proc_cancel = _cancel
        _out_dir = st.session_state.output_dir
        # 预读上传文件到内存（线程启动后 UploadedFile 对象可能失效）
        if upload_mode == "上传文件":
            attach_preread_files(_ctx, uploaded_files)

        if conversion_mode == "pipeline":
            # Pipeline 模式：同步执行（pypdfium2 在 Windows 后台线程中不安全）
            try:
                _proc_body(_ctx, _cancel, _out_dir)
                if _ctx["status"] == "running":
                    _ctx["status"] = "done"
            except Exception as e:
                _ctx["status"] = "error"
                st.error(f"处理异常: {e}")
                st.error(traceback.format_exc())
            # 同步结果到 session_state
            sync_proc_context_to_session(_ctx, st.session_state)
        else:
            # VLM 模式：后台线程执行（async HTTP 调用，不涉及 pypdfium2）
            def _proc_thread():
                run_proc_body_with_streamlit_log(
                    st=st,
                    ctx=_ctx,
                    cancel=_cancel,
                    output_dir=_out_dir,
                    proc_body=_proc_body,
                )

            _thread = threading.Thread(target=_proc_thread, daemon=True)
            _thread.start()
            st.session_state.proc_thread = _thread
            time.sleep(0.3)
            st.rerun()

# ==================== 处理状态显示 ====================
_pctx = st.session_state.proc_ctx
if _pctx["status"] != "idle":
    if _pctx["status"] == "running":
        _pcol1, _pcol2 = st.columns([4, 1])
        with _pcol1:
            st.progress(_pctx["progress"])
        with _pcol2:
            if st.button("⏹ 停止任务", type="secondary", use_container_width=True):
                if st.session_state.proc_cancel:
                    st.session_state.proc_cancel.set()

    render_vlm_progress(st, _pctx)
    _render_proc_log()

    if _pctx["status"] == "running":
        _thr = st.session_state.proc_thread
        if _thr and _thr.is_alive():
            time.sleep(1)
            st.rerun()
        else:
            # 线程结束，同步结果到 session_state
            sync_proc_context_to_session(_pctx, st.session_state)
            if _pctx["status"] == "running":
                _pctx["status"] = "done"
            st.rerun()

    elif _pctx["status"] in ("done", "error", "cancelled"):
        # 显示下载按钮
        _zp = _pctx.get("last_zip_path")
        if _zp and os.path.exists(_zp):
            with open(_zp, "rb") as _f:
                st.download_button(
                    "📦 下载所有结果（ZIP）",
                    data=_f.read(),
                    file_name=_pctx.get("last_zip_name", "results.zip"),
                    mime="application/zip",
                    key="download_proc_results",
                )
        # 重置按钮
        if st.button("🔄 清除日志，开始新任务"):
            cleanup_staged_uploads(st.session_state.proc_ctx)
            st.session_state.proc_ctx = initial_proc_context()
            st.rerun()

elif not (uploaded_files and len(uploaded_files) > 0) and not st.session_state.get("pending_vlm_repair_job"):
    st.info("👆 在上方上传 PDF 文件或选择包含 PDF 的文件夹")
