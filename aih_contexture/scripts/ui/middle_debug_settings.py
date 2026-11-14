from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass


@dataclass(slots=True)
class MiddleArtifactSettings:
    emit_middle_json: bool
    emit_middle_report: bool
    emit_middle_debug: bool
    emit_middle_scholarly: bool
    emit_middle_scholarly_report: bool
    emit_layout_overlay: bool
    emit_span_overlay: bool
    emit_middle_full_json: bool


def _key(prefix: str, name: str) -> str:
    return f"{prefix}_{name}" if prefix else name


def _advanced_format_container(st, label: str):
    expander = getattr(st, "expander", None)
    if callable(expander):
        return expander(label, expanded=False)
    return nullcontext()


def render_middle_debug_settings(st, *, key_prefix: str = "pipeline", force_enabled: bool = False) -> bool:
    # Keep the argument for existing callers; the core artifact is always required.
    key = _key(key_prefix, "emit_middle_json")
    if getattr(st, "session_state", None) is not None:
        st.session_state[key] = True
    st.checkbox(
        "Middle JSON 核心文件（必需）",
        disabled=True,
        help="成功转换始终保存 *_middle.json，供复查与重新渲染。下方报告、调试文件和附加的阅读 Markdown 可按需开启。",
        key=key,
    )
    return True


def render_middle_report_settings(st, *, key_prefix: str = "pipeline") -> bool:
    return st.checkbox(
        "导出 Middle 校验报告",
        value=False,
        help="生成 *_middle_report.json，用于检查 Middle JSON 的结构、缺失字段与数据异常。",
        key=_key(key_prefix, "emit_middle_report"),
    )


def render_middle_debug_markdown_settings(st, *, key_prefix: str = "pipeline") -> bool:
    return st.checkbox(
        "导出 Middle 调试 Markdown",
        value=False,
        help="生成 *_middle_debug.md，用于快速查看 Middle JSON 的页面级展开结果。",
        key=_key(key_prefix, "emit_middle_debug"),
    )


def render_middle_scholarly_settings(st, *, key_prefix: str = "pipeline") -> bool:
    return st.checkbox(
        "导出附加阅读 Markdown（Scholarly Markdown）",
        value=False,
        help="生成 *_middle_scholarly.md，用于按学术重排规则重新渲染 Middle JSON。",
        key=_key(key_prefix, "emit_middle_scholarly"),
    )


def render_middle_scholarly_report_settings(st, *, key_prefix: str = "pipeline") -> bool:
    return st.checkbox(
        "导出阅读 Markdown 校验报告",
        value=False,
        help="生成 *_middle_scholarly_report.json，用于检查阅读 Markdown 的结构与格式，不评定 OCR 识别准确率。",
        key=_key(key_prefix, "emit_middle_scholarly_report"),
    )


def render_layout_overlay_debug_settings(st, *, key_prefix: str = "pipeline") -> bool:
    return st.checkbox(
        "导出版面叠图（Overlay）",
        value=False,
        help="生成 *_layout_overlay/ 和 *_layout_overlay.pdf，用于检查 Middle JSON 中的 bbox、顺序、标签和置信度。",
        key=_key(key_prefix, "emit_layout_overlay"),
    )


def render_span_overlay_debug_settings(st, *, key_prefix: str = "pipeline") -> bool:
    return st.checkbox(
        "导出文字跨度叠图（Span Overlay）",
        value=False,
        help="生成 *_span_overlay/ 和 *_span_overlay.pdf，用于检查 Middle JSON 中的 span bbox、文本和 OCR 来源。",
        key=_key(key_prefix, "emit_span_overlay"),
    )


def render_middle_full_json_settings(st, *, key_prefix: str = "pipeline") -> bool:
    return st.checkbox(
        "保存完整 Middle JSON（含 spans）",
        value=False,
        help="生成 *_middle_full.json，保留 span 级 bbox、字体和来源信息；仅建议在排查逐字坐标或 OCR 细节时开启。",
        key=_key(key_prefix, "emit_middle_full_json"),
    )


def render_middle_artifact_settings(
    st,
    *,
    key_prefix: str = "pipeline",
    overlays: bool = True,
    force_middle_json: bool = False,
) -> MiddleArtifactSettings:
    emit_middle_json = render_middle_debug_settings(
        st,
        key_prefix=key_prefix,
        force_enabled=force_middle_json,
    )
    emit_layout_overlay = False
    emit_span_overlay = False
    with _advanced_format_container(st, "高级格式（报告、调试与叠图）"):
        emit_middle_report = render_middle_report_settings(st, key_prefix=key_prefix)
        emit_middle_debug = render_middle_debug_markdown_settings(st, key_prefix=key_prefix)
        emit_middle_scholarly = render_middle_scholarly_settings(st, key_prefix=key_prefix)
        emit_middle_scholarly_report = render_middle_scholarly_report_settings(st, key_prefix=key_prefix)
        emit_middle_full_json = render_middle_full_json_settings(st, key_prefix=key_prefix)
        if overlays:
            emit_layout_overlay = render_layout_overlay_debug_settings(st, key_prefix=key_prefix)
            emit_span_overlay = render_span_overlay_debug_settings(st, key_prefix=key_prefix)
            if emit_layout_overlay or emit_span_overlay:
                emit_middle_json = True
        if emit_middle_full_json:
            emit_middle_json = True
    return MiddleArtifactSettings(
        emit_middle_json=emit_middle_json,
        emit_middle_report=emit_middle_report,
        emit_middle_debug=emit_middle_debug,
        emit_middle_scholarly=emit_middle_scholarly,
        emit_middle_scholarly_report=emit_middle_scholarly_report,
        emit_layout_overlay=emit_layout_overlay,
        emit_span_overlay=emit_span_overlay,
        emit_middle_full_json=emit_middle_full_json,
    )
