"""Shared, retained settings for Middle and MinerU JSON reading exports."""
from __future__ import annotations

from aih_contexture.scripts.ui.classical_marginalia_controls import (
    render_classical_marginalia_controls,
    render_generic_line_output_control,
)


def render_middle_rerender_controls(st, *, prefix: str) -> dict:
    state = st.session_state

    def checkbox(suffix, label, default, help=None):
        key = f'{prefix}_{suffix}'
        value = state.get(key, state.get(f'_retained_{key}', default))
        state[key] = default if value is None else bool(value)
        value = st.checkbox(label, key=key, help=help)
        state[f'_retained_{key}'] = value
        return value

    def selection(suffix, label, options, labels, default, *, disabled=False):
        key = f'{prefix}_{suffix}'
        value = state.get(key, state.get(f'_retained_{key}', default))
        state[key] = value if value in options else default
        def normalize():
            if state.get(key) not in options:
                state[key] = default
        value = st.selectbox(label, options=options, key=key, index=None,
                             format_func=labels.get, disabled=disabled, on_change=normalize)
        state[f'_retained_{key}'] = value
        return value

    result = {}
    with st.expander('渲染配置', expanded=True):
        inherit = checkbox('inherit_document_settings', '沿用文档配置', False,
                           '采用 Middle JSON 保存的阅读配置；旧文件没有配置时使用兼容默认值。')
        if inherit:
            st.caption('按文档配置重新渲染。关闭此选项后，可在这里指定覆盖值。')
            return {key: None for key in (
                'middle_rerender_classical_marginalia_mode',
                'middle_rerender_classical_text_marginalia_mode',
                'middle_rerender_generic_line_output_mode',
                'middle_rerender_marginal_output_mode', 'middle_rerender_include_margin_comments',
                'middle_rerender_include_printed_page_comments', 'middle_rerender_include_page_header_comments',
                'middle_rerender_include_page_separators', 'middle_rerender_include_page_footer_comments',
                'middle_rerender_include_provenance', 'middle_rerender_equation_output_mode',
            )}
        st.caption('以下设置覆盖文档中保存的阅读配置。')
        classical, text_mode = render_classical_marginalia_controls(
            st, mode_key=f'{prefix}_classical_marginalia_mode', text_key=f'{prefix}_classical_text_marginalia_mode')
        generic_line = render_generic_line_output_control(
            st, key=f'{prefix}_generic_line_output_mode', classical_mode=classical)
        legacy = selection('marginal_output_mode', '常规边注输出（古典模式关闭时）',
            ['line_markers', 'margin_comments', 'plain', 'drop'], {
                'line_markers': '旁注注释（纯数字简写为行号）',
                'margin_comments': '旁注注释（全部保持旁注）', 'plain': '普通文本', 'drop': '丢弃',
            }, 'plain' if state.get(f'{prefix}_include_margin_comments') is False else 'line_markers',
            disabled=classical == 'page_locators')
        result.update({
            'middle_rerender_classical_marginalia_mode': classical,
            'middle_rerender_classical_text_marginalia_mode': text_mode,
            'middle_rerender_generic_line_output_mode': generic_line,
            'middle_rerender_marginal_output_mode': legacy,
            'middle_rerender_include_margin_comments': legacy in {'line_markers', 'margin_comments'},
        })
        left, right = st.columns(2)
        with left:
            result['middle_rerender_include_printed_page_comments'] = checkbox('include_printed_page_comments', '输出印刷页码注释', True, '输出 <!-- Page: … -->；不改变输入物理页锚点。')
            result['middle_rerender_include_page_header_comments'] = checkbox('include_page_header_comments', '输出页眉注释', True)
            result['middle_rerender_include_page_separators'] = checkbox('include_page_separators', '输出页面分隔线', True)
        with right:
            result['middle_rerender_include_page_footer_comments'] = checkbox('include_page_footer_comments', '输出页脚注释', True)
            result['middle_rerender_include_provenance'] = checkbox('include_provenance', '输出块级 provenance 注释', False, '用于调试来源和锚点；阅读版通常关闭。')
        result['middle_rerender_equation_output_mode'] = selection('equation_output_mode', '公式输出方式',
            ['humanities_safe', 'plain', 'math'], {
                'humanities_safe': '人文学术安全（疑似校勘索引转普通文本）',
                'plain': '全部公式按普通文本', 'math': '保留全部公式块',
            }, 'humanities_safe')
    st.caption('仅重新渲染已有结构；不调用 OCR 或 LLM。保存阅读 Markdown 和 Middle JSON；诊断信息需单独勾选输出。')
    return result
