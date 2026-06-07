from __future__ import annotations


def render_pipeline_processor_settings(st) -> dict[str, object]:
    with st.expander("文本处理器", expanded=False):
        markdown_noise_removal_enabled = st.checkbox(
            "Markdown 噪音清理",
            value=True,
            help="清理 OCR 误识别出的 Markdown 控制符，避免污染标题、引用和列表结构。",
            key="markdown_noise_removal_enabled_pipeline",
        )

        if markdown_noise_removal_enabled:
            with st.expander("高级设置", expanded=False):
                markdown_noise_cleaning_level = st.radio(
                    "清理级别",
                    options=["basic", "medium", "aggressive"],
                    index=0,
                    format_func=lambda value: {
                        "basic": "基础（只清理 # 标题符号）",
                        "medium": "中等（清理 #, >, -, * 等常见符号）",
                        "aggressive": "激进（清理所有 Markdown 符号）",
                    }.get(value, value),
                    help="基础级别最保守；更高强度会清理更多 Markdown 符号。",
                    key="markdown_noise_cleaning_level_pipeline",
                )

                markdown_noise_custom_symbols = st.text_input(
                    "自定义符号列表（可选）",
                    value="",
                    placeholder="输入要过滤的符号，逗号分隔，如：#, >, -",
                    help="留空时使用上方清理级别；填写后覆盖默认符号集。",
                    key="markdown_noise_custom_symbols_pipeline",
                )

                markdown_noise_line_start_only = st.checkbox(
                    "只清理行首符号",
                    value=True,
                    help="默认只处理行首，避免误删正文中的合法符号。",
                    key="markdown_noise_line_start_only_pipeline",
                )
        else:
            markdown_noise_cleaning_level = "basic"
            markdown_noise_custom_symbols = ""
            markdown_noise_line_start_only = True

        line_merge_enabled = st.checkbox(
            "行合并",
            value=True,
            help="将同一段落的多行文本合并。特殊分行格式（如诗歌）可关闭。",
            key="line_merge_enabled_pipeline",
        )

        blockquote_enabled = st.checkbox(
            "引用块检测",
            value=True,
            help="检测并标记缩进的引用块（使用 > 符号）。诗歌或特殊缩进格式可关闭。",
            key="blockquote_enabled_pipeline",
        )

        code_enabled = st.checkbox(
            "代码块检测",
            value=True,
            help="检测并标记代码块（使用 ``` 符号）。",
            key="code_enabled_pipeline",
        )

    with st.expander("结构处理器", expanded=False):
        section_header_enabled = st.checkbox(
            "章节标题检测",
            value=True,
            help="将疑似章节标题渲染为 Markdown 标题。",
            key="section_header_enabled_pipeline",
        )

        equation_enabled = st.checkbox(
            "公式处理",
            value=True,
            help="处理公式区域；关闭可减少对页面图像的依赖。",
            key="equation_enabled_pipeline",
        )

        list_enabled = st.checkbox(
            "列表检测",
            value=True,
            help="识别项目符号和编号列表。",
            key="list_enabled_pipeline",
        )

        footnote_enabled = st.checkbox(
            "脚注检测",
            value=True,
            help="识别并后置页底脚注。",
            key="footnote_enabled_pipeline",
        )

        reference_enabled = st.checkbox(
            "参考文献检测",
            value=True,
            help="识别参考文献区域并保留结构。",
            key="reference_enabled_pipeline",
        )

    with st.expander("表格处理器", expanded=False):
        table_enabled = st.checkbox(
            "表格处理",
            value=True,
            help="将表格区域转为结构化输出。",
            key="table_enabled_pipeline",
        )

    return {
        "markdown_noise_removal_enabled": markdown_noise_removal_enabled,
        "markdown_noise_cleaning_level": markdown_noise_cleaning_level,
        "markdown_noise_custom_symbols": markdown_noise_custom_symbols,
        "markdown_noise_line_start_only": markdown_noise_line_start_only,
        "line_merge_enabled": line_merge_enabled,
        "blockquote_enabled": blockquote_enabled,
        "code_enabled": code_enabled,
        "section_header_enabled": section_header_enabled,
        "equation_enabled": equation_enabled,
        "list_enabled": list_enabled,
        "footnote_enabled": footnote_enabled,
        "reference_enabled": reference_enabled,
        "table_enabled": table_enabled,
    }
