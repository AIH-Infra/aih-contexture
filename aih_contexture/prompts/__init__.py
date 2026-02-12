"""
VLM Prompt Template System

Provides customizable prompt templates for different document types
with API parameter control and cross-API compatibility.

Usage:
    from aih_contexture.prompts import PromptBuilder

    # Use built-in template
    template = PromptBuilder.from_template("modern_publication")
    prompt = template.build_prompt()
    api_params = template.get_api_params("qwen")

    # Custom template
    template = PromptBuilder.from_params(
        text_direction="vertical",
        has_footnotes=True,
        temperature=0.0
    )
"""

from aih_contexture.prompts.base import VlmPromptTemplate, validate_and_clean_output
from aih_contexture.prompts.builder import PromptBuilder
from aih_contexture.prompts.api_adapter import APIParameterAdapter
from aih_contexture.prompts.templates import BUILTIN_TEMPLATES, TEMPLATE_DISPLAY_NAMES

__all__ = [
    "VlmPromptTemplate",
    "PromptBuilder",
    "APIParameterAdapter",
    "validate_and_clean_output",
    "BUILTIN_TEMPLATES",
    "TEMPLATE_DISPLAY_NAMES",
]
