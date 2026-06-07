import os

os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GLOG_minloglevel"] = "2"
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = (
    "1"  # Transformers uses .isin for a simple op, which is not supported on MPS
)

import json
import sys
import time
import traceback

import click

from aih_contexture.config.parser import ConfigParser
from aih_contexture.config.printer import CustomClickPrinter
from aih_contexture.logger import configure_logging, get_logger
from aih_contexture.models import create_model_dict
from aih_contexture.runtime.artifacts import (
    process_pipeline_job as runtime_process_pipeline_job,
    save_contexture_result,
)
from aih_contexture.runtime.job import ContextureJob
from aih_contexture.runtime.runner import run_job

configure_logging()
logger = get_logger()


def write_pipeline_result(result_path: str | None, payload: dict):
    if result_path:
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    else:
        click.echo(json.dumps(payload, ensure_ascii=False))


def run_pipeline_job_from_argv(argv: list[str]) -> int:
    pipeline_job_json = None
    pipeline_result_json = None

    idx = 0
    while idx < len(argv):
        arg = argv[idx]
        if arg == "--pipeline_job_json" and idx + 1 < len(argv):
            pipeline_job_json = argv[idx + 1]
            idx += 2
            continue
        if arg == "--pipeline_result_json" and idx + 1 < len(argv):
            pipeline_result_json = argv[idx + 1]
            idx += 2
            continue
        idx += 1

    if not pipeline_job_json:
        return -1

    try:
        with open(pipeline_job_json, "r", encoding="utf-8") as f:
            job = json.load(f)
        result = process_pipeline_job(job)
        write_pipeline_result(pipeline_result_json, result)
        return 0
    except Exception as e:
        result = {
            "success": False,
            "file_name": None,
            "result_key": None,
            "file_outputs": [],
            "elapsed_seconds": None,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }
        write_pipeline_result(pipeline_result_json, result)
        return 1


def process_pipeline_job(job: dict) -> dict:
    return runtime_process_pipeline_job(job)


@click.command(cls=CustomClickPrinter, help="Convert a single PDF to markdown.")
@click.argument("fpath", type=str, required=False)
@click.option("--pipeline_job_json", type=str, default=None, help="Path to a serialized pipeline file job.")
@click.option("--pipeline_result_json", type=str, default=None, help="Path to write pipeline job result JSON.")
@ConfigParser.common_options
def convert_single_cli(fpath: str = None, pipeline_job_json: str = None, pipeline_result_json: str = None, **kwargs):
    if pipeline_job_json:
        try:
            with open(pipeline_job_json, "r", encoding="utf-8") as f:
                job = json.load(f)
            result = process_pipeline_job(job)
            write_pipeline_result(pipeline_result_json, result)
            return
        except Exception as e:
            result = {
                "success": False,
                "file_name": None,
                "result_key": None,
                "file_outputs": [],
                "elapsed_seconds": None,
                "error": str(e),
                "traceback": traceback.format_exc(),
            }
            write_pipeline_result(pipeline_result_json, result)
            raise SystemExit(1)

    if not fpath:
        raise click.UsageError("Missing argument 'FPATH' or --pipeline_job_json.")

    models = create_model_dict()
    start = time.time()
    output_format = kwargs.get("output_format", "markdown")
    config_parser = ConfigParser(kwargs)
    job = ContextureJob.from_dict(
        {
            "input_path": fpath,
            "mode": "pipeline",
            "output_formats": [output_format],
            "page_range": kwargs.get("page_range"),
            "config": kwargs,
        }
    )
    result = run_job(job, artifact_dict=models)
    out_folder = config_parser.get_output_folder(fpath)
    save_contexture_result(result, out_folder, config_parser.get_base_filename(fpath), output_format)

    logger.info(f"Saved markdown to {out_folder}")
    logger.info(f"Total time: {time.time() - start}")


if __name__ == "__main__":
    pipeline_exit_code = run_pipeline_job_from_argv(sys.argv[1:])
    if pipeline_exit_code >= 0:
        raise SystemExit(pipeline_exit_code)
    convert_single_cli()
