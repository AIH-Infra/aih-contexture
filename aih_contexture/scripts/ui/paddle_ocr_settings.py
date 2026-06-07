from __future__ import annotations

from aih_contexture.backends.external_config import PADDLE_PYTHON_ENV, default_paddle_python


_DEVICE_OPTIONS = ["", "cpu", "gpu", "gpu:0", "gpu:1", "custom"]
_DEVICE_LABELS = {
    "": "自动（PaddleOCR 默认）",
    "cpu": "CPU",
    "gpu": "GPU（默认 GPU）",
    "gpu:0": "GPU 0",
    "gpu:1": "GPU 1",
    "custom": "自定义...",
}

_ENGINE_OPTIONS = ["", "paddle", "paddle_static", "paddle_dynamic"]
_ENGINE_LABELS = {
    "": "自动（PaddleOCR 默认）",
    "paddle": "paddle",
    "paddle_static": "paddle_static",
    "paddle_dynamic": "paddle_dynamic",
}


def _render_device_selector(st, *, key: str, label: str, help: str) -> str | None:
    current = str(st.session_state.get(key, "") or "").strip()
    selected = current if current in _DEVICE_OPTIONS[:-1] else "custom" if current else ""
    device_choice = st.selectbox(
        label,
        options=_DEVICE_OPTIONS,
        index=_DEVICE_OPTIONS.index(selected),
        format_func=lambda value: _DEVICE_LABELS.get(value, value),
        help=help,
        key=f"{key}_choice",
    )
    if device_choice == "custom":
        custom_device = st.text_input(
            "自定义运行设备",
            value=current if current not in _DEVICE_OPTIONS else "",
            help="例如 gpu:2、xpu、npu；具体取值取决于 PaddleOCR/PaddlePaddle 环境。",
            key=key,
        )
        return custom_device.strip() or None
    st.session_state[key] = device_choice
    return device_choice or None


def render_paddle_ocr_settings(
    st,
    *,
    description: str,
) -> dict[str, object]:
    st.info(description)

    paddle_ocr_python = st.text_input(
        "Paddle 外部 Python",
        value=st.session_state.get("paddle_ocr_python", default_paddle_python() or ""),
        help=f"指向独立 Paddle/GPU 虚拟环境的 Python 可执行文件；也可用 {PADDLE_PYTHON_ENV} 指定。",
        key="paddle_ocr_python",
    )
    paddle_ocr_lang = st.text_input(
        "语言",
        value=st.session_state.get("paddle_ocr_lang", "ch"),
        help="PaddleOCR lang 参数，例如 ch、en、chinese_cht、japan。",
        key="paddle_ocr_lang",
    )
    paddle_ocr_version = st.text_input(
        "OCR 版本",
        value=st.session_state.get("paddle_ocr_version", "PP-OCRv5"),
        help="默认使用 PP-OCRv5。",
        key="paddle_ocr_version",
    )
    paddle_ocr_device = _render_device_selector(
        st,
        key="paddle_ocr_device",
        label="运行设备",
        help="留空时使用 PaddleOCR 默认策略；GPU 需外部环境安装 paddlepaddle-gpu。",
    )
    paddle_ocr_engine = st.selectbox(
        "推理引擎",
        options=_ENGINE_OPTIONS,
        index=_ENGINE_OPTIONS.index(
            st.session_state.get("paddle_ocr_engine", "")
            if st.session_state.get("paddle_ocr_engine", "") in _ENGINE_OPTIONS
            else ""
        ),
        format_func=lambda value: _ENGINE_LABELS.get(value, value),
        help="通常留空；排查 Paddle 推理兼容性时再切换。",
        key="paddle_ocr_engine",
    )
    paddle_ocr_enable_mkldnn = st.checkbox(
        "启用 MKL-DNN",
        value=bool(st.session_state.get("paddle_ocr_enable_mkldnn", False)),
        help="仅 CPU 推理相关；Windows 下默认关闭以减少兼容问题。",
        key="paddle_ocr_enable_mkldnn",
    )
    paddle_ocr_cpu_threads = st.number_input(
        "CPU 线程数",
        min_value=0,
        max_value=64,
        value=int(st.session_state.get("paddle_ocr_cpu_threads", 0)),
        step=1,
        help="0 表示不显式覆盖 PaddleOCR 默认线程数。",
        key="paddle_ocr_cpu_threads",
    )

    with st.expander("预处理模型", expanded=False):
        st.caption("这些模型会增加耗时；普通横排印刷文本默认关闭。")
        paddle_ocr_use_doc_orientation_classify = st.checkbox(
            "文档方向分类",
            value=bool(st.session_state.get("paddle_ocr_use_doc_orientation_classify", False)),
            key="paddle_ocr_use_doc_orientation_classify",
        )
        paddle_ocr_use_doc_unwarping = st.checkbox(
            "文档去弯曲",
            value=bool(st.session_state.get("paddle_ocr_use_doc_unwarping", False)),
            key="paddle_ocr_use_doc_unwarping",
        )
        paddle_ocr_use_textline_orientation = st.checkbox(
            "文本行方向分类",
            value=bool(st.session_state.get("paddle_ocr_use_textline_orientation", False)),
            key="paddle_ocr_use_textline_orientation",
        )

    return {
        "paddle_ocr_python": paddle_ocr_python.strip() or None,
        "paddle_ocr_lang": paddle_ocr_lang.strip() or "ch",
        "paddle_ocr_version": paddle_ocr_version.strip() or "PP-OCRv5",
        "paddle_ocr_device": paddle_ocr_device,
        "paddle_ocr_engine": paddle_ocr_engine or None,
        "paddle_ocr_enable_mkldnn": bool(paddle_ocr_enable_mkldnn),
        "paddle_ocr_cpu_threads": int(paddle_ocr_cpu_threads) if int(paddle_ocr_cpu_threads) > 0 else None,
        "paddle_ocr_use_doc_orientation_classify": bool(paddle_ocr_use_doc_orientation_classify),
        "paddle_ocr_use_doc_unwarping": bool(paddle_ocr_use_doc_unwarping),
        "paddle_ocr_use_textline_orientation": bool(paddle_ocr_use_textline_orientation),
        "force_ocr": True,
        "use_llm": False,
        "ocr_batch_size": 32,
    }
