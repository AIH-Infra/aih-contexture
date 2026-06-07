from aih_contexture.middle.schema import MiddleBlock, MiddleDocument, MiddlePage, MiddleProvenance, MiddleSpan
from aih_contexture.middle.scholarly_markdown import render_middle_scholarly_markdown


def test_render_middle_scholarly_markdown_uses_interval_anchors_and_page_comments():
    data = MiddleDocument(
        source_name="sample.pdf",
        pages=[
            MiddlePage(
                index=0,
                printed_page="iv",
                blocks=[
                    MiddleBlock(id="h", type="PageHeader", page_index=0, order=0, text="Chapter header"),
                    MiddleBlock(id="t", type="SectionHeader", page_index=0, order=1, text="Introduction"),
                    MiddleBlock(
                        id="body",
                        type="Text",
                        page_index=0,
                        order=2,
                        text="",
                        spans=[MiddleSpan(text="Hello"), MiddleSpan(text="world")],
                        provenance=[MiddleProvenance(backend="surya", stage="layout")],
                    ),
                    MiddleBlock(id="f", type="PageFooter", page_index=0, order=3, text="Footer"),
                ],
            )
        ],
    ).to_dict()

    markdown = render_middle_scholarly_markdown(data)

    assert "{0}" in markdown
    assert "{1}" in markdown
    assert "<!-- Page: iv -->" in markdown
    assert "<!-- PageHeader: Chapter header -->" in markdown
    assert "<!-- PageFooter: Footer -->" in markdown
    assert "## Introduction" in markdown
    assert "Hello world" in markdown


def test_render_middle_scholarly_markdown_uses_middle_heading_level_attrs():
    data = MiddleDocument(
        pages=[
            MiddlePage(
                index=0,
                blocks=[
                    MiddleBlock(
                        id="h1",
                        type="SectionHeader",
                        page_index=0,
                        order=0,
                        text="Document Title",
                        attrs={"heading_level": 1},
                    ),
                    MiddleBlock(
                        id="h3",
                        type="SectionHeader",
                        page_index=0,
                        order=1,
                        text="A Smaller Section",
                        attrs={"heading_level": 3},
                    ),
                ],
            )
        ],
    ).to_dict()

    markdown = render_middle_scholarly_markdown(data)

    assert "# Document Title" in markdown
    assert "### A Smaller Section" in markdown


def test_render_middle_scholarly_markdown_can_filter_header_footer_comments():
    data = MiddleDocument(
        pages=[
            MiddlePage(
                index=0,
                blocks=[
                    MiddleBlock(id="h", type="PageHeader", page_index=0, order=0, text="Running header"),
                    MiddleBlock(id="body", type="Text", page_index=0, order=1, text="Body"),
                    MiddleBlock(id="f", type="PageFooter", page_index=0, order=2, text="Publisher"),
                ],
            )
        ],
    ).to_dict()

    markdown = render_middle_scholarly_markdown(
        data,
        include_page_header_comments=False,
        include_page_footer_comments=False,
    )

    assert "<!-- PageHeader:" not in markdown
    assert "<!-- PageFooter:" not in markdown
    assert "Body" in markdown


def test_render_middle_scholarly_markdown_puts_separator_after_page_anchors():
    data = MiddleDocument(
        pages=[
            MiddlePage(
                index=3,
                blocks=[MiddleBlock(id="body", type="Text", page_index=3, order=0, text="Body")],
            )
        ],
    ).to_dict()

    markdown = render_middle_scholarly_markdown(data)

    assert "{3}\n\n---\n\nBody" in markdown
    assert markdown.rstrip().endswith("{4}\n\n---")


def test_render_middle_scholarly_markdown_can_filter_printed_page_comments():
    data = MiddleDocument(
        pages=[
            MiddlePage(
                index=0,
                printed_page="35",
                blocks=[MiddleBlock(id="body", type="Text", page_index=0, order=0, text="Body")],
            )
        ],
    ).to_dict()

    markdown = render_middle_scholarly_markdown(data, include_printed_page_comments=False)

    assert "<!-- Page:" not in markdown
    assert "Body" in markdown


def test_render_middle_scholarly_markdown_uses_page_number_block_as_printed_page():
    data = MiddleDocument(
        source_name="sample.pdf",
        pages=[
            MiddlePage(
                index=2,
                blocks=[
                    MiddleBlock(id="pn", type="PageNumber", page_index=2, order=0, text="35"),
                    MiddleBlock(id="body", type="Text", page_index=2, order=1, text="Body"),
                ],
            )
        ],
    ).to_dict()

    markdown = render_middle_scholarly_markdown(data)

    assert "<!-- Page: 35 -->" in markdown
    assert "Body" in markdown


def test_render_middle_scholarly_markdown_outputs_structured_notes_and_descriptions():
    data = MiddleDocument(
        pages=[
            MiddlePage(
                index=1,
                blocks=[
                    MiddleBlock(id="m", type="MarginalNote", page_index=1, order=0, text="Side note", attrs={"side": "left"}),
                    MiddleBlock(id="i", type="ImageDescription", page_index=1, order=1, text="A seal impression"),
                    MiddleBlock(id="e", type="Equation", page_index=1, order=2, text="a^2+b^2=c^2"),
                    MiddleBlock(id="fn", type="Footnote", page_index=1, order=3, text="Archive note"),
                ],
            )
        ],
    ).to_dict()

    markdown = render_middle_scholarly_markdown(data)

    assert "<!-- Margin:left" in markdown
    assert "> Side note" in markdown
    assert "<!-- ImageDescription:" in markdown
    assert "A seal impression" in markdown
    assert "$$\na^2+b^2=c^2\n$$" in markdown
    assert "<!-- FootnoteBlock:" not in markdown
    assert "<sup>1</sup> Archive note" in markdown


def test_render_middle_scholarly_markdown_can_filter_margin_comments_as_plain_text():
    data = MiddleDocument(
        pages=[
            MiddlePage(
                index=1,
                blocks=[
                    MiddleBlock(id="m", type="MarginalNote", page_index=1, order=0, text="Side note", attrs={"side": "left"}),
                    MiddleBlock(id="body", type="Text", page_index=1, order=1, text="Body text"),
                ],
            )
        ],
    ).to_dict()

    markdown = render_middle_scholarly_markdown(data, include_margin_comments=False)

    assert "<!-- Margin:" not in markdown
    assert "<!-- /Margin" not in markdown
    assert "> Side note" not in markdown
    assert "Side note" in markdown
    assert "Body text" in markdown


def test_render_middle_scholarly_markdown_can_include_provenance_comments():
    data = MiddleDocument(
        pages=[
            MiddlePage(
                index=0,
                blocks=[
                    MiddleBlock(
                        id="b0",
                        type="Text",
                        page_index=0,
                        order=0,
                        text="hello",
                        confidence=0.9,
                        provenance=[MiddleProvenance(backend="paddle_pp_structure_v3", stage="layout")],
                    )
                ],
            )
        ],
    ).to_dict()

    markdown = render_middle_scholarly_markdown(data, include_provenance_comments=True)

    assert "<!-- Block:" in markdown
    assert 'layout="paddle_pp_structure_v3"' in markdown


def test_render_middle_scholarly_markdown_normalizes_footnote_markers_and_dedupes():
    data = MiddleDocument(
        pages=[
            MiddlePage(
                index=7,
                height=800,
                blocks=[
                    MiddleBlock(
                        id="body",
                        type="Text",
                        page_index=7,
                        order=0,
                        text="A claim \\( ^{35} \\), a dollar marker $^{36}$, and another¹.",
                    ),
                    MiddleBlock(
                        id="fn1",
                        type="Footnote",
                        page_index=7,
                        order=1,
                        text="\\( ^{35} \\) De Corpore 4.26.1.",
                    ),
                    MiddleBlock(
                        id="fn1-dup",
                        type="Text",
                        page_index=7,
                        order=2,
                        text="35 De Corpore 4.26.1.",
                        bbox=[40, 700, 500, 730],
                    ),
                ],
            )
        ],
    ).to_dict()

    markdown = render_middle_scholarly_markdown(data)

    assert "A claim <sup>35</sup>, a dollar marker <sup>36</sup>, and another<sup>1</sup>." in markdown
    assert markdown.count("<sup>35</sup> De Corpore 4.26.1.") == 1
    assert "\\( ^{35} \\)" not in markdown


def test_render_middle_scholarly_markdown_attaches_bare_superscript_lines():
    data = MiddleDocument(
        pages=[
            MiddlePage(
                index=0,
                blocks=[
                    MiddleBlock(
                        id="body",
                        type="Text",
                        page_index=0,
                        order=0,
                        text="Hobbes shared a commonplace view.\n^{6}\nBut Hobbes's God is different.",
                    ),
                    MiddleBlock(
                        id="fn6",
                        type="Footnote",
                        page_index=0,
                        order=1,
                        text="^{6} See Martinich 1992.",
                    ),
                ],
            )
        ],
    ).to_dict()

    markdown = render_middle_scholarly_markdown(data)

    assert "view.<sup>6</sup> But Hobbes" in markdown
    assert "\n^{6}\n" not in markdown
    assert "<sup>6</sup> See Martinich 1992." in markdown


def test_render_middle_scholarly_markdown_joins_soft_line_breaks_in_prose():
    data = MiddleDocument(
        pages=[
            MiddlePage(
                index=0,
                blocks=[
                    MiddleBlock(
                        id="body",
                        type="Text",
                        page_index=0,
                        order=0,
                        text=(
                            "Spinoza's\n"
                            "deus-sive-natura\n"
                            ".<sup>1</sup>\n"
                            "As in ethics."
                        ),
                    ),
                ],
            )
        ],
    ).to_dict()

    markdown = render_middle_scholarly_markdown(data)

    assert "Spinoza's deus-sive-natura.<sup>1</sup> As in ethics." in markdown


def test_render_middle_scholarly_markdown_splits_footnote_block_without_comments_or_leading_spaces():
    data = MiddleDocument(
        pages=[
            MiddlePage(
                index=2,
                blocks=[
                    MiddleBlock(
                        id="fn",
                        type="Footnote",
                        page_index=2,
                        order=0,
                        text=(
                            "<sup>1</sup> First note.\n\n"
                            " <sup>2</sup> Second note.\n\n"
                            " <sup>3</sup> Third note."
                        ),
                    ),
                    MiddleBlock(
                        id="fn-dup",
                        type="Footnote",
                        page_index=2,
                        order=1,
                        text="\\( ^{2} \\) Second note.",
                    ),
                ],
            )
        ],
    ).to_dict()

    markdown = render_middle_scholarly_markdown(data)

    assert "<!-- FootnoteBlock:" not in markdown
    assert "\n <sup>" not in markdown
    assert markdown.count("<sup>1</sup> First note.") == 1
    assert markdown.count("<sup>2</sup> Second note.") == 1
    assert markdown.count("<sup>3</sup> Third note.") == 1


def test_render_middle_scholarly_markdown_keeps_footnotes_on_source_page():
    data = MiddleDocument(
        pages=[
            MiddlePage(
                index=0,
                blocks=[
                    MiddleBlock(id="body0", type="Text", page_index=0, order=0, text="Page zero text<sup>1</sup>."),
                    MiddleBlock(id="fn0", type="Footnote", page_index=0, order=1, text="1 Page zero note."),
                ],
            ),
            MiddlePage(
                index=1,
                blocks=[
                    MiddleBlock(id="body1", type="Text", page_index=1, order=0, text="Page one text<sup>2</sup>."),
                    MiddleBlock(id="fn1", type="Footnote", page_index=1, order=1, text="2 Page one note."),
                ],
            ),
        ],
    ).to_dict()

    markdown = render_middle_scholarly_markdown(data)

    page0_note = markdown.index("<sup>1</sup> Page zero note.")
    page1_anchor = markdown.index("\n{1}\n")
    page1_note = markdown.index("<sup>2</sup> Page one note.")
    final_anchor = markdown.rindex("\n{2}")
    assert page0_note < page1_anchor
    assert page1_note < final_anchor
