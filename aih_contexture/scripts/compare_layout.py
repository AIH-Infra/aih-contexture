from __future__ import annotations

import json
from pathlib import Path

import click

from aih_contexture.evaluation.layout_compare import (
    compare_layout_eval_reports,
    render_layout_comparison_markdown,
    write_layout_comparison_review_crops,
)


@click.command(help="Compare Contexture layout evaluation reports.")
@click.argument("report_paths", nargs=-1, type=click.Path(exists=True, dir_okay=False))
@click.option("--output-json", type=click.Path(dir_okay=False), help="Write comparison JSON.")
@click.option("--output-markdown", type=click.Path(dir_okay=False), help="Write comparison Markdown.")
@click.option("--review-crop-dir", type=click.Path(file_okay=False), help="Write review crop images for flagged cases.")
@click.option(
    "--review-target",
    type=click.Choice(["small_empty_complex", "empty_complex", "complex", "all"]),
    default="small_empty_complex",
    show_default=True,
    help="Review crop target when --review-crop-dir is set.",
)
@click.option("--review-dpi", default=144, show_default=True, type=int, help="DPI for review crop PDF rendering.")
@click.option("--review-padding", default=24, show_default=True, type=int, help="Pixel padding around review crops.")
def compare_layout_cli(
    report_paths: tuple[str, ...],
    output_json: str | None,
    output_markdown: str | None,
    review_crop_dir: str | None,
    review_target: str,
    review_dpi: int,
    review_padding: int,
):
    if not report_paths:
        raise click.UsageError("At least one layout evaluation report is required.")

    payload = compare_layout_eval_reports(list(report_paths))
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    click.echo(text)

    if output_json:
        path = Path(output_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    if output_markdown:
        path = Path(output_markdown)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_layout_comparison_markdown(payload), encoding="utf-8")
    if review_crop_dir:
        review_report = write_layout_comparison_review_crops(
            payload,
            review_crop_dir,
            target=review_target,
            dpi=review_dpi,
            padding=review_padding,
        )
        click.echo(json.dumps({"review_crops": review_report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    compare_layout_cli()
