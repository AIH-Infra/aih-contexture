from aih_contexture.evaluation.scholarly_markdown import evaluate_scholarly_markdown_text
from aih_contexture.middle.adapters.vlm_json import vlm_json_document_to_middle_document
from aih_contexture.middle.scholarly_markdown import render_middle_scholarly_markdown
from aih_contexture.middle.validation import validate_middle_json


def test_vlm_json_adapter_maps_page_metadata_and_humanities_labels():
    data = vlm_json_document_to_middle_document(
        {
            "pages": [
                {
                    "page_number": 1,
                    "printed_page_number": "iv",
                    "page_width": 600,
                    "page_height": 800,
                    "regions": [
                        {"label": "Page-Header", "bbox": [10, 10, 590, 30], "text": "Header", "confidence": 0.91},
                        {"label": "Section-Header", "bbox": [20, 50, 400, 80], "text": "Introduction"},
                        {"label": "Text", "bbox": [20, 90, 560, 200], "text": "Main text"},
                        {"label": "Marginal-Note-Left", "bbox": [0, 100, 15, 180], "text": "Side note"},
                        {"label": "Footnote", "bbox": [20, 720, 560, 760], "text": "1. Archive note"},
                        {"label": "Equation-Block", "bbox": [20, 210, 560, 250], "text": "a^2+b^2=c^2"},
                        {"label": "Code-Block", "bbox": [20, 260, 560, 320], "text": "print('x')"},
                        {"label": "Table-Of-Contents", "bbox": [20, 330, 560, 390], "text": "1 Intro"},
                    ],
                }
            ]
        },
        backend="vlm_specialized",
        model="contexture-vlm",
        source_name="sample.pdf",
        source="sample.json",
    ).to_dict()

    page = data["pages"][0]
    blocks = page["blocks"]

    assert validate_middle_json(data).ok is True
    assert page["index"] == 0
    assert page["printed_page"] == "iv"
    assert data["backends"]["vlm"] == "vlm_specialized"
    assert [block["type"] for block in blocks] == [
        "PageHeader",
        "SectionHeader",
        "Text",
        "MarginalNote",
        "Footnote",
        "Equation",
        "Code",
        "TableOfContents",
    ]
    assert blocks[3]["attrs"]["side"] == "left"
    assert blocks[2]["spans"][0]["text"] == "Main text"
    assert blocks[2]["provenance"][0]["stage"] == "vlm_parse"
    assert blocks[2]["spans"][0]["provenance"][0]["stage"] == "vlm_text"


def test_vlm_json_adapter_accepts_json_pages_strings_and_polygon_coordinates():
    data = vlm_json_document_to_middle_document(
        {
            "json_pages": [
                """{
                    "printed_page_number": "1",
                    "page_width": 100,
                    "page_height": 120,
                    "regions": [
                        {
                            "label": "Image-Description",
                            "points": [[1, 2], [21, 2], [21, 22], [1, 22]],
                            "text": "A manuscript image",
                            "confidence": 0.8
                        }
                    ]
                }"""
            ]
        },
        backend="vlm_generalized",
    ).to_dict()

    block = data["pages"][0]["blocks"][0]

    assert validate_middle_json(data).ok is True
    assert block["type"] == "ImageDescription"
    assert block["bbox"] == [1.0, 2.0, 21.0, 22.0]
    assert block["polygon"] == [[1.0, 2.0], [21.0, 2.0], [21.0, 22.0], [1.0, 22.0]]


def test_vlm_json_scholarly_markdown_passes_syntax_evaluation():
    data = vlm_json_document_to_middle_document(
        [
            {
                "printed_page_number": "1",
                "page_width": 100,
                "page_height": 120,
                "regions": [
                    {"label": "Page-Footer", "text": "Footer"},
                    {"label": "Text", "text": "Text body"},
                    {"label": "Footnote", "text": "Footnote body"},
                    {"label": "Caption", "text": "Fig. 1"},
                ],
            }
        ],
        backend="vlm_specialized",
    ).to_dict()

    markdown = render_middle_scholarly_markdown(data)
    report = evaluate_scholarly_markdown_text(markdown)

    assert report["ok"] is True
    assert "<!-- PageFooter: Footer -->" in markdown
    assert "<!-- FootnoteBlock:" not in markdown
    assert "<sup>1</sup> Footnote body" in markdown
