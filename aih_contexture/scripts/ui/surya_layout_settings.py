from __future__ import annotations

def render_surya_layout_settings(
    st,
    *,
    description: str,
    extract_printed_pages: bool,
) -> dict[str, object]:
    del extract_printed_pages
    st.info(description)
    st.caption("首次使用 Surya 版面识别时需要联网下载模型；下载完成后会缓存复用。")
    return {}
