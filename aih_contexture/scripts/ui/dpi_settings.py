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
    "fast": "快速 - 96 DPI",
    "standard": "标准 - 144 DPI",
    "high": "高质量 - 192 DPI",
}

_OCR_QUALITY_OPTIONS = ["auto", "low", "medium", "high"]
_OCR_QUALITY_LABELS = {
    "auto": "自动 - 按 OCR 后端默认值",
    "low": "低档 - 192 DPI",
    "medium": "中档 - 300 DPI",
    "high": "高档 - 400 DPI",
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

    with st.expander("版面渲染 DPI", expanded=False):
        if backend_name == "surya":
            selected_quality = st.selectbox(
                "Surya 版面质量",
                options=_LAYOUT_QUALITY_OPTIONS,
                index=_option_index(_LAYOUT_QUALITY_OPTIONS, selected_quality, "fast"),
                format_func=lambda value: _LAYOUT_QUALITY_LABELS.get(value, value),
                help="只影响 Surya Layout 的页面渲染 DPI；坐标会统一归化到 PDF 点。",
                key="surya_layout_quality",
            )
            preset_dpi = LAYOUT_QUALITY_PRESETS.get(selected_quality, LAYOUT_QUALITY_PRESETS["fast"])
        else:
            preset_dpi = LAYOUT_BACKEND_DEFAULT_DPI.get(backend_name, 96)
            st.caption(f"当前版面后端默认使用 {preset_dpi} DPI；需要诊断或特殊材料时可手动覆盖。")

        override_input = st.number_input(
            "版面 DPI 覆盖",
            min_value=0,
            max_value=1200,
            value=override_value or 0,
            step=1,
            help="0 表示使用所选版面后端的默认 DPI。",
            key="layout_dpi_override",
        )
        override_value = _positive_or_none(override_input)
        effective_dpi = get_layout_dpi(
            backend_name,
            surya_quality=selected_quality,
            override=override_value,
        )
        st.caption(f"实际版面渲染 DPI：{effective_dpi}。")

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

    with st.expander("OCR 渲染 DPI", expanded=False):
        selected_quality = st.selectbox(
            "OCR DPI 档位",
            options=_OCR_QUALITY_OPTIONS,
            index=_option_index(_OCR_QUALITY_OPTIONS, selected_quality, "auto"),
            format_func=lambda value: _OCR_QUALITY_LABELS.get(value, value),
            help="自动模式下，Surya/Paddle OCR 使用 192 DPI，Tesseract/Calamari/VLM 使用 300 DPI。",
            key="ocr_quality",
        )
        override_input = st.number_input(
            "OCR DPI 覆盖",
            min_value=0,
            max_value=1200,
            value=override_value or 0,
            step=1,
            help="0 表示使用所选 OCR 档位或后端自动默认值。",
            key="ocr_dpi_override",
        )
        override_value = _positive_or_none(override_input)
        effective_dpi = get_ocr_dpi(
            backend_name,
            quality=selected_quality,
            override=override_value,
        )
        default_quality = OCR_BACKEND_DEFAULT_QUALITY.get(backend_name, "low")
        st.caption(
            "实际 OCR 渲染 DPI："
            f"{effective_dpi}；当前后端自动档为 {OCR_QUALITY_PRESETS[default_quality]} DPI。"
        )

    return {
        "ocr_quality": selected_quality,
        "ocr_dpi_override": override_value,
    }
