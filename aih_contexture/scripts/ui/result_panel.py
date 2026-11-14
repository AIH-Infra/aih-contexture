from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from aih_contexture.scripts.ui.output_restore import scan_output_records_for_restore
from aih_contexture.scripts.ui.markdown_preview import render_markdown_preview


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
    restore_outputs: Callable[[str], dict[str, list[dict[str, str]]]] = scan_output_records_for_restore,
) -> bool:
    col_start, col_restore = st.columns([3, 1])
    with col_start:
        start_button = st.button(
            "🚀 开始后处理" if conversion_mode == "markdown_postprocess" else "🚀 开始转换",
            type="primary",
            use_container_width=True,
        )
    with col_restore:
        if st.button("🔄 恢复历史", help="从输出目录恢复之前的处理记录", use_container_width=True):
            restored = restore_outputs(output_dir)
            _session_set(st.session_state, "processed_files", restored)
            st.success(f"已恢复 {len(restored)} 组文件")

    return start_button


def render_result_history(st) -> None:
    last_zip_path = _session_get(st.session_state, "last_zip_path")
    if last_zip_path and os.path.exists(last_zip_path):
        st.subheader("⬇️ 上次任务下载")
        with open(last_zip_path, "rb") as f:
            st.download_button(
                "📦 下载所有结果（ZIP）",
                data=f.read(),
                file_name=_session_get(st.session_state, "last_zip_name") or os.path.basename(last_zip_path),
                mime="application/zip",
                key="download_all_persist",
            )

    processed_files = _session_get(st.session_state, "processed_files", {})
    if processed_files:
        with st.expander("📌 已处理文件记录", expanded=False):
            for group, items in processed_files.items():
                st.write(f"**{group}**")
                for item in items:
                    st.caption(f"  └─ [{item.get('format', 'file')}] {item.get('name')}")
        diagnostics = {item['path'] for items in processed_files.values() for item in items
                       if item.get('format') == 'reading_diagnostics' and item.get('path')
                       and Path(item['path']).is_file()}
        if diagnostics and st.checkbox('查看或下载诊断文件', value=False, key='reading_diagnostic_files'):
            with st.expander('独立诊断文件', expanded=True):
                for value in sorted(diagnostics):
                    path = Path(value)
                    try:
                        st.download_button('下载诊断 · ' + path.name, data=path.read_bytes(),
                                           file_name=path.name, mime='application/json',
                                           key='reading_diagnostic_download:' + str(path))
                    except OSError:
                        st.info('该诊断文件已移动或无法读取，请恢复历史记录后重试。')
        render_markdown_preview(st, processed_files)
