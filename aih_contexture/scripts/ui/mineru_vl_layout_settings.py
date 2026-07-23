from __future__ import annotations

from aih_contexture.config.vlm_model_presets import default_quant, default_version, quant_options, resolve_vlm_model, version_label, version_options


def render_mineru_vl_layout_settings(st, *, description: str) -> dict[str, object]:
    st.info(description)
    st.caption("仅调用 MinerU-VL 的 Layout Detection；正文 OCR 仍由下方 OCR 后端决定。")

    api_style_options = ["lmstudio-native", "openai"]
    api_style = st.selectbox(
        "协议风格",
        options=api_style_options,
        index=option_index(api_style_options, st.session_state.get("mineru_vl_api_style", "lmstudio-native")),
        format_func=lambda x: {
            "openai": "OpenAI 兼容 Chat Completions",
            "lmstudio-native": "LM Studio 原生 /api/v1/chat",
        }[x],
        key="mineru_vl_api_style",
    )

    versions = version_options("mineru_vl")
    version = st.selectbox(
        "MinerU-VL 版本",
        options=versions,
        index=option_index(versions, st.session_state.get("mineru_vl_version", default_version("mineru_vl"))),
        format_func=lambda value: version_label("mineru_vl", value),
        key="mineru_vl_version",
    )
    quants = quant_options("mineru_vl", version)
    quant = st.selectbox(
        "量化/模型规格",
        options=quants,
        index=option_index(quants, st.session_state.get("mineru_vl_quant", default_quant("mineru_vl"))),
        key="mineru_vl_quant",
    )
    default_model = resolve_vlm_model("mineru_vl", version=version, quant=quant)

    endpoint = st.text_input(
        "Endpoint",
        value=st.session_state.get("mineru_vl_endpoint", _default_endpoint(api_style)),
        help="OpenAI 兼容通常以 /v1/chat/completions 结尾；LM Studio 原生通常为 /api/v1/chat。",
        key="mineru_vl_endpoint",
    )
    model = st.text_input(
        "模型名称",
        value=st.session_state.get("mineru_vl_model", default_model),
        key="mineru_vl_model",
    )
    api_key = st.text_input(
        "API Key",
        value=st.session_state.get("mineru_vl_api_key", ""),
        type="password",
        key="mineru_vl_api_key",
    )

    col1, col2 = st.columns(2)
    with col1:
        concurrency = st.slider(
            "Layout 请求并发",
            min_value=1,
            max_value=8,
            value=int(st.session_state.get("mineru_vl_layout_concurrency", 1)),
            key="mineru_vl_layout_concurrency",
        )
        timeout = st.number_input(
            "Layout 超时（秒）",
            min_value=30,
            max_value=1200,
            value=int(st.session_state.get("mineru_vl_layout_timeout", 120)),
            step=30,
            key="mineru_vl_layout_timeout",
        )
    with col2:
        image_size = st.number_input(
            "Layout 图像边长",
            min_value=512,
            max_value=2048,
            value=int(_image_size_value(st.session_state.get("mineru_vl_layout_image_size", (1036, 1036)))),
            step=16,
            key="mineru_vl_layout_image_size_scalar",
        )
        image_quality = st.slider(
            "图像质量",
            min_value=50,
            max_value=100,
            value=int(st.session_state.get("mineru_vl_image_quality", 90)),
            key="mineru_vl_image_quality",
        )

    return {
        "mineru_vl_endpoint": endpoint,
        "mineru_vl_api_key": api_key,
        "mineru_vl_api_style": api_style,
        "mineru_vl_version": version,
        "mineru_vl_quant": quant,
        "mineru_vl_model": model,
        "mineru_vl_layout_image_size": (int(image_size), int(image_size)),
        "mineru_vl_layout_timeout": int(timeout),
        "mineru_vl_layout_max_tokens": 4096,
        "mineru_vl_layout_batch_size": int(concurrency),
        "mineru_vl_layout_concurrency": int(concurrency),
        "mineru_vl_request_concurrency": int(concurrency),
        "mineru_vl_image_quality": int(image_quality),
    }


def _default_endpoint(api_style: str) -> str:
    if str(api_style).strip().lower() == "lmstudio-native":
        return "http://localhost:1234/api/v1/chat"
    return "http://127.0.0.1:1234/v1/chat/completions"


def _image_size_value(value: object) -> int:
    if isinstance(value, (list, tuple)) and value:
        return int(value[0])
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1036


def option_index(options: list[str], value: object) -> int:
    try:
        return options.index(str(value))
    except ValueError:
        return 0
