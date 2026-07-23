from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from aih_contexture.util import parse_range_str

ContextureMode = Literal[
    "pipeline",
    "vlm_generalized",
    "vlm_specialized",
    "office",
    "markdown_postprocess",
]


def normalize_page_range(value: Any) -> list[int] | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return parse_range_str(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, list):
        return value
    raise TypeError(f"Unsupported page_range type: {type(value).__name__}")


@dataclass(slots=True)
class ContextureJob:
    input_path: str | None = None
    input_bytes: bytes | None = None
    input_name: str | None = None
    mode: ContextureMode = "pipeline"
    output_formats: list[str] = field(default_factory=lambda: ["markdown"])
    page_range: list[int] | None = None
    config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ContextureJob":
        config = dict(payload.get("config") or {})
        page_range = normalize_page_range(payload.get("page_range", config.get("page_range")))
        if page_range is not None:
            config["page_range"] = page_range

        output_formats = payload.get("output_formats")
        if output_formats is None:
            output_format = payload.get("output_format") or config.get("output_format") or "markdown"
            output_formats = [output_format]
        elif isinstance(output_formats, str):
            output_formats = [output_formats]

        return cls(
            input_path=payload.get("input_path") or payload.get("filepath") or payload.get("file_path"),
            input_bytes=payload.get("input_bytes"),
            input_name=payload.get("input_name") or payload.get("file_name"),
            mode=payload.get("mode") or payload.get("conversion_mode") or config.get("conversion_mode", "pipeline"),
            output_formats=list(output_formats),
            page_range=page_range,
            config=config,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_path": self.input_path,
            "input_name": self.input_name,
            "mode": self.mode,
            "output_formats": self.output_formats,
            "page_range": self.page_range,
            "config": self.config,
        }


@dataclass(slots=True)
class ContextureResult:
    markdown: str | None = None
    html: str | None = None
    json_text: str | None = None
    chunks: str | None = None
    page_count: int = 0
    middle_json: dict[str, Any] | None = None
    images: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    debug_artifacts: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    file_outputs: list[dict[str, Any]] = field(default_factory=list)
