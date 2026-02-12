# Debug: Printed Page Number Issue

## Problem

The test shows that PageNumberProcessor is successfully extracting printed page numbers ('127' and '128'), but the `<!-- Page: X -->` tags are not appearing in the Markdown output.

## Expected Flow

```
1. PageNumberProcessor extracts page numbers
   ↓ Stores in page._internal_metadata["printed_page_number"]

2. HTMLRenderer reads metadata
   ↓ Sets data-printed-page attribute on page divs

3. MarkdownRenderer reads data-printed-page
   ↓ Generates <!-- Page: X --> tags

4. Final output contains tags
```

## Debug Script

Run the debug script to trace the complete flow:

```bash
python debug_page_number_flow.py <your_pdf_file>
```

## What to Check

### Stage 1: Page Metadata
- Does each page have `_internal_metadata`?
- Does `_internal_metadata` contain `"printed_page_number"`?
- What is the value of `printed_page_number`?

### Stage 2: HTML Attributes
- Do the page divs have `data-printed-page` attributes?
- Are the attribute values correct (not empty)?
- Do they match the metadata values?

### Stage 3: Markdown Tags
- Are `<!-- Page: X -->` tags present in the output?
- Do they match the printed page numbers?

## Possible Issues

1. **Metadata not set**: PageNumberProcessor not storing values correctly
2. **HTML not reading metadata**: HTMLRenderer not finding the metadata
3. **Markdown not reading HTML**: MarkdownRenderer not parsing attributes correctly
4. **Empty string issue**: Attribute exists but is empty, causing tag generation to skip

## Code Locations

- **PageNumberProcessor**: [marker/processors/page_number.py:459](marker/processors/page_number.py#L459)
  - Stores: `page._internal_metadata["printed_page_number"] = printed_page_number`

- **HTMLRenderer**: [marker/renderers/html.py:118-123](marker/renderers/html.py#L118-L123)
  - Reads metadata and sets HTML attribute

- **MarkdownRenderer**: [marker/renderers/markdown.py:84-98](marker/renderers/markdown.py#L84-L98)
  - Reads HTML attribute and generates tag
