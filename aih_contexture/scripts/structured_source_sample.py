"""Create deterministic random XML/EPUB acceptance samples."""
from __future__ import annotations

import json
import random
import shutil
from pathlib import Path

import click

from aih_contexture.structured_source import convert_structured_source, validate_source_package
from aih_contexture.structured_source.util import stable_slug


@click.command(help="Randomly convert XML/EPUB sources into JSON, Markdown, and HTML samples.")
@click.argument("input_root", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--output-root", required=True, type=click.Path(file_okay=False, path_type=Path))
@click.option("--samples", type=click.IntRange(1, 1000), default=50, show_default=True)
@click.option("--seed", type=int, default=20260815, show_default=True)
@click.option("--emit-line-indexes", is_flag=True)
def structured_source_sample_cli(input_root: Path, output_root: Path, samples: int, seed: int, emit_line_indexes: bool) -> None:
    candidates = sorted(p for p in input_root.rglob("*") if p.is_file() and p.suffix.lower() in {".xml", ".tei", ".epub"})
    if len(candidates) < samples:
        raise click.ClickException(f"Only {len(candidates)} XML/EPUB files found; cannot sample {samples}")
    selected = candidates[:]
    random.Random(seed).shuffle(selected)
    selected = selected[:samples]
    output_root.mkdir(parents=True, exist_ok=True)
    package_root = output_root / "packages"
    records = []
    for number, source in enumerate(selected, 1):
        result = convert_structured_source(str(source), str(package_root), emit_line_indexes=emit_line_indexes)
        package = Path(result.package_path)
        base = stable_slug(source.stem)
        destination = output_root / f"{number:03d}_{base}"
        destination.mkdir(parents=True, exist_ok=True)
        for suffix, component in (("json", "document.json"), ("md", "document.md"), ("html", "document.html")):
            shutil.copyfile(package / component, destination / f"{base}.{suffix}")
        validate_source_package(package)
        records.append({
            "sample": number, "source": str(source), "source_name": source.name,
            "output_dir": str(destination), "base_name": base,
            "package": str(package), "document_id": result.document["id"],
            "footnotes": sum(1 for b in result.document["blocks"] if b.get("type") == "Footnote"),
            "footnote_references": sum(1 for r in result.document["relations"] if r.get("kind") == "footnote_reference"),
        })
    (output_root / "sample_manifest.json").write_text(json.dumps({"samples": records, "seed": seed}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    click.echo(json.dumps({"samples": len(records), "output_root": str(output_root), "seed": seed}, ensure_ascii=False))


if __name__ == "__main__":
    structured_source_sample_cli()
