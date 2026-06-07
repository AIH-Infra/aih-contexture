from __future__ import annotations


def render_pipeline_page_margin_settings(
    st,
    *,
    extract_printed_pages: bool,
) -> dict[str, object]:
    printed_page_zones = ["footer", "header"]
    printed_page_header_end = 0.15
    printed_page_footer_start = 0.83

    with st.expander("📑 页眉页脚处理", expanded=False):
        st.caption("仅 Pipeline 模式生效。印刷页码总开关仍使用上方“页码锚点配置”。")

        output_col1, output_col2 = st.columns(2)
        with output_col1:
            emit_page_header_comment = st.checkbox(
                "输出页眉注释",
                value=st.session_state.get(
                    "emit_page_header_comment_pipeline",
                    st.session_state.get("emit_page_header_comment_global", False),
                ),
                help="将检测到的页眉输出为 `<!-- PageHeader: ... -->`，不依赖印刷页码提取。",
                key="emit_page_header_comment_pipeline",
            )
            keep_pageheader_in_output = st.checkbox(
                "直接输出页眉",
                value=st.session_state.get(
                    "keep_pageheader_in_output_pipeline",
                    st.session_state.get("keep_pageheader_in_output_global", False),
                ),
                help="将页眉作为可见内容直接输出到 HTML/Markdown，不只写入注释元数据。",
                key="keep_pageheader_in_output_pipeline",
            )
        with output_col2:
            emit_page_footer_comment = st.checkbox(
                "输出页脚注释",
                value=st.session_state.get(
                    "emit_page_footer_comment_pipeline",
                    st.session_state.get("emit_page_footer_comment_global", False),
                ),
                help="将检测到的页脚输出为 `<!-- PageFooter: ... -->`。若内容仅为页码，Markdown 会与 `<!-- Page: X -->` 自动去重。",
                key="emit_page_footer_comment_pipeline",
            )
            keep_pagefooter_in_output = st.checkbox(
                "直接输出页脚",
                value=st.session_state.get(
                    "keep_pagefooter_in_output_pipeline",
                    st.session_state.get("keep_pagefooter_in_output_global", False),
                ),
                help="将页脚作为可见内容直接输出到 HTML/Markdown，不只写入注释元数据。",
                key="keep_pagefooter_in_output_pipeline",
            )

        if (
            extract_printed_pages
            or emit_page_header_comment
            or emit_page_footer_comment
            or keep_pageheader_in_output
            or keep_pagefooter_in_output
        ):
            st.markdown("---")
            st.caption("这里仅控制 Pipeline 如何采集和输出页眉页脚内容；页码格式、自定义页码正则和自定义编号由上方“页码锚点配置”管理。")
            col1, col2 = st.columns(2)
            with col1:
                printed_page_zones = st.multiselect(
                    "页边采集区域",
                    options=["header", "footer"],
                    default=st.session_state.get("printed_page_zones_pipeline", ["footer", "header"]),
                    help="设置页眉/页脚文本与页码候选的采集区域。",
                    key="printed_page_zones_pipeline",
                )
            with col2:
                printed_page_header_end = st.slider(
                    "页眉区域",
                    0.0,
                    0.3,
                    float(st.session_state.get("printed_page_header_end_pipeline", 0.15)),
                    0.01,
                    help="页面顶部多少比例作为页眉区域。",
                    key="printed_page_header_end_pipeline",
                )
                printed_page_footer_start = st.slider(
                    "页脚区域",
                    0.7,
                    1.0,
                    float(st.session_state.get("printed_page_footer_start_pipeline", 0.83)),
                    0.01,
                    help="页面底部多少比例作为页脚区域。",
                    key="printed_page_footer_start_pipeline",
                )

    return {
        "emit_page_header_comment": emit_page_header_comment,
        "emit_page_footer_comment": emit_page_footer_comment,
        "keep_pageheader_in_output": keep_pageheader_in_output,
        "keep_pagefooter_in_output": keep_pagefooter_in_output,
        "printed_page_zones": printed_page_zones,
        "printed_page_header_end": printed_page_header_end,
        "printed_page_footer_start": printed_page_footer_start,
    }
