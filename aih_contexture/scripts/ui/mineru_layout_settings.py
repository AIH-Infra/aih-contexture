from __future__ import annotations

from aih_contexture.backends.external_config import (
    MINERU_COMMAND_ENV,
    MINERU_PYTHON_ENV,
    default_mineru_command,
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

    mineru_layout_python = st.text_input(
        "MinerU 外部 Python",
        value=st.session_state.get("mineru_layout_python", default_mineru_python() or ""),
        help=f"指向 MinerU 虚拟环境的 Python 可执行文件；也可用 {MINERU_PYTHON_ENV} 指定。",
        key="mineru_layout_python",
    )
    _DEVICE_OPTIONS = ["auto", "cuda", "cuda:0", "cpu", "custom"]
    _DEVICE_LABELS = {
        "auto": "自动（使用 MinerU 配置）",
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
        help="auto 使用 MinerU 配置。若外部环境里的 torch 是 CPU 版，cuda 会失败。",
        key="mineru_layout_device_select",
    )
    if mineru_layout_device == "custom":
        custom_device = st.text_input(
            "自定义运行设备",
            value=current_device if current_device not in _DEVICE_OPTIONS else "",
            help="例如 cuda:1。可用设备取决于 MinerU 外部虚拟环境中的 torch。",
            key="mineru_layout_device",
        )
        resolved_device = custom_device.strip() or None
    else:
        resolved_device = None if mineru_layout_device == "auto" else mineru_layout_device
        st.session_state["mineru_layout_device"] = resolved_device or ""
    mineru_layout_model_dir = st.text_input(
        "PP-DocLayoutV2 模型目录",
        value=st.session_state.get("mineru_layout_model_dir", ""),
        help="留空时按 MinerU 官方逻辑从 ModelScope/HuggingFace 缓存解析。",
        key="mineru_layout_model_dir",
    )
    mineru_layout_batch_size = st.number_input(
        "批大小",
        min_value=1,
        max_value=64,
        value=int(st.session_state.get("mineru_layout_batch_size", 1)),
        step=1,
        help="默认保守为 1。显存足够时可逐步试 2/4/8。",
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
