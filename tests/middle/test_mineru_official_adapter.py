import pytest

from aih_contexture.middle.adapters.mineru_official import (
    detect_mineru_official_json_kind,
    mineru_official_json_to_middle_document,
)
from aih_contexture.middle.scholarly_markdown import render_middle_scholarly_markdown
from aih_contexture.middle.validation import validate_middle_json


def test_mineru_content_list_json_imports_to_contexture_middle():
    payload = [
        {"type": "header", "text": "Journal", "bbox": [10, 20, 200, 40], "page_idx": 0},
        {"type": "text", "text": "Article Title", "text_level": 1, "bbox": [10, 60, 800, 100], "page_idx": 0},
        {"type": "text", "text": "Body paragraph.", "bbox": [10, 120, 800, 200], "page_idx": 0},
        {"type": "page_number", "text": "33", "bbox": [480, 950, 520, 980], "page_idx": 0},
        {
            "type": "list",
            "sub_type": "ref_text",
            "list_items": ["Hobbes, Leviathan.", "Spinoza, Ethics."],
            "bbox": [10, 200, 800, 260],
            "page_idx": 1,
        },
    ]

    data = mineru_official_json_to_middle_document(payload, source_name="sample.pdf", file_name="sample_content_list.json")

    assert validate_middle_json(data).ok is True
    assert data["metadata"]["import_source"] == "mineru_official_json"
    assert data["metadata"]["official_protocol"] == "mineru_content_list"
    assert data["pages"][0]["printed_page"] == "33"
    assert [block["type"] for block in data["pages"][0]["blocks"]] == [
        "PageHeader",
        "SectionHeader",
        "Text",
        "PageNumber",
    ]
    assert [block["type"] for block in data["pages"][1]["blocks"]] == ["Reference", "Reference"]
    markdown = render_middle_scholarly_markdown(data)
    assert "# Article Title" in markdown
    assert "Hobbes, Leviathan." in markdown


def test_mineru_content_list_v2_json_imports_structured_content():
    payload = [
        [
            {
                "type": "title",
                "content": {"title_content": [{"type": "text", "content": "Introduction"}], "level": 2},
                "bbox": [100, 80, 300, 120],
            },
            {
                "type": "paragraph",
                "content": {"paragraph_content": [{"type": "text", "content": "A paragraph."}]},
                "bbox": [100, 140, 900, 220],
            },
            {
                "type": "page_number",
                "content": {"page_number_content": [{"type": "text", "content": "34"}]},
                "bbox": [850, 40, 880, 60],
            },
        ]
    ]

    data = mineru_official_json_to_middle_document(payload, source_name="sample.pdf", file_name="sample_content_list_v2.json")

    assert detect_mineru_official_json_kind(payload, file_name="sample_content_list_v2.json") == "mineru_content_list_v2"
    assert validate_middle_json(data).ok is True
    assert data["pages"][0]["printed_page"] == "34"
    assert [block["type"] for block in data["pages"][0]["blocks"]] == ["SectionHeader", "Text", "PageNumber"]
    assert data["pages"][0]["blocks"][0]["text"] == "Introduction"


def test_mineru_import_preserves_body_footnote_reference_and_page_footnote_definition():
    payload = [
        {
            "type": "text",
            "text": "Some claim $^{35}$ continues in the body.",
            "bbox": [100, 100, 900, 300],
            "page_idx": 0,
        },
        {
            "type": "page_footnote",
            "text": "$^{35}$ De Corpore 4.26.1.",
            "bbox": [100, 850, 900, 930],
            "page_idx": 0,
        },
    ]

    data = mineru_official_json_to_middle_document(payload, source_name="sample.pdf", file_name="sample_content_list.json")
    markdown = render_middle_scholarly_markdown(data)

    assert validate_middle_json(data).ok is True
    assert [block["type"] for block in data["pages"][0]["blocks"]] == ["Text", "Footnote"]
    assert "Some claim <sup>35</sup> continues in the body." in markdown
    assert "<sup>35</sup> De Corpore 4.26.1." in markdown


def test_mineru_official_middle_json_imports_pdf_info_without_becoming_contexture_middle():
    payload = {
        "_backend": "pipeline",
        "_version_name": "3.2.1",
        "pdf_info": [
            {
                "page_idx": 0,
                "page_size": [612, 792],
                "para_blocks": [
                    {
                        "type": "title",
                        "bbox": [10, 20, 500, 60],
                        "lines": [{"spans": [{"type": "text", "content": "Chapter", "bbox": [10, 20, 500, 60]}]}],
                    }
                ],
            }
        ],
    }

    data = mineru_official_json_to_middle_document(payload, source_name="sample.pdf", file_name="sample_middle.json")

    assert validate_middle_json(data).ok is True
    assert data["metadata"]["official_protocol"] == "mineru_middle_json"
    assert data["pages"][0]["blocks"][0]["type"] == "SectionHeader"
    assert data["pages"][0]["blocks"][0]["text"] == "Chapter"


def test_mineru_import_rejects_contexture_middle_json_to_prevent_protocol_confusion():
    payload = {"schema_version": "contexture-middle-json/0.1", "pages": []}

    with pytest.raises(ValueError, match="Contexture Middle JSON"):
        mineru_official_json_to_middle_document(payload, file_name="doc_middle.json")
