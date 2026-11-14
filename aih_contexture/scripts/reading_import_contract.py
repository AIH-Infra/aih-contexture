"""Shared reading options contract and helper for dedicated import CLIs."""
from __future__ import annotations

from typing import Any
import click

from aih_contexture.runtime.middle_rerender import MiddleRerender, prepare_middle_rerender

GENERIC_LINE_HELP = (
    "Universal line number output mode: drop (default) or page_comments. "
    "Requires classical_marginalia_mode=page_locators; affects only confirmed line numbers. "
    "Body numbers are preserved; Bekker locators are controlled separately."
)


def reading_render_options_click_options(fn):
    """Add standardized reading render options to Click commands."""
    fn = click.option(
        "--include-provenance-comments/--no-include-provenance-comments",
        "--include-provenance/--no-provenance",
        "include_provenance_comments",
        default=None,
        help="Include block provenance comments in scholarly Markdown; omitted inherits saved options.",
    )(fn)
    fn = click.option(
        "--no-provenance-comments",
        "no_provenance_comments",
        is_flag=True,
        flag_value=False,
        default=None,
        hidden=True,
        help="Alias to disable provenance comments.",
    )(fn)
    fn = click.option(
        "--classical-marginalia-mode",
        type=click.Choice(["off", "page_locators"]),
        default=None,
        help="Classical marginalia rendering mode: off or page_locators; omitted inherits saved options.",
    )(fn)
    fn = click.option(
        "--classical-text-marginalia-mode",
        type=click.Choice(["separate", "drop"]),
        default=None,
        help="Classical text marginalia mode: separate or drop; omitted inherits saved options.",
    )(fn)
    fn = click.option(
        "--generic-line-output-mode",
        type=click.Choice(["drop", "page_comments"]),
        default=None,
        help=GENERIC_LINE_HELP,
    )(fn)
    fn = click.option('--reading-diagnostics', 'emit_reading_diagnostics', is_flag=True, default=False,
                      help='Write separate optional diagnostics; disabled by default.')(fn)
    return fn


def build_reading_render_config(
    *,
    include_provenance_comments: bool | None = None,
    classical_marginalia_mode: str | None = None,
    classical_text_marginalia_mode: str | None = None,
    generic_line_output_mode: str | None = None,
    no_provenance_comments: bool | None = None,
) -> dict[str, Any]:
    """Build canonical reading render options dictionary.

    Only canonical reading options are included; no model or pipeline parameters.
    None values are omitted so that snapshot inheritance or defaults work.
    """
    config: dict[str, Any] = {}
    if (no_provenance_comments is not None and include_provenance_comments is not None
            and no_provenance_comments != include_provenance_comments):
        raise click.ClickException('Conflicting explicit options for include_provenance_comments')
    effective_provenance = (
        no_provenance_comments if no_provenance_comments is not None else include_provenance_comments
    )
    if effective_provenance is not None:
        config["include_provenance_comments"] = effective_provenance
    if classical_marginalia_mode is not None:
        config["classical_marginalia_mode"] = classical_marginalia_mode
    if classical_text_marginalia_mode is not None:
        config["classical_text_marginalia_mode"] = classical_text_marginalia_mode
    if generic_line_output_mode is not None:
        config["generic_line_output_mode"] = generic_line_output_mode
    return config


def prepare_import_middle_for_publication(
    data: dict[str, Any],
    *,
    include_provenance_comments: bool | None = None,
    classical_marginalia_mode: str | None = None,
    classical_text_marginalia_mode: str | None = None,
    generic_line_output_mode: str | None = None,
    no_provenance_comments: bool | None = None,
    emit_reading_diagnostics: bool = False,
    diagnostic_output_path=None,
    diagnostic_markdown_path=None,
) -> MiddleRerender:
    """Solidify canonical reading options snapshot and render scholarly Markdown."""
    reading_config = build_reading_render_config(
        include_provenance_comments=include_provenance_comments,
        classical_marginalia_mode=classical_marginalia_mode,
        classical_text_marginalia_mode=classical_text_marginalia_mode,
        generic_line_output_mode=generic_line_output_mode,
        no_provenance_comments=no_provenance_comments,
    )
    try:
        plan = prepare_middle_rerender(data, {**reading_config, 'emit_reading_diagnostics':emit_reading_diagnostics})
    except ValueError as exc:
        raise click.ClickException(f"Middle re-render preparation failed: {exc}") from exc
    for warning in plan.warnings:
        click.echo(f'Warning: {warning}', err=True)
    if emit_reading_diagnostics and diagnostic_output_path:
        from pathlib import Path
        from aih_contexture.runtime.reading_diagnostics import write_reading_diagnostics
        output = Path(diagnostic_markdown_path or diagnostic_output_path)
        write_reading_diagnostics(plan.diagnostics, output.parent, output.stem,
                                  markdown=plan.markdown if diagnostic_markdown_path else None,
                                  markdown_name=output.name if diagnostic_markdown_path else None)
    return plan
