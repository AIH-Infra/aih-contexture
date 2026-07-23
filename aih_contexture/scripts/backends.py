from __future__ import annotations

import json

import click

from aih_contexture.backends.catalog import backend_catalog
from aih_contexture.backends.external_config import default_mineru_command


@click.command("contexture_backends")
@click.option("--all", "include_planned", is_flag=True, help="Include planned but unimplemented backends.")
@click.option("--status", "include_status", is_flag=True, help="Include optional dependency and service diagnostics.")
@click.option("--json-output", is_flag=True, help="Print raw JSON instead of a compact table.")
@click.option("--mineru-command", default=None, help="Legacy MinerU command used for full-pipeline diagnostic/import workflows.")
@click.option("--paddle-python", default=None, help="External Python used for Paddle sidecar diagnostics.")
@click.option("--probe-services", is_flag=True, help="Probe configured HTTP/model services instead of only reporting configuration requirements.")
@click.option("--health-timeout", default=3.0, type=float, show_default=True, help="Timeout in seconds for service probes.")
@click.option("--openai-base-url", default=None, help="OpenAI-compatible base URL used for VLM service diagnostics.")
@click.option("--ocr-endpoint", default=None, help="OCR/VLM endpoint used for specialized VLM diagnostics.")
@click.option("--calamari-base-url", default=None, help="Calamari service base URL used for health diagnostics.")
@click.option("--paddleocr-vl-endpoint", default=None, help="PaddleOCR-VL endpoint used for service diagnostics.")
@click.option("--surya2-endpoint", default=None, help="Surya 2 endpoint used for service diagnostics.")
def backends_cli(
    include_planned: bool,
    include_status: bool,
    json_output: bool,
    mineru_command: str,
    paddle_python: str | None,
    probe_services: bool,
    health_timeout: float,
    openai_base_url: str | None,
    ocr_endpoint: str | None,
    calamari_base_url: str | None,
    paddleocr_vl_endpoint: str | None,
    surya2_endpoint: str | None,
) -> None:
    catalog = backend_catalog(
        implemented_only=not include_planned,
        include_status=include_status,
        config={
            "mineru_command": mineru_command or default_mineru_command(),
            "paddle_python": paddle_python,
            "probe_services": probe_services,
            "backend_health_timeout": health_timeout,
            "openai_base_url": openai_base_url,
            "ocr_endpoint": ocr_endpoint,
            "calamari_base_url": calamari_base_url,
            "paddleocr_vl_endpoint": paddleocr_vl_endpoint,
            "surya2_endpoint": surya2_endpoint,
        },
    )
    if json_output:
        click.echo(json.dumps(catalog, ensure_ascii=False, indent=2))
        return

    for kind in ("layout", "ocr", "vlm"):
        click.echo(f"{kind}:")
        for backend in catalog[kind]:
            suffix = ""
            if include_status:
                status = backend["status"]
                suffix = f" [{status['level']}: {status['message']}]"
            click.echo(f"  - {backend['name']} ({backend['display_name']}){suffix}")


if __name__ == "__main__":
    backends_cli()
