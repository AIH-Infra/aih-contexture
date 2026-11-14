from __future__ import annotations


def render_external_layout_sidecar_settings(st, *, description: str) -> dict:
    if str(description or "").strip():
        st.caption(description)

    external_layout_json = st.text_input(
        "外部版面 JSON 路径",
        value=st.session_state.get("external_layout_json", ""),
        help="支持 MinerU、PaddleOCR 或通用版面 JSON，也支持 Contexture Middle JSON。",
        key="external_layout_json",
    )
    external_layout_block_source = st.selectbox(
        "块来源",
        options=[
            "auto",
            "all",
            "blocks",
            "layout_bboxes",
            "boxes",
            "bboxes",
            "layout",
            "regions",
            "para_blocks",
            "preproc_blocks",
            "discarded_blocks",
        ],
        index=0,
        help="MinerU/Paddle 输出中常有多组块列表；auto 使用第一个可用列表，all 合并所有可识别列表。",
        key="external_layout_block_source",
    )
    external_layout_backend_name = st.text_input(
        "来源后端名称",
        value=st.session_state.get("external_layout_backend_name", "external_layout_sidecar"),
        help="记录版面结果的来源，例如 MinerU 或 PaddleOCR；不会改变本次使用的版面模型。",
        key="external_layout_backend_name",
    )
    external_layout_model = st.text_input(
        "来源模型名称",
        value=st.session_state.get("external_layout_model", ""),
        help="可填 PP-DocLayoutV2、PP-DocLayoutV3 等模型名；留空也可以运行。",
        key="external_layout_model",
    )
    external_layout_allow_missing_pages = st.checkbox(
        "允许外部版面 JSON 缺页",
        value=st.session_state.get("external_layout_allow_missing_pages", False),
        help="开启后，外部 JSON 中缺失的页面按整页文字区域处理；默认关闭，避免缺页或页码错配未被发现。",
        key="external_layout_allow_missing_pages",
    )

    return {
        "external_layout_json": external_layout_json.strip(),
        "external_layout_block_source": external_layout_block_source,
        "external_layout_backend_name": external_layout_backend_name.strip() or "external_layout_sidecar",
        "external_layout_model": external_layout_model.strip() or None,
        "external_layout_allow_missing_pages": external_layout_allow_missing_pages,
    }
