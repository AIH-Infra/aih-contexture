from aih_contexture.utils.vlm_json_output import parse_json_to_markdown


def test_parse_json_to_markdown_does_not_append_uncertainty_marker():
    markdown, printed_page = parse_json_to_markdown(
        """{
            "printed_page_number": "12",
            "regions": [
                {"label": "Text", "text": "Main text", "confidence": 0.2}
            ]
        }""",
        {},
    )

    assert printed_page == "12"
    assert markdown == "Main text"


def test_parse_json_to_markdown_renders_marginal_note_when_enabled():
    markdown, _ = parse_json_to_markdown(
        """{
            "printed_page_number": null,
            "regions": [
                {"label": "Marginal-Note-Left", "text": "Side note", "confidence": null}
            ]
        }""",
        {"vlm_direct_marginal_note_enabled": True},
    )

    assert markdown == "<!-- Margin:left -->\n> Side note\n<!-- /Margin -->"


def test_parse_json_to_markdown_renders_normalized_marginal_label_when_enabled():
    markdown, _ = parse_json_to_markdown(
        """{
            "printed_page_number": null,
            "regions": [
                {"label": "Marginal-Left", "text": "Side note", "confidence": null}
            ]
        }""",
        {"vlm_direct_marginal_note_enabled": True},
    )

    assert markdown == "<!-- Margin:left -->\n> Side note\n<!-- /Margin -->"


def test_parse_json_to_markdown_can_filter_marginal_note_markers():
    markdown, _ = parse_json_to_markdown(
        """{
            "printed_page_number": null,
            "regions": [
                {"label": "Marginal-Note-Left", "text": "Side note", "confidence": null}
            ]
        }""",
        {"vlm_direct_marginal_note_enabled": True, "vlm_filter_margin_notes": True},
    )

    assert markdown == "Side note"


def test_parse_json_to_markdown_does_not_emit_top_bottom_margin_blocks():
    markdown, _ = parse_json_to_markdown(
        """{
            "printed_page_number": null,
            "regions": [
                {"label": "Marginal-Note-Bottom", "text": "Likely footnote", "confidence": null}
            ]
        }""",
        {"vlm_direct_marginal_note_enabled": True},
    )

    assert markdown == "Likely footnote"


def test_parse_json_to_markdown_outputs_contexture_footnote_blocks():
    markdown, _ = parse_json_to_markdown(
        """{
            "printed_page_number": null,
            "regions": [
                {"label": "Text", "text": "Body<sup>1)</sup>", "confidence": null},
                {"label": "Footnote", "text": "1) Note body", "confidence": null}
            ]
        }""",
        {"vlm_direct_use_markdown_footnotes": True, "vlm_direct_footnote_backlink": True},
    )

    assert "Body<sup>1</sup>" in markdown
    assert "<!-- FootnoteBlock: marker=\"1\" -->" in markdown
    assert "<sup>1</sup> Note body" in markdown
    assert "[^1]" not in markdown
    assert "<sup id=" not in markdown
