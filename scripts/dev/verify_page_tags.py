"""
Simple verification script to check if page tags are in the output.
"""

import sys
import io
import re

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from aih_contexture.converters.pdf import PdfConverter
from aih_contexture.models import create_model_dict

def verify_page_tags(pdf_path):
    print("=" * 80)
    print("Verification: Page Tags in Output")
    print("=" * 80)
    print()

    config = {
        "layout_backend": "surya",
        "ocr_backend": "surya",
        "disable_ocr": True,
        "page_range": [0, 1, 2],
        "page_numbering_enabled": True,
        "use_printed_page_number": True,
        "printed_page_zones": ["footer", "header"],
        "page_number_format": "auto",
        "paginate_output": True,
    }

    print("Creating converter...")
    model_dict = create_model_dict()
    converter = PdfConverter(artifact_dict=model_dict, config=config)

    print("Converting PDF...")
    result = converter(pdf_path)

    markdown = str(result)

    print()
    print("=" * 80)
    print("Results")
    print("=" * 80)
    print()

    # Find all page tags
    page_tags = re.findall(r"<!-- Page: ([^>]+) -->", markdown)

    if page_tags:
        print(f"✅ SUCCESS: Found {len(page_tags)} page tags")
        for i, tag in enumerate(page_tags):
            print(f"  Tag {i+1}: <!-- Page: {tag} -->")
    else:
        print("❌ FAILED: No page tags found")

    print()

    # Find all page anchors
    page_anchors = re.findall(r"\{(\d+)\}", markdown)
    print(f"Found {len(page_anchors)} page anchors: {page_anchors}")

    print()
    print("=" * 80)
    print("First 2000 characters of output:")
    print("=" * 80)
    print(markdown[:2000])
    print("=" * 80)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python verify_page_tags.py <pdf_path>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    verify_page_tags(pdf_path)
