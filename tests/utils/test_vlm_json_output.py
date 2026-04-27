import pytest

from aih_contexture.utils.vlm_json_output import (
    load_and_validate_vlm_json,
    parse_json_to_markdown,
)


def test_load_and_validate_vlm_json_rejects_missing_regions():
    with pytest.raises(ValueError):
        load_and_validate_vlm_json('{"printed_page_number": "1"}')


def test_parse_json_to_markdown_returns_printed_page():
    json_str = """{
        "printed_page_number": "12",
        "page_width": 100,
        "page_height": 200,
        "regions": [
            {
                "label": "Text",
                "bbox": [0, 0, 10, 10],
                "text": "Hello world",
                "confidence": 0.95
            }
        ]
    }"""

    markdown, printed_page = parse_json_to_markdown(json_str)

    assert "Hello world" in markdown
    assert printed_page == "12"


def test_parse_json_to_markdown_raises_on_invalid_json():
    with pytest.raises(ValueError):
        parse_json_to_markdown("not json")
