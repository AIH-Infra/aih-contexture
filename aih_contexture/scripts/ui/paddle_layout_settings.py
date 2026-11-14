from __future__ import annotations

from aih_contexture.backends.external_config import default_paddle_python


_DEVICE_OPTIONS = ["", "cpu", "gpu", "gpu:0", "gpu:1", "custom"]
_DEVICE_LABELS = {
    "": "自动",
    "cpu": "CPU",
    "gpu": "GPU",
    "gpu:0": "GPU 0",
    "gpu:1": "GPU 1",
    "custom": "手动指定",
}

_ENGINE_OPTIONS = ["", "paddle", "paddle_static", "paddle_dynamic"]
_ENGINE_LABELS = {
    "": "自动",
    "paddle": "Paddle",
    "paddle_static": "静态模式",
    "paddle_dynamic": "动态模式",
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
            "设备名称",
            value=current if current not in _DEVICE_OPTIONS else "",
            help="例如 gpu:2。",
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
    del description

    is_v3 = default_model_name == "PP-DocLayoutV3"
    v3_engine = None
    paddle_layout_python = None
    paddle_layout_model_name = default_model_name
    paddle_layout_model_dir = st.session_state.get("paddle_layout_model_dir", "")
    paddle_layout_device = None
    paddle_layout_enable_mkldnn = False
    paddle_layout_threshold = None
    paddle_layout_img_size = None
    paddle_layout_allow_download = False

    if not is_v3 and st.session_state.get("paddle_layout_engine") == "onnxruntime":
        st.session_state["paddle_layout_engine"] = ""

    with st.expander("高级：模型与运行环境", expanded=False):
        if is_v3:
            engines = ["onnxruntime", "paddle_static", "paddle_dynamic", "paddle"]
            current = st.session_state.get("paddle_layout_engine")
            if not current:
                from aih_contexture.backends.layout.pp_doclayoutv3_onnx import native_v3_selected

                selected = {
                    **dict(st.session_state),
                    "layout_backend": "paddle_pp_doclayout_v3",
                    "paddle_layout_model_name": "PP-DocLayoutV3",
                }
                current = "onnxruntime" if native_v3_selected(selected) else "paddle_static"
            v3_engine = st.selectbox(
                "运行方式",
                engines,
                index=engines.index(current) if current in engines else 0,
                format_func=lambda value: {
                    "onnxruntime": "内置运行方式",
                    "paddle_static": "Paddle 静态模式",
                    "paddle_dynamic": "Paddle 动态模式",
                    "paddle": "Paddle",
                }[value],
                key="paddle_layout_engine",
            )

        if not is_v3 or v3_engine != "onnxruntime":
            paddle_layout_python = st.text_input(
                "Python 路径",
                value=st.session_state.get("paddle_layout_python", default_paddle_python() or ""),
                help="留空使用当前配置的环境。",
                key="paddle_layout_python",
            )
            paddle_layout_model_name = st.text_input(
                "模型名称",
                value=st.session_state.get("paddle_layout_model_name", default_model_name),
                key="paddle_layout_model_name",
            )
            paddle_layout_model_dir = st.text_input(
                "模型目录",
                value=st.session_state.get("paddle_layout_model_dir", ""),
                help="留空时自动查找模型目录。",
                key="paddle_layout_model_dir",
            )
            paddle_layout_device = _render_device_selector(
                st,
                key="paddle_layout_device",
                label="运行设备",
                help="自动使用当前环境可用的设备。",
            )
            if not is_v3:
                paddle_layout_engine = st.selectbox(
                    "运行方式",
                    options=_ENGINE_OPTIONS,
                    index=_ENGINE_OPTIONS.index(
                        st.session_state.get("paddle_layout_engine", "")
                        if st.session_state.get("paddle_layout_engine", "") in _ENGINE_OPTIONS
                        else ""
                    ),
                    format_func=lambda value: _ENGINE_LABELS.get(value, value),
                    key="paddle_layout_engine",
                )
            else:
                paddle_layout_engine = v3_engine

            paddle_layout_enable_mkldnn = st.checkbox(
                "启用 MKL-DNN",
                value=bool(st.session_state.get("paddle_layout_enable_mkldnn", False)),
                key="paddle_layout_enable_mkldnn",
            )
            paddle_layout_threshold_value = st.number_input(
                "置信度阈值",
                min_value=0.0,
                max_value=1.0,
                value=float(st.session_state.get("paddle_layout_threshold", 0.0) or 0.0),
                step=0.05,
                key="paddle_layout_threshold",
            )
            paddle_layout_threshold = paddle_layout_threshold_value if paddle_layout_threshold_value > 0 else None
            paddle_layout_img_size_value = st.number_input(
                "输入图像尺寸",
                min_value=0,
                max_value=4096,
                value=int(st.session_state.get("paddle_layout_img_size", 0) or 0),
                step=32,
                key="paddle_layout_img_size",
            )
            paddle_layout_img_size = int(paddle_layout_img_size_value) if paddle_layout_img_size_value > 0 else None
        else:
            paddle_layout_model_dir = st.text_input(
                "模型目录",
                value=st.session_state.get("paddle_layout_model_dir", ""),
                help="留空时自动查找模型目录。",
                key="paddle_layout_model_dir",
            )
            paddle_layout_allow_download = st.checkbox(
                "允许下载缺失模型",
                value=bool(st.session_state.get("paddle_layout_allow_download", False)),
                key="paddle_layout_allow_download",
            )

    if is_v3 and v3_engine == "onnxruntime":
        return _render_native_v3(
            st,
            model_dir=paddle_layout_model_dir,
            allow_download=paddle_layout_allow_download,
        )

    paddle_layout_cpu_threads = st.number_input(
        "CPU 线程数",
        min_value=0,
        max_value=64,
        value=int(st.session_state.get("paddle_layout_cpu_threads", 0) or 0),
        step=1,
        help="0 表示自动。",
        key="paddle_layout_cpu_threads",
    )
    paddle_layout_batch_size = st.number_input(
        "版面分析批次",
        min_value=0,
        max_value=512,
        value=int(st.session_state.get("paddle_layout_batch_size", 0) or 0),
        step=1,
        help="0 表示使用默认批次；增加批次可能提高速度，也会增加内存占用。",
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
        "paddle_layout_threshold": paddle_layout_threshold,
        "paddle_layout_img_size": paddle_layout_img_size,
        "paddle_layout_batch_size": int(paddle_layout_batch_size) if int(paddle_layout_batch_size) > 0 else None,
    }


def _render_native_v3(st, *, model_dir: str, allow_download: bool) -> dict:
    threads = st.number_input(
        "CPU 线程数",
        min_value=0,
        max_value=64,
        value=int(st.session_state.get("paddle_layout_cpu_threads", 0) or 0),
        help="0 表示自动。",
        key="paddle_layout_cpu_threads",
    )
    threshold = st.number_input(
        "置信度阈值",
        min_value=0.0,
        max_value=1.0,
        value=float(st.session_state.get("paddle_layout_threshold", 0.0) or 0.0),
        step=0.05,
        help="0 表示使用默认值。",
        key="paddle_layout_threshold",
    )
    current_batch = int(st.session_state.get("paddle_layout_batch_size", 1) or 1)
    if not 1 <= current_batch <= 8:
        st.warning("批次设置已超出当前支持范围，已重设为 1。")
        st.session_state["paddle_layout_batch_size"] = 1
        current_batch = 1
    batch = st.number_input(
        "版面分析批次",
        min_value=1,
        max_value=8,
        value=current_batch,
        help="增加批次会增加内存占用。",
        key="paddle_layout_batch_size",
    )
    return {
        "paddle_layout_python": None,
        "paddle_layout_model_name": "PP-DocLayoutV3",
        "paddle_layout_model_dir": model_dir.strip() or None,
        "paddle_layout_device": "cpu",
        "paddle_layout_engine": "onnxruntime",
        "paddle_layout_allow_download": bool(allow_download),
        "paddle_layout_enable_mkldnn": False,
        "paddle_layout_cpu_threads": int(threads) or None,
        "paddle_layout_threshold": float(threshold) if threshold > 0 else None,
        "paddle_layout_img_size": None,
        "paddle_layout_batch_size": int(batch),
    }
