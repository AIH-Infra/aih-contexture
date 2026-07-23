from __future__ import annotations

from aih_contexture.config.vlm_model_presets import (
    default_version,
    resolve_vlm_model,
    version_label,
    version_options,
)

IMAGE_FORMAT_OPTIONS = ["jpeg", "png", "webp"]
PADDLEOCR_VL_IMAGE_FORMAT_OPTIONS = ["JPEG", "PNG", "WEBP"]
VLM_MODE_OPTIONS = ["tile", "merge", "full_page"]
VLM_RESPONSE_MODE_OPTIONS = ["text", "json"]


def option_index(options: list[str], value: str, default: int = 0) -> int:
    try:
        return options.index(value)
    except ValueError:
        return default


def count_api_keys(api_keys: str) -> int:
    if not api_keys:
        return 0
    return len([key.strip() for key in api_keys.replace("\n", ",").split(",") if key.strip()])


def vlm_mode_label(value: str) -> str:
    return {
        "tile": "逐块（默认）",
        "merge": "区域合并",
        "full_page": "整页",
    }.get(value, value)


def render_vlm_ocr_settings(
    st,
    *,
    description: str,
    layout_backend: str,
    base_url: str,
    model: str,
    api_key: str,
    max_concurrent: int,
    image_format: str,
    mode: str,
    response_mode: str,
    prompt: str,
    use_stop: bool,
    merge_y_threshold: int,
    merge_max_blocks: int,
    full_page_max_tokens: int,
) -> dict[str, object]:
    st.info(description)

    st.markdown("**API 配置**")
    base_url = st.text_input(
        "Base URL",
        value=base_url,
        help="OpenAI 兼容 API 地址，例如 LM Studio 或云端中转。",
        key="vlm_ocr_base_url",
    )
    model = st.text_input("模型名称", value=model, key="vlm_ocr_model")
    api_key = st.text_area(
        "API Keys (支持多个)",
        value=api_key,
        height=100,
        help="每行一个或用英文逗号分隔。多 key 可轮换请求。",
        key="vlm_ocr_api_key",
    )

    key_count = count_api_keys(api_key)
    if key_count > 1:
        st.caption(f"已检测到 {key_count} 个 API Key，可适当提高并发。")

    max_concurrent = st.slider(
        "最大并发数",
        min_value=1,
        max_value=50,
        value=int(max_concurrent),
        help="同时发起的 OCR 请求数。本地模型显存有限时保持较低。",
        key="vlm_ocr_max_concurrent",
    )

    image_format = st.selectbox(
        "图像格式",
        options=IMAGE_FORMAT_OPTIONS,
        index=option_index(IMAGE_FORMAT_OPTIONS, image_format),
        help="发送给 VLM 的图像格式。",
        key="vlm_ocr_image_format",
    )

    st.markdown("---")
    st.markdown("**OCR 模式**")
    mode = st.radio(
        "处理模式",
        options=VLM_MODE_OPTIONS,
        index=option_index(VLM_MODE_OPTIONS, mode),
        format_func=vlm_mode_label,
        horizontal=False,
    )

    if mode == "full_page":
        if layout_backend == "surya":
            st.info(
                "当前为 Surya Layout + VLM 整页 OCR：Surya 提供区域结构，VLM 负责整页识别。"
                "适用于复杂页面试验；速度和稳定性取决于 VLM 服务。"
            )
        elif layout_backend == "none":
            st.warning(
                "整页 VLM OCR 需要版面结构来组织结果；应先启用一个版面识别后端。"
            )
        else:
            st.info(
                "整页模式会把页面整体交给 VLM；适用于复杂版式，但会增加 token 和显存压力。"
            )

    response_mode = st.radio(
        "返回格式",
        options=VLM_RESPONSE_MODE_OPTIONS,
        index=option_index(VLM_RESPONSE_MODE_OPTIONS, response_mode),
        horizontal=True,
        help="text 更稳；json 可保留结构但更依赖模型遵循格式。",
    )

    with st.expander("高级参数", expanded=False):
        prompt = st.text_area("自定义 Prompt", value=prompt, height=100, key="vlm_prompt")
        use_stop = st.checkbox(
            "启用 stop 参数",
            value=bool(use_stop),
            help="部分本地服务不兼容 stop 参数，默认关闭。",
            key="openai_use_stop",
        )

        if mode == "merge":
            st.markdown("**区域合并参数**")
            merge_y_threshold = st.slider("Y 合并阈值", 30, 200, int(merge_y_threshold))
            merge_max_blocks = st.slider("单组最大块数", 3, 30, int(merge_max_blocks))
        else:
            merge_y_threshold = 80
            merge_max_blocks = 15

        if mode == "full_page":
            full_page_max_tokens = st.number_input(
                "整页 max_tokens",
                min_value=512,
                max_value=8192,
                value=int(full_page_max_tokens),
            )
        else:
            full_page_max_tokens = 2048

    return {
        "openai_base_url": base_url,
        "openai_model": model,
        "openai_api_key": api_key,
        "openai_max_concurrent": max_concurrent,
        "openai_image_format": image_format,
        "vlm_mode": mode,
        "vlm_response_mode": response_mode,
        "vlm_prompt": prompt,
        "openai_use_stop": use_stop,
        "vlm_merge_y_threshold": merge_y_threshold,
        "vlm_merge_max_blocks": merge_max_blocks,
        "vlm_full_page_max_tokens": full_page_max_tokens,
        "force_ocr": True,
        "use_llm": False,
        "ocr_batch_size": 32,
    }


def render_paddleocr_vl_ocr_settings(
    st,
    *,
    description: str,
    endpoint: str,
    model: str,
    api_key: str,
    api_style: str,
    block_concurrency: int,
    image_format: str,
    image_quality: int,
    crop_padding_px: int,
    crop_padding_frac: float,
) -> dict[str, object]:
    st.info(description)

    st.markdown("**API 配置**")
    api_style_options = ["openai", "lmstudio-native"]
    api_style = st.selectbox(
        "协议风格",
        options=api_style_options,
        index=option_index(api_style_options, api_style),
        format_func=lambda x: {
            "openai": "OpenAI 兼容 Chat Completions",
            "lmstudio-native": "LM Studio 原生 /api/v1/chat",
        }[x],
        key="paddleocr_vl_api_style",
    )
    _sync_paddleocr_vl_endpoint_state(st, api_style=api_style, endpoint=endpoint)

    paddle_versions = version_options("paddleocr_vl")
    selected_version = st.selectbox(
        "PaddleOCR-VL 版本",
        options=paddle_versions,
        index=option_index(paddle_versions, _state_get(st, "paddleocr_vl_version", default_version("paddleocr_vl"))),
        format_func=lambda x: version_label("paddleocr_vl", x),
        key="paddleocr_vl_version",
    )
    default_model = resolve_vlm_model("paddleocr_vl", version=selected_version)
    _sync_paddleocr_vl_model_state(st, version=selected_version, default_model=default_model)

    endpoint = st.text_input(
        "Endpoint",
        value=_normalize_paddleocr_vl_endpoint(endpoint, api_style=api_style),
        help="PaddleOCR-VL prompt/VLRecognition 的完整请求地址。OpenAI 兼容通常以 /v1/chat/completions 结尾。",
        key="paddleocr_vl_endpoint",
    )
    model = st.text_input(
        "模型名称",
        value=model,
        help="默认来自 PaddleOCR-VL 版本预设；只在服务端使用不同模型名时覆盖。",
        key="paddleocr_vl_model",
    )
    api_key = st.text_input(
        "API Key",
        value=api_key,
        type="password",
        help="本地 LM Studio 通常可使用 lm-studio；云端或中转服务填写真实 key。",
        key="paddleocr_vl_api_key",
    )
    block_concurrency = st.slider(
        "块级请求并发",
        min_value=1,
        max_value=20,
        value=max(1, int(block_concurrency)),
        help="Pipeline 中同时提交给 PaddleOCR-VL 的 layout block crop 数量；本地模型通常从 1 开始较稳。",
        key="paddleocr_vl_block_concurrency",
    )

    return {
        "paddleocr_vl_endpoint": endpoint,
        "paddleocr_vl_version": selected_version,
        "paddleocr_vl_model": model,
        "paddleocr_vl_api_key": api_key,
        "paddleocr_vl_api_style": api_style,
        "paddleocr_vl_request_concurrency": block_concurrency,
        "paddleocr_vl_block_concurrency": block_concurrency,
        # Official PaddleOCR-VL VLRecognition tasks are selected internally
        # from the Contexture block type; the prompt is not user-facing here.
        "paddleocr_vl_prompt_label": "ocr",
        "paddleocr_vl_image_format": str(image_format or "JPEG").upper(),
        "paddleocr_vl_image_quality": int(image_quality),
        "paddleocr_vl_crop_padding_px": int(crop_padding_px),
        "paddleocr_vl_crop_padding_frac": float(crop_padding_frac),
        "force_ocr": True,
        "use_llm": False,
        "ocr_batch_size": 32,
    }


def _normalize_paddleocr_vl_endpoint(endpoint: str, *, api_style: str) -> str:
    if endpoint:
        stripped = str(endpoint).strip().rstrip("/")
        if str(api_style).strip().lower() == "openai" and stripped.endswith("/v1"):
            return f"{stripped}/chat/completions"
        return str(endpoint).strip()
    if str(api_style).strip().lower() == "lmstudio-native":
        return "http://localhost:1234/api/v1/chat"
    return "http://127.0.0.1:1234/v1/chat/completions"


def _paddleocr_vl_default_endpoint(api_style: str) -> str:
    if str(api_style).strip().lower() == "lmstudio-native":
        return "http://localhost:1234/api/v1/chat"
    return "http://127.0.0.1:1234/v1/chat/completions"


def _state_get(st, key: str, default=None):
    state = getattr(st, "session_state", None)
    if state is None:
        return default
    try:
        return state.get(key, default)
    except AttributeError:
        return getattr(state, key, default)


def _state_set(st, key: str, value) -> None:
    state = getattr(st, "session_state", None)
    if state is None:
        return
    try:
        state[key] = value
    except TypeError:
        setattr(state, key, value)


def _sync_paddleocr_vl_endpoint_state(st, *, api_style: str, endpoint: str) -> None:
    last_key = "_last_paddleocr_vl_api_style"
    last_style = _state_get(st, last_key)
    if last_style is None:
        _state_set(st, "paddleocr_vl_endpoint", _paddleocr_vl_endpoint_for_style(endpoint, api_style=api_style))
        _state_set(st, last_key, api_style)
        return
    if last_style != api_style:
        _state_set(st, "paddleocr_vl_endpoint", _paddleocr_vl_default_endpoint(api_style))
        _state_set(st, last_key, api_style)


def _paddleocr_vl_endpoint_for_style(endpoint: str, *, api_style: str) -> str:
    style = str(api_style or "openai").strip().lower()
    text = str(endpoint or "").strip()
    if style == "lmstudio-native":
        if text.rstrip("/").endswith("/api/v1/chat"):
            return text
        return _paddleocr_vl_default_endpoint(style)
    if text.rstrip("/").endswith("/api/v1/chat"):
        return _paddleocr_vl_default_endpoint(style)
    return _normalize_paddleocr_vl_endpoint(text, api_style=style)


def _sync_paddleocr_vl_model_state(st, *, version: str, default_model: str) -> None:
    last_key = "_last_paddleocr_vl_version"
    if _state_get(st, last_key) != version:
        _state_set(st, "paddleocr_vl_model", default_model)
        _state_set(st, last_key, version)
