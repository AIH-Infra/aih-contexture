"""
Debug script to trace the complete flow of printed page number extraction and rendering.
"""

import sys
import io
import logging

# Fix Windows console encoding issues
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Set up detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

from aih_contexture.converters.pdf import PdfConverter
from aih_contexture.models import create_model_dict
from aih_contexture.renderers.html import HTMLRenderer
from aih_contexture.renderers.markdown import MarkdownRenderer
from bs4 import BeautifulSoup
import re

def debug_page_number_flow(pdf_path):
    print("=" * 80)
    print("DEBUG: Printed Page Number Flow")
    print("=" * 80)
    print(f"PDF: {pdf_path}")
    print()

    # Configuration
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

    print("Configuration:")
    for key, value in config.items():
        print(f"  {key}: {value}")
    print()

    # Create models
    print("Loading models...")
    model_dict = create_model_dict()

    # Create converter
    print("Creating converter...")
    converter = PdfConverter(
        artifact_dict=model_dict,
        config=config
    )

    # Build document (this runs all processors)
    print()
    print("=" * 80)
    print("STAGE 1: Building Document (runs processors)")
    print("=" * 80)
    print()

    with converter.filepath_to_str(pdf_path) as temp_path:
        document = converter.build_document(temp_path)

        print()
        print("=" * 80)
        print("STAGE 2: Checking Page Metadata")
        print("=" * 80)
        print()

        for i, page in enumerate(document.pages):
            print(f"Page {i}:")
            if hasattr(page, "_internal_metadata"):
                print(f"  Has _internal_metadata: Yes")
                print(f"  Metadata keys: {list(page._internal_metadata.keys())}")
                if "printed_page_number" in page._internal_metadata:
                    print(f"  ✅ printed_page_number: '{page._internal_metadata['printed_page_number']}'")
                else:
                    print(f"  ❌ printed_page_number: NOT FOUND")
            else:
                print(f"  ❌ Has _internal_metadata: No")
            print()

        print("=" * 80)
        print("STAGE 3: Rendering HTML")
        print("=" * 80)
        print()

        # Render HTML
        html_renderer = HTMLRenderer(config={"paginate_output": True})
        html_output = html_renderer(document)

        # Parse HTML and check data-printed-page attributes
        soup = BeautifulSoup(html_output.html, "html.parser")
        page_divs = soup.find_all("div", class_="page")

        print(f"Found {len(page_divs)} page divs in HTML")
        print()

        for div in page_divs:
            page_id = div.get("data-page-id", "?")
            printed_page = div.get("data-printed-page", "")
            print(f"Page div {page_id}:")
            print(f"  data-page-id: {page_id}")
            print(f"  data-printed-page: '{printed_page}'")
            if printed_page:
                print(f"  ✅ Has printed page number")
            else:
                print(f"  ❌ No printed page number")
            print()

        print("=" * 80)
        print("STAGE 4: Rendering Markdown")
        print("=" * 80)
        print()

        # Render Markdown
        md_renderer = MarkdownRenderer(config={"paginate_output": True})
        md_output = md_renderer(document)

        markdown = md_output.markdown

        # Check for page tags
        page_tags = re.findall(r"<!-- Page: ([^>]+) -->", markdown)

        if page_tags:
            print(f"✅ Found {len(page_tags)} page tags:")
            for i, tag in enumerate(page_tags):
                print(f"  Page {i}: <!-- Page: {tag} -->")
        else:
            print("❌ No page tags found in Markdown output")

        print()
        print("=" * 80)
        print("Markdown Preview (first 1000 characters):")
        print("=" * 80)
        print(markdown[:1000])
        print("=" * 80)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python debug_page_number_flow.py <pdf_path>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    debug_page_number_flow(pdf_path)
