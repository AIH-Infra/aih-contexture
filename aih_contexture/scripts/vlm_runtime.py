"""Command-line entry points for Contexture's direct VLM runtime modes.

The GUI builds a rich runtime configuration before calling ``run_job``.  These
commands expose the same two runtime modes for headless and SSH use while
keeping an escape hatch (``--config-json`` / ``--set``) for every converter
setting, including newly added ones.
"""

from __future__ import annotations

import json
import time
import os
from pathlib import Path
from typing import Any

import click

from aih_contexture.runtime.job import ContextureJob
from aih_contexture.runtime.output_contract import document_output_folder
from aih_contexture.runtime.run_summary import allocate_processing_id, utc_now_iso, write_document_summary
from aih_contexture.runtime.runner import run_job
from aih_contexture.scripts.ui.vlm_config import (
    build_vlm_generalized_config,
    build_vlm_specialized_config,
)
from aih_contexture.scripts.ui.vlm_output_saver import (
    save_vlm_generalized_outputs,
    save_vlm_specialized_outputs,
)


_OUTPUT_FORMATS = ("markdown", "json", "html")
_SENSITIVE_CONFIG_MARKERS = ("api_key", "api_keys", "secret", "password")


def _load_config_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise click.ClickException("--config-json must contain one JSON object.")
    return payload


def _parse_set_values(values: tuple[str, ...]) -> dict[str, Any]:
    config: dict[str, Any] = {}
    for item in values:
        key, separator, raw_value = item.partition("=")
        key = key.strip()
        if not separator or not key:
            raise click.ClickException("--set must use KEY=VALUE, for example --set ocr_timeout=600.")
        try:
            config[key] = json.loads(raw_value)
        except json.JSONDecodeError:
            config[key] = raw_value
    return config


def _redact_config(config: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in config.items():
        normalized_key = key.lower()
        is_token = normalized_key == "token" or normalized_key.endswith("_token")
        if any(marker in normalized_key for marker in _SENSITIVE_CONFIG_MARKERS) or is_token:
            redacted[key] = "***" if value else value
        elif isinstance(value, dict):
            redacted[key] = _redact_config(value)
        else:
            redacted[key] = value
    return redacted


def _add_if_set(config: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        config[key] = value


def _resolve_api_key(explicit_value: str | None, environment_name: str | None) -> str | None:
    if explicit_value:
        return explicit_value
    if environment_name:
        value = os.environ.get(environment_name)
        if value:
            return value
    return None


def _runtime_config(
    *,
    mode: str,
    config_json: Path | None,
    set_values: tuple[str, ...],
    output_formats: tuple[str, ...],
    page_range: str | None,
    explicit_values: dict[str, Any],
) -> dict[str, Any]:
    params = _load_config_json(config_json)
    params.update(_parse_set_values(set_values))
    params["conversion_mode"] = mode
    params["output_formats"] = list(output_formats)
    params["final_output_formats"] = list(output_formats)
    if page_range:
        params["page_range"] = page_range
    for key, value in explicit_values.items():
        _add_if_set(params, key, value)

    # These are the same builders used by the GUI.  Merge the source params
    # back afterwards so unknown/new runtime keys pass through untouched.
    if mode == "vlm_generalized":
        runtime_config, _ = build_vlm_generalized_config(
            params,
            output_formats=list(output_formats),
            template_manager=None,
        )
    else:
        runtime_config = build_vlm_specialized_config(
            params,
            output_formats=list(output_formats),
        )
    runtime_config.update(params)
    # GUI builders retain ``None`` for optional widgets.  Direct converter
    # constructors use ``dict.get(key, default)`` plus numeric casts, so an
    # explicit None would suppress their defaults and fail at runtime.
    runtime_config = {key: value for key, value in runtime_config.items() if value is not None}
    runtime_config["conversion_mode"] = mode
    # Middle JSON is a mandatory canonical artifact.
    runtime_config["emit_middle_json"] = True
    return runtime_config


def _save_result(
    *,
    mode: str,
    result,
    output_dir: Path,
    input_path: Path,
    output_formats: tuple[str, ...],
    config: dict[str, Any],
) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    shared = {
        "result": result,
        "markdown_text": result.markdown or "",
        "output_dir": str(output_dir),
        "fname_base": input_path.stem,
        "file_name": input_path.name,
        "output_formats": output_formats,
        "emit_middle_json": True,
        "emit_middle_report": bool(config.get("emit_middle_report", False)),
        "emit_middle_debug": bool(config.get("emit_middle_debug", False)),
        "emit_middle_scholarly": bool(config.get("emit_middle_scholarly", False)),
        "emit_middle_scholarly_report": bool(config.get("emit_middle_scholarly_report", False)),
        "emit_layout_overlay": bool(config.get("emit_layout_overlay", False)),
        "emit_span_overlay": bool(config.get("emit_span_overlay", False)),
        "emit_middle_full_json": bool(config.get("emit_middle_full_json", False)),
    }
    if mode == "vlm_generalized":
        return save_vlm_generalized_outputs(**shared)
    return save_vlm_specialized_outputs(converter=None, **shared)


def _run_cli(
    *,
    mode: str,
    input_path: Path,
    output_dir: Path,
    output_formats: tuple[str, ...],
    page_range: str | None,
    config_json: Path | None,
    set_values: tuple[str, ...],
    dry_run: bool,
    explicit_values: dict[str, Any],
) -> None:
    config = _runtime_config(
        mode=mode,
        config_json=config_json,
        set_values=set_values,
        output_formats=output_formats,
        page_range=page_range,
        explicit_values=explicit_values,
    )
    # Keep the caller-provided directory as a root and isolate this source
    # document in a timestamped child directory.
    document_dir = Path(document_output_folder(output_dir, input_path))
    processing_id = allocate_processing_id(output_dir)
    started_at = utc_now_iso()
    started_clock = time.perf_counter()
    summary = {
        "mode": mode,
        "input_path": str(input_path),
        "output_dir": str(document_dir),
        "output_formats": list(output_formats),
        "config": _redact_config(config),
    }
    if dry_run:
        click.echo(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    job = ContextureJob(
        input_path=str(input_path),
        input_name=input_path.name,
        mode=mode,  # type: ignore[arg-type]
        output_formats=list(output_formats),
        page_range=None,
        config=config,
    )
    try:
        result = run_job(job)
        outputs = _save_result(
            mode=mode,
            result=result,
            output_dir=document_dir,
            input_path=input_path,
            output_formats=output_formats,
            config=config,
        )
        write_document_summary(
            output_dir=document_dir, source_name=input_path.name, processing_id=processing_id,
            file_index=1, mode=mode, strategy=mode,
            models={"vlm": config.get("vlm_direct_model") or config.get("ocr_model") or config.get("ocr_backend")},
            config=config, started_at=started_at, finished_at=utc_now_iso(),
            elapsed_seconds=time.perf_counter() - started_clock, status="succeeded", page_count=result.page_count,
            output_paths=outputs, warnings=result.warnings, errors=[], source_path=input_path,
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    summary.update(
        {
            "success": True,
            "page_count": result.page_count,
            "failed_pages": result.failed_pages,
            "outputs": outputs,
        }
    )
    click.echo(json.dumps(summary, ensure_ascii=False, indent=2))


_COMMON_OPTIONS = [
    click.argument("input_path", type=click.Path(exists=True, dir_okay=False, path_type=Path)),
    click.option("--output-dir", type=click.Path(file_okay=False, path_type=Path), default=Path("output"), show_default=True),
    click.option("--output-format", "output_formats", type=click.Choice(_OUTPUT_FORMATS), multiple=True, default=("markdown",), show_default=True, help="Repeat to save multiple derived outputs."),
    click.option("--page-range", type=str, default=None, help="Pages such as 0,2-4."),
    click.option("--config-json", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None, help="JSON object with any runtime configuration keys."),
    click.option("--set", "set_values", multiple=True, metavar="KEY=VALUE", help="Override or pass through any runtime key; VALUE accepts JSON."),
    click.option("--dry-run", is_flag=True, help="Print the resolved, redacted runtime configuration without running inference."),
]


@click.command(help="Run Contexture's generalized VLM mode from the command line.")
@click.option("--base-url", type=str, default=None, help="OpenAI-compatible base URL, e.g. http://127.0.0.1:1234/v1.")
@click.option("--model", type=str, default=None, help="Model name exposed by the VLM service.")
@click.option("--api-key", type=str, default=None, help="API key; prefer --api-key-env on shared shells.")
@click.option("--api-key-env", type=str, default="CONTEXTURE_VLM_API_KEY", show_default=True, help="Environment variable used when --api-key is absent.")
@click.option("--prompt", type=str, default=None, help="Override vlm_direct_prompt.")
@click.option("--max-concurrent", type=int, default=None, help="Override vlm_direct_max_concurrent.")
@click.option("--timeout", type=int, default=None, help="Override vlm_direct_timeout in seconds.")
@click.option("--max-tokens", type=int, default=None, help="Override vlm_direct_max_tokens.")
@click.option("--output-mode", type=click.Choice(["json", "markdown"]), default=None, help="Underlying VLM response mode.")
@_COMMON_OPTIONS[0]
@_COMMON_OPTIONS[1]
@_COMMON_OPTIONS[2]
@_COMMON_OPTIONS[3]
@_COMMON_OPTIONS[4]
@_COMMON_OPTIONS[5]
@_COMMON_OPTIONS[6]
def vlm_generalized_cli(
    input_path: Path,
    output_dir: Path,
    output_formats: tuple[str, ...],
    page_range: str | None,
    config_json: Path | None,
    set_values: tuple[str, ...],
    dry_run: bool,
    base_url: str | None,
    model: str | None,
    api_key: str | None,
    api_key_env: str | None,
    prompt: str | None,
    max_concurrent: int | None,
    timeout: int | None,
    max_tokens: int | None,
    output_mode: str | None,
) -> None:
    _run_cli(
        mode="vlm_generalized",
        input_path=input_path,
        output_dir=output_dir,
        output_formats=output_formats,
        page_range=page_range,
        config_json=config_json,
        set_values=set_values,
        dry_run=dry_run,
        explicit_values={
            "vlm_direct_base_url": base_url,
            "vlm_direct_model": model,
            "vlm_direct_api_key": _resolve_api_key(api_key, api_key_env),
            "vlm_direct_prompt": prompt,
            "vlm_direct_max_concurrent": max_concurrent,
            "vlm_direct_timeout": timeout,
            "vlm_direct_max_tokens": max_tokens,
            "vlm_direct_output_mode": output_mode,
        },
    )


@click.command(help="Run Contexture's specialized VLM/OCR mode from the command line.")
@click.option("--backend", type=str, default="chandra", show_default=True, help="Specialized backend, e.g. chandra, mineru_vl, paddleocr_vl, surya2, or churro.")
@click.option("--endpoint", type=str, default=None, help="LM Studio/native service endpoint. Defaults to localhost:1234 for the selected API style.")
@click.option("--api-style", type=click.Choice(["lmstudio-native", "openai", "openai-compatible"]), default=None, help="LM Studio native is the default for most specialized backends.")
@click.option("--model", type=str, default=None, help="Model name mounted by LM Studio.")
@click.option("--api-key", type=str, default=None, help="API key; LM Studio accepts a placeholder such as lm-studio.")
@click.option("--api-key-env", type=str, default="CONTEXTURE_OCR_API_KEY", show_default=True, help="Environment variable used when --api-key is absent.")
@click.option("--ocr-output-format", type=click.Choice(["json", "html", "markdown", "xml"]), default=None, help="Native response representation requested from the specialized backend.")
@click.option("--concurrency", type=int, default=None, help="Override ocr_concurrency.")
@click.option("--timeout", type=int, default=None, help="Override ocr_timeout in seconds.")
@click.option("--max-tokens", type=int, default=None, help="Override ocr_max_tokens.")
@_COMMON_OPTIONS[0]
@_COMMON_OPTIONS[1]
@_COMMON_OPTIONS[2]
@_COMMON_OPTIONS[3]
@_COMMON_OPTIONS[4]
@_COMMON_OPTIONS[5]
@_COMMON_OPTIONS[6]
def vlm_specialized_cli(
    input_path: Path,
    output_dir: Path,
    output_formats: tuple[str, ...],
    page_range: str | None,
    config_json: Path | None,
    set_values: tuple[str, ...],
    dry_run: bool,
    backend: str,
    endpoint: str | None,
    api_style: str | None,
    model: str | None,
    api_key: str | None,
    api_key_env: str | None,
    ocr_output_format: str | None,
    concurrency: int | None,
    timeout: int | None,
    max_tokens: int | None,
) -> None:
    _run_cli(
        mode="vlm_specialized",
        input_path=input_path,
        output_dir=output_dir,
        output_formats=output_formats,
        page_range=page_range,
        config_json=config_json,
        set_values=set_values,
        dry_run=dry_run,
        explicit_values={
            "ocr_backend": backend,
            "ocr_endpoint": endpoint,
            "ocr_api_style": api_style,
            "ocr_model": model,
            "ocr_api_key": _resolve_api_key(api_key, api_key_env),
            "ocr_output_format": ocr_output_format,
            "ocr_concurrency": concurrency,
            "ocr_timeout": timeout,
            "ocr_max_tokens": max_tokens,
        },
    )


if __name__ == "__main__":
    vlm_generalized_cli()
