from __future__ import annotations

from aih_contexture.backends.external_config import (
    DEFAULT_MINERU_LAYOUT_BATCH_SIZE,
    default_mineru_command,
    default_mineru_layout_model_dir,
    default_mineru_layout_python,
    default_mineru_python,
)


def render_mineru_layout_settings(st, *, description: str) -> dict:
    del description
    st.caption("此选项运行 MinerU 完整解析，可能执行文字、表格和公式识别。")

    mineru_backend = "pipeline"
    mineru_api_url = None
    mineru_server_url = None
    mineru_extra_args = None
    with st.expander("高级：模型与运行环境", expanded=False):
        mineru_command = st.text_input(
            "MinerU 命令",
            value=st.session_state.get("mineru_command", default_mineru_command()),
            key="mineru_command",
        )
        mineru_method = st.selectbox(
            "文字识别方式",
            options=["txt", "ocr", "auto"],
            index=0,
            format_func=lambda value: {
                "txt": "优先使用 PDF 文字",
                "ocr": "执行 OCR",
                "auto": "自动选择",
            }[value],
            key="mineru_method",
        )
        mineru_lang = st.text_input(
            "识别语言",
            value=st.session_state.get("mineru_lang", "ch"),
            key="mineru_lang",
        )
        mineru_output_dir = st.text_input(
            "临时结果目录",
            value=st.session_state.get("mineru_output_dir", ""),
            key="mineru_output_dir",
        )
        mineru_timeout = st.number_input(
            "超时秒数",
            min_value=60,
            max_value=86400,
            value=int(st.session_state.get("mineru_timeout", 3600)),
            step=60,
            key="mineru_timeout",
        )

        st.caption("以下选项用于连接其他 MinerU 服务。")
        mineru_backend = st.selectbox(
            "运行方式",
            options=["pipeline", "hybrid-auto-engine", "hybrid-http-client", "vlm-auto-engine", "vlm-http-client"],
            index=0,
            format_func=lambda value: {
                "pipeline": "默认",
                "hybrid-auto-engine": "混合模式",
                "hybrid-http-client": "混合服务",
                "vlm-auto-engine": "视觉模型模式",
                "vlm-http-client": "视觉模型服务",
            }[value],
            key="mineru_backend",
        )
        mineru_api_url_value = st.text_input(
            "MinerU 服务地址",
            value=st.session_state.get("mineru_api_url", ""),
            key="mineru_api_url",
        )
        mineru_server_url_value = st.text_input(
            "视觉模型服务地址",
            value=st.session_state.get("mineru_server_url", ""),
            key="mineru_server_url",
        )
        mineru_extra_args_value = st.text_input(
            "其他参数",
            value=st.session_state.get("mineru_extra_args", ""),
            key="mineru_extra_args",
        )
        mineru_api_url = mineru_api_url_value.strip() or None
        mineru_server_url = mineru_server_url_value.strip() or None
        mineru_extra_args = mineru_extra_args_value.strip() or None

    return {
        "mineru_command": mineru_command.strip() or "mineru",
        "mineru_backend": mineru_backend,
        "mineru_method": mineru_method,
        "mineru_lang": mineru_lang.strip() or "ch",
        "mineru_output_dir": mineru_output_dir.strip() or None,
        "mineru_api_url": mineru_api_url,
        "mineru_server_url": mineru_server_url,
        "mineru_timeout": int(mineru_timeout),
        "mineru_extra_args": mineru_extra_args,
    }


def render_mineru_direct_layout_settings(st, *, description: str) -> dict:
    del description

    with st.expander("高级：模型与运行环境", expanded=False):
        resolved_python = default_mineru_layout_python()
        st.caption(f"当前 Python：{resolved_python}" if resolved_python else "当前未检测到 Python 环境。")
        mineru_layout_python = st.text_input(
            "Python 路径",
            value=st.session_state.get("mineru_layout_python", ""),
            help="留空使用当前环境。",
            key="mineru_layout_python",
        )
        _DEVICE_OPTIONS = ["auto", "cuda", "cuda:0", "cpu", "custom"]
        _DEVICE_LABELS = {
            "auto": "自动",
            "cuda": "默认 GPU",
            "cuda:0": "GPU 0",
            "cpu": "CPU",
            "custom": "手动指定",
        }
        current_device = str(st.session_state.get("mineru_layout_device", "") or "").strip()
        selected_device = current_device if current_device in _DEVICE_OPTIONS[:-1] else "custom" if current_device else "auto"
        mineru_layout_device = st.selectbox(
            "运行设备",
            options=_DEVICE_OPTIONS,
            index=_DEVICE_OPTIONS.index(selected_device),
            format_func=lambda value: _DEVICE_LABELS.get(value, value),
            help="自动使用当前环境可用的设备。",
            key="mineru_layout_device_select",
        )
        if mineru_layout_device == "custom":
            custom_device = st.text_input(
                "设备名称",
                value=current_device if current_device not in _DEVICE_OPTIONS else "",
                key="mineru_layout_device",
            )
            resolved_device = custom_device.strip() or None
        else:
            resolved_device = None if mineru_layout_device == "auto" else mineru_layout_device
            st.session_state["mineru_layout_device"] = resolved_device or ""
        mineru_layout_model_dir = st.text_input(
            "模型目录",
            value=st.session_state.get("mineru_layout_model_dir", default_mineru_layout_model_dir() or ""),
            help="留空时自动查找模型目录。",
            key="mineru_layout_model_dir",
        )
        mineru_layout_timeout = st.number_input(
            "超时秒数",
            min_value=60,
            max_value=86400,
            value=int(st.session_state.get("mineru_layout_timeout", 3600)),
            step=60,
            key="mineru_layout_timeout",
        )
    mineru_layout_batch_size = st.number_input(
        "模型推理批次",
        min_value=1,
        max_value=64,
        value=int(st.session_state.get("mineru_layout_batch_size", DEFAULT_MINERU_LAYOUT_BATCH_SIZE)),
        step=1,
        help="增加批次可能提高处理速度，也会增加内存占用。",
        key="mineru_layout_batch_size",
    )
    use_filter = st.checkbox(
        "过滤重叠和较小区域",
        value=bool(st.session_state.get("mineru_layout_use_paddlex_filter_boxes", False)),
        key="mineru_layout_use_paddlex_filter_boxes",
    )

    return {
        "mineru_layout_python": mineru_layout_python.strip() or None,
        "mineru_layout_device": resolved_device,
        "mineru_layout_model_dir": mineru_layout_model_dir.strip() or None,
        "mineru_layout_batch_size": int(mineru_layout_batch_size),
        "mineru_layout_timeout": int(mineru_layout_timeout),
        "mineru_layout_use_paddlex_filter_boxes": bool(use_filter),
    }


def render_mineru_ocr_settings(st, *, description: str) -> dict:
    del description
    mineru_ocr_lang = st.text_input(
        "识别语言",
        value=st.session_state.get("mineru_ocr_lang", st.session_state.get("paddle_ocr_lang", "ch")),
        help="例如中文 ch、英语 en。",
        key="mineru_ocr_lang",
    )
    with st.expander("高级：模型与运行环境", expanded=False):
        mineru_ocr_python = st.text_input(
            "Python 路径",
            value=st.session_state.get("mineru_ocr_python", default_mineru_python() or ""),
            help="留空使用当前环境。",
            key="mineru_ocr_python",
        )
        versions = ["PP-OCRv5", "PP-OCRv6"]
        current_version = st.session_state.get("mineru_ocr_version", "PP-OCRv5")
        mineru_ocr_version = st.selectbox(
            "识别模型版本", options=versions,
            index=versions.index(current_version) if current_version in versions else 0,
            key="mineru_ocr_version",
        )
        mineru_ocr_model_dir = st.text_input(
            "模型目录",
            value=st.session_state.get("mineru_ocr_model_dir", ""),
            help="留空时自动查找模型目录。",
            key="mineru_ocr_model_dir",
        )
        mineru_ocr_allow_download = st.checkbox(
            "允许下载缺失模型",
            value=bool(st.session_state.get("mineru_ocr_allow_download", False)),
            key="mineru_ocr_allow_download",
        )
        _DEVICE_OPTIONS = ["auto", "cuda", "cuda:0", "cpu", "custom"]
        _DEVICE_LABELS = {
            "auto": "自动",
            "cuda": "默认 GPU",
            "cuda:0": "GPU 0",
            "cpu": "CPU",
            "custom": "手动指定",
        }
        current_device = str(st.session_state.get("mineru_ocr_device", "") or "").strip()
        selected_device = current_device if current_device in _DEVICE_OPTIONS[:-1] else "custom" if current_device else "auto"
        mineru_ocr_device = st.selectbox(
            "运行设备",
            options=_DEVICE_OPTIONS,
            index=_DEVICE_OPTIONS.index(selected_device),
            format_func=lambda value: _DEVICE_LABELS.get(value, value),
            help="自动使用当前环境可用的设备。",
            key="mineru_ocr_device_select",
        )
        if mineru_ocr_device == "custom":
            custom_device = st.text_input(
                "设备名称",
                value=current_device if current_device not in _DEVICE_OPTIONS else "",
                key="mineru_ocr_device",
            )
            resolved_device = custom_device.strip() or None
        else:
            resolved_device = None if mineru_ocr_device == "auto" else mineru_ocr_device
            st.session_state["mineru_ocr_device"] = resolved_device or ""
        mineru_ocr_timeout = st.number_input(
            "超时秒数",
            min_value=60,
            max_value=86400,
            value=int(st.session_state.get("mineru_ocr_timeout", st.session_state.get("mineru_timeout", 3600))),
            step=60,
            key="mineru_ocr_timeout",
        )
        det_db_box_thresh = st.number_input(
            "检测框阈值",
            min_value=0.0,
            max_value=1.0,
            value=float(st.session_state.get("mineru_ocr_det_db_box_thresh", 0.3)),
            step=0.05,
            key="mineru_ocr_det_db_box_thresh",
        )
        det_db_unclip_ratio = st.number_input(
            "检测框扩张系数",
            min_value=1.0,
            max_value=5.0,
            value=float(st.session_state.get("mineru_ocr_det_db_unclip_ratio", 1.8)),
            step=0.1,
            key="mineru_ocr_det_db_unclip_ratio",
        )
        enable_merge_det_boxes = st.checkbox(
            "合并相邻检测框",
            value=bool(st.session_state.get("mineru_ocr_enable_merge_det_boxes", True)),
            key="mineru_ocr_enable_merge_det_boxes",
        )

    return {
        "mineru_ocr_python": mineru_ocr_python.strip() or None,
        "mineru_ocr_model_dir": mineru_ocr_model_dir.strip() or None,
        "mineru_ocr_version": mineru_ocr_version,
        "mineru_ocr_allow_download": bool(mineru_ocr_allow_download),
        "mineru_ocr_device": resolved_device,
        "mineru_ocr_lang": mineru_ocr_lang.strip() or "ch",
        "mineru_ocr_timeout": int(mineru_ocr_timeout),
        "mineru_ocr_det_db_box_thresh": float(det_db_box_thresh),
        "mineru_ocr_det_db_unclip_ratio": float(det_db_unclip_ratio),
        "mineru_ocr_enable_merge_det_boxes": bool(enable_merge_det_boxes),
        "force_ocr": True,
        "use_llm": False,
        "ocr_batch_size": 1,
    }
