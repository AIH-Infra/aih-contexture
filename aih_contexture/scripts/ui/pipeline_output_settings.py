from __future__ import annotations

from aih_contexture.scripts.ui.middle_debug_settings import (
    render_middle_artifact_settings,
)

PIPELINE_OUTPUT_FORMATS = ["markdown", "json", "html", "chunks"]
PIPELINE_DEFAULT_OUTPUT_FORMATS = ["markdown", "json", "html"]
PIPELINE_LEGACY_DEFAULT_OUTPUT_FORMATS = [["markdown"]]


def default_pipeline_output_formats() -> list[str]:
    return list(PIPELINE_DEFAULT_OUTPUT_FORMATS)


def render_pipeline_output_settings(st, *, force_middle_json: bool = False):
    st.markdown("**📄 输出格式**")
    session_state = getattr(st, "session_state", None)
    if session_state is not None and list(session_state.get("pipeline_output_formats", [])) in PIPELINE_LEGACY_DEFAULT_OUTPUT_FORMATS:
        session_state["pipeline_output_formats"] = list(PIPELINE_DEFAULT_OUTPUT_FORMATS)
    output_formats = st.multiselect(
        "选择输出格式",
        PIPELINE_OUTPUT_FORMATS,
        default=PIPELINE_DEFAULT_OUTPUT_FORMATS,
        help="选择需要生成的正式输出格式（默认输出 markdown/json/html；chunks 可按需开启）",
        key="pipeline_output_formats",
    )
    middle_settings = render_middle_artifact_settings(
        st,
        key_prefix="pipeline",
        force_middle_json=force_middle_json,
    )
    return output_formats, middle_settings
