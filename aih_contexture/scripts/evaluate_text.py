from __future__ import annotations

import json
from pathlib import Path

import click

from aih_contexture.evaluation.text_baseline import evaluate_text_baseline_files


@click.command(
    help="Score a Contexture Middle JSON against its source PDF's text layer (CER, content overlap, "
    "reading-order proxy, table checks). Only pages whose text layer passes the trust gate are scored."
)
@click.argument("middle_json_path", type=click.Path(exists=True, dir_okay=False))
@click.argument("pdf_path", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--truth",
    "truth_path",
    type=click.Path(exists=True, dir_okay=False),
    help='Hand-labelled JSON: {"tables": {block_id: html}, "reading_order": {page_index: [block_id, ...]}}.',
)
@click.option("--page", "pages", type=int, multiple=True, help="0-based page index to score. Can be repeated.")
@click.option(
    "--allow-embedded-ocr",
    is_flag=True,
    help="Also use a scan's invisible OCR layer as the reference. Scores then measure agreement with that OCR.",
)
@click.option("--output", type=click.Path(dir_okay=False), help="Write the report JSON to this path.")
@click.option("--details", is_flag=True, help="Print per-page and per-block rows too (default: summary only).")
def evaluate_text_cli(
    middle_json_path: str,
    pdf_path: str,
    truth_path: str | None,
    pages: tuple[int, ...],
    allow_embedded_ocr: bool,
    output: str | None,
    details: bool,
):
    payload = evaluate_text_baseline_files(
        middle_json_path,
        pdf_path,
        truth_path=truth_path,
        pages=list(pages) or None,
        allow_embedded_ocr=allow_embedded_ocr,
    )
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    shown = payload if details else {key: value for key, value in payload.items() if key != "page_reports"}
    click.echo(json.dumps(shown, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    evaluate_text_cli()
