from __future__ import annotations

import json
from pathlib import Path

import click

from aih_contexture.evaluation.layout_overlay import (
    render_middle_layout_overlay_file,
    render_middle_review_crops_file,
    render_middle_span_overlay_file,
)


@click.command(help="Render Contexture Middle JSON layout bbox overlays as inspection images.")
@click.argument("middle_json_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--kind", type=click.Choice(["layout", "span", "review"]), default="layout", show_default=True, help="Inspection artifact type to render.")
@click.option("--source-pdf", type=click.Path(exists=True, dir_okay=False), help="Optional source PDF used as page background.")
@click.option("--output-dir", type=click.Path(file_okay=False), required=True, help="Directory for per-page overlay PNG files.")
@click.option("--output-pdf", type=click.Path(dir_okay=False), help="Optional multi-page overlay PDF path.")
@click.option("--dpi", default=96, show_default=True, type=int, help="Render DPI for PDF backgrounds and blank pages.")
@click.option("--max-label-chars", default=42, show_default=True, type=int, help="Maximum overlay label length.")
@click.option(
    "--review-target",
    type=click.Choice(["small_empty_complex", "empty_complex", "complex", "all"]),
    default="small_empty_complex",
    show_default=True,
    help="Review crop target when --kind=review.",
)
@click.option("--review-padding", default=24, show_default=True, type=int, help="Pixel padding around review crops.")
def visualize_layout_cli(
    middle_json_path: str,
    kind: str,
    source_pdf: str | None,
    output_dir: str,
    output_pdf: str | None,
    dpi: int,
    max_label_chars: int,
    review_target: str,
    review_padding: int,
):
    if kind == "review":
        payload = render_middle_review_crops_file(
            middle_json_path,
            source_pdf=source_pdf,
            output_dir=output_dir,
            dpi=dpi,
            padding=review_padding,
            target=review_target,
        )
    else:
        render = render_middle_span_overlay_file if kind == "span" else render_middle_layout_overlay_file
        payload = render(
            middle_json_path,
            source_pdf=source_pdf,
            output_dir=output_dir,
            output_pdf=output_pdf,
            dpi=dpi,
            max_label_chars=max_label_chars,
        )
    click.echo(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    visualize_layout_cli()
