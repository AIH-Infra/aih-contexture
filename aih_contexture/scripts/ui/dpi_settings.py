from __future__ import annotations

from aih_contexture.config.dpi_presets import (
    LAYOUT_BACKEND_DEFAULT_DPI,
    LAYOUT_QUALITY_PRESETS,
    OCR_BACKEND_DEFAULT_QUALITY,
    OCR_QUALITY_PRESETS,
    get_layout_dpi,
    get_ocr_dpi,
    get_ocr_quality_for_backend,
    normalize_backend_name,
)


_LAYOUT_QUALITY_OPTIONS = ["fast", "standard", "high"]
_LAYOUT_QUALITY_LABELS = {
    "fast": "快速 96 DPI",
    "standard": "标准 144 DPI",
    "high": "高质量 192 DPI",
}

_OCR_QUALITY_OPTIONS = ["auto", "low", "medium", "high"]
_OCR_QUALITY_LABELS = {
    "auto": "自动",
    "low": "低 192 DPI",
    "medium": "中 300 DPI",
    "high": "高 400 DPI",
}


def _positive_or_none(value: object) -> int | None:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _option_index(options: list[str], value: object, default: str) -> int:
    normalized = str(value or default).strip().lower().replace("-", "_")
    if normalized in options:
        return options.index(normalized)
    return options.index(default)


def render_pipeline_layout_dpi_settings(
    st,
    *,
    layout_backend: str,
    surya_layout_quality: str = "fast",
    layout_dpi_override: int | None = None,
) -> dict[str, object]:
    backend_name = normalize_backend_name(layout_backend)
    selected_quality = str(surya_layout_quality or "fast").strip().lower().replace("-", "_")
    override_value = _positive_or_none(layout_dpi_override)

    with st.expander("版面页面图像 DPI", expanded=False):
        if backend_name == "surya":
            selected_quality = st.selectbox(
                "Surya 页面图像质量",
                options=_LAYOUT_QUALITY_OPTIONS,
                index=_option_index(_LAYOUT_QUALITY_OPTIONS, selected_quality, "fast"),
                format_func=lambda value: _LAYOUT_QUALITY_LABELS.get(value, value),
                help="控制送入 Surya 版面模型的页面图像分辨率。",
                key="surya_layout_quality",
            )
            preset_dpi = LAYOUT_QUALITY_PRESETS.get(selected_quality, LAYOUT_QUALITY_PRESETS["fast"])
        else:
            preset_dpi = LAYOUT_BACKEND_DEFAULT_DPI.get(backend_name, 96)
            if backend_name == "indra_layout":
                st.caption("此项控制 Pipeline 页面图像；Indra 模型输入 DPI 在 Indra 设置中调整。")
            st.caption(f"默认页面图像分辨率：{preset_dpi} DPI。")

        override_input = st.number_input(
            "页面图像 DPI 覆盖",
            min_value=0,
            max_value=1200,
            value=override_value or 0,
            step=1,
            help="0 表示使用所选后端的默认页面图像分辨率。",
            key="layout_dpi_override",
        )
        override_value = _positive_or_none(override_input)
        effective_dpi = get_layout_dpi(
            backend_name,
            surya_quality=selected_quality,
            override=override_value,
        )
        if backend_name == "indra_layout":
            st.caption(f"Pipeline 页面图像：{effective_dpi} DPI。Indra 模型输入分辨率由 Indra 设置控制。")
        elif backend_name == "surya":
            st.caption(f"Surya 模型输入页面图像：{effective_dpi} DPI。")
        else:
            st.caption(f"Pipeline 页面图像：{effective_dpi} DPI。")

    return {
        "surya_layout_quality": selected_quality,
        "layout_dpi_override": override_value,
    }


def render_pipeline_ocr_dpi_settings(
    st,
    *,
    ocr_backend: str,
    ocr_quality: str = "auto",
    ocr_dpi_override: int | None = None,
) -> dict[str, object]:
    backend_name = normalize_backend_name(ocr_backend)
    if backend_name == "none":
        return {
            "ocr_quality": "auto",
            "ocr_dpi_override": None,
        }

    selected_quality = str(ocr_quality or "auto").strip().lower().replace("-", "_")
    if selected_quality not in _OCR_QUALITY_OPTIONS:
        selected_quality = "auto"
    override_value = _positive_or_none(ocr_dpi_override)

    with st.expander("OCR 页面图像 DPI", expanded=False):
        selected_quality = st.selectbox(
            "页面图像质量",
            options=_OCR_QUALITY_OPTIONS,
            index=_option_index(_OCR_QUALITY_OPTIONS, selected_quality, "auto"),
            format_func=lambda value: _OCR_QUALITY_LABELS.get(value, value),
            help="自动模式使用所选 OCR 后端的默认页面图像分辨率。",
            key="ocr_quality",
        )
        override_input = st.number_input(
            "页面图像 DPI 覆盖",
            min_value=0,
            max_value=1200,
            value=override_value or 0,
            step=1,
            help="0 表示使用所选 OCR 档位或后端默认分辨率。",
            key="ocr_dpi_override",
        )
        override_value = _positive_or_none(override_input)
        effective_dpi = get_ocr_dpi(
            backend_name,
            quality=selected_quality,
            override=override_value,
        )
        default_quality = OCR_BACKEND_DEFAULT_QUALITY.get(backend_name, "low")
        if backend_name == "indra_ocr":
            st.caption(
                f"Pipeline 页面图像：{effective_dpi} DPI。Indra 模型输入 DPI 在 Indra 设置中调整。"
            )
        else:
            st.caption(
                f"OCR 输入页面图像：{effective_dpi} DPI；后端默认值为 {OCR_QUALITY_PRESETS[default_quality]} DPI。"
            )

    return {
        "ocr_quality": selected_quality,
        "ocr_dpi_override": override_value,
    }
