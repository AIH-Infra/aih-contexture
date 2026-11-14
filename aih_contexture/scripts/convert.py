import atexit
import os
import time

import psutil
try:
    import torch
    import torch.multiprocessing as mp
except (ImportError, OSError):
    torch = None
    import multiprocessing as mp

from aih_contexture.utils.batch import get_batch_sizes_worker_counts

# Ensure threads don't contend
os.environ["MKL_DYNAMIC"] = "FALSE"
os.environ["OMP_DYNAMIC"] = "FALSE"
os.environ["OMP_NUM_THREADS"] = "2"  # Avoid OpenMP issues with multiprocessing
os.environ["OPENBLAS_NUM_THREADS"] = "2"
os.environ["MKL_NUM_THREADS"] = "2"
os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GLOG_minloglevel"] = "2"
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = (
    "1"  # Transformers uses .isin for a simple op, which is not supported on MPS
)
os.environ["IN_STREAMLIT"] = "true"  # Avoid multiprocessing inside surya

import math
import traceback

import click
from tqdm import tqdm
import gc

from aih_contexture.config.parser import ConfigParser
from aih_contexture.config.printer import CustomClickPrinter
from aih_contexture.logger import configure_logging, get_logger
from aih_contexture.models import create_model_dict
from aih_contexture.runtime.artifacts import save_contexture_result
from aih_contexture.runtime.indra_pipeline import is_indra_direct
from aih_contexture.runtime.job import ContextureJob
from aih_contexture.runtime.runner import run_job
from aih_contexture.runtime.reuse import (
    build_reuse_identity,
    expected_image_paths,
    find_reusable_result,
    primary_artifact_name,
    result_is_reusable,
    write_reuse_manifest,
)
from aih_contexture.settings import settings
from aih_contexture.utils.gpu import GPUManager

configure_logging()
logger = get_logger()


def worker_init():
    global model_refs
    # Do not create models at worker startup.  The text-layer fast path is
    # intentionally model-free; regular Pipeline jobs initialize lazily on
    # their first use below.
    model_refs = None

    # Ensure we clean up the model references on exit
    atexit.register(worker_exit)


def worker_exit():
    global model_refs
    try:
        if model_refs is None:
            return
        release_all = getattr(model_refs, "release_all", None)
        if callable(release_all):
            release_all()
        del model_refs
    except Exception:
        pass


def process_single_pdf(args):
    global model_refs
    page_count = 0
    fpath, cli_options = args
    cli_options = dict(cli_options)
    total_torch_threads = cli_options.pop("total_torch_threads")
    if torch is not None:
        torch.set_num_threads(total_torch_threads)

    config_parser = ConfigParser(cli_options, explicit_options=cli_options.keys())
    effective_options = config_parser.get_effective_options()
    effective_options.setdefault("output_format", "markdown")
    output_root = str(
        os.path.abspath(
            os.path.expanduser(effective_options.get("output_dir") or settings.OUTPUT_DIR)
        )
    )
    effective_options["output_dir"] = output_root
    config_parser = ConfigParser(effective_options, explicit_options=effective_options.keys())
    base_name = config_parser.get_base_filename(fpath)
    output_format = str(effective_options.get("output_format") or "markdown")
    config_dict = config_parser.generate_config_dict()
    identity = build_reuse_identity(
        fpath,
        source_name=fpath,
        config=config_dict,
        output_formats=[output_format],
    )
    if effective_options.get("skip_existing"):
        reusable = find_reusable_result(
            output_root,
            identity=identity,
            expected_primary_names=[primary_artifact_name(base_name, output_format)],
        )
        if reusable is not None:
            return page_count

    # Allocate exactly one timestamped directory after reuse lookup. The old
    # output_exists check created a fresh timestamp directory first, which
    # made previously completed results impossible to find.
    out_folder = config_parser.get_output_folder(fpath)

    try:
        if cli_options.get("debug_print"):
            logger.debug(f"Converting {fpath}")
        effective_options["disable_tqdm"] = True
        job = ContextureJob.from_dict(
            {
                "input_path": fpath,
                "mode": "pipeline",
                "output_formats": [output_format],
                "page_range": effective_options.get("page_range"),
                "config": effective_options,
            }
        )
        is_text_layer_fast_path = (
            str(effective_options.get("layout_backend") or "").strip().lower().replace("-", "_") == "none"
            and bool(config_dict.get("disable_ocr", False))
        )
        skip_models = is_text_layer_fast_path or is_indra_direct(effective_options)
        if not skip_models and model_refs is None:
            model_refs = create_model_dict()
        result = run_job(job, artifact_dict=None if skip_models else model_refs)
        save_contexture_result(result, out_folder, base_name, output_format)
        page_count = result.page_count
        image_paths = expected_image_paths(result, out_folder)
        if result_is_reusable(result) and image_paths is not None:
            try:
                write_reuse_manifest(
                    out_folder,
                    identity=identity,
                    primary_names=[primary_artifact_name(base_name, output_format)],
                    required_paths=image_paths,
                    source_path=fpath,
                )
            except (OSError, ValueError):
                logger.warning("Could not record reusable result manifest for %s", fpath)

        if cli_options.get("debug_print"):
            logger.debug(f"Converted {fpath}")
        del result
    except Exception as e:
        logger.error(f"Error converting {fpath}: {e}")
        traceback.print_exc()
    finally:
        gc.collect()

    return page_count


@click.command(cls=CustomClickPrinter)
@click.argument("in_folder", type=str)
@click.option("--chunk_idx", type=int, default=0, help="Chunk index to convert")
@click.option(
    "--num_chunks",
    type=int,
    default=1,
    help="Number of chunks being processed in parallel",
)
@click.option(
    "--max_files", type=int, default=None, help="Maximum number of pdfs to convert"
)
@click.option(
    "--skip_existing",
    is_flag=True,
    default=False,
    help="Skip existing converted files.",
)
@click.option(
    "--debug_print", is_flag=True, default=False, help="Print debug information."
)
@click.option(
    "--max_tasks_per_worker",
    type=int,
    default=10,
    help="Maximum number of tasks per worker process before recycling.",
)
@click.option(
    "--workers",
    type=int,
    default=None,
    help="Number of worker processes to use.  Set automatically by default, but can be overridden.",
)
@ConfigParser.common_options
def convert_cli(in_folder: str, **kwargs):
    total_pages = 0
    config_parser = ConfigParser.from_click(kwargs)
    effective_options = config_parser.get_effective_options()
    effective_options.setdefault("output_format", "markdown")
    effective_options.setdefault("output_dir", settings.OUTPUT_DIR)
    effective_options["output_dir"] = str(
        os.path.abspath(os.path.expanduser(effective_options["output_dir"]))
    )
    in_folder = os.path.abspath(in_folder)
    files = [os.path.join(in_folder, f) for f in os.listdir(in_folder)]
    files = [f for f in files if os.path.isfile(f)]

    # Handle chunks if we're processing in parallel
    # Ensure we get all files into a chunk
    chunk_size = math.ceil(len(files) / effective_options["num_chunks"])
    start_idx = effective_options["chunk_idx"] * chunk_size
    end_idx = start_idx + chunk_size
    files_to_convert = files[start_idx:end_idx]

    # Limit files converted if needed
    if effective_options.get("max_files"):
        files_to_convert = files_to_convert[: effective_options["max_files"]]

    # Disable nested multiprocessing
    effective_options["disable_multiprocessing"] = True

    try:
        mp.set_start_method("spawn")  # Required for CUDA, forkserver doesn't work
    except RuntimeError:
        raise RuntimeError(
            "Set start method to spawn twice. This may be a temporary issue with the script. Please try running it again."
        )

    chunk_idx = effective_options["chunk_idx"]

    # Use GPU context manager for automatic setup/cleanup
    with GPUManager(chunk_idx) as gpu_manager:
        batch_sizes, workers = get_batch_sizes_worker_counts(gpu_manager, 7)

        # Override workers if specified
        if effective_options.get("workers") is not None:
            workers = effective_options["workers"]

        # Set proper batch sizes and thread counts
        total_processes = max(1, min(len(files_to_convert), workers))
        effective_options["total_torch_threads"] = max(
            2, psutil.cpu_count(logical=False) // total_processes
        )
        effective_options.update(batch_sizes)

        logger.info(
            f"Converting {len(files_to_convert)} pdfs in chunk {effective_options['chunk_idx'] + 1}/{effective_options['num_chunks']} with {total_processes} processes and saving to {effective_options['output_dir']}"
        )
        task_args = [(f, effective_options) for f in files_to_convert]

        start_time = time.time()
        with mp.Pool(
            processes=total_processes,
            initializer=worker_init,
            maxtasksperchild=effective_options["max_tasks_per_worker"],
        ) as pool:
            pbar = tqdm(total=len(task_args), desc="Processing PDFs", unit="pdf")
            for page_count in pool.imap_unordered(process_single_pdf, task_args):
                pbar.update(1)
                total_pages += page_count
            pbar.close()

        total_time = time.time() - start_time
        print(
            f"Inferenced {total_pages} pages in {total_time:.2f} seconds, for a throughput of {total_pages / total_time:.2f} pages/sec for chunk {chunk_idx + 1}/{effective_options['num_chunks']}"
        )

if __name__ == "__main__":
    convert_cli()
