from __future__ import annotations

from collections.abc import MutableMapping

from aih_contexture.backends.layout import default_layout_registry
from aih_contexture.backends.ocr import default_ocr_registry


LAYOUT_BACKEND_LABELS = {
    "none": "跳过版面分析（PDF 文本层）",
    "surya": "Surya（本地版面分析）",
    "mineru_pp_doclayout_v2_direct": "MinerU PP-DocLayoutV2（共享 PyTorch）",
    "mineru_vl_layout": "MinerU-VL（API 版面分析）",
    "surya2_layout": "Surya 2（API 版面分析）",
    "paddle_pp_doclayout_plus_l": "Paddle PP-DocLayout Plus-L（SDK）",
    "paddle_pp_doclayout_v3": "Paddle PP-DocLayoutV3（CPU ONNX）",
    "external_layout_sidecar": "导入外部版面 JSON",
    "indra_layout": "Indra（CPU 版面分析）",
}

HIDDEN_LAYOUT_BACKENDS = {"vlm", "vlm_layout"}

OCR_BACKEND_LABELS = {
    "none": "不重新 OCR（读取 PDF 文本层）",
    "chrome_screenai": "Chrome ScreenAI（生成可搜索 PDF）",
    "surya": "Surya OCR（本地）",
    "vlm": "通用 VLM OCR（API）",
    "vlm_ocr": "通用 VLM OCR（API）",
    "calamari": "Calamari（历史文献 HTTP 服务）",
    "paddle_ocr_v5": "PaddleOCR PP-OCRv5（旧 SDK 配置）",
    "paddleocr_vl_ocr": "PaddleOCR-VL OCR（API）",
    "surya2_ocr": "Surya 2 OCR（API）",
    "glm_ocr": "GLM-OCR（本地 API）",
    "mineru_pytorch_paddle_ocr": "Paddle OCR Torch（本地 PyTorch）",
    "indra_ocr": "Indra OCR（CPU）",
    "tesseract": "Tesseract OCR（系统 CPU）",
}


def layout_backend_options() -> list[str]:
    names = [name for name in default_layout_registry.names() if name not in HIDDEN_LAYOUT_BACKENDS]
    preferred = [
        "surya",
        "paddle_pp_doclayout_v3",
        "mineru_pp_doclayout_v2_direct",
        "indra_layout",
        "paddle_pp_doclayout_plus_l",
        "mineru_vl_layout",
        "surya2_layout",
        "external_layout_sidecar",
    ]
    ordered = [name for name in preferred if name in names]
    ordered.extend(name for name in names if name not in preferred)
    return [*ordered, "none"]


def ocr_backend_options() -> list[str]:
    # Keep the old PaddlePaddle backend registered for API/CLI configurations,
    # but offer one primary local Paddle OCR entry in new UI selections.
    names = [name for name in default_ocr_registry.names() if name != "paddle_ocr_v5"]
    preferred = [
        "none",
        "chrome_screenai",
        "surya",
        "mineru_pytorch_paddle_ocr",
        "indra_ocr",
        "tesseract",
        "glm_ocr",
        "paddleocr_vl_ocr",
        "surya2_ocr",
        "vlm_ocr",
        "calamari",
    ]
    ordered = [name for name in preferred if name == "none" or name in names]
    ordered.extend(name for name in names if name not in ordered)
    return ordered


def normalize_layout_backend_state(value: str | None) -> tuple[str | None, str | None]:
    if value == "yolo":
        return (
            "surya",
            "旧配置中的 DocLayout-YOLO 已停用，当前已切换为 Surya；也可从下方选择其他版面后端。",
        )
    if value in HIDDEN_LAYOUT_BACKENDS:
        return (
            "surya",
            "旧配置中的通用 VLM 版面选项已停用，当前已切换为 Surya；如需 API 版面分析，可选择 MinerU-VL 或 Surya 2。",
        )
    if value == "mineru_pp_doclayout_v2":
        return (
            "mineru_pp_doclayout_v2_direct",
            "旧配置中的 MinerU Pipeline Sidecar 已迁移为 MinerU PP-DocLayoutV2 Direct。已有 MinerU 完整解析结果可在「Markdown 后处理 → MinerU 官方 JSON 转换」中导入。",
        )
    return value, None


def normalize_ocr_backend_state(value: str | None) -> tuple[str | None, str | None]:
    if value == "vlm":
        return "vlm_ocr", None
    return value, None


def should_migrate_legacy_screenai_preprocess(
    legacy_preprocess_backend: str | None,
    current_ocr_backend: str | None,
) -> bool:
    """Recognize legacy ScreenAI settings while loading a saved configuration.

    Do not apply this migration during widget reruns: the old preprocessing
    value may simply belong to the user's previous OCR selection.
    Explicit ``none`` configurations retain the embedded-text path.
    """
    legacy = str(legacy_preprocess_backend or "none").strip().lower().replace("-", "_")
    return legacy == "chrome_screenai_searchable_pdf" and current_ocr_backend not in {
        "none",
        "chrome_screenai",
    }


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
        help="只决定区域检测和阅读顺序，不识别文字；PDF 文本层、ScreenAI 或文字识别由 OCR 选项决定。",
        key="layout_backend",
    )


def render_ocr_backend_selector(st, *, options: list[str] | None = None):
    for warning in _normalize_ocr_state(st.session_state):
        st.warning(warning)

    available_options = options or ocr_backend_options()
    if st.session_state.get("ocr_backend") == "paddle_ocr_v5" and "paddle_ocr_v5" not in available_options:
        available_options = [*available_options, "paddle_ocr_v5"]
        st.caption("当前使用旧配置中的 PaddlePaddle 后端。可手动选择 Paddle OCR Torch，切换前请核对模型版本和语言。")
    if st.session_state.get("ocr_backend") not in available_options:
        st.session_state["ocr_backend"] = available_options[0]

    return st.selectbox(
        "选择 OCR 引擎",
        options=available_options,
        index=0,
        format_func=lambda value: OCR_BACKEND_LABELS.get(value, value),
        help="选择文字来源：无 OCR 读取 PDF 文本层；Chrome ScreenAI 先生成可搜索 PDF；其他后端按各自方式识别文字。",
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
