from __future__ import annotations

import json
from pathlib import Path

import click

from aih_contexture.middle.debug_markdown import render_middle_debug_markdown
from aih_contexture.middle.scholarly_markdown import render_middle_scholarly_markdown
from aih_contexture.middle.validation import validate_middle_json


@click.command(help="Validate and summarize a Contexture Middle JSON file.")
@click.argument("middle_json_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--strict", is_flag=True, help="Treat warnings as command failures.")
@click.option("--summary-only", is_flag=True, help="Only print the summary.")
@click.option("--debug-markdown", type=click.Path(dir_okay=False), help="Write a debug Markdown preview for inspection.")
@click.option("--debug-max-text-chars", default=240, show_default=True, type=int, help="Maximum block text length in debug Markdown.")
@click.option("--scholarly-markdown", type=click.Path(dir_okay=False), help="Write normalized scholarly Markdown from Middle JSON.")
@click.option("--include-provenance-comments", is_flag=True, help="Include block provenance comments in scholarly Markdown.")
def middle_cli(
    middle_json_path: str,
    strict: bool = False,
    summary_only: bool = False,
    debug_markdown: str | None = None,
    debug_max_text_chars: int = 240,
    scholarly_markdown: str | None = None,
    include_provenance_comments: bool = False,
):
    path = Path(middle_json_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    report = validate_middle_json(data)

    click.echo(json.dumps(report.summary, ensure_ascii=False, indent=2))
    if not summary_only:
        for issue in report.issues:
            click.echo(f"{issue.severity.upper()} {issue.path}: {issue.message}")

    if debug_markdown:
        debug_path = Path(debug_markdown)
        debug_path.write_text(
            render_middle_debug_markdown(data, max_text_chars=debug_max_text_chars),
            encoding="utf-8",
        )
        click.echo(f"Wrote debug Markdown: {debug_path}")

    if scholarly_markdown:
        scholarly_path = Path(scholarly_markdown)
        scholarly_path.parent.mkdir(parents=True, exist_ok=True)
        scholarly_path.write_text(
            render_middle_scholarly_markdown(data, include_provenance_comments=include_provenance_comments),
            encoding="utf-8",
        )
        click.echo(f"Wrote scholarly Markdown: {scholarly_path}")

    failed = bool(report.errors) or (strict and bool(report.warnings))
    if failed:
        raise click.ClickException(
            f"Middle JSON validation failed: {len(report.errors)} errors, {len(report.warnings)} warnings"
        )


if __name__ == "__main__":
    middle_cli()
