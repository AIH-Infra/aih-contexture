from __future__ import annotations


def render_surya_ocr_settings(
    st,
    *,
    description: str,
    batch_size: int,
    force_ocr: bool,
) -> dict[str, object]:
    if str(description or "").strip():
        st.caption(description)
    with st.expander("Surya OCR 参数", expanded=False):
        batch_size = st.slider(
            "模型推理批次",
            1,
            64,
            int(batch_size),
            help="每次送入 Surya OCR 模型的图像数。",
            key="ocr_batch_size",
        )

    return {
        "ocr_batch_size": batch_size,
        "force_ocr": True,
    }
