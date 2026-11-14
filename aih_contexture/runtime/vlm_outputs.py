from __future__ import annotations

from typing import Any, Protocol


class GeneralizedVlmOutput(Protocol):
    """Public result surface exposed by generalized VLM converters."""

    model: str
    config: dict[str, Any]

    @property
    def last_json_pages(self) -> list[str] | None: ...

    @property
    def last_clean_html_pages(self) -> list[str] | None: ...

    @property
    def last_markdown_pages(self) -> list[str] | None: ...

    @property
    def last_json_diagnostics(self) -> list[dict[str, Any]] | None: ...

    @property
    def last_response_metadata(self) -> list[dict[str, Any]]: ...

    @property
    def checkpoint_path(self) -> str | None: ...


class SpecializedVlmOutput(Protocol):
    """Public result surface exposed by specialized OCR/VLM converters."""

    backend: str
    model: str

    @property
    def last_xml_pages(self) -> list[str] | None: ...

    @property
    def last_clean_html_pages(self) -> list[str] | None: ...

    @property
    def last_chunks(self) -> list[Any] | None: ...

    @property
    def last_printed_pages(self) -> list[str | None] | None: ...

    @property
    def last_official_markdown_pages(self) -> list[str] | None: ...

    @property
    def last_searchable_pdf_path(self) -> str | None: ...
