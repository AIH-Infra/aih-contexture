from __future__ import annotations

from typing import Any

INDRA_MODE_LABELS = {
    "auto": "自动使用文字层，缺失时识别",
    "ocr": "重新识别全部文字",
    "text": "优先使用文字层，缺失部分再识别",
}


def render_indra_settings(st, *, description: str, key_prefix: str = "ocr_indra",
                          layout_only: bool = False, layout_auxiliary: bool = False) -> dict[str, Any]:
    def widget_key(name: str) -> str:
        return f"{key_prefix}_{name}"

    def state_value(name: str, default: Any) -> Any:
        return st.session_state.get(widget_key(name), st.session_state.get(name, default))

    del description

    python = None
    model_dir = None
    allow_download = bool(state_value("indra_allow_download", False))
    cache_dir = state_value("indra_cache_dir", "")
    with st.expander("高级：模型与运行环境", expanded=False):
        python = st.text_input(
            "Python 路径",
            value=state_value("indra_python", ""),
            key=widget_key("indra_python"),
            help="留空使用当前环境；仅在手动切换环境时填写。",
        )
        model_dir = st.text_input(
            "模型目录",
            value=state_value("indra_model_dir", ""),
            key=widget_key("indra_model_dir"),
            help="留空时自动查找已配置的模型目录。",
        )
        from aih_contexture.backends.ocr.indra.settings import IndraSettings

        resolved_model_dir = IndraSettings.from_config({"indra_model_dir": model_dir}).model_dir
        if resolved_model_dir:
            st.caption(f"当前模型目录：{resolved_model_dir}")
        allow_download = st.checkbox(
            "允许下载缺失模型",
            value=bool(state_value("indra_allow_download", False)),
            key=widget_key("indra_allow_download"),
        )
        cache_dir = st.text_input(
            "逐页缓存目录",
            value=state_value("indra_cache_dir", ""),
            key=widget_key("indra_cache_dir"),
        )
    modes = list(INDRA_MODE_LABELS)
    saved_mode = state_value("indra_mode", "auto")
    if layout_only:
        mode = saved_mode if saved_mode in modes else "auto"
    else:
        mode = st.selectbox(
            "版面辅助文字来源" if layout_auxiliary else "Indra OCR 文字来源",
            options=modes,
            index=modes.index(saved_mode) if saved_mode in modes else 0,
            format_func=INDRA_MODE_LABELS.get,
            help=(
                "仅用于版面分析的辅助文字；最终输出仍由文字来源设置决定。"
                if layout_auxiliary
                else "控制 Indra 如何使用 PDF 文字层或重新识别页面。"
            ),
            key=widget_key("indra_mode"),
        )
    col_a, col_b = st.columns(2)
    with col_a:
        dpi = st.number_input(
            "Indra 模型输入 DPI",
            min_value=72,
            max_value=400,
            value=int(state_value("indra_dpi", 200)),
            step=25,
            help="较高分辨率会增加处理时间和内存占用。",
            key=widget_key("indra_dpi"),
        )
    with col_b:
        cores = st.number_input(
            "CPU 核心数",
            min_value=0,
            max_value=128,
            value=int(state_value("indra_cores", 0) or 0),
            key=widget_key("indra_cores"),
            help="0 表示自动。手动设置最多使用全部物理核心，内存估算超预算时提示。",
        )
    math = False
    if not layout_only:
        math = st.checkbox(
            "识别公式为 LaTeX",
            value=bool(state_value("indra_math", False)),
            help="需要模型目录包含公式识别模型。",
            key=widget_key("indra_math"),
        )
    return {
        "indra_python": python.strip() or None,
        "indra_model_dir": model_dir.strip() or None,
        "indra_allow_download": bool(allow_download),
        "indra_mode": mode,
        "indra_dpi": int(dpi),
        "indra_cores": int(cores) or None,
        "indra_math": bool(math),
        "indra_cache_dir": cache_dir.strip() or None,
        "force_ocr": False,
        "use_llm": False,
        "ocr_batch_size": 32,
    }
