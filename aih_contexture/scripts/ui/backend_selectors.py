from __future__ import annotations

from collections.abc import MutableMapping

from aih_contexture.backends.layout import default_layout_registry
from aih_contexture.backends.ocr import default_ocr_registry


LAYOUT_BACKEND_LABELS = {
    "surya": "Surya（内置通用版面分析）",
    "mineru_pp_doclayout_v2_direct": "MinerU PP-DocLayoutV2 Direct",
    "paddle_pp_doclayout_plus_l": "Paddle PP-DocLayout Plus-L",
    "paddle_pp_doclayout_v3": "Paddle PP-DocLayoutV3",
    "external_layout_sidecar": "External Layout Sidecar（读取 JSON）",
    "mineru_pp_doclayout_v2": "MinerU Pipeline Sidecar（兼容/诊断）",
}

HIDDEN_LAYOUT_BACKENDS = {"vlm", "vlm_layout"}

OCR_BACKEND_LABELS = {
    "none": "禁用 OCR（使用 PDF 文本层）",
    "surya": "Surya OCR（内置通用 OCR）",
    "vlm": "VLM OCR（API 识别）",
    "vlm_ocr": "VLM OCR（API 识别）",
    "calamari": "Calamari OCR（欧洲历史文献）",
    "paddle_ocr_v5": "PaddleOCR PP-OCRv5",
    "paddleocr_vl_ocr": "PaddleOCR-VL OCR（块级 VLM）",
    "tesseract": "Tesseract OCR（传统 CPU OCR）",
}


def layout_backend_options() -> list[str]:
    names = [name for name in default_layout_registry.names() if name not in HIDDEN_LAYOUT_BACKENDS]
    preferred = [
        "surya",
        "paddle_pp_doclayout_plus_l",
        "paddle_pp_doclayout_v3",
        "mineru_pp_doclayout_v2_direct",
        "external_layout_sidecar",
        "mineru_pp_doclayout_v2",
    ]
    return [name for name in preferred if name in names] + [name for name in names if name not in preferred]


def ocr_backend_options() -> list[str]:
    return ["none"] + default_ocr_registry.names()


def normalize_layout_backend_state(value: str | None) -> tuple[str | None, str | None]:
    if value == "yolo":
        return (
            "surya",
            "DocLayout-YOLO 已从主线移除；当前会话已重置为 Surya。后续强版面识别将通过 MinerU/Paddle adapter 接入。",
        )
    if value in HIDDEN_LAYOUT_BACKENDS:
        return (
            "surya",
            "VLM Layout 已从前端隐藏；当前会话已重置为 Surya。API 版面识别可通过 VLM 泛化或 VLM 特化模式处理。",
        )
    return value, None


def normalize_ocr_backend_state(value: str | None) -> tuple[str | None, str | None]:
    if value == "vlm":
        return "vlm_ocr", None
    return value, None


def normalize_backend_session_state(session_state: MutableMapping[str, str]) -> list[str]:
    warnings = []

    layout_backend, layout_warning = normalize_layout_backend_state(session_state.get("layout_backend"))
    if layout_backend != session_state.get("layout_backend"):
        session_state["layout_backend"] = layout_backend
    if layout_warning:
        warnings.append(layout_warning)

    ocr_backend, ocr_warning = normalize_ocr_backend_state(session_state.get("ocr_backend"))
    if ocr_backend != session_state.get("ocr_backend"):
        session_state["ocr_backend"] = ocr_backend
    if ocr_warning:
        warnings.append(ocr_warning)

    return warnings


def render_layout_backend_selector(st):
    for warning in _normalize_layout_state(st.session_state):
        st.warning(warning)

    return st.selectbox(
        "选择版面识别引擎",
        options=layout_backend_options(),
        index=0,
        format_func=lambda value: LAYOUT_BACKEND_LABELS.get(value, value),
        help="只决定区域检测和阅读顺序；文字识别由 OCR 后端单独决定。",
        key="layout_backend",
    )


def render_ocr_backend_selector(st):
    for warning in _normalize_ocr_state(st.session_state):
        st.warning(warning)

    return st.selectbox(
        "选择 OCR 引擎",
        options=ocr_backend_options(),
        index=0,
        format_func=lambda value: OCR_BACKEND_LABELS.get(value, value),
        help="选择文字来源：禁用 OCR 时使用 PDF 文本层；选择任意 OCR 后端时会强制重新识别。",
        key="ocr_backend",
    )


def _normalize_layout_state(session_state: MutableMapping[str, str]) -> list[str]:
    backend, warning = normalize_layout_backend_state(session_state.get("layout_backend"))
    if backend != session_state.get("layout_backend"):
        session_state["layout_backend"] = backend
    return [warning] if warning else []


def _normalize_ocr_state(session_state: MutableMapping[str, str]) -> list[str]:
    backend, warning = normalize_ocr_backend_state(session_state.get("ocr_backend"))
    if backend != session_state.get("ocr_backend"):
        session_state["ocr_backend"] = backend
    return [warning] if warning else []
