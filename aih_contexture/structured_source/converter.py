from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters import parse_epub, parse_tei_xml
from .errors import StructuredSourceError
from .package import write_source_package
from .renderer import render_scholarly_markdown
from .validation import assert_valid_source_document


@dataclass(slots=True)
class StructuredSourceConversion:
    document: dict[str, Any]
    markdown: str
    package_path: str | None = None
    package_manifest: dict[str, Any] | None = None


class StructuredSourceConverter:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = dict(config or {})

    def convert_bytes(self, data: bytes, source_name: str) -> StructuredSourceConversion:
        suffix = Path(source_name).suffix.lower()
        if suffix == ".epub":
            document, artifacts = parse_epub(data, source_name)
        elif suffix in {".xml", ".tei"}:
            document, artifacts = parse_tei_xml(data, source_name)
        else:
            raise StructuredSourceError("Structured source mode accepts only .xml, .tei, and .epub")
        assert_valid_source_document(document)
        markdown = render_scholarly_markdown(document)
        package_path = None
        package_manifest = None
        output_dir = self.config.get("output_dir")
        if output_dir:
            package, package_manifest = write_source_package(
                document, output_dir, source_data=data, source_name=source_name, raw_artifacts=artifacts,
                emit_line_indexes=bool(self.config.get("emit_line_indexes", False)),
            )
            package_path = os.fspath(package)
        return StructuredSourceConversion(document, markdown, package_path, package_manifest)

    def __call__(self, input_path: str | os.PathLike[str]) -> StructuredSourceConversion:
        path = Path(input_path)
        return self.convert_bytes(path.read_bytes(), path.name)


def convert_structured_source(input_path: str, output_dir: str, **config: Any) -> StructuredSourceConversion:
    return StructuredSourceConverter({"output_dir": output_dir, **config})(input_path)
