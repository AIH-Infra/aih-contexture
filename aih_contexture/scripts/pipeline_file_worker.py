"""Process successive file jobs while keeping the models and sidecars alive."""
from __future__ import annotations

import json
import sys

RESULT_PREFIX = "@@CONTEXTURE_FILE_RESULT@@ "


def serve(input_stream=None, output_stream=None, *, model_factory=None, pool_factory=None, process_job=None):
    from aih_contexture.backends.sidecar_pool import SidecarRuntimePool
    from aih_contexture.models import create_model_dict
    from aih_contexture.runtime.artifacts import process_pipeline_job
    from aih_contexture.runtime.progress_events import clear_progress_context
    from aih_contexture.scripts.convert_single import failed_pipeline_result, write_pipeline_result

    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    artifacts = (model_factory or create_model_dict)()
    pool = (pool_factory or SidecarRuntimePool)()
    try:
        for line in input_stream:
            request = json.loads(line)
            if request.get("shutdown"):
                break
            job = request["job"]
            result_path = request["result_path"]
            job["_pipeline_result_json"] = result_path
            # The outer queue owns concurrency; never start nested GPU pools.
            job["pipeline_workers"] = 1
            clear_progress_context()
            try:
                result = (process_job or process_pipeline_job)(job, artifacts=artifacts, sidecar_pool=pool)
            except Exception as exc:
                result = failed_pipeline_result(result_path, exc)
            write_pipeline_result(result_path, result)
            output_stream.write(RESULT_PREFIX + request["request_id"] + "\n")
            output_stream.flush()
    finally:
        pool.close_all()


if __name__ == "__main__":
    serve()
