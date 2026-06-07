from aih_contexture.renderers.markdown import Markdownify


def _make_converter():
    return Markdownify(
        paginate_output=True,
        page_separator="\n\n---\n\n",
        inline_math_delimiters=("$", "$"),
        block_math_delimiters=("$$", "$$"),
        html_tables_in_markdown=False,
        heading_style="ATX",
        bullets="-",
        escape_misc=False,
        escape_underscores=True,
        escape_asterisks=True,
        escape_dollars=True,
        sub_symbol="<sub>",
        sup_symbol="<sup>",
    )


def test_image_descriptions_render_as_page_scoped_comments():
    converter = _make_converter()
    html = """
    <div class='page' data-page-id='0'>
      <p role='img' data-original-image-id='/page/0/Picture/1'>First image description.</p>
      <p>Body text.</p>
      <p role='img' data-original-image-id='/page/0/Picture/2'>Second image description.</p>
    </div>
    <div class='page' data-page-id='1'>
      <p role='img' data-original-image-id='/page/1/Picture/1'>Third image description.</p>
    </div>
    """

    markdown = converter.convert(html)

    assert "<!-- image-description-1: First image description. -->" in markdown
    assert "<!-- image-description-2: Second image description. -->" in markdown
    assert "<!-- image-description-1: Third image description. -->" in markdown
    assert "Image /page/0/Picture/1 description:" not in markdown
