import json

from click.testing import CliRunner

from aih_contexture.middle.debug_markdown import render_middle_debug_markdown
from aih_contexture.middle.schema import MiddleBlock, MiddleDocument, MiddlePage, MiddleProvenance
from aih_contexture.scripts.middle import middle_cli


def test_render_middle_debug_markdown_shows_page_anchors_and_block_metadata():
    data = MiddleDocument(
        source_name="sample.pdf",
        backends={"layout": "mineru_pp_doclayout_v2"},
        pages=[
            MiddlePage(
                index=0,
                width=100,
                height=200,
                blocks=[
                    MiddleBlock(
                        id="p0-b0",
                        type="Footnote",
                        page_index=0,
                        order=2,
                        text="A footnote",
                        bbox=[1.0, 2.0, 3.0, 4.0],
                        confidence=0.91,
                        provenance=[
                            MiddleProvenance(
                                backend="mineru_pp_doclayout_v2",
                                stage="layout",
                                raw_label="page_footnote",
                                model="PP-DocLayoutV2",
                            )
                        ],
                    )
                ],
            )
        ],
    ).to_dict()

    markdown = render_middle_debug_markdown(data)

    assert "# Contexture Middle Debug Preview" in markdown
    assert "{0}" in markdown
    assert "{1}" in markdown
    assert "## Page 0" in markdown
    assert "### Footnote `p0-b0`" in markdown
    assert 'raw_label="page_footnote"' in markdown
    assert 'backend="mineru_pp_doclayout_v2"' in markdown
    assert "bbox=[1,2,3,4]" in markdown
    assert "> A footnote" in markdown


def test_render_middle_debug_markdown_truncates_long_text():
    data = MiddleDocument(
        pages=[
            MiddlePage(
                index=0,
                blocks=[
                    MiddleBlock(
                        id="p0-b0",
                        type="Text",
                        page_index=0,
                        order=0,
                        text="abcdef",
                    )
                ],
            )
        ],
    ).to_dict()

    markdown = render_middle_debug_markdown(data, max_text_chars=4)

    assert "> abc…" in markdown
    assert "> abcdef" not in markdown


def test_middle_cli_can_write_debug_markdown(tmp_path):
    data = MiddleDocument(
        pages=[
            MiddlePage(
                index=0,
                blocks=[
                    MiddleBlock(id="p0-b0", type="Text", page_index=0, order=0, text="hello"),
                ],
            )
        ],
    ).to_dict()
    input_path = tmp_path / "sample_middle.json"
    output_path = tmp_path / "sample_debug.md"
    input_path.write_text(json.dumps(data), encoding="utf-8")

    result = CliRunner().invoke(
        middle_cli,
        [str(input_path), "--summary-only", "--debug-markdown", str(output_path)],
    )

    assert result.exit_code == 0
    assert output_path.exists()
    assert "Wrote debug Markdown" in result.output
    assert "### Text `p0-b0`" in output_path.read_text(encoding="utf-8")
