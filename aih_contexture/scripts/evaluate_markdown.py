from __future__ import annotations

import json
from pathlib import Path

import click

from aih_contexture.evaluation.scholarly_markdown import evaluate_scholarly_markdown_files


@click.command(help="Evaluate normalized scholarly Markdown syntax artifacts.")
@click.argument("markdown_paths", nargs=-1, type=click.Path(exists=True, dir_okay=False))
@click.option("--output", type=click.Path(dir_okay=False), help="Write the evaluation report JSON to this path.")
@click.option("--strict", is_flag=True, help="Fail the command when any Markdown file does not pass.")
def evaluate_markdown_cli(
    markdown_paths: tuple[str, ...],
    output: str | None,
    strict: bool,
):
    if not markdown_paths:
        raise click.UsageError("At least one Markdown file is required.")

    payload = evaluate_scholarly_markdown_files(list(markdown_paths))
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    click.echo(text)

    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")

    if strict and not payload["ok"]:
        raise click.ClickException("Scholarly Markdown evaluation failed.")


if __name__ == "__main__":
    evaluate_markdown_cli()
