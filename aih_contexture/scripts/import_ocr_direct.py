from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import click

from aih_contexture.middle.adapters.ocr_direct import ocr_direct_outputs_to_middle_document
from aih_contexture.middle.debug_markdown import render_middle_debug_markdown
from aih_contexture.middle.semantics import resolve_middle_for_rendering
from aih_contexture.middle.validation import validate_middle_for_publication
from aih_contexture.scripts.reading_import_contract import (
    prepare_import_middle_for_publication,
    reading_render_options_click_options,
)


@click.command(help="Import Chandra/Churro official OCR-direct output into Contexture Middle JSON.")
@click.argument("input_json_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--output", "-o", type=click.Path(dir_okay=False), help="Output Middle JSON path.")
@click.option(
    "--backend",
    required=True,
    type=click.Choice(["chandra", "churro"], case_sensitive=False),
    help="Specialized OCR/VLM backend whose official output is being imported.",
)
@click.option("--model", default=None, help="Specialized model name.")
@click.option("--source-name", default=None, help="Original document name stored in Middle JSON.")
@click.option("--strict", is_flag=True, help="Fail when validation emits warnings.")
@click.option("--report", type=click.Path(dir_okay=False), help="Optional validation report path.")
@click.option("--debug-markdown", type=click.Path(dir_okay=False), help="Optional debug Markdown preview path.")
@click.option("--scholarly-markdown", type=click.Path(dir_okay=False), help="Optional normalized scholarly Markdown output path.")
@reading_render_options_click_options
def import_ocr_direct_cli(
    input_json_path: str,
    output: str | None = None,
    backend: str = "chandra",
    model: str | None = None,
    source_name: str | None = None,
    strict: bool = False,
    report: str | None = None,
    debug_markdown: str | None = None,
    scholarly_markdown: str | None = None,
    include_provenance_comments: bool | None = None,
    classical_marginalia_mode: str | None = None,
    classical_text_marginalia_mode: str | None = None,
    generic_line_output_mode: str | None = None,
    no_provenance_comments: bool | None = None,
    emit_reading_diagnostics: bool = False,
):
    input_path = Path(input_json_path)
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("pages") or payload.get("outputs") or payload.get("results") or [payload]
    if not isinstance(payload, list):
        raise click.ClickException("Input must be a list, or an object containing pages/outputs/results.")

    data = ocr_direct_outputs_to_middle_document(
        payload,
        backend=backend.lower(),
        model=model,
        source_name=source_name or input_path.name,
        source=str(input_path),
    ).to_dict()
    data = resolve_middle_for_rendering(data)
    validation = validate_middle_for_publication(data)

    output_path = Path(output) if output else input_path.with_name(f"{input_path.stem}_contexture_middle.json")

    report_data = {
        "ok": validation.ok,
        "summary": validation.summary,
        "errors": [asdict(issue) for issue in validation.errors],
        "warnings": [asdict(issue) for issue in validation.warnings],
        "ocr_direct_import": {
            "backend": backend.lower(),
            "model": model,
            "source": str(input_path),
            "protocol": "official_upstream_output",
        },
    }
    if report:
        report_path = Path(report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8")

    failed = bool(validation.errors) or (strict and bool(validation.warnings))
    if failed:
        raise click.ClickException(
            f"OCR direct import validation failed: {len(validation.errors)} errors, {len(validation.warnings)} warnings"
        )

    plan = prepare_import_middle_for_publication(
        data,
        include_provenance_comments=include_provenance_comments,
        classical_marginalia_mode=classical_marginalia_mode,
        classical_text_marginalia_mode=classical_text_marginalia_mode,
        generic_line_output_mode=generic_line_output_mode,
        no_provenance_comments=no_provenance_comments,
        emit_reading_diagnostics=emit_reading_diagnostics,
        diagnostic_output_path=output_path, diagnostic_markdown_path=scholarly_markdown,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(plan.document, ensure_ascii=False, indent=2), encoding="utf-8")

    if debug_markdown:
        debug_path = Path(debug_markdown)
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_text(render_middle_debug_markdown(plan.document), encoding="utf-8")

    if scholarly_markdown:
        scholarly_path = Path(scholarly_markdown)
        scholarly_path.parent.mkdir(parents=True, exist_ok=True)
        scholarly_path.write_text(plan.markdown, encoding="utf-8")

    click.echo(json.dumps(report_data, ensure_ascii=False, indent=2))
    click.echo(f"Wrote {output_path}")
    if debug_markdown:
        click.echo(f"Wrote debug Markdown: {debug_markdown}")
    if scholarly_markdown:
        click.echo(f"Wrote scholarly Markdown: {scholarly_markdown}")


if __name__ == "__main__":
    import_ocr_direct_cli()
