from dataclasses import dataclass


@dataclass
class MarkdownPostprocessConfig:
    markdown_postprocess_enabled: bool = False
    markdown_postprocess_review_only: bool = True
    markdown_postprocess_save_report: bool = True
    markdown_postprocess_enable_cleanup: bool = True
    markdown_postprocess_enable_printed_page_repair: bool = False
    markdown_postprocess_enable_llm: bool = False
    markdown_postprocess_llm_provider: str = "openai"
    markdown_postprocess_llm_base_url: str | None = None
    markdown_postprocess_llm_model: str | None = None
    markdown_postprocess_llm_api_key: str | None = None
    markdown_postprocess_llm_timeout: int = 60
    markdown_postprocess_llm_max_retries: int = 1
    markdown_postprocess_strict_null_policy: bool = True
