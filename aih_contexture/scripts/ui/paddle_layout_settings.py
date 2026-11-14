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


def render_paddle_layout_settings(
    st,
    *,
    description: str,
    default_model_name: str = "PP-DocLayout_plus-L",
) -> dict:
    st.info(description)

    v3_engine = None
    if default_model_name == "PP-DocLayoutV3":
        engines = ["onnxruntime", "paddle_static", "paddle_dynamic", "paddle"]
        current = st.session_state.get("paddle_layout_engine")
        if not current:
            from aih_contexture.backends.layout.pp_doclayoutv3_onnx import native_v3_selected
            selected = {**dict(st.session_state), "layout_backend": "paddle_pp_doclayout_v3", "paddle_layout_model_name": "PP-DocLayoutV3"}
            current = "onnxruntime" if native_v3_selected(selected) else "paddle_static"
        v3_engine = st.selectbox(
            "运行方式", engines,
            index=engines.index(current) if current in engines else 0,
            format_func=lambda value: "内置 ONNX Runtime（CPU）" if value == "onnxruntime" else f"Paddle SDK 兼容路径（{value}）",
            key="paddle_layout_engine",
        )
        if v3_engine == "onnxruntime":
            return _render_native_v3(st)
    elif st.session_state.get("paddle_layout_engine") == "onnxruntime":
        st.caption("内置 ONNX 路径当前用于 PP-DocLayoutV3；Plus-L 使用 Paddle SDK 兼容路径。")
        st.session_state["paddle_layout_engine"] = ""

    paddle_layout_python = st.text_input(
        "Paddle 外部 Python",
        value=st.session_state.get("paddle_layout_python", default_paddle_python() or ""),
        help=f"指向独立 Paddle/GPU 虚拟环境的 Python 可执行文件；也可用 {PADDLE_PYTHON_ENV} 指定。",
        key="paddle_layout_python",
    )
    paddle_layout_model_name = st.text_input(
        "LayoutDetection 模型名称",
        value=st.session_state.get("paddle_layout_model_name", default_model_name),
        help=f"默认使用 {default_model_name}。",
        key="paddle_layout_model_name",
    )
    paddle_layout_model_dir = st.text_input(
        "LayoutDetection 本地模型目录",
        value=st.session_state.get("paddle_layout_model_dir", ""),
        help="指定后从本地目录加载模型；留空使用 PaddleOCR 默认缓存。",
        key="paddle_layout_model_dir",
    )
    paddle_layout_device = _render_device_selector(
        st,
        key="paddle_layout_device",
        label="运行设备",
        help="留空时使用 PaddleOCR 默认策略；GPU 需外部环境安装 paddlepaddle-gpu。",
    )
    paddle_layout_engine = v3_engine or st.selectbox(
        "推理引擎",
        options=_ENGINE_OPTIONS,
        index=_ENGINE_OPTIONS.index(
            st.session_state.get("paddle_layout_engine", "")
            if st.session_state.get("paddle_layout_engine", "") in _ENGINE_OPTIONS
            else ""
        ),
        format_func=lambda value: _ENGINE_LABELS.get(value, value),
        help="通常留空；排查 Paddle 推理兼容性时再切换。",
        key="paddle_layout_engine",
    )
    paddle_layout_enable_mkldnn = st.checkbox(
        "启用 MKL-DNN",
        value=bool(st.session_state.get("paddle_layout_enable_mkldnn", False)),
        help="仅 CPU 推理相关；Windows 下默认关闭以减少兼容问题。",
        key="paddle_layout_enable_mkldnn",
    )
    paddle_layout_cpu_threads = st.number_input(
        "CPU 线程数",
        min_value=0,
        max_value=64,
        value=int(st.session_state.get("paddle_layout_cpu_threads", 0)),
        step=1,
        help="0 表示不显式覆盖 PaddleOCR 默认线程数。",
        key="paddle_layout_cpu_threads",
    )
    paddle_layout_threshold = st.number_input(
        "置信度阈值",
        min_value=0.0,
        max_value=1.0,
        value=float(st.session_state.get("paddle_layout_threshold", 0.0)),
        step=0.05,
        help="0 表示不显式覆盖 PaddleOCR 默认阈值。",
        key="paddle_layout_threshold",
    )
    paddle_layout_img_size = st.number_input(
        "输入图像尺寸",
        min_value=0,
        max_value=4096,
        value=int(st.session_state.get("paddle_layout_img_size", 0)),
        step=32,
        help="0 表示不显式覆盖 PaddleOCR 默认尺寸。",
        key="paddle_layout_img_size",
    )
    paddle_layout_batch_size = st.number_input(
        "Paddle 推理批次",
        min_value=0,
        max_value=512,
        value=int(st.session_state.get("paddle_layout_batch_size", 0)),
        step=1,
        help="0 表示使用 PaddleOCR 默认批次。GPU 利用率低时可逐步尝试 8/16/32；显存不足则调低。",
        key="paddle_layout_batch_size",
    )

    return {
        "paddle_layout_python": paddle_layout_python.strip() or None,
        "paddle_layout_model_name": paddle_layout_model_name.strip() or default_model_name,
        "paddle_layout_model_dir": paddle_layout_model_dir.strip() or None,
        "paddle_layout_device": paddle_layout_device,
        "paddle_layout_engine": paddle_layout_engine or None,
        "paddle_layout_enable_mkldnn": bool(paddle_layout_enable_mkldnn),
        "paddle_layout_cpu_threads": int(paddle_layout_cpu_threads) if int(paddle_layout_cpu_threads) > 0 else None,
        "paddle_layout_threshold": paddle_layout_threshold if paddle_layout_threshold > 0 else None,
        "paddle_layout_img_size": int(paddle_layout_img_size) if int(paddle_layout_img_size) > 0 else None,
        "paddle_layout_batch_size": int(paddle_layout_batch_size) if int(paddle_layout_batch_size) > 0 else None,
    }


def _render_native_v3(st) -> dict:
    st.caption("推理与后处理已内置，使用当前环境的 CPU ONNX Runtime；无需 Paddle/PaddleX 或独立 Python。模型保留阅读顺序和原生多边形，权重默认不下载。")
    model_dir = st.text_input(
        "PP-DocLayoutV3 ONNX 模型目录（可选）",
        value=st.session_state.get("paddle_layout_model_dir", ""),
        help="目录需包含 inference.onnx 与 inference.yml。留空使用 Contexture 的共享托管目录。",
        key="paddle_layout_model_dir",
    )
    allow_download = st.checkbox(
        "允许下载缺失的版面模型权重",
        value=bool(st.session_state.get("paddle_layout_allow_download", False)),
        key="paddle_layout_allow_download",
    )
    threads = st.number_input(
        "CPU 线程数", min_value=0, max_value=64,
        value=int(st.session_state.get("paddle_layout_cpu_threads", 0) or 0),
        help="0 表示自动使用最多 4 个线程。", key="paddle_layout_cpu_threads",
    )
    threshold = st.number_input(
        "置信度阈值", min_value=0.0, max_value=1.0,
        value=float(st.session_state.get("paddle_layout_threshold", 0.0) or 0.0),
        step=0.05, help="0 表示使用模型默认阈值 0.5。", key="paddle_layout_threshold",
    )
    current_batch = int(st.session_state.get("paddle_layout_batch_size", 1) or 1)
    if not 1 <= current_batch <= 8:
        st.warning("原批次设置超出内置 CPU 路径支持的 1–8，已重设为 1；可在下方重新选择。")
        st.session_state["paddle_layout_batch_size"] = 1
        current_batch = 1
    batch = st.number_input(
        "版面推理批次", min_value=1, max_value=8, value=current_batch,
        help="默认 1；增加批次会增加内存占用。", key="paddle_layout_batch_size",
    )
    return {
        "paddle_layout_python": None,
        "paddle_layout_model_name": "PP-DocLayoutV3",
        "paddle_layout_model_dir": model_dir.strip() or None,
        "paddle_layout_device": "cpu", "paddle_layout_engine": "onnxruntime",
        "paddle_layout_allow_download": bool(allow_download),
        "paddle_layout_enable_mkldnn": False,
        "paddle_layout_cpu_threads": int(threads) or None,
        "paddle_layout_threshold": float(threshold) if threshold > 0 else None,
        "paddle_layout_img_size": None,
        "paddle_layout_batch_size": int(batch),
    }
