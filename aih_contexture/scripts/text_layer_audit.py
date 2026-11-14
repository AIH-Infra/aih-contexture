"""Create inspectable random samples and structural acceptance data for the text-layer fast path."""

from __future__ import annotations

import json
import os
import random
import re
from pathlib import Path
from typing import Any

import click

from aih_contexture.runtime.job import ContextureJob
from aih_contexture.runtime.runner import run_job


_ANCHOR_RE = re.compile(r"(?m)^\{(\d+)\}\s*$")
_BAD_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f\u200b\ufffd]")


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)


def _record_for(source: Path, input_root: Path, output_root: Path) -> dict[str, Any]:
    result = run_job(ContextureJob(
        input_path=str(source), input_name=source.name, mode="pipeline",
        output_formats=["markdown"],
        config={"layout_backend": "none", "ocr_backend": "none", "disable_ocr": True, "pdftext_workers": 1},
    ))
    markdown = result.markdown or ""
    output = output_root / source.relative_to(input_root).with_suffix(".md")
    _atomic_write(output, markdown)
    anchors = [int(value) for value in _ANCHOR_RE.findall(markdown)]
    expected = list(range(result.page_count))
    issues: list[str] = []
    if anchors != expected:
        issues.append("physical_page_anchors_do_not_match_source_pages")
    if _BAD_CONTROL_RE.search(markdown):
        issues.append("forbidden_control_or_replacement_character")
    if "\n\n\n" in markdown:
        issues.append("excess_blank_line_run")
    if result.page_count and not markdown.strip():
        issues.append("empty_markdown")
    text_layer = (result.metadata or {}).get("text_layer") or {}
    return {
        "source": str(source),
        "output": str(output.relative_to(output_root)),
        "page_count": result.page_count,
        "markdown_characters": len(markdown),
        "anchors": len(anchors),
        "printed_page_summary": text_layer.get("printed_page_summary"),
        "recommendation": text_layer.get("recommendation"),
        "warnings": result.warnings,
        "acceptance_issues": issues,
        "accepted": not issues,
    }


@click.command("contexture_text_layer_audit")
@click.argument("input_root", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("output_root", type=click.Path(file_okay=False, path_type=Path))
@click.option("--samples", type=click.IntRange(1, 100), default=12, show_default=True)
@click.option("--seed", type=int, default=20260725, show_default=True)
def text_layer_audit_cli(input_root: Path, output_root: Path, samples: int, seed: int) -> None:
    """Audit random PDF samples and mirror inspectable Markdown below OUTPUT_ROOT."""
    input_root = input_root.resolve()
    output_root = output_root.resolve()
    candidates = [path for path in input_root.rglob("*") if path.is_file() and path.suffix.lower() == ".pdf"]
    random.Random(seed).shuffle(candidates)
    selected = candidates[:samples]
    output_root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for index, source in enumerate(selected, start=1):
        try:
            record = _record_for(source, input_root, output_root)
        except Exception as exc:
            record = {"source": str(source), "accepted": False, "acceptance_issues": [f"{type(exc).__name__}: {exc}"]}
        records.append(record)
        click.echo(f"[{index}/{len(selected)}] {'accepted' if record['accepted'] else 'review'}: {source.name}")
    report = {
        "input_root": str(input_root),
        "samples": len(records),
        "seed": seed,
        "accepted": sum(bool(record.get("accepted")) for record in records),
        "requires_screenai_recommendation": sum(
            bool((record.get("recommendation") or {}).get("recommend_screenai")) for record in records
        ),
        "records": records,
    }
    _atomic_write(output_root / "text-layer-audit.json", json.dumps(report, ensure_ascii=False, indent=2))
    click.echo(json.dumps({key: report[key] for key in ("samples", "accepted", "requires_screenai_recommendation")}, ensure_ascii=False))


if __name__ == "__main__":
    text_layer_audit_cli()
