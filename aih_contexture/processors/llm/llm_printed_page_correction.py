"""
LLM辅助印刷页码修正处理器

复用独立 Markdown 后处理引擎的 sparse+tightened printed-page repair 路径，
在 Pipeline 的 LLM 增强主线上写回页级印刷页码元数据。
"""

from typing import Annotated

from aih_contexture.logger import get_logger
from aih_contexture.postprocess.markdown_engine import MarkdownPostprocessEngine
from aih_contexture.postprocess.markdown_lm import MarkdownLMAdapter
from aih_contexture.postprocess.printed_page_repair import parse_markdown_pages, _roman_to_int
from aih_contexture.processors.llm import BaseLLMProcessor
from aih_contexture.renderers.markdown import MarkdownRenderer
from aih_contexture.schema.document import Document

logger = get_logger()


class LLMPrintedPageCorrectionProcessor(BaseLLMProcessor):
    """在 Pipeline 的 LLM 增强路径中复用 sparse/tightened printed-page repair。"""

    use_llm: Annotated[
        bool,
        "Whether to use the LLM model.",
    ] = True

    correction_prompt: Annotated[
        str, "用户自定义的修正提示（当前保留，尚未注入 sparse prompt）"
    ] = ""

    def _build_markdown_snapshot(self, document: Document) -> str:
        renderer = MarkdownRenderer(
            {
                "paginate_output": True,
                "page_separator": "-" * 48,
                "markdown_formatting_enabled": False,
                "markdown_postprocess_enabled": False,
                "custom_id_source": "none",
            }
        )
        rendered = renderer(document)
        return rendered.markdown

    def _build_adapter_from_service(self) -> MarkdownLMAdapter:
        service = self.llm_service
        provider = "openai"
        base_url = getattr(service, "openai_base_url", None)
        model = getattr(service, "openai_model", None)
        api_key = getattr(service, "openai_api_key", None)

        if hasattr(service, "lmstudio_base_url") or hasattr(service, "lmstudio_model"):
            provider = "lmstudio_native"
            base_url = getattr(service, "lmstudio_base_url", base_url)
            model = getattr(service, "lmstudio_model", model)
            api_key = getattr(service, "lmstudio_api_key", api_key)

        config = {
            "markdown_postprocess_enable_cleanup": False,
            "markdown_postprocess_enable_printed_page_repair": False,
            "markdown_postprocess_enable_llm": True,
            "markdown_postprocess_review_only": False,
            "markdown_postprocess_llm_provider": provider,
            "markdown_postprocess_llm_base_url": base_url,
            "markdown_postprocess_llm_model": model,
            "markdown_postprocess_llm_api_key": api_key,
            "markdown_postprocess_llm_timeout": getattr(service, "timeout", 60),
            "markdown_postprocess_llm_max_retries": getattr(service, "max_retries", 1),
        }
        return MarkdownLMAdapter(config, service=service)

    def __call__(self, document: Document):
        if not self.use_llm or not self.llm_service:
            logger.warning("[LLMPrintedPageCorrectionProcessor] LLM service not configured")
            return

        markdown = self._build_markdown_snapshot(document)
        pages = parse_markdown_pages(markdown)
        valid_count = sum(1 for page in pages if page.normalized_candidate is not None)
        if valid_count == 0:
            logger.info("[LLMPrintedPageCorrectionProcessor] No printed page numbers found, skipping")
            return

        adapter = self._build_adapter_from_service()
        engine = MarkdownPostprocessEngine(
            {
                "markdown_postprocess_enable_cleanup": False,
                "markdown_postprocess_enable_printed_page_repair": False,
                "markdown_postprocess_enable_llm": True,
                "markdown_postprocess_review_only": False,
                "markdown_postprocess_llm_provider": adapter.config.markdown_postprocess_llm_provider,
                "markdown_postprocess_llm_base_url": adapter.config.markdown_postprocess_llm_base_url,
                "markdown_postprocess_llm_model": adapter.config.markdown_postprocess_llm_model,
                "markdown_postprocess_llm_api_key": adapter.config.markdown_postprocess_llm_api_key,
                "markdown_postprocess_llm_timeout": adapter.config.markdown_postprocess_llm_timeout,
                "markdown_postprocess_llm_max_retries": adapter.config.markdown_postprocess_llm_max_retries,
            },
            llm_adapter=adapter,
        )
        result = engine.process(markdown)
        updated_pages = {page.pdf_page: page for page in parse_markdown_pages(result.markdown)}

        applied = 0
        for page in document.pages:
            metadata = getattr(page, "_internal_metadata", None)
            if metadata is None:
                metadata = {}
                page._internal_metadata = metadata

            updated = updated_pages.get(int(page.page_id))
            if updated is None or updated.normalized_candidate is None:
                continue

            original = metadata.get("printed_page_number")
            final_value = updated.normalized_candidate
            if original == final_value:
                continue

            metadata["printed_page_number"] = final_value
            numeric = int(final_value) if final_value.isdigit() else _roman_to_int(final_value)
            if numeric is not None:
                metadata["printed_page_number_numeric"] = numeric
            metadata["printed_page_number_corrected"] = True
            applied += 1

        document._internal_metadata = getattr(document, "_internal_metadata", {})
        document._internal_metadata["llm_printed_page_correction_report"] = result.summary()
        logger.info(
            "[LLMPrintedPageCorrectionProcessor] Applied sparse printed-page repair: suggestions=%s applied=%s status=%s",
            result.summary().get("suggested_action_count", 0),
            result.summary().get("applied_action_count", applied),
            result.summary().get("status"),
        )
