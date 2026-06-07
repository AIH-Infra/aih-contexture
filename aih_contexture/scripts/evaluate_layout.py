from __future__ import annotations

import json
from pathlib import Path

import click

from aih_contexture.evaluation.layout_middle import (
    evaluate_middle_layout_files,
    evaluate_middle_layout_manifest,
)


@click.command(help="Evaluate one or more Contexture Middle JSON layout artifacts.")
@click.argument("middle_json_paths", nargs=-1, type=click.Path(exists=True, dir_okay=False))
@click.option("--manifest", type=click.Path(exists=True, dir_okay=False), help="Evaluate cases from a JSON manifest.")
@click.option(
    "--require-block-type",
    "required_block_types",
    multiple=True,
    help="Require at least one block of this canonical type. Can be repeated.",
)
@click.option("--min-blocks", default=1, show_default=True, type=int, help="Minimum total block count per file.")
@click.option("--output", type=click.Path(dir_okay=False), help="Write the evaluation report JSON to this path.")
@click.option("--strict", is_flag=True, help="Fail the command when any evaluated file does not pass.")
def evaluate_layout_cli(
    middle_json_paths: tuple[str, ...],
    manifest: str | None,
    required_block_types: tuple[str, ...],
    min_blocks: int,
    output: str | None,
    strict: bool,
):
    if manifest and middle_json_paths:
        raise click.UsageError("Use either --manifest or direct Middle JSON paths, not both.")
    if not manifest and not middle_json_paths:
        raise click.UsageError("At least one Middle JSON file or --manifest is required.")

    if manifest:
        manifest_path = Path(manifest)
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload = evaluate_middle_layout_manifest(manifest_payload, base_dir=manifest_path.parent)
    else:
        payload = evaluate_middle_layout_files(
            list(middle_json_paths),
            required_block_types=list(required_block_types),
            min_blocks=min_blocks,
        )
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    click.echo(text)

    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")

    if strict and not payload["ok"]:
        raise click.ClickException("Layout Middle evaluation failed.")


if __name__ == "__main__":
    evaluate_layout_cli()
