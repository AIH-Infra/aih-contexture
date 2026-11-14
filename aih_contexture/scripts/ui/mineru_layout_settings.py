from __future__ import annotations

from aih_contexture.backends.external_config import (
    DEFAULT_MINERU_LAYOUT_BATCH_SIZE,
    EXPECTED_BACKEND_ENV,
    MINERU_COMMAND_ENV,
    MINERU_LAYOUT_PYTHON_ENV,
    MINERU_PYTHON_ENV,
    default_mineru_command,
    default_mineru_layout_model_dir,
    default_mineru_layout_python,
    default_mineru_python,
)


def render_mineru_layout_settings(st, *, description: str) -> dict:
    st.warning(
        description
        + "\n\n"
        "兼容/诊断路径：调用 MinerU CLI 完整 pipeline 生成 *_middle.json，再交给 Contexture 映射和渲染。\n\n"
        "这不是纯版面检测。即使 Contexture OCR 选择“禁用”，MinerU 内部仍可能执行 OCR、表格、公式等阶段。"
    )

    mineru_command = st.text_input(
        "MinerU CLI 命令",
        value=st.session_state.get("mineru_command", default_mineru_command()),
        help=f"可以是 PATH 中的 mineru，也可以是完整路径；也可用 {MINERU_COMMAND_ENV} 指定。",
        key="mineru_command",
    )
    mineru_method = st.selectbox(
        "CLI 解析方法",
        options=["txt", "ocr", "auto"],
        index=0,
        help=(
            "只影响 MinerU sidecar 生成。txt 倾向使用文本层，ocr 面向扫描件，auto 由 MinerU 判断。"
            "Contexture 最终 OCR 后端仍由下方设置决定。"
        ),
        key="mineru_method",
    )
    mineru_lang = st.text_input(
        "CLI 语言",
        value=st.session_state.get("mineru_lang", "ch"),
        help="传给 MinerU -l，例如 ch、en、latin、japan、chinese_cht。",
        key="mineru_lang",
    )
    mineru_output_dir = st.text_input(
        "CLI 输出目录",
        value=st.session_state.get("mineru_output_dir", ""),
        help="留空时使用临时目录；调试时可填固定目录保留 MinerU 原始输出。",
        key="mineru_output_dir",
    )
    mineru_timeout = st.number_input(
        "超时秒数",
        min_value=60,
        max_value=86400,
        value=int(st.session_state.get("mineru_timeout", 3600)),
        step=60,
        key="mineru_timeout",
    )

    mineru_backend = "pipeline"
    mineru_api_url = None
    mineru_server_url = None
    mineru_extra_args = None
    with st.expander("MinerU CLI 实验选项", expanded=False):
        st.caption(
            "这些选项会让 MinerU 使用 hybrid/vlm 或远程服务生成 sidecar，仅用于对照实验。"
        )
        mineru_backend = st.selectbox(
            "MinerU CLI 后端",
            options=["pipeline", "hybrid-auto-engine", "hybrid-http-client", "vlm-auto-engine", "vlm-http-client"],
            index=0,
            help="默认保持 pipeline。hybrid/vlm 会增加额外模型或服务依赖，只用于实验。",
            key="mineru_backend",
        )
        mineru_api_url_value = st.text_input(
            "MinerU API URL",
            value=st.session_state.get("mineru_api_url", ""),
            help="可选；传给 mineru --api-url，复用已有 mineru-api 服务。",
            key="mineru_api_url",
        )
        mineru_server_url_value = st.text_input(
            "MinerU VLM/Hybrid 服务 URL",
            value=st.session_state.get("mineru_server_url", ""),
            help="可选；使用 *-http-client 后端时传给 mineru -u。",
            key="mineru_server_url",
        )
        mineru_extra_args_value = st.text_input(
            "额外参数",
            value=st.session_state.get("mineru_extra_args", ""),
            help="追加到 mineru CLI 命令末尾；仅用于高级调试。",
            key="mineru_extra_args",
        )
        mineru_api_url = mineru_api_url_value.strip() or None
        mineru_server_url = mineru_server_url_value.strip() or None
        mineru_extra_args = mineru_extra_args_value.strip() or None

    return {
        "mineru_command": mineru_command.strip() or "mineru",
        "mineru_backend": mineru_backend,
        "mineru_method": mineru_method,
        "mineru_lang": mineru_lang.strip() or "ch",
        "mineru_output_dir": mineru_output_dir.strip() or None,
        "mineru_api_url": mineru_api_url,
        "mineru_server_url": mineru_server_url,
        "mineru_timeout": int(mineru_timeout),
        "mineru_extra_args": mineru_extra_args,
    }


def render_mineru_direct_layout_settings(st, *, description: str) -> dict:
    st.info(description)
    st.caption(
        "版面模型代码已内置在 Contexture 中，与 Surya 共用同一个 PyTorch 环境，不需要外部 MinerU 环境；"
        "此后端只做版面分析，不执行 MinerU 的文字、表格或公式识别。"
    )

    with st.expander("高级：指定其他 Python 环境（通常留空）", expanded=False):
        resolved_python = default_mineru_layout_python()
        st.caption(f"当前使用：`{resolved_python}`" if resolved_python else "当前使用：未找到可用的 Python")
        mineru_layout_python = st.text_input(
            "版面子进程 Python（留空 = 当前 PyTorch 环境）",
            value=st.session_state.get("mineru_layout_python", ""),
            help=(
                "只在需要让版面子进程跑在另一个装有 PyTorch 的环境时填写。留空时按本实例的 GPU 环境"
                f"（{EXPECTED_BACKEND_ENV}）、再按当前运行 Contexture 的环境解析；"
                f"也可用 {MINERU_LAYOUT_PYTHON_ENV} 指定。"
                "OCR 的 Python 可单独指定；只有 MinerU CLI 兼容路径需要完整 MinerU 环境。"
            ),
            key="mineru_layout_python",
        )
    _DEVICE_OPTIONS = ["auto", "cuda", "cuda:0", "cpu", "custom"]
    _DEVICE_LABELS = {
        "auto": "自动（有 GPU 用 GPU）",
        "cuda": "CUDA（默认 GPU）",
        "cuda:0": "CUDA 0",
        "cpu": "CPU",
        "custom": "自定义...",
    }
    current_device = str(st.session_state.get("mineru_layout_device", "") or "").strip()
    selected_device = current_device if current_device in _DEVICE_OPTIONS[:-1] else "custom" if current_device else "auto"
    mineru_layout_device = st.selectbox(
        "运行设备",
        options=_DEVICE_OPTIONS,
        index=_DEVICE_OPTIONS.index(selected_device),
        format_func=lambda value: _DEVICE_LABELS.get(value, value),
        help="auto 按当前 PyTorch 环境探测（CUDA/ROCm 可用即用 GPU）。若该环境里的 torch 是 CPU 版，cuda 会失败。",
        key="mineru_layout_device_select",
    )
    if mineru_layout_device == "custom":
        custom_device = st.text_input(
            "自定义运行设备",
            value=current_device if current_device not in _DEVICE_OPTIONS else "",
            help="例如 cuda:1。可用设备取决于版面子进程所用环境中的 torch。",
            key="mineru_layout_device",
        )
        resolved_device = custom_device.strip() or None
    else:
        resolved_device = None if mineru_layout_device == "auto" else mineru_layout_device
        st.session_state["mineru_layout_device"] = resolved_device or ""
    mineru_layout_model_dir = st.text_input(
        "PP-DocLayoutV2 模型目录",
        value=st.session_state.get("mineru_layout_model_dir", default_mineru_layout_model_dir() or ""),
        help=(
            "留空时按 CONTEXTURE_MINERU_MODEL_DIR、共享托管目录、旧的官方缓存依次解析；"
            "都没有时首次运行会自动下载到共享托管目录（需安装 modelscope）。"
        ),
        key="mineru_layout_model_dir",
    )
    mineru_layout_batch_size = st.number_input(
        "版面推理批次大小",
        min_value=1,
        max_value=64,
        value=int(st.session_state.get("mineru_layout_batch_size", DEFAULT_MINERU_LAYOUT_BATCH_SIZE)),
        step=1,
        help="默认每次推理提交 4 页；显存不足时可减至 1，资源充足时可逐步增大，并用实际材料检查耗时与稳定性。",
        key="mineru_layout_batch_size",
    )
    mineru_layout_timeout = st.number_input(
        "超时秒数",
        min_value=60,
        max_value=86400,
        value=int(st.session_state.get("mineru_layout_timeout", 3600)),
        step=60,
        key="mineru_layout_timeout",
    )
    use_filter = st.checkbox(
        "启用官方后处理过滤",
        value=bool(st.session_state.get("mineru_layout_use_paddlex_filter_boxes", False)),
        help="按 MinerU/PaddleX 风格过滤重叠框和小框；精度对比时可先关闭。",
        key="mineru_layout_use_paddlex_filter_boxes",
    )

    return {
        "mineru_layout_python": mineru_layout_python.strip() or None,
        "mineru_layout_device": resolved_device,
        "mineru_layout_model_dir": mineru_layout_model_dir.strip() or None,
        "mineru_layout_batch_size": int(mineru_layout_batch_size),
        "mineru_layout_timeout": int(mineru_layout_timeout),
        "mineru_layout_use_paddlex_filter_boxes": bool(use_filter),
    }


def render_mineru_ocr_settings(st, *, description: str) -> dict:
    st.info(description)
    st.caption("推理代码已内置。安装 Contexture 的 paddle-torch 可选依赖后，复用当前 PyTorch 环境；无需完整 MinerU 或 PaddlePaddle。")

    mineru_ocr_python = st.text_input(
        "OCR Python（通常留空）",
        value=st.session_state.get("mineru_ocr_python", ""),
        help="留空使用运行 Contexture 的 Python。仅在手动指定其他已安装可选依赖的环境时填写。",
        key="mineru_ocr_python",
    )
    versions = ["PP-OCRv5", "PP-OCRv6"]
    current_version = st.session_state.get("mineru_ocr_version", "PP-OCRv5")
    mineru_ocr_version = st.selectbox(
        "OCR 模型版本", options=versions,
        index=versions.index(current_version) if current_version in versions else 0,
        key="mineru_ocr_version",
    )
    if mineru_ocr_version == "PP-OCRv6":
        st.caption("PP-OCRv6 官方 safetensors 可在显式启用下载后自动获取；也可指定已有权重目录。")
    mineru_ocr_model_dir = st.text_input(
        "OCR 权重目录（可选）",
        value=st.session_state.get("mineru_ocr_model_dir", ""),
        help="目录中直接放置所选模型的权重文件。留空时复用 Contexture 托管目录或已有模型缓存。",
        key="mineru_ocr_model_dir",
    )
    mineru_ocr_allow_download = st.checkbox(
        "允许下载缺失的 OCR 权重",
        value=bool(st.session_state.get("mineru_ocr_allow_download", False)),
        key="mineru_ocr_allow_download",
    )
    _DEVICE_OPTIONS = ["auto", "cuda", "cuda:0", "cpu", "custom"]
    _DEVICE_LABELS = {
        "auto": "自动（按当前 Torch 环境）",
        "cuda": "CUDA（默认 GPU）",
        "cuda:0": "CUDA 0",
        "cpu": "CPU",
        "custom": "自定义...",
    }
    current_device = str(st.session_state.get("mineru_ocr_device", "") or "").strip()
    selected_device = current_device if current_device in _DEVICE_OPTIONS[:-1] else "custom" if current_device else "auto"
    mineru_ocr_device = st.selectbox(
        "OCR 运行设备",
        options=_DEVICE_OPTIONS,
        index=_DEVICE_OPTIONS.index(selected_device),
        format_func=lambda value: _DEVICE_LABELS.get(value, value),
        help="复用当前 PyTorch 的 CPU、CUDA 或 ROCm 支持；ROCm 同样使用 cuda 设备名。",
        key="mineru_ocr_device_select",
    )
    if mineru_ocr_device == "custom":
        custom_device = st.text_input(
            "自定义 OCR 运行设备",
            value=current_device if current_device not in _DEVICE_OPTIONS else "",
            help="例如 cuda:1。可用设备取决于版面子进程所用环境中的 torch。",
            key="mineru_ocr_device",
        )
        resolved_device = custom_device.strip() or None
    else:
        resolved_device = None if mineru_ocr_device == "auto" else mineru_ocr_device
        st.session_state["mineru_ocr_device"] = resolved_device or ""

    mineru_ocr_lang = st.text_input(
        "OCR 语言",
        value=st.session_state.get("mineru_ocr_lang", st.session_state.get("paddle_ocr_lang", "ch")),
        help="例如 ch、ch_server、en、japan、latin；不同模型版本支持的语言配置不同，不支持的取值会明确报错。",
        key="mineru_ocr_lang",
    )
    mineru_ocr_timeout = st.number_input(
        "OCR 超时秒数",
        min_value=60,
        max_value=86400,
        value=int(st.session_state.get("mineru_ocr_timeout", st.session_state.get("mineru_timeout", 3600))),
        step=60,
        key="mineru_ocr_timeout",
    )
    det_db_box_thresh = st.number_input(
        "检测框阈值",
        min_value=0.0,
        max_value=1.0,
        value=float(st.session_state.get("mineru_ocr_det_db_box_thresh", 0.3)),
        step=0.05,
        key="mineru_ocr_det_db_box_thresh",
    )
    det_db_unclip_ratio = st.number_input(
        "检测框扩张系数",
        min_value=1.0,
        max_value=5.0,
        value=float(st.session_state.get("mineru_ocr_det_db_unclip_ratio", 1.8)),
        step=0.1,
        key="mineru_ocr_det_db_unclip_ratio",
    )
    enable_merge_det_boxes = st.checkbox(
        "合并相邻检测框",
        value=bool(st.session_state.get("mineru_ocr_enable_merge_det_boxes", True)),
        help="沿用 MinerU/PaddleOCR 检测框合并逻辑。",
        key="mineru_ocr_enable_merge_det_boxes",
    )

    return {
        "mineru_ocr_python": mineru_ocr_python.strip() or None,
        "mineru_ocr_model_dir": mineru_ocr_model_dir.strip() or None,
        "mineru_ocr_version": mineru_ocr_version,
        "mineru_ocr_allow_download": bool(mineru_ocr_allow_download),
        "mineru_ocr_device": resolved_device,
        "mineru_ocr_lang": mineru_ocr_lang.strip() or "ch",
        "mineru_ocr_timeout": int(mineru_ocr_timeout),
        "mineru_ocr_det_db_box_thresh": float(det_db_box_thresh),
        "mineru_ocr_det_db_unclip_ratio": float(det_db_unclip_ratio),
        "mineru_ocr_enable_merge_det_boxes": bool(enable_merge_det_boxes),
        "force_ocr": True,
        "use_llm": False,
        "ocr_batch_size": 1,
    }
