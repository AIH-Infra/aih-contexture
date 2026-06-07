from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import click

from aih_contexture.middle.adapters.external_ocr import merge_external_ocr_into_middle_document
from aih_contexture.middle.debug_markdown import render_middle_debug_markdown
from aih_contexture.middle.validation import validate_middle_json


@click.command(help="Merge external OCR JSON into an existing Contexture Middle JSON file.")
@click.argument("middle_json_path", type=click.Path(exists=True, dir_okay=False))
@click.argument("ocr_json_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--output", "-o", type=click.Path(dir_okay=False), help="Output Middle JSON path.")
@click.option("--backend", required=True, help="OCR backend name, e.g. paddle_ocr_v5.")
@click.option("--model", default=None, help="OCR model name, e.g. PP-OCRv5.")
@click.option(
    "--unmatched-policy",
    type=click.Choice(["append_text_blocks", "drop"]),
    default="append_text_blocks",
    show_default=True,
    help="How to handle OCR boxes that do not overlap existing text blocks.",
)
@click.option("--min-containment", default=0.20, show_default=True, type=float, help="Minimum OCR-box containment ratio needed to attach to a block.")
@click.option("--strict", is_flag=True, help="Fail when validation emits warnings.")
@click.option("--report", type=click.Path(dir_okay=False), help="Optional validation report path.")
@click.option("--debug-markdown", type=click.Path(dir_okay=False), help="Optional debug Markdown preview path.")
def import_external_ocr_cli(
    middle_json_path: str,
    ocr_json_path: str,
    output: str | None,
    backend: str,
    model: str | None,
    unmatched_policy: str,
    min_containment: float,
    strict: bool,
    report: str | None,
    debug_markdown: str | None,
):
    middle_path = Path(middle_json_path)
    ocr_path = Path(ocr_json_path)
    middle_payload = json.loads(middle_path.read_text(encoding="utf-8"))
    ocr_payload = json.loads(ocr_path.read_text(encoding="utf-8"))

    data = merge_external_ocr_into_middle_document(
        middle_payload,
        ocr_payload,
        backend=backend,
        model=model,
        source=str(ocr_path),
        unmatched_policy=unmatched_policy,
        min_containment=min_containment,
    )
    validation = validate_middle_json(data)

    output_path = Path(output) if output else middle_path.with_name(f"{middle_path.stem}_with_ocr.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    report_data = {
        "ok": validation.ok,
        "summary": validation.summary,
        "errors": [asdict(issue) for issue in validation.errors],
        "warnings": [asdict(issue) for issue in validation.warnings],
        "ocr_import": data.get("metadata", {}).get("ocr_import"),
    }
    if report:
        report_path = Path(report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8")

    if debug_markdown:
        debug_path = Path(debug_markdown)
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_text(render_middle_debug_markdown(data), encoding="utf-8")

    click.echo(json.dumps(report_data, ensure_ascii=False, indent=2))
    click.echo(f"Wrote {output_path}")
    if debug_markdown:
        click.echo(f"Wrote debug Markdown: {debug_markdown}")

    failed = bool(validation.errors) or (strict and bool(validation.warnings))
    if failed:
        raise click.ClickException(
            f"External OCR import validation failed: {len(validation.errors)} errors, {len(validation.warnings)} warnings"
        )


if __name__ == "__main__":
    import_external_ocr_cli()
