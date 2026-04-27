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
from datetime import datetime
from pathlib import Path

import click

from aih_contexture.config.parser import ConfigParser
from aih_contexture.config.printer import CustomClickPrinter
from aih_contexture.converters.pdf import PdfConverter
from aih_contexture.logger import configure_logging, get_logger
from aih_contexture.models import create_model_dict
from aih_contexture.output import save_output, text_from_rendered
from aih_contexture.renderers.chunk import ChunkRenderer
from aih_contexture.renderers.html import HTMLRenderer
from aih_contexture.renderers.json import JSONRenderer
from aih_contexture.renderers.markdown import MarkdownRenderer
from aih_contexture.settings import settings

configure_logging()
logger = get_logger()


def append_text(path: str | None, content: str):
    if not path or not content:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(content)


def write_meta_once(meta: dict, out_dir: str, fname_base: str):
    if not meta:
        return
    meta_path = os.path.join(out_dir, f"{fname_base}_meta.json")
    if os.path.exists(meta_path):
        return
    with open(meta_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(meta, ensure_ascii=False, indent=2))


def save_images(images_dict: dict, out_dir: str):
    if not images_dict:
        return
    from aih_contexture.output import convert_if_not_rgb

    for img_name, img in images_dict.items():
        try:
            img = convert_if_not_rgb(img)
            img.save(os.path.join(out_dir, img_name), settings.OUTPUT_IMAGE_FORMAT)
        except Exception:
            pass


def merge_json_batches(output_path: str, batch_paths: list[str], metadata: dict):
    with open(output_path, "w", encoding="utf-8") as out_f:
        out_f.write('{\n  "children": [\n')
        first_child = True
        for batch_path in batch_paths:
            with open(batch_path, "r", encoding="utf-8") as f:
                batch_data = json.load(f)
            for child in batch_data.get("children", []):
                if not first_child:
                    out_f.write(',\n')
                out_f.write(json.dumps(child, ensure_ascii=False, indent=2))
                first_child = False
            try:
                os.remove(batch_path)
            except OSError:
                pass
        out_f.write('\n  ],\n')
        out_f.write('  "block_type": "Document",\n')
        out_f.write('  "metadata": ')
        out_f.write(json.dumps(metadata, ensure_ascii=False, indent=2))
        out_f.write('\n}')


def merge_chunk_batches(output_path: str, batch_paths: list[str], metadata: dict):
    with open(output_path, "w", encoding="utf-8") as out_f:
        out_f.write('{\n  "blocks": [\n')
        first_block = True
        page_info_items = []
        for batch_path in batch_paths:
            with open(batch_path, "r", encoding="utf-8") as f:
                batch_data = json.load(f)
            for block in batch_data.get("blocks", []):
                if not first_block:
                    out_f.write(',\n')
                out_f.write(json.dumps(block, ensure_ascii=False, indent=2))
                first_block = False
            page_info_items.extend(batch_data.get("page_info", {}).items())
            try:
                os.remove(batch_path)
            except OSError:
                pass
        out_f.write('\n  ],\n')
        out_f.write('  "page_info": {\n')
        for idx, (page_key, page_value) in enumerate(page_info_items):
            if idx > 0:
                out_f.write(',\n')
            out_f.write(f'    {json.dumps(page_key, ensure_ascii=False)}: ')
            out_f.write(json.dumps(page_value, ensure_ascii=False, indent=2))
        out_f.write('\n  },\n')
        out_f.write('  "metadata": ')
        out_f.write(json.dumps(metadata, ensure_ascii=False, indent=2))
        out_f.write('\n}')


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
    start = time.time()
    file_path = job["file_path"]
    file_name = job["file_name"]
    out_dir_final = job["output_dir"]
    output_formats = job["output_formats"]
    fname_base = job["fname_base"]
    batch_jobs = job["batch_jobs"]
    total_batches = len(batch_jobs)

    os.makedirs(out_dir_final, exist_ok=True)

    markdown_path = os.path.join(out_dir_final, f"{fname_base}.md") if "markdown" in output_formats else None
    html_path = os.path.join(out_dir_final, f"{fname_base}.html") if "html" in output_formats else None
    json_batch_paths = []
    chunks_batch_paths = []
    merged_metadata = {}

    for path in (markdown_path, html_path):
        if path and os.path.exists(path):
            os.remove(path)

    artifacts = create_model_dict()
    renderer_map = {
        "markdown": MarkdownRenderer,
        "json": JSONRenderer,
        "html": HTMLRenderer,
        "chunks": ChunkRenderer,
    }
    file_outputs = []

    for bidx, batch_job in enumerate(batch_jobs):
        batch_label = batch_job["label"]
        logger.info("[pipeline-worker] batch %s/%s: %s", bidx + 1, total_batches, batch_label)

        config_dict = batch_job["config_dict"]
        converter = PdfConverter(config=config_dict, artifact_dict=artifacts)
        document = converter.build_document(file_path)

        saved_batch_images = False
        for fmt in output_formats:
            renderer = renderer_map[fmt](config_dict)
            rendered = renderer(document)
            text, _, images = text_from_rendered(rendered)

            if not merged_metadata and getattr(rendered, "metadata", None) is not None:
                merged_metadata = rendered.metadata
                write_meta_once(merged_metadata, out_dir_final, fname_base)

            if fmt == "markdown":
                append_text(markdown_path, text)
                if not saved_batch_images:
                    save_images(images, out_dir_final)
                    saved_batch_images = True
            elif fmt == "html":
                append_text(html_path, text)
                if not saved_batch_images:
                    save_images(images, out_dir_final)
                    saved_batch_images = True
            elif fmt == "json":
                batch_json_path = os.path.join(out_dir_final, f"{fname_base}.json.batch{bidx:04d}")
                with open(batch_json_path, "w", encoding="utf-8") as f:
                    f.write(text)
                json_batch_paths.append(batch_json_path)
            elif fmt == "chunks":
                batch_chunks_path = os.path.join(out_dir_final, f"{fname_base}_chunks.json.batch{bidx:04d}")
                with open(batch_chunks_path, "w", encoding="utf-8") as f:
                    f.write(text)
                chunks_batch_paths.append(batch_chunks_path)

            del renderer, rendered, text, images

        del document, converter

    if "markdown" in output_formats and markdown_path:
        file_outputs.append({"format": "markdown", "path": markdown_path, "name": os.path.basename(markdown_path)})

    if "html" in output_formats and html_path:
        file_outputs.append({"format": "html", "path": html_path, "name": os.path.basename(html_path)})

    if "json" in output_formats:
        jp = os.path.join(out_dir_final, f"{fname_base}.json")
        merge_json_batches(jp, json_batch_paths, merged_metadata)
        file_outputs.append({"format": "json", "path": jp, "name": os.path.basename(jp)})

    if "chunks" in output_formats:
        cp = os.path.join(out_dir_final, f"{fname_base}_chunks.json")
        merge_chunk_batches(cp, chunks_batch_paths, merged_metadata)
        file_outputs.append({"format": "chunks", "path": cp, "name": os.path.basename(cp)})

    result_key = f"{file_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    elapsed = time.time() - start
    return {
        "success": True,
        "file_name": file_name,
        "result_key": result_key,
        "file_outputs": file_outputs,
        "elapsed_seconds": elapsed,
        "error": None,
        "traceback": None,
    }


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
    config_parser = ConfigParser(kwargs)

    converter_cls = config_parser.get_converter_cls()
    converter = converter_cls(
        config=config_parser.generate_config_dict(),
        artifact_dict=models,
        processor_list=config_parser.get_processors(),
        renderer=config_parser.get_renderer(),
        llm_service=config_parser.get_llm_service(),
    )
    rendered = converter(fpath)
    out_folder = config_parser.get_output_folder(fpath)
    save_output(rendered, out_folder, config_parser.get_base_filename(fpath))

    logger.info(f"Saved markdown to {out_folder}")
    logger.info(f"Total time: {time.time() - start}")


if __name__ == "__main__":
    pipeline_exit_code = run_pipeline_job_from_argv(sys.argv[1:])
    if pipeline_exit_code >= 0:
        raise SystemExit(pipeline_exit_code)
    convert_single_cli()
