from __future__ import annotations

import json
from pathlib import Path

import click

from aih_contexture.structured_source import convert_structured_source, validate_source_package


@click.command(help="Import TEI/XML or EPUB into a Contexture Source Package.")
@click.argument("input_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--output-dir", type=click.Path(file_okay=False, path_type=Path), default=Path("output"), show_default=True)
@click.option("--emit-line-indexes", is_flag=True, help="Write byte-offset .idx sidecars for JSONL components.")
def structured_source_cli(input_path: Path, output_dir: Path, emit_line_indexes: bool) -> None:
    result = convert_structured_source(str(input_path), str(output_dir), emit_line_indexes=emit_line_indexes)
    click.echo(json.dumps({"package_path": result.package_path, "document_id": result.document["id"], "components": result.package_manifest["components"]}, ensure_ascii=False, indent=2))


@click.command(help="Validate a Contexture Source Package.")
@click.argument("package_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
def validate_source_package_cli(package_dir: Path) -> None:
    manifest = validate_source_package(package_dir)
    click.echo(json.dumps({"valid": True, "document_id": manifest["document_id"]}, ensure_ascii=False))
