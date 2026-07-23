from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import click

from aih_contexture.middle.adapters.vlm_json import vlm_json_document_to_middle_document
from aih_contexture.middle.debug_markdown import render_middle_debug_markdown
from aih_contexture.middle.semantics import resolve_middle_for_rendering
from aih_contexture.middle.scholarly_markdown import render_middle_scholarly_markdown
from aih_contexture.middle.validation import validate_middle_json


@click.command(help="Import VLM JSON page output into Contexture Middle JSON.")
@click.argument("input_json_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--output", "-o", type=click.Path(dir_okay=False), help="Output Middle JSON path.")
@click.option("--backend", default="vlm_generalized", show_default=True, help="VLM backend name.")
@click.option("--model", default=None, help="VLM model name.")
@click.option("--source-name", default=None, help="Original document name stored in Middle JSON.")
@click.option("--strict", is_flag=True, help="Fail when validation emits warnings.")
@click.option("--report", type=click.Path(dir_okay=False), help="Optional validation report path.")
@click.option("--debug-markdown", type=click.Path(dir_okay=False), help="Optional debug Markdown preview path.")
@click.option("--scholarly-markdown", type=click.Path(dir_okay=False), help="Optional normalized scholarly Markdown output path.")
@click.option("--include-provenance-comments", is_flag=True, help="Include block provenance comments in scholarly Markdown.")
def import_vlm_json_cli(
    input_json_path: str,
    output: str | None,
    backend: str,
    model: str | None,
    source_name: str | None,
    strict: bool,
    report: str | None,
    debug_markdown: str | None,
    scholarly_markdown: str | None,
    include_provenance_comments: bool,
):
    input_path = Path(input_json_path)
    payload = json.loads(input_path.read_text(encoding="utf-8"))

    data = vlm_json_document_to_middle_document(
        payload,
        backend=backend,
        model=model,
        source_name=source_name or input_path.name,
        source=str(input_path),
    ).to_dict()
    data = resolve_middle_for_rendering(data)
    validation = validate_middle_json(data)

    output_path = Path(output) if output else input_path.with_name(f"{input_path.stem}_contexture_middle.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    report_data = {
        "ok": validation.ok,
        "summary": validation.summary,
        "errors": [asdict(issue) for issue in validation.errors],
        "warnings": [asdict(issue) for issue in validation.warnings],
        "vlm_import": {
            "backend": backend,
            "model": model,
            "source": str(input_path),
        },
    }
    if report:
        report_path = Path(report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8")

    if debug_markdown:
        debug_path = Path(debug_markdown)
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_text(render_middle_debug_markdown(data), encoding="utf-8")

    if scholarly_markdown:
        scholarly_path = Path(scholarly_markdown)
        scholarly_path.parent.mkdir(parents=True, exist_ok=True)
        scholarly_path.write_text(
            render_middle_scholarly_markdown(data, include_provenance_comments=include_provenance_comments),
            encoding="utf-8",
        )

    click.echo(json.dumps(report_data, ensure_ascii=False, indent=2))
    click.echo(f"Wrote {output_path}")
    if debug_markdown:
        click.echo(f"Wrote debug Markdown: {debug_markdown}")
    if scholarly_markdown:
        click.echo(f"Wrote scholarly Markdown: {scholarly_markdown}")

    failed = bool(validation.errors) or (strict and bool(validation.warnings))
    if failed:
        raise click.ClickException(
            f"VLM JSON import validation failed: {len(validation.errors)} errors, {len(validation.warnings)} warnings"
        )


if __name__ == "__main__":
    import_vlm_json_cli()
