from __future__ import annotations


SURYA_LAYOUT_BATCH_SIZE_OPTIONS = (2, 4, 6, 8, 12)
SURYA_LAYOUT_BATCH_SIZE_LABELS = {
    2: "2 页",
    4: "4 页",
    6: "6 页",
    8: "8 页",
    12: "12 页",
}


def render_surya_layout_settings(
    st,
    *,
    description: str,
    extract_printed_pages: bool,
    layout_batch_size: int = 8,
) -> dict[str, object]:
    del extract_printed_pages
    if str(description or "").strip():
        st.caption(description)
    try:
        selected_batch_size = int(layout_batch_size)
    except (TypeError, ValueError):
        selected_batch_size = 8
    if selected_batch_size not in SURYA_LAYOUT_BATCH_SIZE_OPTIONS:
        selected_batch_size = 8

    selected_batch_size = st.selectbox(
        "模型推理批次",
        options=SURYA_LAYOUT_BATCH_SIZE_OPTIONS,
        index=SURYA_LAYOUT_BATCH_SIZE_OPTIONS.index(selected_batch_size),
        format_func=lambda value: SURYA_LAYOUT_BATCH_SIZE_LABELS[value],
        help="每次送入 Surya 版面模型的页面数。较小批次占用较少显存；较大批次可能提高吞吐量。",
        key="layout_batch_size",
    )
    return {"layout_batch_size": int(selected_batch_size)}
