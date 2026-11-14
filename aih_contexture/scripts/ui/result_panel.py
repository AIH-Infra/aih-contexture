from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from aih_contexture.scripts.ui.output_restore import scan_output_records_for_restore
from aih_contexture.scripts.ui.markdown_preview import render_markdown_preview
from aih_contexture.scripts.ui.file_transfer import render_file_download


_OUTPUT_FORMAT_LABELS = {
    "reading_diagnostics": "阅读诊断",
    "markdown": "阅读 Markdown",
    "json": "JSON",
    "html": "HTML",
    "chunks": "文本分块",
    "xml": "XML",
    "meta": "元数据",
    "middle_json": "结构数据 JSON",
    "middle_report": "结构分析报告",
    "middle_debug": "结构调试记录",
    "middle_scholarly": "学术阅读 Markdown",
    "middle_scholarly_report": "学术阅读报告",
    "postprocess_report": "后处理报告",
    "layout_overlay": "版面预览 PDF",
    "span_overlay": "区域预览 PDF",
    "table_review": "表格复核数据",
    "classical_marginalia": "古典边注数据",
    "classical_manifest": "边注索引",
    "pdf": "PDF",
    "zip": "ZIP",
    "file": "文件",
}


def _session_get(session_state, key: str, default=None):
    if hasattr(session_state, "get"):
        return session_state.get(key, default)
    return getattr(session_state, key, default)


def _session_set(session_state, key: str, value) -> None:
    if isinstance(session_state, dict):
        session_state[key] = value
    else:
        setattr(session_state, key, value)


def render_process_controls(
    st,
    conversion_mode: str,
    output_dir: str,
    *,
    has_input: bool = True,
    output_dir_valid: bool = True,
    restore_outputs: Callable[[str], dict[str, list[dict[str, str]]]] = scan_output_records_for_restore,
) -> bool:
    proc_ctx = _session_get(st.session_state, "proc_ctx", {}) or {}
    is_running = _session_get(proc_ctx, "status", "idle") == "running"
    col_start, col_restore = st.columns([3, 1])
    with col_start:
        start_button = st.button(
            "🚀 开始后处理" if conversion_mode == "markdown_postprocess" else "🚀 开始转换",
            type="primary",
            use_container_width=True,
            disabled=is_running or not has_input or not output_dir_valid,
        )
    with col_restore:
        if st.button(
            "🔄 恢复历史",
            help="从输出目录恢复之前的处理记录",
            use_container_width=True,
            disabled=is_running or not output_dir_valid,
        ):
            restored = restore_outputs(output_dir)
            _session_set(st.session_state, "processed_files", restored)
            st.success(f"已恢复 {len(restored)} 组文件")

    return start_button


def render_result_history(st) -> None:
    last_zip_path = _session_get(st.session_state, "last_zip_path")
    if last_zip_path and os.path.exists(last_zip_path):
        st.subheader("⬇️ 上次任务下载")
        render_file_download(st, last_zip_path, "📦 下载所有结果（ZIP）")

    processed_files = _session_get(st.session_state, "processed_files", {})
    if processed_files:
        st.subheader("处理结果")
        for group, items in processed_files.items():
            st.write(f"**{group}**")
            for item in items:
                artifact_format = item.get("format", "file")
                label = _OUTPUT_FORMAT_LABELS.get(artifact_format, artifact_format)
                st.caption(f"{label} · {item.get('name')}")
        diagnostics = {item['path'] for items in processed_files.values() for item in items
                       if item.get('format') == 'reading_diagnostics' and item.get('path')
                       and Path(item['path']).is_file()}
        if diagnostics and st.checkbox('查看或下载诊断文件', value=False, key='reading_diagnostic_files'):
            with st.expander('独立诊断文件', expanded=True):
                for value in sorted(diagnostics):
                    path = Path(value)
                    try:
                        render_file_download(st, str(path), '下载诊断 · ' + path.name)
                    except OSError:
                        st.info('该诊断文件已移动或无法读取，请恢复历史记录后重试。')
        render_markdown_preview(st, processed_files)
