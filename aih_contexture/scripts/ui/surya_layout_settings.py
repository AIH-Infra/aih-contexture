from __future__ import annotations


SURYA_LAYOUT_BATCH_SIZE_OPTIONS = (2, 4, 6, 8, 12)
SURYA_LAYOUT_BATCH_SIZE_LABELS = {
    2: "2 页（较低显存占用）",
    4: "4 页",
    6: "6 页",
    8: "8 页（默认）",
    12: "12 页（较高显存占用）",
}


def render_surya_layout_settings(
    st,
    *,
    description: str,
    extract_printed_pages: bool,
    layout_batch_size: int = 8,
) -> dict[str, object]:
    del extract_printed_pages
    st.info(description)
    st.caption("缺少模型缓存时，首次使用会下载模型；之后复用本地缓存。")
    try:
        selected_batch_size = int(layout_batch_size)
    except (TypeError, ValueError):
        selected_batch_size = 8
    if selected_batch_size not in SURYA_LAYOUT_BATCH_SIZE_OPTIONS:
        selected_batch_size = 8

    selected_batch_size = st.selectbox(
        "Surya 版面推理批次大小",
        options=SURYA_LAYOUT_BATCH_SIZE_OPTIONS,
        index=SURYA_LAYOUT_BATCH_SIZE_OPTIONS.index(selected_batch_size),
        format_func=lambda value: SURYA_LAYOUT_BATCH_SIZE_LABELS[value],
        help="每次版面推理提交的页面数。减小批次可降低显存占用，增大批次可能提高吞吐量；显存不足时可先减至 4 或 2。这与文件并发数、作业分批页数不同。",
        key="layout_batch_size",
    )
    return {"layout_batch_size": int(selected_batch_size)}
