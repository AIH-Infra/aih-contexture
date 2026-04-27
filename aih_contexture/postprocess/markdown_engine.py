from __future__ import annotations

from aih_contexture.postprocess.markdown_config import MarkdownPostprocessConfig
from aih_contexture.postprocess.markdown_lm import MarkdownLMAdapter
from aih_contexture.postprocess.printed_page_repair import build_segment_diagnostics, build_segment_review_proposals, infer_sequence_repairs
import re

from aih_contexture.postprocess.reporting import MarkdownPostprocessResult


def _cleanup_text(full_text: str) -> str:
    full_text = re.sub(r"\n{3,}", "\n\n", full_text)
    full_text = re.sub(r"(\n\s){3,}", "\n\n", full_text)
    return full_text.strip()


def _normalize_spacing(markdown: str) -> str:
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    return markdown.strip()


class MarkdownPostprocessEngine:
    def __init__(self, config: MarkdownPostprocessConfig | dict | None = None, llm_adapter: MarkdownLMAdapter | None = None):
        if isinstance(config, dict):
            self.config = MarkdownPostprocessConfig(**{
                key: value for key, value in config.items() if key in MarkdownPostprocessConfig.__dataclass_fields__
            })
        else:
            self.config = config or MarkdownPostprocessConfig()
        self.llm_adapter = llm_adapter or MarkdownLMAdapter(self.config)

    def process(self, markdown: str) -> MarkdownPostprocessResult:
        original = markdown or ""
        current = original
        warnings: list[str] = []
        actions = []

        if self.config.markdown_postprocess_enable_cleanup:
            current = _cleanup_text(current)
            current = _normalize_spacing(current)

        review_base = current

        if self.config.markdown_postprocess_enable_printed_page_repair:
            current, actions, repair_warnings = infer_sequence_repairs(current)
            warnings.extend(repair_warnings)

        final_markdown = review_base if self.config.markdown_postprocess_review_only else current

        result = MarkdownPostprocessResult(
            markdown=final_markdown,
            changed=(final_markdown != original),
            warnings=warnings,
            actions=actions,
            metadata={
                "cleanup_enabled": self.config.markdown_postprocess_enable_cleanup,
                "printed_page_repair_enabled": self.config.markdown_postprocess_enable_printed_page_repair,
                "review_only": self.config.markdown_postprocess_review_only,
                "review_span_count": 0,
                "mode": "review" if self.config.markdown_postprocess_review_only else "apply",
                "status": "review_only" if self.config.markdown_postprocess_review_only else "applied",
                "segment_diagnostics": build_segment_diagnostics(review_base),
                "segment_review_proposals": build_segment_review_proposals(review_base),
            },
        )

        if self.config.markdown_postprocess_enable_llm:
            result = self.llm_adapter.enhance(current, result)
            llm_meta = result.metadata.get("llm", {}) if isinstance(result.metadata, dict) else {}
            result.metadata["review_span_count"] = llm_meta.get("span_count", 0) if isinstance(llm_meta, dict) else 0

        return result
