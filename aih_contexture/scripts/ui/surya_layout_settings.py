from __future__ import annotations


SURYA_LAYOUT_BATCH_SIZE_OPTIONS = (2, 4, 6, 8, 12)
SURYA_LAYOUT_BATCH_SIZE_LABELS = {
    2: "2 - Maximum stability",
    4: "4 - Stable",
    6: "6 - Conservative balanced",
    8: "8 - Default balanced",
    12: "12 - High throughput",
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
    st.caption("The Surya model is downloaded on first use and reused from the local cache.")
    try:
        selected_batch_size = int(layout_batch_size)
    except (TypeError, ValueError):
        selected_batch_size = 8
    if selected_batch_size not in SURYA_LAYOUT_BATCH_SIZE_OPTIONS:
        selected_batch_size = 8

    selected_batch_size = st.selectbox(
        "Surya GPU inference batch size",
        options=SURYA_LAYOUT_BATCH_SIZE_OPTIONS,
        index=SURYA_LAYOUT_BATCH_SIZE_OPTIONS.index(selected_batch_size),
        format_func=lambda value: SURYA_LAYOUT_BATCH_SIZE_LABELS[value],
        help="Pages sent to Surya Layout per GPU inference call. Smaller values are more stable; larger values may be faster but use more VRAM. Use 4 or 2 if an RTX 2080 Ti reports CUDA errors.",
        key="layout_batch_size",
    )
    return {"layout_batch_size": int(selected_batch_size)}
