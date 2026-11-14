from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from aih_contexture.middle.debug_markdown import render_middle_debug_markdown
from aih_contexture.middle.validation import validate_middle_json, validate_middle_for_publication
from aih_contexture.runtime.middle_rerender import prepare_middle_rerender
from aih_contexture.scripts.reading_import_contract import GENERIC_LINE_HELP


@click.command(help="Validate and summarize a Contexture Middle JSON file.")
@click.argument("middle_json_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--strict", is_flag=True, help="Treat warnings as command failures.")
@click.option("--summary-only", is_flag=True, help="Only print the summary.")
@click.option("--debug-markdown", type=click.Path(dir_okay=False), help="Write a debug Markdown preview for inspection.")
@click.option("--debug-max-text-chars", default=240, show_default=True, type=int, help="Maximum block text length in debug Markdown.")
@click.option("--scholarly-markdown", type=click.Path(dir_okay=False), help="Write normalized scholarly Markdown from Middle JSON.")
@click.option("--include-provenance-comments/--no-provenance-comments", default=None, help="Override block provenance comments; omitted inherits saved options.")
@click.option("--classical-marginalia-mode", type=click.Choice(["off", "page_locators"]), default=None)
@click.option("--classical-text-marginalia-mode", type=click.Choice(["separate", "drop"]), default=None)
@click.option("--generic-line-output-mode", type=click.Choice(["drop", "page_comments"]), default=None, help=GENERIC_LINE_HELP)
@click.option('--reading-diagnostics', 'emit_reading_diagnostics', is_flag=True, default=False,
              help='Write a separate diagnostics file; disabled by default.')
def middle_cli(
    middle_json_path: str,
    strict: bool = False,
    summary_only: bool = False,
    debug_markdown: str | None = None,
    debug_max_text_chars: int = 240,
    scholarly_markdown: str | None = None,
    include_provenance_comments: bool | None = None,
    classical_marginalia_mode: str | None = None,
    classical_text_marginalia_mode: str | None = None,
    generic_line_output_mode: str | None = None,
    emit_reading_diagnostics: bool = False,
):
    path = Path(middle_json_path)
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    from aih_contexture.middle.adapters.pipeline_json import is_pipeline_render_json, pipeline_json_to_middle_document
    if is_pipeline_render_json(data):
        data = pipeline_json_to_middle_document(data, source_name=path.name, source_dir=path.parent)
    report = validate_middle_for_publication(data) if scholarly_markdown else validate_middle_json(data)

    click.echo(json.dumps(report.summary, ensure_ascii=False, indent=2))
    if not summary_only:
        for issue in report.issues:
            click.echo(f"{issue.severity.upper()} {issue.path}: {issue.message}")

    failed = bool(report.errors) or (strict and bool(report.warnings))
    if failed:
        raise click.ClickException(
            f"Middle JSON validation failed: {len(report.errors)} errors, {len(report.warnings)} warnings"
        )

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
        config: dict[str, Any] = {'emit_reading_diagnostics': emit_reading_diagnostics}
        if include_provenance_comments is not None:
            config["include_provenance_comments"] = include_provenance_comments
        if classical_marginalia_mode is not None:
            config["classical_marginalia_mode"] = classical_marginalia_mode
        if classical_text_marginalia_mode is not None:
            config["classical_text_marginalia_mode"] = classical_text_marginalia_mode
        if generic_line_output_mode is not None:
            config["generic_line_output_mode"] = generic_line_output_mode

        try:
            plan = prepare_middle_rerender(data, config)
        except ValueError as exc:
            raise click.ClickException(f"Middle re-render preparation failed: {exc}") from exc

        for warning in plan.warnings:
            if not warning.startswith('$.'):
                click.echo(f'Warning: {warning}', err=True)

        from aih_contexture.middle.reading_structure import copy_existing_reading_resources
        from aih_contexture.runtime.artifacts import atomic_write_text
        copy_existing_reading_resources(plan.document, path.parent, scholarly_path.parent)
        atomic_write_text(str(scholarly_path), plan.markdown)
        if emit_reading_diagnostics:
            from aih_contexture.runtime.reading_diagnostics import write_reading_diagnostics
            write_reading_diagnostics(plan.diagnostics, scholarly_path.parent, scholarly_path.stem,
                                      markdown=plan.markdown, markdown_name=scholarly_path.name)
        click.echo(f"Wrote scholarly Markdown: {scholarly_path}")

if __name__ == "__main__":
    middle_cli()
