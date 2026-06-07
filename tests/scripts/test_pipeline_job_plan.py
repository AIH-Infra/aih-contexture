from aih_contexture.scripts.ui.pipeline_job_plan import (
    build_pipeline_batch_jobs,
    build_pipeline_file_job_spec,
)
from aih_contexture.runtime.config_builder import config_from_ui_params


def test_build_pipeline_batch_jobs_uses_page_labels_and_config_builder():
    seen = []

    def fake_config_builder(config_params):
        seen.append(dict(config_params))
        return {
            "page_range": config_params["page_range"],
            "layout_backend": config_params["layout_backend"],
            "ocr_backend": config_params["ocr_backend"],
        }

    jobs = build_pipeline_batch_jobs(
        [(0, 2), (2, 5)],
        {
            "conversion_mode": "pipeline",
            "layout_backend": "surya",
            "ocr_backend": "none",
            "use_llm": False,
        },
        fake_config_builder,
    )

    assert jobs == [
        {"label": "1-2", "config_dict": {"page_range": "0-1", "layout_backend": "surya", "ocr_backend": "none"}},
        {"label": "3-5", "config_dict": {"page_range": "2-4", "layout_backend": "surya", "ocr_backend": "none"}},
    ]
    assert [item["page_range"] for item in seen] == ["0-1", "2-4"]


def test_build_pipeline_batch_jobs_uses_runtime_config_mapping_for_backends():
    jobs = build_pipeline_batch_jobs(
        [(0, 1)],
        {
            "conversion_mode": "pipeline",
            "layout_backend": "vlm_layout",
            "ocr_backend": "vlm_ocr",
            "use_llm": False,
            "vlm_layout_base_url": "http://localhost:1234/v1",
            "vlm_layout_model": "qwen-vl",
            "vlm_layout_max_concurrent": 4,
            "openai_base_url": "http://localhost:1234/v1",
            "openai_model": "churro",
            "openai_max_concurrent": 6,
            "vlm_mode": "merge",
            "emit_middle_json": True,
        },
        config_from_ui_params,
    )

    config = jobs[0]["config_dict"]
    assert config["page_range"] == [0]
    assert config["layout_backend"] == "vlm_layout"
    assert config["vlm_layout_model"] == "qwen-vl"
    assert config["vlm_layout_max_concurrent"] == 4
    assert config["vlm_layout_batch_size"] == 4
    assert config["ocr_backend"] == "vlm_ocr"
    assert config["openai_max_concurrent"] == 6
    assert config["vlm_merge_enabled"] is True
    assert config["emit_middle_json"] is True


def test_build_pipeline_file_job_spec_preserves_worker_payload_shape():
    batch_jobs = [{"label": "1-1", "config_dict": {"page_range": [0]}}]

    job = build_pipeline_file_job_spec(
        file_path="input.pdf",
        file_name="input.pdf",
        output_dir="out",
        output_formats=("markdown", "json"),
        fname_base="input_20260509_120000",
        batch_jobs=batch_jobs,
    )

    assert job == {
        "file_path": "input.pdf",
        "file_name": "input.pdf",
        "output_dir": "out",
        "output_formats": ["markdown", "json"],
        "fname_base": "input_20260509_120000",
        "batch_jobs": batch_jobs,
    }
