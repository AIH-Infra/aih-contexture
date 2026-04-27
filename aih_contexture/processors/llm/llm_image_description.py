from pydantic import BaseModel

from aih_contexture.processors.llm import PromptData, BaseLLMSimpleBlockProcessor, BlockData

from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document

from typing import Annotated, List
import re


class LLMImageDescriptionProcessor(BaseLLMSimpleBlockProcessor):
    block_types = (
        BlockTypes.Picture,
        BlockTypes.Figure,
    )
    extract_images: Annotated[bool, "Extract images from the document."] = True
    image_description_language: Annotated[
        str,
        "Target language for image descriptions. Use 'auto' to follow the document language when possible.",
    ] = "auto"
    image_description_prompt: Annotated[
        str,
        "The prompt to use for generating image descriptions.",
        "Default is a string containing the Gemini prompt.",
    ] = """You are a document analysis expert who specializes in creating text descriptions for images.
You will receive an image of a picture or figure.  Your job will be to create a short description of the image.
**Instructions:**
1. Carefully examine the provided image.
2. Analyze any text that was extracted from within the image.
3. Output a faithful description of the image.  Make sure there is enough specific detail to accurately reconstruct the image.  If the image is a figure or contains numeric data, include the numeric data in the output.
4. Output only the description itself. Do not prepend labels like "Image description:", "Figure description:", block IDs, or file paths.
**Example:**
Input:
```text
"Fruit Preference Survey"
20, 15, 10
Apples, Bananas, Oranges
```
Output:
In this figure, a bar chart titled "Fruit Preference Survey" is showing the number of people who prefer different types of fruits.  The x-axis shows the types of fruits, and the y-axis shows the number of people.  The bar chart shows that most people prefer apples, followed by bananas and oranges.  20 people prefer apples, 15 people prefer bananas, and 10 people prefer oranges.
**Input:**
```text
{raw_text}
```

{output_language_instruction}
"""

    def inference_blocks(self, document: Document) -> List[BlockData]:
        blocks = super().inference_blocks(document)
        if self.extract_images:
            return []
        return blocks

    def block_prompts(self, document: Document) -> List[PromptData]:
        prompt_data = []
        for block_data in self.inference_blocks(document):
            block = block_data["block"]
            prompt = self._build_prompt(block.raw_text(document))
            image = self.extract_image(document, block)

            prompt_data.append(
                {
                    "prompt": prompt,
                    "image": image,
                    "block": block,
                    "schema": ImageSchema,
                    "page": block_data["page"],
                }
            )

        return prompt_data

    def rewrite_block(
        self, response: dict, prompt_data: PromptData, document: Document
    ):
        block = prompt_data["block"]

        if not response or "image_description" not in response:
            block.update_metadata(llm_error_count=1)
            return

        image_description = response["image_description"]
        image_description = self._normalize_image_description(image_description)
        if len(image_description) < 10:
            block.update_metadata(llm_error_count=1)
            return

        block.description = image_description

    def _build_prompt(self, raw_text: str) -> str:
        language_instruction = self._language_instruction()
        prompt = self.image_description_prompt.replace("{raw_text}", raw_text)

        if "{output_language_instruction}" in prompt:
            return prompt.replace(
                "{output_language_instruction}", language_instruction
            )

        return f"{prompt.rstrip()}\n\n{language_instruction}"

    def _language_instruction(self) -> str:
        language = (self.image_description_language or "auto").strip().lower()
        language_map = {
            "zh": "Write the final image description entirely in Simplified Chinese. Do not mix in other languages unless the image contains names or text that should be quoted as-is.",
            "en": "Write the final image description entirely in English.",
            "ja": "Write the final image description entirely in Japanese.",
            "fr": "Write the final image description entirely in French.",
            "de": "Write the final image description entirely in German.",
        }

        if language in language_map:
            return language_map[language]

        return (
            "Write the final image description in the primary language of the surrounding document text when it is clear. "
            "If the document language is unclear, default to English. Do not mix multiple languages in the same description unless necessary for quoted text."
        )

    def _normalize_image_description(self, image_description: str) -> str:
        text = (image_description or "").strip()
        if not text:
            return ""

        patterns = [
            r"^\s*image\s+/page/\d+/(?:picture|figure)/\d+\s+description\s*:\s*",
            r"^\s*(?:image|figure)\s+description\s*:\s*",
            r"^\s*(?:image|figure)\s+/[^:]+?\s+description\s*:\s*",
        ]

        for pattern in patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        return text.strip()


class ImageSchema(BaseModel):
    image_description: str
