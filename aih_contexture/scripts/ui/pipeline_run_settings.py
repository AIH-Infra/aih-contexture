from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from aih_contexture.runtime.pipeline_parallelism import (
    AUTO,
    MANUAL,
    MAX_WORKERS,
    describe_plan,
    plan_from_values,
    probe_memory,
)

PERFORMANCE_MODE_LABELS = {AUTO: "自动（按可用显存）", MANUAL: "手动"}


def render_pipeline_run_settings(st, backend_values: Mapping[str, Any] | None = None) -> dict[str, object]:
    backend_values = dict(backend_values or {})
    with st.expander("运行高级选项", expanded=False):
        st.markdown("**性能配置**")
        st.caption(
            "并行进程各自加载一份模型，进程数由可用显存决定；每批页数只影响内存。"
            "并行时小批次（约 25 页）让各进程的 GPU 与 CPU 阶段错开，单进程时约 100 页最快。"
        )
        if st.session_state.get("pipeline_performance_mode") not in PERFORMANCE_MODE_LABELS:
            st.session_state["pipeline_performance_mode"] = AUTO
        performance_mode = st.radio(
            "性能配置",
            options=list(PERFORMANCE_MODE_LABELS),
            format_func=PERFORMANCE_MODE_LABELS.get,
            horizontal=True,
            key="pipeline_performance_mode",
            help="自动：按当前空闲显存、内存和版面后端推荐并行进程数与每批页数，每个文件开始前按实际页数再确认一次。",
        )
        probe = probe_memory()
        recommended = plan_from_values({**backend_values, "pipeline_performance_mode": AUTO}, probe=probe)
        cooling_seconds = 0

        if performance_mode == AUTO:
            st.info(f"推荐：{describe_plan(recommended)}")
            for note in recommended.notes:
                st.caption(note)
            batch_mode = "自动"
            batch_threshold = recommended.batch_threshold
            pages_per_batch = recommended.pages_per_batch
            pipeline_workers = recommended.workers
        else:
            st.caption(f"自动推荐：{recommended.workers} 个进程 × 每批 {recommended.pages_per_batch} 页")
            batch_mode = st.radio(
                "处理模式",
                options=["自动", "单批处理", "分批处理"],
                index=0,
                horizontal=True,
                key="pipeline_batch_mode",
                help="控制 Pipeline 作业如何按页切分；这不是模型推理 batch size。",
            )
            col_a, col_b = st.columns(2)
            with col_a:
                pipeline_workers = int(st.number_input(
                    "并行进程数",
                    min_value=1,
                    max_value=MAX_WORKERS,
                    value=int(st.session_state.get("pipeline_workers", recommended.workers)),
                    key="pipeline_workers",
                    help="超过显存或内存安全上限时会自动降低，避免显存溢出到系统内存后卡死。",
                ))
                pages_per_batch = int(st.number_input(
                    "每批页数",
                    min_value=5,
                    max_value=1000,
                    value=int(st.session_state.get("pipeline_pages_per_batch", 25)),
                    key="pipeline_pages_per_batch",
                    help="每个 Pipeline 子作业包含的页数。",
                ))
            with col_b:
                batch_threshold = int(st.number_input(
                    "分批阈值（页）",
                    min_value=10,
                    max_value=2000,
                    value=int(st.session_state.get("pipeline_batch_threshold", 50)),
                    key="pipeline_batch_threshold",
                    help="仅“自动”处理模式生效；超过该页数后按批处理。",
                ))
            if batch_mode == "单批处理":
                pipeline_workers = 1
            manual = plan_from_values(
                {
                    **backend_values,
                    "pipeline_performance_mode": MANUAL,
                    "pipeline_workers": pipeline_workers,
                    "pages_per_batch": pages_per_batch,
                    "batch_threshold": batch_threshold,
                },
                probe=probe,
            )
            for note in manual.notes:
                st.warning(note)

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

        stall_timeout_minutes = st.number_input(
            "无进展自动跳过（分钟）",
            min_value=3,
            max_value=180,
            value=_default_stall_timeout_minutes(),
            step=1,
            help="结构化页数、阶段或批次在此时间内没有任何推进时，终止当前文件子进程并继续下一文件。",
        )

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
        "pipeline_performance_mode": performance_mode,
        "pipeline_workers": int(pipeline_workers),
        "cooling_seconds": cooling_seconds,
        "process_mode": process_mode,
        "use_page_range": use_page_range,
        "start_page_1based": start_page_1based,
        "end_page_1based": end_page_1based,
        "use_fp16": use_fp16,
        "stall_timeout_minutes": int(stall_timeout_minutes),
    }


def _default_stall_timeout_minutes() -> int:
    try:
        value = int(os.environ.get("CONTEXTURE_PIPELINE_STALL_TIMEOUT_MINUTES", "15"))
    except (TypeError, ValueError):
        value = 15
    return max(3, min(180, value))
