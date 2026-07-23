from __future__ import annotations

import json

import click

from aih_contexture.backends.catalog import backend_catalog
from aih_contexture.backends.external_config import default_mineru_command


@click.command("contexture_doctor")
@click.option("--all", "include_planned", is_flag=True, help="Include planned but unimplemented backends.")
@click.option("--json-output", is_flag=True, help="Print raw JSON instead of a compact report.")
@click.option("--probe-services", is_flag=True, help="Probe configured HTTP/model services.")
@click.option("--health-timeout", default=3.0, type=float, show_default=True, help="Timeout in seconds for service probes.")
@click.option("--mineru-command", default=None, help="Legacy MinerU command used for full-pipeline diagnostic/import workflows.")
@click.option("--paddle-python", default=None, help="External Python used for Paddle sidecar diagnostics.")
@click.option("--openai-base-url", default=None, help="OpenAI-compatible base URL used for VLM service diagnostics.")
@click.option("--ocr-endpoint", default=None, help="OCR/VLM endpoint used for specialized VLM diagnostics.")
@click.option("--calamari-base-url", default=None, help="Calamari service base URL used for health diagnostics.")
@click.option("--paddleocr-vl-endpoint", default=None, help="PaddleOCR-VL endpoint used for service diagnostics.")
def doctor_cli(
    include_planned: bool,
    json_output: bool,
    probe_services: bool,
    health_timeout: float,
    mineru_command: str | None,
    paddle_python: str | None,
    openai_base_url: str | None,
    ocr_endpoint: str | None,
    calamari_base_url: str | None,
    paddleocr_vl_endpoint: str | None,
) -> None:
    """Run a backend dependency and service readiness check."""

    catalog = backend_catalog(
        implemented_only=not include_planned,
        include_status=True,
        config={
            "mineru_command": mineru_command or default_mineru_command(),
            "paddle_python": paddle_python,
            "probe_services": probe_services,
            "backend_health_timeout": health_timeout,
            "openai_base_url": openai_base_url,
            "ocr_endpoint": ocr_endpoint,
            "calamari_base_url": calamari_base_url,
            "paddleocr_vl_endpoint": paddleocr_vl_endpoint,
        },
    )

    if json_output:
        click.echo(json.dumps(catalog, ensure_ascii=False, indent=2))
        return

    _print_report(catalog)


def _print_report(catalog: dict) -> None:
    totals = {"ok": 0, "missing_dependency": 0, "requires_configuration": 0, "planned": 0, "unknown": 0}
    for group in catalog.values():
        for backend in group:
            status = backend.get("status") or {}
            level = status.get("level", "unknown")
            totals[level] = totals.get(level, 0) + 1

    click.echo("AIH-Contexture backend doctor")
    click.echo(
        "summary: "
        + ", ".join(f"{name}={count}" for name, count in totals.items() if count)
    )
    for kind in ("layout", "ocr", "vlm"):
        click.echo(f"\n{kind}:")
        for backend in catalog[kind]:
            status = backend["status"]
            marker = _marker(status["level"])
            click.echo(f"  {marker} {backend['name']}: {status['message']}")


def _marker(level: str) -> str:
    return {
        "ok": "[ok]",
        "missing_dependency": "[missing]",
        "requires_configuration": "[config]",
        "planned": "[planned]",
    }.get(level, "[?]")


if __name__ == "__main__":
    doctor_cli()
