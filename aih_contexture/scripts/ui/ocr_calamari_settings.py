from __future__ import annotations

from collections.abc import Callable

DEFAULT_CALAMARI_MODELS = ["gt4histocr", "fraktur_19th_century", "antiqua_historical"]


def default_model_index(models: list[str], preferred: str = "gt4histocr") -> int:
    try:
        return models.index(preferred)
    except ValueError:
        return 0


def render_calamari_ocr_settings(
    st,
    *,
    description: str,
    base_url: str,
    model: str,
    batch_size: int,
    timeout: int,
    sequential_mode: bool,
    trust_batch_order: bool,
    require_ordering_info: bool,
    fallback_to_sequential_on_ordering_failure: bool,
    footnote_y_frac: float,
    binarize_lines: bool,
    check_health: Callable[[str], tuple[bool, list[str]]],
    get_models: Callable[[str], list[str]],
    preprocess: str | None = None,
    crop_padding_px: int = 5,
    crop_padding_frac: float = 0.08,
    upscale_min_height: int = 0,
    split_large_batches: bool = True,
) -> dict[str, object]:
    st.info(description)

    base_url = st.text_input(
        "API 地址",
        value=base_url,
        help="Calamari OCR 服务地址。",
        key="calamari_base_url",
    )

    col_status, col_refresh = st.columns([3, 1])
    with col_refresh:
        _ = st.button("刷新", help="检查服务状态")

    is_healthy, cached_models = check_health(base_url)

    with col_status:
        if is_healthy:
            st.success("服务正常")
        else:
            st.error("服务不可用")
            st.caption("Calamari 服务需要保持运行。")

    available_models = get_models(base_url) if is_healthy else []
    if available_models:
        model = st.selectbox(
            "OCR 模型",
            options=available_models,
            index=default_model_index(available_models),
            key="calamari_model",
        )
        if cached_models:
            st.caption(f"已预热模型: {', '.join(cached_models)}")
    else:
        model = st.selectbox(
            "OCR 模型",
            options=DEFAULT_CALAMARI_MODELS,
            index=0,
            help="服务离线时仅显示默认模型名。",
        )

    with st.expander("高级设置", expanded=False):
        batch_size = st.number_input(
            "批次大小",
            min_value=10,
            max_value=500,
            value=int(batch_size),
            help="每次请求发送的最大行图数。",
            key="calamari_batch_size_input",
        )
        timeout = st.number_input(
            "超时时间（秒）",
            min_value=30,
            max_value=600,
            value=int(timeout),
            key="calamari_timeout_input",
        )

        st.markdown("**行图预处理**")
        default_preprocess = preprocess if preprocess is not None else ("otsu" if binarize_lines else "none")
        preprocess_options = ["otsu", "adaptive", "none"]
        if default_preprocess not in preprocess_options:
            default_preprocess = "otsu"
        preprocess = st.selectbox(
            "行图像预处理",
            options=preprocess_options,
            index=preprocess_options.index(default_preprocess),
            format_func=lambda value: {
                "otsu": "Otsu 二值化（泛黄纸张）",
                "adaptive": "自适应二值化（背景不均）",
                "none": "不处理（清晰扫描/细笔画）",
            }[value],
            help="Calamari 对行图质量敏感；优先保证裁切完整、背景干净、边缘留白适中。",
            key="calamari_preprocess_select",
        )
        binarize_lines = preprocess != "none"

        st.markdown("**Tesseract 行检测代理**")
        proxy_col_a, proxy_col_b = st.columns(2)
        with proxy_col_a:
            tesseract_line_psm = st.selectbox(
                "行检测 PSM",
                options=[1, 6, 4, 3, 11],
                index=0,
                format_func=lambda value: {
                    1: "1 - 自动分割 + OSD（默认，整页 hOCR）",
                    6: "6 - 单块文本",
                    4: "4 - 单列文本",
                    3: "3 - 自动分割",
                    11: "11 - 稀疏文本",
                }[value],
                key="calamari_tesseract_line_psm",
                help="只用于整页 hOCR 切行；识别文本仍由 Calamari 完成。",
            )
        with proxy_col_b:
            tesseract_thresholding_method = st.selectbox(
                "Tesseract 阈值算法",
                options=["auto", "adaptive-otsu", "sauvola"],
                index=0,
                format_func=lambda value: {
                    "auto": "auto / Otsu",
                    "adaptive-otsu": "adaptive Otsu",
                    "sauvola": "Sauvola",
                }[value],
                key="calamari_tesseract_thresholding_method",
                help="对应 OCRmyPDF 的 Tesseract thresholding_method；用于行检测代理。",
            )

        crop_col_a, crop_col_b = st.columns(2)
        with crop_col_a:
            crop_padding_px = st.number_input(
                "裁线 padding（px）",
                min_value=0,
                max_value=50,
                value=int(crop_padding_px),
                help="给行框四周补边，避免裁掉上升/下降笔画和标点。",
                key="calamari_crop_padding_px_input",
            )
        with crop_col_b:
            crop_padding_frac = st.number_input(
                "裁线 padding（比例）",
                min_value=0.0,
                max_value=0.5,
                value=float(crop_padding_frac),
                step=0.01,
                help="按行宽/高比例补边；最终取 px 与比例中的较大值。",
                key="calamari_crop_padding_frac_input",
            )

        upscale_min_height = st.number_input(
            "行图最小高度放大到（px，0 为关闭）",
            min_value=0,
            max_value=256,
            value=int(upscale_min_height),
            help="旧印刷或低分辨率行图可适度放大后再送 Calamari。",
            key="calamari_upscale_min_height_input",
        )

        st.markdown("**脚注后置阈值**")
        footnote_y_frac = st.slider(
            "页底区域阈值 (y_frac)",
            min_value=0.60,
            max_value=0.95,
            value=float(footnote_y_frac),
            step=0.01,
            help="行中心超过该页面高度比例时视为页底内容，输出时后置。",
            key="calamari_footnote_y_frac_slider",
        )
        st.markdown("**顺序保证设置**")

        sequential_mode = st.checkbox(
            "使用串行模式",
            value=bool(sequential_mode),
            help="逐张发送行图，顺序最稳定但速度较慢。",
            key="calamari_sequential_mode_checkbox",
        )

        require_ordering_info = st.checkbox(
            "批量模式要求可重排信息",
            value=bool(require_ordering_info),
            help="批量响应必须带可解析索引；否则降级处理，避免行文错位。",
            key="calamari_require_ordering_info_checkbox",
        )

        fallback_to_sequential_on_ordering_failure = st.checkbox(
            "批量失败时串行重试",
            value=bool(fallback_to_sequential_on_ordering_failure),
            help="仅重试当前批次，避免生成错位 Markdown。",
            key="calamari_fallback_checkbox",
        )

        split_large_batches = st.checkbox(
            "大批量自动拆分",
            value=bool(split_large_batches),
            help="按批次大小拆分行图，并保留全局索引用于稳定重排。",
            key="calamari_split_large_batches_checkbox",
        )

        if not sequential_mode:
            trust_batch_order = st.checkbox(
                "信任批量返回顺序",
                value=bool(trust_batch_order),
                help="仅当服务端已验证严格按请求顺序返回时开启。",
                key="calamari_trust_batch_order_checkbox",
            )
        else:
            trust_batch_order = False
            require_ordering_info = False
            fallback_to_sequential_on_ordering_failure = False

    return {
        "calamari_base_url": base_url,
        "calamari_model": model,
        "calamari_batch_size": batch_size,
        "calamari_timeout": timeout,
        "calamari_sequential_mode": sequential_mode,
        "calamari_trust_batch_order": trust_batch_order,
        "calamari_require_ordering_info": require_ordering_info,
        "calamari_fallback_to_sequential_on_ordering_failure": fallback_to_sequential_on_ordering_failure,
        "calamari_footnote_y_frac": footnote_y_frac,
        "calamari_binarize_lines": binarize_lines,
        "calamari_preprocess": preprocess,
        "ocr_line_source": "tesseract",
        "tesseract_line_psm": tesseract_line_psm,
        "tesseract_line_preprocess": preprocess,
        "tesseract_thresholding_method": tesseract_thresholding_method,
        "calamari_crop_padding_px": crop_padding_px,
        "calamari_crop_padding_frac": crop_padding_frac,
        "calamari_upscale_min_height": upscale_min_height,
        "calamari_split_large_batches": split_large_batches,
        "force_ocr": True,
        "use_llm": False,
        "ocr_batch_size": 32,
    }
