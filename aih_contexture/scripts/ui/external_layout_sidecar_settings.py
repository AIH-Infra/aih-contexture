from __future__ import annotations


def render_external_layout_sidecar_settings(st, *, description: str) -> dict:
    st.info(
        description
        + "\n\n"
        "读取已经生成好的 layout JSON，不在 Contexture 内启动 MinerU/Paddle 模型。"
        "适用于先用外部工具离线跑版面识别，再进入 Contexture Pipeline 的流程。"
    )

    external_layout_json = st.text_input(
        "外部 layout JSON 路径",
        value=st.session_state.get("external_layout_json", ""),
        help="支持 MinerU/Paddle/通用 layout JSON，也支持已归一化的 Contexture Middle JSON。",
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
        help="写入 provenance，用于区分 mineru_pp_doclayout_v2、paddle_pp_doclayout_v3 等来源。",
        key="external_layout_backend_name",
    )
    external_layout_model = st.text_input(
        "来源模型名称",
        value=st.session_state.get("external_layout_model", ""),
        help="可填 PP-DocLayoutV2、PP-DocLayoutV3 等模型名；留空也可以运行。",
        key="external_layout_model",
    )
    external_layout_allow_missing_pages = st.checkbox(
        "允许 sidecar 缺页",
        value=st.session_state.get("external_layout_allow_missing_pages", False),
        help="开启后，sidecar 中缺失的页面会退回为整页 Text 块；默认关闭以避免页码错配不被发现。",
        key="external_layout_allow_missing_pages",
    )

    return {
        "external_layout_json": external_layout_json.strip(),
        "external_layout_block_source": external_layout_block_source,
        "external_layout_backend_name": external_layout_backend_name.strip() or "external_layout_sidecar",
        "external_layout_model": external_layout_model.strip() or None,
        "external_layout_allow_missing_pages": external_layout_allow_missing_pages,
    }
