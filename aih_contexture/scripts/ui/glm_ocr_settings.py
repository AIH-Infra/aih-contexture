from __future__ import annotations

from typing import Any

from aih_contexture.config.vlm_model_presets import default_quant, quant_options, resolve_vlm_model


def render_glm_ocr_settings(st, *, description: str, key_prefix: str = "ocr_glm") -> dict[str, Any]:
    def widget_key(name: str) -> str:
        return f"{key_prefix}_{name}"

    def state_value(name: str, default: Any) -> Any:
        return st.session_state.get(widget_key(name), st.session_state.get(name, default))

    if str(description or "").strip():
        st.caption(description)
    endpoint = st.text_input(
        "GLM-OCR API 端点（OpenAI 兼容）",
        value=state_value("glm_ocr_endpoint", "http://127.0.0.1:1234/v1/chat/completions"),
        key=widget_key("glm_ocr_endpoint"),
    )
    quants = quant_options("glm_ocr")
    saved_quant = state_value("glm_ocr_quant", default_quant("glm_ocr"))
    quant = st.selectbox(
        "量化版本",
        options=quants,
        index=quants.index(saved_quant) if saved_quant in quants else 0,
        key=widget_key("glm_ocr_quant"),
    )
    model = st.text_input(
        "模型名称",
        value=state_value("glm_ocr_model", resolve_vlm_model("glm_ocr", quant=quant)),
        key=widget_key("glm_ocr_model"),
    )
    api_key = st.text_input(
        "API Key（可选）",
        value=state_value("glm_ocr_api_key", ""),
        type="password",
        key=widget_key("glm_ocr_api_key"),
    )
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        block_concurrency = st.number_input(
            "块调度上限",
            min_value=1,
            max_value=32,
            value=int(state_value("glm_ocr_block_concurrency", 4)),
            key=widget_key("glm_ocr_block_concurrency"),
        )
    with col_b:
        timeout = st.number_input(
            "请求超时（秒）",
            min_value=30,
            max_value=1800,
            value=int(state_value("glm_ocr_timeout", 120)),
            step=30,
            key=widget_key("glm_ocr_timeout"),
        )
    with col_c:
        max_tokens = st.number_input(
            "最大输出 token 数",
            min_value=512,
            max_value=8192,
            value=int(state_value("glm_ocr_max_tokens", 4096)),
            step=512,
            key=widget_key("glm_ocr_max_tokens"),
        )
    recognize_formulas = st.checkbox(
        "同时识别公式块",
        value=bool(state_value("glm_ocr_recognize_formulas", False)),
        key=widget_key("glm_ocr_recognize_formulas"),
    )
    return {
        "glm_ocr_endpoint": endpoint,
        "glm_ocr_quant": quant,
        "glm_ocr_model": model,
        "glm_ocr_api_key": api_key,
        "glm_ocr_block_concurrency": int(block_concurrency),
        "glm_ocr_timeout": int(timeout),
        "glm_ocr_max_tokens": int(max_tokens),
        "glm_ocr_recognize_formulas": bool(recognize_formulas),
        "force_ocr": True,
        "use_llm": False,
        "ocr_batch_size": 32,
    }
