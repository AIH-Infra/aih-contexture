"""Shared visible controls for classical marginalia in all UI entry points."""
from __future__ import annotations

from typing import Any
from aih_contexture.middle.semantics.classical_marginalia import (
    normalize_classical_marginalia_mode, normalize_classical_text_marginalia_mode,
)


def normalize_generic_line_output_mode(value: Any) -> str:
    mode = str(value or "").strip().lower().replace("-", "_")
    return mode if mode in ("drop", "page_comments") else "drop"


def render_classical_marginalia_controls(
    st: Any, *, mode_key: str, text_key: str, generic_line_key: str | None = None,
) -> tuple[str, ...]:
    # Streamlit removes state for widgets hidden by a mode switch. Keep their
    # choices independently so visiting another processing mode is reversible.
    state = getattr(st, "session_state", {})
    keys_to_normalize = [
        (mode_key, normalize_classical_marginalia_mode),
        (text_key, normalize_classical_text_marginalia_mode),
    ]
    if generic_line_key is not None:
        keys_to_normalize.append((generic_line_key, normalize_generic_line_output_mode))

    for key, normalize in keys_to_normalize:
        saved_key = f"_retained_{key}"
        state[key] = normalize(state.get(key, state.get(saved_key)))

    def _normalize_selection(key, normalize):
        state[key] = normalize(state.get(key))

    mode = st.selectbox(
        "古典边码输出", options=["off", "page_locators"], index=None,
        format_func=lambda value: {"off": "关闭（兼容旧输出）", "page_locators": "按物理页汇总定位边码"}.get(value, value),
        key=mode_key,
        on_change=_normalize_selection, args=(mode_key, normalize_classical_marginalia_mode),
        help="适用于带版面信息的书页；只调整阅读版 Markdown，保留原始识别数据。",
    )
    text_mode = st.selectbox(
        "古典文字边注", options=["separate", "drop"], index=None,
        format_func=lambda value: {"separate": "独立保留", "drop": "不输出已确认的文字边注"}.get(value, value),
        key=text_key, disabled=mode != "page_locators",
        on_change=_normalize_selection, args=(text_key, normalize_classical_text_marginalia_mode),
        help=(
            "开启古典边码后生效；独立边注位于本页正文之后、脚注之前，英文标签为 Left marginal note / Right marginal note，"
            "方位不明时沿用 Margin。坐标和来源 ID 保存在 JSON 中。隐藏仅影响阅读版中已确认的文字边注，"
            "未判定内容和手写待核仍保留。"
        ),
    )
    state[f"_retained_{mode_key}"] = mode
    state[f"_retained_{text_key}"] = text_mode

    generic_line_mode = None
    if generic_line_key is not None:
        generic_line_mode = render_generic_line_output_control(
            st, key=generic_line_key, classical_mode=mode,
        )

    if mode == "page_locators":
        st.info("古典模式已启用：文字边注由此处设置控制。缺少可靠版面坐标的输入会保留原输出并提示复核。")
        st.caption("此模式替代旧的边注输出方式；JSON、XML、HTML 等原生格式按各自流程保存。")
        st.caption(
            "定位说明：{n}为从0开始的输入物理页；Page为本版印刷页，已确认的[n]注释为旧版页。"
            "范围显示可见定位点；…表示有证据的延展，无…不保证闭区间。数字可能是行、章或节。"
        )

    if generic_line_key is not None:
        return mode, text_mode, generic_line_mode
    return mode, text_mode


def render_generic_line_output_control(
    st: Any, *, key: str, classical_mode: str,
) -> str:
    state = getattr(st, "session_state", {})
    saved_key = f"_retained_{key}"
    state[key] = normalize_generic_line_output_mode(state.get(key, state.get(saved_key, "drop")))

    def _normalize_selection():
        state[key] = normalize_generic_line_output_mode(state.get(key))

    is_classical_enabled = classical_mode == "page_locators"
    line_mode = st.selectbox(
        "通用行号输出",
        options=["drop", "page_comments"],
        index=None,
        format_func=lambda value: {"drop": "舍去（默认）", "page_comments": "页首注释保留"}.get(value, value),
        key=key,
        disabled=not is_classical_enabled,
        on_change=_normalize_selection,
        help="仅对已确认行号生效，正文数字不删；Bekker另行控制。古典边码输出关闭时此开关不生效。",
    )
    state[saved_key] = line_mode
    if not is_classical_enabled:
        st.caption("通用行号输出需开启古典边码输出后生效（当前处于关闭状态）。")
    return line_mode

