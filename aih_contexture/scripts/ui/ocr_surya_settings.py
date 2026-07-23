from __future__ import annotations


def render_surya_ocr_settings(
    st,
    *,
    description: str,
    batch_size: int,
    force_ocr: bool,
) -> dict[str, object]:
    st.info(description)
    st.caption("首次使用需要下载模型；下载后会缓存复用。")
    with st.expander("Surya 配置", expanded=False):
        batch_size = st.slider(
            "OCR 批次大小",
            1,
            64,
            int(batch_size),
            help="每批处理的图像数量",
            key="ocr_batch_size",
        )

    return {
        "ocr_batch_size": batch_size,
        "force_ocr": True,
    }
