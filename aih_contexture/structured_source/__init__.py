"""Native TEI/XML and EPUB ingestion for preservation-oriented source packages."""

from .converter import StructuredSourceConverter, convert_structured_source
from .package import validate_source_package
from .renderer import render_scholarly_html

__all__ = ["StructuredSourceConverter", "convert_structured_source", "validate_source_package", "render_scholarly_html"]
