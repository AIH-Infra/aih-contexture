from __future__ import annotations

from aih_contexture.postprocess.markdown_config import MarkdownPostprocessConfig
from aih_contexture.postprocess.markdown_lm import MarkdownLMAdapter
from aih_contexture.postprocess.printed_page_repair import build_segment_diagnostics, build_segment_review_proposals, infer_sequence_repairs
import re
from aih_contexture.utils.markdown_regions import markdown_lines

from aih_contexture.postprocess.reporting import MarkdownPostprocessResult


def _cleanup_text(full_text: str) -> str:
    # Structural regions own their whitespace (including string literals in
    # code). Never run a whole-document cleanup after restoring those regions.
    output, prose = [], []
    def flush():
        value = ''.join(prose)
        value = re.sub(r'(?:(?:\r?\n)[ \t]*){3,}',
                       lambda m: ('\r\n' if '\r\n' in m[0] else '\n') * 2, value)
        if output and output[-1].endswith('\n'):
            value = re.sub(r'^(?:[ \t]*\r?\n){2,}',
                           lambda m: '\r\n' if '\r\n' in m[0] else '\n', value)
        output.append(value)
        prose.clear()
    for line, protected in markdown_lines(full_text, protect_indented=True):
        if protected:
            flush()
            output.append(line)
        else:
            prose.append(line)
    flush()
    return ''.join(output)


def _normalize_spacing(markdown: str) -> str:
    return _cleanup_text(markdown)


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
