from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


_SUFFIX_FORMATS: tuple[tuple[str, str], ...] = (
    (".postprocess_report.json", "postprocess_report"),
    ("_middle_scholarly_report.json", "middle_scholarly_report"),
    ("_middle_scholarly.md", "middle_scholarly"),
    ("_middle_report.json", "middle_report"),
    ("_middle_debug.md", "middle_debug"),
    ("_middle.json", "middle_json"),
    ("_layout_overlay.pdf", "layout_overlay"),
    ("_span_overlay.pdf", "span_overlay"),
    ("_chunks.json", "chunks"),
    ("_meta.json", "meta"),
)

_EXTENSION_FORMATS: dict[str, str] = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".html": "html",
    ".json": "json",
    ".xml": "xml",
    ".pdf": "pdf",
    ".zip": "zip",
}

_FORMAT_ORDER: dict[str, int] = {
    "markdown": 10,
    "json": 20,
    "html": 30,
    "chunks": 40,
    "xml": 50,
    "meta": 60,
    "middle_json": 70,
    "middle_report": 80,
    "middle_debug": 90,
    "middle_scholarly": 100,
    "middle_scholarly_report": 110,
    "postprocess_report": 120,
    "layout_overlay": 130,
    "span_overlay": 140,
    "pdf": 900,
    "zip": 910,
    "file": 999,
}


def classify_output_file(path: str | os.PathLike[str]) -> tuple[str, str]:
    """Return ``(base_document_name, artifact_format)`` for a saved output."""

    name = os.path.basename(os.fspath(path))
    lower_name = name.lower()
    for suffix, artifact_format in _SUFFIX_FORMATS:
        if lower_name.endswith(suffix):
            base = name[: -len(suffix)]
            return base or Path(name).stem, artifact_format

    ext = Path(name).suffix.lower()
    artifact_format = _EXTENSION_FORMATS.get(ext, "file")
    base = Path(name).stem if ext else name
    return base, artifact_format


def output_file_record(path: str | os.PathLike[str]) -> dict[str, str]:
    _, artifact_format = classify_output_file(path)
    path_str = os.fspath(path)
    return {
        "format": artifact_format,
        "path": path_str,
        "name": os.path.basename(path_str),
    }


def output_file_records(paths: Iterable[str | os.PathLike[str]]) -> list[dict[str, str]]:
    return [
        output_file_record(path)
        for path in paths
        if path and os.path.isfile(path)
    ]


def scan_output_records_for_restore(out_dir: str | os.PathLike[str]) -> dict[str, list[dict[str, str]]]:
    found: dict[str, list[dict[str, str]]] = {}
    out_path = Path(out_dir)
    if not out_path.exists():
        return found

    for entry in sorted(out_path.iterdir(), key=lambda item: item.name.lower()):
        if not entry.is_file():
            continue
        base, artifact_format = classify_output_file(entry)
        found.setdefault(base, []).append(
            {
                "format": artifact_format,
                "path": str(entry),
                "name": entry.name,
            }
        )

    return {
        base: sorted(
            records,
            key=lambda record: (
                _FORMAT_ORDER.get(record.get("format", "file"), _FORMAT_ORDER["file"]),
                record.get("name", "").lower(),
            ),
        )
        for base, records in sorted(found.items(), key=lambda item: item[0].lower())
    }
