from __future__ import annotations

from aih_contexture.scripts.ui.middle_debug_settings import (
    render_middle_artifact_settings,
)

PIPELINE_OUTPUT_FORMATS = ["markdown", "json", "html", "chunks"]
PIPELINE_DEFAULT_OUTPUT_FORMATS = ["markdown", "json", "html"]


def default_pipeline_output_formats() -> list[str]:
    return list(PIPELINE_DEFAULT_OUTPUT_FORMATS)


def render_pipeline_output_settings(st, *, force_middle_json: bool = False):
    st.markdown("**📄 输出格式**")
    session_state = st.session_state
    current_formats = session_state.get("pipeline_output_formats", PIPELINE_DEFAULT_OUTPUT_FORMATS)
    optional_formats = [name for name in PIPELINE_OUTPUT_FORMATS if name != "markdown"]
    if session_state.get("layout_backend") == "none":
        optional_formats = ["json", "html"]
        st.caption("文本层快速路径支持 Markdown、JSON 和 HTML。")
    elif session_state.get("layout_backend") == "indra_layout" and session_state.get("ocr_backend") == "indra_ocr":
        optional_formats = ["json"]
        st.caption("Indra 原生直连支持 Markdown 和 Middle 文档 JSON。")
    optional_key = "_pipeline_optional_output_formats"
    session_state[optional_key] = [name for name in optional_formats if name in current_formats]

    def save_output_formats():
        session_state["pipeline_output_formats"] = ["markdown", *session_state[optional_key]]

    st.checkbox("Markdown（必需）", value=True, disabled=True, key="_pipeline_markdown_required")
    selected = st.multiselect(
        "其他输出格式（可全部取消）",
        optional_formats,
        help="Markdown 始终生成；JSON、HTML、Chunks 按需选择。Indra 原生直连支持 Markdown 和 JSON，后者为 Middle 文档。",
        key=optional_key,
        on_change=save_output_formats,
    )
    output_formats = ["markdown", *selected]
    session_state["pipeline_output_formats"] = output_formats
    middle_settings = render_middle_artifact_settings(
        st,
        key_prefix="pipeline",
        force_middle_json=force_middle_json,
    )
    return output_formats, middle_settings
