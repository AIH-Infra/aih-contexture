import json

from pydantic import BaseModel
from typing import Annotated, Optional

from marker.extractors import BaseExtractor
from marker.logger import get_logger
from marker.schema.document import Document
from marker.schema.groups.page import PageGroup

logger = get_logger()


class PageExtractionSchema(BaseModel):
    description: str
    detailed_notes: str


class PageExtractor(BaseExtractor):
    """
    An extractor that pulls data from a single page.
    """

    page_schema: Annotated[
        str,
        "The JSON schema to be extracted from the page.",
    ] = ""

    page_extraction_prompt = """You are an expert document analyst who reads documents and pulls data out in JSON format. You will receive the markdown representation of a document page, and a JSON schema that we want to extract from the document. Your task is to write detailed notes on this page, so that when you look at all your notes from across the document, you can fill in the schema.
    
Some notes:
- The schema may contain a single object to extract from the entire document, or an array of objects. 
- The schema may contain nested objects, arrays, and other complex structures.

Some guidelines:
- Write very thorough notes, and include specific JSON snippets that can be extracted from the page.
- You may need information from prior or subsequent pages to fully fill in the schema, so make sure to write detailed notes that will let you join entities across pages later on.
- Estimate your confidence in the values you extract, so you can reconstruct the JSON later when you only have your notes.
- Some tables and other data structures may continue on a subsequent page, so make sure to store the positions that data comes from where appropriate.

**Instructions:**
1. Analyze the provided markdown representation of the page.
2. Analyze the JSON schema.
3. Write a short description of the fields in the schema, and the associated values in the markdown.
4. Write detailed notes on the page, including any values that can be extracted from the markdown.  Include snippets of JSON that can be extracted from the page where possible.

**Example:**
Input:

Markdown
```markdown
| Make   | Sales |
|--------|-------|
| Honda  | 100   |
| Toyota | 200   |
```

Schema

```json
{'$defs': {'Cars': {'properties': {'make': {'title': 'Make', 'type': 'string'}, 'sales': {'title': 'Sales', 'type': 'integer'}, 'color': {'title': 'Color', 'type': 'string'}}, 'required': ['make', 'sales', 'color'], 'title': 'Cars', 'type': 'object'}}, 'properties': {'cars': {'items': {'$ref': '#/$defs/Cars'}, 'title': 'Cars', 'type': 'array'}}, 'required': ['cars'], 'title': 'CarsList', 'type': 'object'}
```

Output:

Description: The schema has a list of cars, each with a make, sales, and color. The image and markdown contain a table with 2 cars: Honda with 100 sales and Toyota with 200 sales. The color is not present in the table.
Detailed Notes: On this page, I see a table with car makes and sales. The makes are Honda and Toyota, with sales of 100 and 200 respectively. The color is not present in the table, so I will leave it blank in the JSON.  That information may be present on another page.  Some JSON snippets I may find useful later are:
```json
{
    "make": "Honda",
    "sales": 100,
}
```
```json
{
    "make": "Toyota",
    "sales": 200,
}
```

Honda is the first row in the table, and Toyota is the second row.  Make is the first column, and sales is the second.

**Input:**

Markdown
```markdown
{{page_md}}
```

Schema
```json
{{schema}}
```
"""

    def __call__(
        self, document: Document, page: PageGroup, page_markdown: str, **kwargs
    ) -> Optional[PageExtractionSchema]:
        if not self.page_schema:
            raise ValueError(
                "Page schema must be defined for structured extraction to work."
            )

        prompt = self.page_extraction_prompt.replace(
            "{{page_md}}", page_markdown
        ).replace("{{schema}}", json.dumps(self.page_schema))
        response = self.llm_service(prompt, None, page, PageExtractionSchema)
        logger.debug(f"Page extraction response: {response}")

        if not response or any(
            [
                key not in response
                for key in [
                    "description",
                    "detailed_notes",
                ]
            ]
        ):
            page.update_metadata(llm_error_count=1)
            return None

        return PageExtractionSchema(
            description=response["description"],
            detailed_notes=response["detailed_notes"],
        )
