"""Shared ScreenAI PDF preprocessing controls."""


def render_screenai_preprocess_settings(st):
    labels = {
        "native": "按原页画面识别",
        "strip_existing_ocr": "清理隐藏文字层后识别",
        "rasterize_pdf": "栅格化后识别",
        "strip_then_rasterize": "清理隐藏文字层并栅格化",
    }
    mode = st.selectbox(
        "PDF 预处理", options=list(labels), format_func=labels.get,
        index=list(labels).index(st.session_state.get("chrome_preprocess_mode", "native")),
        key="chrome_preprocess_mode",
    )
    remove_annotations = st.checkbox(
        "清理批注与链接", value=bool(st.session_state.get("chrome_remove_annotations", True)),
        key="chrome_remove_annotations",
        help="识别前移除 PDF 批注、标记、印章和链接，保留正文与表单可见内容。",
    )
    current_dpi = max(72, int(st.session_state.get("chrome_rasterize_dpi") or 144))
    dpi = st.number_input(
        "重建页面 DPI", min_value=72, max_value=max(300, current_dpi),
        value=current_dpi, step=12,
        key="chrome_rasterize_dpi", help="需要栅格化或重建页面背景时使用，影响清晰度与文件体积。",
    )
    return {"chrome_preprocess_mode": mode, "chrome_remove_annotations": remove_annotations,
            "chrome_rasterize_dpi": int(dpi)}
