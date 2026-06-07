from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import click

from aih_contexture.middle.adapters.external_document import external_document_to_middle_document
from aih_contexture.middle.debug_markdown import render_middle_debug_markdown
from aih_contexture.middle.scholarly_markdown import render_middle_scholarly_markdown
from aih_contexture.middle.validation import validate_middle_json


@click.command(help="Import a full external document JSON result into Contexture Middle JSON.")
@click.argument("input_json_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--output", "-o", type=click.Path(dir_okay=False), help="Output Middle JSON path.")
@click.option("--layout-backend", required=True, help="Layout backend name, e.g. mineru_pp_doclayout_v2.")
@click.option("--layout-model", default=None, help="Layout model name, e.g. PP-DocLayoutV2.")
@click.option("--ocr-backend", default=None, help="OCR backend name, e.g. mineru_pytorch_paddle_ocr or paddle_ocr_v5.")
@click.option("--ocr-model", default=None, help="OCR model name, e.g. PP-OCRv5.")
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
@click.option("--scholarly-markdown", type=click.Path(dir_okay=False), help="Optional normalized scholarly Markdown output path.")
@click.option("--include-provenance-comments", is_flag=True, help="Include block provenance comments in scholarly Markdown.")
def import_external_document_cli(
    input_json_path: str,
    output: str | None,
    layout_backend: str,
    layout_model: str | None,
    ocr_backend: str | None,
    ocr_model: str | None,
    source_name: str | None,
    block_source: str,
    unmatched_policy: str,
    min_containment: float,
    strict: bool,
    report: str | None,
    debug_markdown: str | None,
    scholarly_markdown: str | None,
    include_provenance_comments: bool,
):
    input_path = Path(input_json_path)
    payload = json.loads(input_path.read_text(encoding="utf-8"))

    data = external_document_to_middle_document(
        payload,
        layout_backend=layout_backend,
        layout_model=layout_model,
        ocr_backend=ocr_backend,
        ocr_model=ocr_model,
        source_name=source_name or input_path.name,
        source=str(input_path),
        block_source=block_source,
        unmatched_policy=unmatched_policy,
        min_containment=min_containment,
    )
    validation = validate_middle_json(data)

    output_path = Path(output) if output else input_path.with_name(f"{input_path.stem}_contexture_middle.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    report_data = {
        "ok": validation.ok,
        "summary": validation.summary,
        "errors": [asdict(issue) for issue in validation.errors],
        "warnings": [asdict(issue) for issue in validation.warnings],
        "document_import": data.get("metadata", {}).get("document_import"),
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
            f"External document import validation failed: {len(validation.errors)} errors, {len(validation.warnings)} warnings"
        )


if __name__ == "__main__":
    import_external_document_cli()
