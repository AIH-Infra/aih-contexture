from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from aih_contexture.runtime.pipeline_parallelism import (
    AUTO,
    MANUAL,
    MAX_WORKERS,
    plan_from_values,
    probe_memory,
)

PERFORMANCE_MODE_LABELS = {AUTO: "自动", MANUAL: "手动配置"}


def render_pipeline_run_settings(st, backend_values: Mapping[str, Any] | None = None) -> dict[str, object]:
    backend_values = dict(backend_values or {})
    uses_indra = backend_values.get("layout_backend") == "indra_layout" or backend_values.get("ocr_backend") == "indra_ocr"
    with st.container():
        if st.session_state.get("pipeline_performance_mode") not in PERFORMANCE_MODE_LABELS:
            st.session_state["pipeline_performance_mode"] = AUTO
        performance_mode = st.radio(
            "性能配置",
            options=list(PERFORMANCE_MODE_LABELS),
            format_func=PERFORMANCE_MODE_LABELS.get,
            horizontal=True,
            key="pipeline_performance_mode",
            help=(
                "按 CPU 核心数、可用内存和当前作业页数规划 Indra 内部并行度。"
                if uses_indra
                else "按所选后端的资源档案和可用资源规划并行进程数。"
            ),
        )
        # Migrate before creating widgets; old configs retain their batch size.
        batch_mode = st.session_state.get("pipeline_batch_mode", "分批处理")
        st.session_state["pipeline_batch_mode"] = "整份处理" if batch_mode in {"单批处理", "整份处理"} else "分批处理"
        batch_mode = st.radio(
            "作业处理方式", ["分批处理", "整份处理"], horizontal=True,
            key="pipeline_batch_mode",
        )
        pages_per_batch = int(st.number_input(
            "每批页数", min_value=1, max_value=2000,
            value=int(st.session_state.get("pipeline_pages_per_batch", 100)),
            key="pipeline_pages_per_batch", disabled=batch_mode == "整份处理",
            help="不超过此页数的文件整份处理，超过时按此页数拆分。",
        ))
        st.session_state.pop("pipeline_batch_threshold", None)
        batch_threshold = pages_per_batch
        process_mode = "强制单批" if batch_mode == "整份处理" else "自动"
        probe = probe_memory()
        recommended = plan_from_values({
            **backend_values, "pipeline_performance_mode": AUTO,
            "pages_per_batch": pages_per_batch,
        }, probe=probe)
        cooling_seconds = 0
        if performance_mode == AUTO:
            pipeline_workers = recommended.workers
            st.info(f"推荐：{pipeline_workers} 个任务进程")
            resources = []
            if recommended.worker_vram_gb is not None:
                resources.append(f"每进程预计显存 {recommended.worker_vram_gb:.1f} GB")
            if probe.vram_free_gb is not None:
                resources.append(f"可用显存 {probe.vram_free_gb:.1f} GB")
            if probe.ram_available_gb is not None:
                resources.append(f"可用内存 {probe.ram_available_gb:.1f} GB")
            if resources:
                st.caption(" · ".join(resources))
            for note in recommended.notes:
                st.caption(note)
        else:
            pipeline_workers = int(st.number_input(
                "并行作业进程数", min_value=1, max_value=MAX_WORKERS,
                value=1 if uses_indra else int(st.session_state.get("pipeline_workers", recommended.workers)),
                key="pipeline_workers_indra" if uses_indra else "pipeline_workers",
                disabled=uses_indra,
                help="每个进程处理一个短文件或长文件的一个批次。",
            ))
            if uses_indra:
                pipeline_workers = 1
            manual = plan_from_values({
                **backend_values, "pipeline_performance_mode": MANUAL,
                "pipeline_workers": pipeline_workers, "pages_per_batch": pages_per_batch,
            }, probe=probe)
            for note in manual.notes:
                st.warning(note)

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

        stall_timeout_minutes = st.number_input(
            "无进展自动跳过（分钟）",
            min_value=3,
            max_value=180,
            value=_default_stall_timeout_minutes(),
            step=1,
            key="pipeline_stall_timeout_minutes",
            help="处理进度在此时间内没有更新时，终止当前文件并继续队列。",
        )

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
        "use_fp16": False,
        "stall_timeout_minutes": int(stall_timeout_minutes),
    }


def _default_stall_timeout_minutes() -> int:
    try:
        value = int(os.environ.get("CONTEXTURE_PIPELINE_STALL_TIMEOUT_MINUTES", "15"))
    except (TypeError, ValueError):
        value = 15
    return max(3, min(180, value))
