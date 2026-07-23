from __future__ import annotations

import os


def render_pipeline_run_settings(st) -> dict[str, object]:
    with st.expander("运行高级选项", expanded=False):
        st.markdown("**处理设置**")

        batch_mode = st.radio(
            "处理模式",
            options=["自动", "单批处理", "分批处理"],
            index=0,
            horizontal=True,
            help="控制 Pipeline 作业如何按页切分；这不是模型推理 batch size。",
        )

        if batch_mode in ("分批处理", "自动"):
            st.caption("分批可降低长文档的峰值资源占用；批次间冷却只影响作业节奏，不改变模型内部批次。")
            col_a, col_b = st.columns(2)
            with col_a:
                batch_threshold = st.number_input(
                    "分批阈值（页）",
                    min_value=10,
                    max_value=2000,
                    value=50,
                    help="仅自动模式生效；超过该页数后按批处理。",
                )
                pages_per_batch = st.number_input(
                    "每批页数",
                    min_value=5,
                    max_value=1000,
                    value=25,
                    help="每个 Pipeline 子作业包含的页数。",
                )
            with col_b:
                cooling_seconds = st.number_input(
                    "批次间冷却（秒）",
                    min_value=0,
                    max_value=30,
                    value=3,
                    help="每个子作业结束后的等待时间。",
                )
        else:
            batch_threshold = 50
            pages_per_batch = 25
            cooling_seconds = 0

        process_mode = {
            "自动": "自动",
            "单批处理": "强制单批",
            "分批处理": "强制分批",
        }[batch_mode]

        st.markdown("---")

        use_page_range = st.checkbox("指定页码范围", value=False, key="use_page_range")
        if use_page_range:
            col_start, col_end = st.columns(2)
            with col_start:
                start_page_1based = st.number_input("起始页", min_value=1, value=1, key="start_page")
            with col_end:
                end_page_1based = st.number_input("结束页", min_value=1, value=10, key="end_page")
        else:
            start_page_1based = None
            end_page_1based = None

        st.markdown("---")
        st.markdown("**其他设置**")

        use_fp16 = st.checkbox(
            "使用 FP16",
            value=os.environ.get("USE_FP16", "false").lower() == "true",
            help="半精度推理，可降低显存占用；具体是否生效取决于后端。",
        )

        st.divider()

    return {
        "batch_mode": batch_mode,
        "batch_threshold": batch_threshold,
        "pages_per_batch": pages_per_batch,
        "cooling_seconds": cooling_seconds,
        "process_mode": process_mode,
        "use_page_range": use_page_range,
        "start_page_1based": start_page_1based,
        "end_page_1based": end_page_1based,
        "use_fp16": use_fp16,
    }
