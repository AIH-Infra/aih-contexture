from aih_contexture.processors.llm.llm_image_description import (
    LLMImageDescriptionProcessor,
)


def test_image_description_prompt_uses_simplified_chinese_instruction():
    processor = LLMImageDescriptionProcessor(
        {
            "extract_images": False,
            "image_description_language": "zh",
        }
    )

    prompt = processor._build_prompt("示例原文")

    assert "Simplified Chinese" in prompt
    assert "示例原文" in prompt


def test_image_description_prompt_auto_mode_defaults_to_document_language():
    processor = LLMImageDescriptionProcessor(
        {
            "extract_images": False,
            "image_description_language": "auto",
        }
    )

    prompt = processor._build_prompt("Sample raw text")

    assert "primary language of the surrounding document text" in prompt
    assert "Sample raw text" in prompt


def test_image_description_normalizer_strips_internal_image_prefix():
    processor = LLMImageDescriptionProcessor(
        {
            "extract_images": False,
            "image_description_language": "en",
        }
    )

    normalized = processor._normalize_image_description(
        "Image /page/0/Picture/0 description: An ornate, framed illustration depicting a maritime scene."
    )

    assert normalized == "An ornate, framed illustration depicting a maritime scene."
