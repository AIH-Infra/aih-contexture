from __future__ import annotations

import os


def file_input_spec(conversion_mode: str, postprocess_input_kind: str | None = None) -> dict[str, object]:
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
    if not folder_path or not os.path.exists(folder_path):
        return files_found

    normalized_suffixes = tuple(suffix.lower() for suffix in suffixes)
    for root, _, files in os.walk(folder_path):
        for file_name in files:
            if file_name.lower().endswith(normalized_suffixes):
                files_found.append(os.path.join(root, file_name))
    return files_found


def render_file_input_selector(st, conversion_mode: str, postprocess_input_kind: str | None = None):
    spec = file_input_spec(conversion_mode, postprocess_input_kind)
    upload_mode = st.radio(
        "选择模式",
        ["上传文件", "选择文件夹"],
        index=0,
        horizontal=True,
        key="upload_mode_global",
    )

    if upload_mode == "上传文件":
        uploaded_files = st.file_uploader(
            f"上传 {spec['label']}",
            type=spec["types"],
            accept_multiple_files=True,
            label_visibility="collapsed",
            key="file_uploader_global",
        )
        return upload_mode, uploaded_files

    folder_path = st.text_input(
        "文件夹路径",
        value="",
        label_visibility="collapsed",
        placeholder="输入文件夹路径...",
        key="folder_path_global",
    )
    uploaded_files: list[str] = []
    if folder_path:
        if os.path.exists(folder_path):
            uploaded_files = collect_folder_files(folder_path, spec["suffixes"])
            st.success(f"找到 {len(uploaded_files)} 个 {spec['success_name']} 文件")
        else:
            st.error("文件夹路径不存在")

    return upload_mode, uploaded_files
