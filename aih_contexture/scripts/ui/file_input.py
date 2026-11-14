from __future__ import annotations

import os
import json
from pathlib import Path

from aih_contexture.scripts.ui.file_transfer import get_transfer_server, get_transfer_session


def file_input_spec(conversion_mode: str, postprocess_input_kind: str | None = None) -> dict[str, object]:
    if conversion_mode == "structured_source":
        return {
            "label": "TEI/XML 或 EPUB 文件",
            "types": ["xml", "tei", "epub"],
            "suffixes": (".xml", ".tei", ".epub"),
            "success_name": "结构化源",
        }
    if conversion_mode == "markdown_postprocess":
        if postprocess_input_kind == "middle_json":
            return {
                "label": "Contexture Middle JSON 文件",
                "types": ["json"],
                "suffixes": (".json",),
                "success_name": "Contexture Middle JSON",
            }
        if postprocess_input_kind == "mineru_json":
            return {
                "label": "MinerU 官方 JSON 文件",
                "types": ["json"],
                "suffixes": (".json",),
                "success_name": "MinerU 官方 JSON",
            }
        return {
            "label": "Markdown 文件",
            "types": ["md", "markdown"],
            "suffixes": (".md", ".markdown"),
            "success_name": "Markdown",
        }
    return {
        "label": "PDF 文件",
        "types": ["pdf"],
        "suffixes": (".pdf",),
        "success_name": "PDF",
    }


def collect_folder_files(folder_path: str, suffixes: tuple[str, ...]) -> list[str]:
    files_found: list[str] = []
    if not folder_path or not os.path.isdir(folder_path):
        return files_found

    normalized_suffixes = tuple(suffix.lower() for suffix in suffixes)
    for root, _, files in os.walk(folder_path):
        for file_name in files:
            if file_name.lower().endswith(normalized_suffixes):
                files_found.append(os.path.join(root, file_name))
    return sorted(files_found, key=str.casefold)


def _render_selected_file_list(st, files: list[str]) -> None:
    if not files:
        return
    with st.expander(f"查看待处理文件（{len(files)} 个）", expanded=False):
        st.code("\n".join(files))


def render_file_input_selector(st, conversion_mode: str, postprocess_input_kind: str | None = None):
    spec = file_input_spec(conversion_mode, postprocess_input_kind)
    upload_mode = st.radio(
        "文件来源",
        ["上传文件", "选择文件夹"],
        index=0,
        horizontal=True,
        key="upload_mode_global",
        label_visibility="collapsed",
    )

    if upload_mode == "上传文件":
        return upload_mode, render_disk_upload(st, spec)

    folder_path = st.text_input(
        "文件夹路径",
        value="",
        label_visibility="collapsed",
        placeholder="输入文件夹路径...",
        key="folder_path_global",
    )
    uploaded_files: list[str] = []
    if folder_path:
        if not os.path.exists(folder_path):
            st.error("文件夹路径不存在")
        elif not os.path.isdir(folder_path):
            st.error("该路径不是文件夹")
        else:
            uploaded_files = collect_folder_files(folder_path, spec["suffixes"])
            if uploaded_files:
                st.success(f"找到 {len(uploaded_files)} 个 {spec['success_name']} 文件")
                _render_selected_file_list(st, uploaded_files)
            else:
                st.warning(f"文件夹及其子文件夹中没有找到可处理的 {spec['success_name']} 文件")

    return upload_mode, uploaded_files


def render_disk_upload(st, spec):
    import streamlit.components.v1 as components

    session = get_transfer_session(st)
    queue = session.queue
    legacy = st.session_state.get('file_uploader_global')
    if legacy and st.session_state.get('proc_ctx', {}).get('status') != 'running':
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        script_context = get_script_run_ctx()
        for item in list(legacy):
            item.seek(0)
            queue.receive(item, item.name, item.size)
            script_context.uploaded_file_mgr.remove_file(script_context.session_id, item.file_id)
            legacy.remove(item)
            item.close()
        del st.session_state['file_uploader_global']
    st.caption(f"上传 {spec['label']}")
    with queue.lock:
        busy = queue.running
    if not busy:
        template = Path(__file__).parents[3] / 'assets/file_upload.html'
        config = {'port': get_transfer_server().server_port, 'token': session.token,
                  'accept': ','.join(spec['suffixes'])}
        components.html(template.read_text(encoding='utf-8').replace('__CONFIG__', json.dumps(config)), height=170)

    @st.fragment(run_every=0.5)
    def render_queue():
        files = queue.ready(spec['suffixes'])
        with queue.lock:
            snapshot = (tuple(item.path for item in files), len(queue.uploading), bool(queue.incoming_batches), queue.running)
        changed = st.session_state.get('_upload_queue_snapshot') != snapshot
        if changed:
            st.session_state['_upload_queue_snapshot'] = snapshot
        if snapshot[1] or snapshot[2]:
            st.caption('文件正在上传')
        if files:
            st.caption(f'待处理 {len(files)} 个文件 · {sum(item.size for item in files) / 1024**2:.1f} MB')
            _render_selected_file_list(st, [item.name for item in files])
            if not snapshot[1] and not snapshot[3]:
                selected = st.multiselect('移除暂存文件', options=[item.path for item in files],
                                          format_func=lambda path: next(item.name for item in files if item.path == path),
                                          key='staged_upload_remove')
                remove, clear = st.columns(2)
                if remove.button('移除所选', disabled=not selected, key='remove_staged_uploads'):
                    try:
                        queue.remove(set(selected))
                    except (OSError, ValueError) as exc:
                        st.error(f'暂存清理失败 {exc}')
                    else:
                        st.rerun()
                if clear.button('清理上传缓存', key='clear_staged_uploads'):
                    try:
                        queue.remove()
                    except (OSError, ValueError) as exc:
                        st.error(f'暂存清理失败 {exc}')
                    else:
                        st.rerun()

        elif snapshot[2] and not snapshot[1]:
            if st.button('清理上传缓存', key='clear_staged_uploads'):
                try:
                    queue.remove()
                except (OSError, ValueError) as exc:
                    st.error(f'暂存清理失败 {exc}')
                else:
                    st.rerun()

        # Handle widget events before a full rerun so a click arriving with
        # the final upload notification is not discarded.
        if changed and not snapshot[1] and not snapshot[2]:
            st.rerun()

    render_queue()
    with queue.lock:
        return [] if queue.uploading or queue.incoming_batches or queue.running else queue.ready(spec['suffixes'])
