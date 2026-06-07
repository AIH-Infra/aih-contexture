from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from aih_contexture.scripts.ui.pipeline_config_sections import pipeline_config_for_page_range


def build_pipeline_batch_jobs(
    page_ranges: Sequence[tuple[int, int]],
    values: Mapping[str, Any],
    config_builder: Callable[[dict[str, Any]], dict[str, Any]],
) -> list[dict[str, Any]]:
    batch_jobs: list[dict[str, Any]] = []
    for start, end in page_ranges:
        config_params = pipeline_config_for_page_range((start, end), values)
        batch_jobs.append({
            "label": f"{start + 1}-{end}",
            "config_dict": config_builder(config_params),
        })
    return batch_jobs


def build_pipeline_file_job_spec(
    *,
    file_path: str,
    file_name: str,
    output_dir: str,
    output_formats: Sequence[str],
    fname_base: str,
    batch_jobs: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "file_path": file_path,
        "file_name": file_name,
        "output_dir": output_dir,
        "output_formats": list(output_formats),
        "fname_base": fname_base,
        "batch_jobs": list(batch_jobs),
    }
