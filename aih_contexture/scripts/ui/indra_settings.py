from __future__ import annotations

from typing import Any

INDRA_MODE_LABELS = {
    "auto": "自动（文字层可信则直接使用，否则 OCR）",
    "ocr": "始终 OCR",
    "text": "只读文字层",
}


def render_indra_settings(st, *, description: str, key_prefix: str = "ocr_indra") -> dict[str, Any]:
    def widget_key(name: str) -> str:
        return f"{key_prefix}_{name}"

    def state_value(name: str, default: Any) -> Any:
        return st.session_state.get(widget_key(name), st.session_state.get(name, default))

    st.markdown(description)
    python = st.text_input(
        "Indra Python 路径",
        value=state_value("indra_python", ""),
        key=widget_key("indra_python"),
        help="可在当前环境安装 Contexture 的 indra 可选依赖，无需独立虚拟环境。留空先读取 CONTEXTURE_INDRA_PYTHON，再使用当前环境；仅手动切换环境时填写。",
    )
    model_dir = st.text_input(
        "Indra 模型目录",
        value=state_value("indra_model_dir", ""),
        key=widget_key("indra_model_dir"),
        help="目录中应包含 det.onnx、rec.onnx、meta.json、order.onnx 等模型文件。留空读取 INDRA_OCR_MODEL_DIR；权重需自行准备，不随 Contexture 分发。",
    )
    modes = list(INDRA_MODE_LABELS)
    saved_mode = state_value("indra_mode", "auto")
    mode = st.selectbox(
        "文字来源",
        options=modes,
        index=modes.index(saved_mode) if saved_mode in modes else 0,
        format_func=INDRA_MODE_LABELS.get,
        key=widget_key("indra_mode"),
    )
    col_a, col_b = st.columns(2)
    with col_a:
        dpi = st.number_input("渲染 DPI", min_value=72, max_value=400, value=int(state_value("indra_dpi", 200)), step=25, key=widget_key("indra_dpi"))
    with col_b:
        cores = st.number_input(
            "CPU 核心数（0 = 自动）",
            min_value=0,
            max_value=128,
            value=int(state_value("indra_cores", 0) or 0),
            key=widget_key("indra_cores"),
            help="自动：按物理核心、可用内存（每进程约 1.5 GB）和页数规划；超出安全上限的手动值会被收紧并提示。",
        )
    math = st.checkbox("识别公式为 LaTeX（需要模型目录含 math 模型）", value=bool(state_value("indra_math", False)), key=widget_key("indra_math"))
    cache_dir = st.text_input("逐页结果缓存目录（可选）", value=state_value("indra_cache_dir", ""), key=widget_key("indra_cache_dir"))
    return {
        "indra_python": python.strip() or None,
        "indra_model_dir": model_dir.strip() or None,
        "indra_mode": mode,
        "indra_dpi": int(dpi),
        "indra_cores": int(cores) or None,
        "indra_math": bool(math),
        "indra_cache_dir": cache_dir.strip() or None,
        "force_ocr": False,
        "use_llm": False,
        "ocr_batch_size": 32,
    }
