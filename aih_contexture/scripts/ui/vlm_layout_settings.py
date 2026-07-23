from __future__ import annotations

IMAGE_FORMAT_OPTIONS = ["jpeg", "png", "webp"]
PROMPT_TEMPLATE_OPTIONS = [
    "modern",
    "chinese_ancient",
    "gothic_german",
    "archive",
    "table_form",
    "scientific",
]

PROMPT_TEMPLATE_LABELS = {
    "modern": "现代出版物（默认）",
    "chinese_ancient": "中文古籍（竖排、右到左）",
    "gothic_german": "哥特体/德文古籍",
    "archive": "档案文件（手写/印章）",
    "table_form": "表格/表单密集",
    "scientific": "科技论文（公式/代码/多栏）",
}


def option_index(options: list[str], value: str, default: int = 0) -> int:
    try:
        return options.index(value)
    except ValueError:
        return default


def count_api_keys(api_keys: str) -> int:
    if not api_keys:
        return 0
    return len([key.strip() for key in api_keys.replace("\n", ",").split(",") if key.strip()])


def render_vlm_layout_settings(
    st,
    *,
    description: str,
    base_url: str,
    model: str,
    api_key: str,
    max_concurrent: int,
    image_format: str,
    max_image_dimension: int,
    jpeg_quality: int,
    timeout: int,
    prompt_template: str,
    prompt: str,
) -> dict[str, object]:
    st.info(description)
    with st.expander("VLM 版面识别配置", expanded=False):
        st.caption("仅用于版面区域检测；OCR 后端仍由下方单独选择。")

        base_url = st.text_input(
            "Base URL",
            value=base_url,
            help="OpenAI 兼容 API 地址，例如 LM Studio 或云端中转。",
            key="vlm_layout_base_url",
        )
        model = st.text_input(
            "模型名称",
            value=model,
            help="例如 gpt-4o、qwen-vl-max 或本地挂载模型名。",
            key="vlm_layout_model",
        )
        api_key = st.text_area(
            "API Keys（可多个）",
            value=api_key,
            height=100,
            help="每行一个或用英文逗号分隔。多 key 可轮换请求。",
            key="vlm_layout_api_key",
        )

        key_count = count_api_keys(api_key)
        if key_count > 1:
            st.caption(f"已检测到 {key_count} 个 API Key，可适当提高并发。")

        max_concurrent = st.slider(
            "最大并发数",
            min_value=1,
            max_value=50,
            value=int(max_concurrent),
            help="同时处理的页面数。本地模型显存有限时保持较低。",
            key="vlm_layout_max_concurrent",
        )

        col1, col2 = st.columns(2)
        with col1:
            image_format = st.selectbox(
                "图像格式",
                options=IMAGE_FORMAT_OPTIONS,
                index=option_index(IMAGE_FORMAT_OPTIONS, image_format),
                key="vlm_layout_image_format",
            )
            max_image_dimension = st.number_input(
                "图像最大边长（像素）",
                min_value=512,
                max_value=4096,
                value=int(max_image_dimension),
                step=128,
                key="vlm_layout_max_image_dimension",
            )
        with col2:
            jpeg_quality = st.number_input(
                "JPEG 质量 (1-100)",
                min_value=1,
                max_value=100,
                value=int(jpeg_quality),
                key="vlm_layout_jpeg_quality",
            )
            timeout = st.number_input(
                "超时时间（秒）",
                min_value=30,
                max_value=300,
                value=int(timeout),
                key="vlm_layout_timeout",
            )

        st.divider()
        st.caption("提示词只影响 VLM 版面检测，不影响 OCR 识别。")

        prompt_config_mode = st.radio(
            "提示词配置方式",
            options=["使用预制模板", "自定义提示词"],
            index=0,
            horizontal=True,
            key="vlm_layout_prompt_mode",
        )

        if prompt_config_mode == "使用预制模板":
            prompt_template = st.selectbox(
                "提示词模板",
                options=PROMPT_TEMPLATE_OPTIONS,
                index=option_index(PROMPT_TEMPLATE_OPTIONS, prompt_template),
                format_func=lambda value: PROMPT_TEMPLATE_LABELS.get(value, value),
                help="选择接近文档类型的版面检测提示词。",
                key="vlm_layout_prompt_template",
            )
            prompt = ""
        else:
            prompt = st.text_area(
                "自定义提示词",
                value=prompt if prompt else "Analyze this document page and identify all layout regions...",
                height=120,
                help="直接指定提示词，会覆盖模板。",
                key="vlm_layout_prompt",
            )
            prompt_template = ""

    return {
        "vlm_layout_base_url": base_url,
        "vlm_layout_model": model,
        "vlm_layout_api_key": api_key,
        "vlm_layout_max_concurrent": max_concurrent,
        "vlm_layout_image_format": image_format,
        "vlm_layout_max_image_dimension": max_image_dimension,
        "vlm_layout_jpeg_quality": jpeg_quality,
        "vlm_layout_timeout": timeout,
        "vlm_layout_prompt_template": prompt_template,
        "vlm_layout_prompt": prompt,
    }
