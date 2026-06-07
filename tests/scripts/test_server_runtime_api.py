from aih_contexture.runtime.job import ContextureJob
from aih_contexture.scripts import server


def test_runtime_convert_error_response_is_stable_without_printing_traceback(monkeypatch):
    def fail_run_job(job, artifact_dict=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(server, "run_job", fail_run_job)
    server.app_data["models"] = {}

    response = server._run_job_response(
        ContextureJob(input_path="sample.pdf", mode="pipeline", output_formats=["markdown"]),
        "markdown",
    )

    assert response == {
        "success": False,
        "error": "boom",
    }


def test_runtime_convert_params_marks_filepath_as_trusted_local_bridge():
    schema = server.RuntimeConvertParams.model_json_schema()
    description = schema["properties"]["filepath"]["description"]

    assert "trusted local deployments" in description
    assert "upload/storage-root job submission" in description

