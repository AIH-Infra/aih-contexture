from __future__ import annotations

from pathlib import Path
from typing import Any

from aih_contexture.backends.catalog import backend_catalog
from aih_contexture.config.parser import ConfigParser
from aih_contexture.models import create_model_dict
from aih_contexture.runtime.artifacts import save_contexture_result
from aih_contexture.runtime.job import ContextureJob
from aih_contexture.runtime.reuse import (
    build_reuse_identity,
    expected_image_paths,
    find_reusable_result,
    primary_artifact_name,
    result_is_reusable,
    write_reuse_manifest,
)
from aih_contexture.runtime.runner import run_job
from aih_contexture.settings import settings


def doctor(*, include_planned: bool = False, probe_services: bool = False, **config: Any) -> dict[str, Any]:
    """Return backend readiness as a JSON-serializable catalog."""
    return backend_catalog(
        implemented_only=not include_planned,
        include_status=True,
        config={"probe_services": probe_services, **config},
    )


def convert_file(
    input_path: str | Path,
    output_dir: str | Path | None = None,
    *,
    layout_backend: str | None = None,
    ocr_backend: str | None = None,
    output_format: str | None = None,
    emit_middle_json: bool | None = None,
    skip_existing: bool = False,
    **config: Any,
) -> dict[str, Any]:
    """Convert one document. Intended for agent / in-process callers.

    Default OCR is text-layer (`ocr_backend='none'`). Pass `ocr_backend='surya'`
    for full OCR. Returns output directory and produced files.
    """
    fpath = str(Path(input_path).expanduser().resolve())
    options: dict[str, Any] = dict(config)
    api_options = {
        "layout_backend": layout_backend,
        "ocr_backend": ocr_backend,
        "output_format": output_format,
        "emit_middle_json": emit_middle_json,
    }
    options.update({key: value for key, value in api_options.items() if value is not None})
    if output_dir is not None:
        options["output_dir"] = str(Path(output_dir).expanduser().resolve())

    parser = ConfigParser(options, explicit_options=options.keys())
    effective_options = parser.get_effective_options()
    effective_options.setdefault("layout_backend", "surya")
    effective_options.setdefault("ocr_backend", "none")
    effective_options.setdefault("output_format", "markdown")
    effective_options.setdefault("emit_middle_json", True)
    output_format = str(effective_options["output_format"])
    output_root = effective_options.get("output_dir") or settings.OUTPUT_DIR
    output_root = str(Path(output_root).expanduser().resolve())
    effective_options["output_dir"] = output_root
    parser = ConfigParser(effective_options, explicit_options=effective_options.keys())
    config_dict = parser.generate_config_dict()
    base_name = parser.get_base_filename(fpath)
    identity = build_reuse_identity(
        fpath,
        source_name=fpath,
        config=config_dict,
        output_formats=[output_format],
    )

    if skip_existing:
        reusable = find_reusable_result(
            output_root,
            identity=identity,
            expected_primary_names=[primary_artifact_name(base_name, output_format)],
        )
        if reusable is not None:
            out_folder = reusable["output_dir"]
            return {
                "success": True,
                "skipped": True,
                "input_path": fpath,
                "output_dir": out_folder,
                "files": _list_output_files(out_folder),
            }

    out_folder = parser.get_output_folder(fpath)
    job_config = dict(effective_options)
    job_config.update(
        {
            "layout_backend": effective_options["layout_backend"],
            "ocr_backend": effective_options["ocr_backend"],
            "output_format": output_format,
            "emit_middle_json": effective_options["emit_middle_json"],
        }
    )
    job = ContextureJob.from_dict(
        {
            "input_path": fpath,
            "mode": "pipeline",
            "output_formats": [output_format],
            "page_range": effective_options.get("page_range"),
            "config": job_config,
        }
    )
    is_text_layer_fast_path = (
        str(effective_options.get("layout_backend") or "").strip().lower().replace("-", "_") == "none"
        and bool(config_dict.get("disable_ocr", False))
    )
    models = None if is_text_layer_fast_path else create_model_dict()
    result = run_job(job, artifact_dict=models)
    save_contexture_result(result, out_folder, base_name, output_format)
    reuse_recorded = False
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
            reuse_recorded = True
        except (OSError, ValueError):
            # A completion marker is optional metadata. A result that was saved
            # successfully remains useful even if its marker cannot be written.
            reuse_recorded = False
    return {
        "success": True,
        "skipped": False,
        "input_path": fpath,
        "output_dir": out_folder,
        "files": _list_output_files(out_folder),
        "reuse_recorded": reuse_recorded,
    }


def _list_output_files(output_dir: str) -> list[str]:
    root = Path(output_dir)
    if not root.exists():
        return []
    return sorted(
        str(path)
        for path in root.iterdir()
        if path.is_file() and not path.name.startswith(".")
    )
