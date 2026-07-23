from __future__ import annotations

from typing import Any

from aih_contexture.config.vlm_model_presets import default_version, resolve_vlm_model, version_label, version_options


def render_surya2_vlm_settings(
    st,
    *,
    description: str,
    layout_mode: bool = False,
    pipeline_ocr: bool = False,
    key_prefix: str = "surya2",
) -> dict[str, Any]:
    def widget_key(name: str) -> str:
        return name if key_prefix == "surya2" else f"{key_prefix}_{name}"

    def state_value(name: str, default: Any) -> Any:
        return st.session_state.get(widget_key(name), st.session_state.get(name, default))

    st.markdown(description)
    api_style_options = ["openai", "lmstudio-native"]
    api_style = st.selectbox(
        "协议风格",
        options=api_style_options,
        index=api_style_options.index(state_value("surya2_api_style", "openai"))
        if state_value("surya2_api_style", "openai") in api_style_options
        else 0,
        format_func=lambda value: {"openai": "OpenAI 兼容协议", "lmstudio-native": "LM Studio 原生协议"}[value],
        key=widget_key("surya2_api_style"),
    )
    versions = version_options("surya2")
    version = st.selectbox(
        "Surya 2 版本",
        options=versions,
        index=versions.index(state_value("surya2_version", default_version("surya2")))
        if state_value("surya2_version", default_version("surya2")) in versions
        else 0,
        format_func=lambda value: version_label("surya2", value),
        key=widget_key("surya2_version"),
    )
    default_model = resolve_vlm_model("surya2", version=version)
    endpoint = st.text_input(
        "Surya 2 Endpoint",
        value=state_value("surya2_endpoint", _default_endpoint(api_style)),
        key=widget_key("surya2_endpoint"),
    )
    model = st.text_input(
        "Surya 2 模型名",
        value=state_value("surya2_model", default_model),
        key=widget_key("surya2_model"),
    )
    api_key = st.text_input(
        "API Key（可选）",
        value=state_value("surya2_api_key", ""),
        type="password",
        key=widget_key("surya2_api_key"),
    )
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        request_concurrency = st.number_input(
            "API 请求并发",
            min_value=1,
            max_value=16,
            value=int(state_value("surya2_request_concurrency", 6)),
            key=widget_key("surya2_request_concurrency"),
        )
    with col_b:
        if layout_mode:
            block_concurrency = 1
            st.markdown(" ")
        else:
            block_concurrency = st.number_input(
                "块调度上限",
                min_value=1,
                max_value=32,
                value=int(state_value("surya2_block_concurrency", 4)),
                key=widget_key("surya2_block_concurrency"),
            )
    with col_c:
        timeout = st.number_input(
            "请求超时（秒）",
            min_value=30,
            max_value=1800,
            value=int(state_value("surya2_layout_timeout", 120)),
            step=30,
            key=widget_key("surya2_layout_timeout"),
        )

    image_col_a, image_col_b, image_col_c = st.columns(3)
    with image_col_a:
        image_format = st.selectbox(
            "图片格式",
            options=["PNG", "JPEG"],
            index=0 if state_value("surya2_image_format", "PNG") == "PNG" else 1,
            key=widget_key("surya2_image_format"),
        )
    with image_col_b:
        image_quality = st.slider(
            "图片质量",
            min_value=40,
            max_value=100,
            value=int(state_value("surya2_image_quality", 90)),
            key=widget_key("surya2_image_quality"),
        )
    with image_col_c:
        max_tokens = st.number_input(
            "Layout 最大 Token",
            min_value=512,
            max_value=8192,
            value=int(state_value("surya2_layout_max_tokens", 4096)),
            step=512,
            key=widget_key("surya2_layout_max_tokens"),
        )

    crop_padding_px = 4
    crop_padding_frac = 0.02
    if pipeline_ocr:
        crop_col_a, crop_col_b = st.columns(2)
        with crop_col_a:
            crop_padding_px = st.number_input(
                "块裁切 padding(px)",
                min_value=0,
                max_value=64,
                value=int(state_value("surya2_crop_padding_px", 4)),
                key=widget_key("surya2_crop_padding_px"),
            )
        with crop_col_b:
            crop_padding_frac = st.number_input(
                "块裁切 padding(比例)",
                min_value=0.0,
                max_value=0.2,
                value=float(state_value("surya2_crop_padding_frac", 0.02)),
                step=0.01,
                key=widget_key("surya2_crop_padding_frac"),
            )

    layout_concurrency = int(request_concurrency)
    if layout_mode:
        layout_concurrency = st.number_input(
            "Layout 并发窗口",
            min_value=1,
            max_value=16,
            value=int(state_value("surya2_layout_concurrency", request_concurrency)),
            key=widget_key("surya2_layout_concurrency"),
        )

    return {
        "surya2_endpoint": endpoint,
        "surya2_api_key": api_key,
        "surya2_api_style": api_style,
        "surya2_version": version,
        "surya2_model": model,
        "surya2_layout_timeout": int(timeout),
        "surya2_layout_max_tokens": int(max_tokens),
        "surya2_layout_batch_size": int(layout_concurrency),
        "surya2_layout_concurrency": int(layout_concurrency),
        "surya2_request_concurrency": int(request_concurrency),
        "surya2_block_concurrency": int(block_concurrency),
        "surya2_image_format": str(image_format).upper(),
        "surya2_image_quality": int(image_quality),
        "surya2_crop_padding_px": int(crop_padding_px),
        "surya2_crop_padding_frac": float(crop_padding_frac),
        "force_ocr": True,
        "use_llm": False,
        "ocr_batch_size": 32,
    }


def _default_endpoint(api_style: str) -> str:
    if str(api_style).strip().lower() == "lmstudio-native":
        return "http://localhost:1234/api/v1/chat"
    return "http://127.0.0.1:1234/v1/chat/completions"
