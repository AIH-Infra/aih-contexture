from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import click

from aih_contexture.middle.adapters.external_layout import external_layout_document_to_middle_document
from aih_contexture.middle.debug_markdown import render_middle_debug_markdown
from aih_contexture.middle.semantics import resolve_middle_for_rendering
from aih_contexture.middle.validation import validate_middle_json


@click.command(help="Import an external layout JSON file into Contexture Middle JSON.")
@click.argument("input_json_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--output", "-o", type=click.Path(dir_okay=False), help="Output Middle JSON path.")
@click.option("--backend", required=True, help="Layout backend name, e.g. mineru_pp_doclayout_v2_direct or paddle_pp_doclayout_v3.")
@click.option("--model", default=None, help="Backend model name, e.g. PP-DocLayoutV2.")
@click.option("--source-name", default=None, help="Original document name stored in Middle JSON.")
@click.option(
    "--block-source",
    default="auto",
    show_default=True,
    type=click.Choice(
        [
            "auto",
            "all",
            "blocks",
            "layout_bboxes",
            "boxes",
            "bboxes",
            "layout",
            "regions",
            "para_blocks",
            "preproc_blocks",
            "discarded_blocks",
            "parsing_res_list",
        ],
        case_sensitive=False,
    ),
    help="Which page block list to import from external JSON.",
)
@click.option("--strict", is_flag=True, help="Fail when validation emits warnings.")
@click.option("--report", type=click.Path(dir_okay=False), help="Optional validation report path.")
@click.option("--debug-markdown", type=click.Path(dir_okay=False), help="Optional debug Markdown preview path.")
def import_external_layout_cli(
    input_json_path: str,
    output: str | None,
    backend: str,
    model: str | None,
    source_name: str | None,
    block_source: str,
    strict: bool,
    report: str | None,
    debug_markdown: str | None,
):
    input_path = Path(input_json_path)
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    middle_doc = external_layout_document_to_middle_document(
        payload,
        backend=backend,
        model=model,
        source_name=source_name or input_path.name,
        source=str(input_path),
        block_source=block_source,
    )
    data = resolve_middle_for_rendering(middle_doc.to_dict())
    validation = validate_middle_json(data)

    output_path = Path(output) if output else input_path.with_name(f"{input_path.stem}_contexture_middle.json")
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    report_data = {
        "ok": validation.ok,
        "summary": validation.summary,
        "errors": [asdict(issue) for issue in validation.errors],
        "warnings": [asdict(issue) for issue in validation.warnings],
    }
    if report:
        Path(report).write_text(json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8")

    if debug_markdown:
        Path(debug_markdown).write_text(render_middle_debug_markdown(data), encoding="utf-8")

    click.echo(json.dumps(validation.summary, ensure_ascii=False, indent=2))
    click.echo(f"Wrote {output_path}")
    if debug_markdown:
        click.echo(f"Wrote debug Markdown: {debug_markdown}")

    failed = bool(validation.errors) or (strict and bool(validation.warnings))
    if failed:
        raise click.ClickException(
            f"External layout import validation failed: {len(validation.errors)} errors, {len(validation.warnings)} warnings"
        )


if __name__ == "__main__":
    import_external_layout_cli()
