from aih_contexture.converters.ocr_direct_async import OcrDirectAsyncConverter


def test_ocr_direct_async_converter_uses_default_endpoint_when_config_value_missing(monkeypatch):
    monkeypatch.setattr(
        "aih_contexture.converters.ocr_direct_async.OcrServiceFactory.create_service",
        lambda config: object(),
    )

    converter = OcrDirectAsyncConverter(
        {
            "ocr_backend": "chandra",
            "ocr_endpoint": None,
            "ocr_api_style": "lmstudio-native",
        }
    )

    assert converter.endpoint == "http://localhost:1234/api/v1/chat"


def test_ocr_direct_specialized_vlm_renders_primary_markdown_from_middle(monkeypatch):
    monkeypatch.setattr(
        "aih_contexture.converters.ocr_direct_async.OcrServiceFactory.create_service",
        lambda config: object(),
    )

    converter = OcrDirectAsyncConverter(
        {
            "ocr_backend": "paddleocr_vl",
            "ocr_endpoint": "http://localhost:1234/v1",
            "ocr_api_style": "openai",
        }
    )
    converter._last_chunks = [
        {
            "page_num": 0,
            "img_size": [100, 200],
            "backend": "paddleocr_vl",
            "official_protocol": "paddleocr_vl_prompt",
            "markdown": "# Official title",
            "blocks": [
                {
                    "label": "section_header",
                    "type": "section_header",
                    "text": "Contexture title",
                    "bbox": [0, 0, 100, 20],
                },
                {
                    "label": "text",
                    "type": "text",
                    "text": "Body text",
                    "bbox": [0, 30, 100, 60],
                },
            ],
        }
    ]
    converter._last_printed_pages = ["12"]

    markdown = converter._render_specialized_vlm_middle_markdown(
        source_name="sample.pdf",
        source="sample.pdf",
    )

    assert markdown is not None
    assert "{0}" in markdown
    assert "{1}" in markdown
    assert "<!-- Page: 12 -->" in markdown
    assert "## Contexture title" in markdown
    assert "# Official title" not in markdown


def test_ocr_direct_filter_page_markers_can_render_margin_blocks_as_plain_text(monkeypatch):
    monkeypatch.setattr(
        "aih_contexture.converters.ocr_direct_async.OcrServiceFactory.create_service",
        lambda config: object(),
    )

    converter = OcrDirectAsyncConverter(
        {
            "ocr_backend": "churro",
            "ocr_endpoint": "http://localhost:1234/v1/chat/completions",
            "ocr_api_style": "openai",
            "ocr_filter_margin_notes": True,
        }
    )

    pages = [
        "Body\n\n<!-- Margin:left id=\"m1\" a=0-1 -->\n> Side note\n> second line\n<!-- /Margin -->"
    ]

    filtered = converter._filter_page_markers(pages)

    assert "<!-- Margin:left" not in filtered[0]
    assert "<!-- /Margin" not in filtered[0]
    assert "> Side note" not in filtered[0]
    assert "Side note\nsecond line" in filtered[0]


def test_ocr_direct_specialized_middle_render_can_filter_margin_comments(monkeypatch):
    monkeypatch.setattr(
        "aih_contexture.converters.ocr_direct_async.OcrServiceFactory.create_service",
        lambda config: object(),
    )

    converter = OcrDirectAsyncConverter(
        {
            "ocr_backend": "paddleocr_vl",
            "ocr_endpoint": "http://localhost:1234/v1",
            "ocr_api_style": "openai",
            "ocr_filter_margin_notes": True,
        }
    )
    converter._last_chunks = [
        {
            "page_num": 0,
            "img_size": [100, 200],
            "backend": "paddleocr_vl",
            "official_protocol": "paddleocr_vl_prompt",
            "blocks": [
                {
                    "label": "marginal_note_left",
                    "type": "marginal_note",
                    "text": "Side note",
                    "bbox": [0, 40, 20, 80],
                    "attrs": {"side": "left"},
                },
                {"label": "text", "type": "text", "text": "Body text", "bbox": [30, 40, 90, 80]},
            ],
        }
    ]

    markdown = converter._render_specialized_vlm_middle_markdown(
        source_name="sample.pdf",
        source="sample.pdf",
    )

    assert markdown is not None
    assert "<!-- Margin:" not in markdown
    assert "> Side note" not in markdown
    assert "Side note" in markdown
    assert "Body text" in markdown
