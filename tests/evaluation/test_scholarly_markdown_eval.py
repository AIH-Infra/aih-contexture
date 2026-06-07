from aih_contexture.evaluation.scholarly_markdown import (
    evaluate_scholarly_markdown_files,
    evaluate_scholarly_markdown_text,
)


def test_evaluate_scholarly_markdown_accepts_normalized_output():
    text = """{0}

<!-- Page: iv -->
<!-- PageHeader: Chapter -->

Body text.

<!-- ImageDescription: id="img1" anchors={0}-{1} -->
Seal impression
<!-- /ImageDescription -->

<!-- Margin:left id="m1" a=0-1 -->
> Side note
<!-- /Margin -->

<sup>1</sup> Archive note

{1}
"""

    result = evaluate_scholarly_markdown_text(text)

    assert result["ok"] is True
    assert result["metrics"]["anchor_count"] == 2
    assert result["metrics"]["final_anchor"] == 1
    assert result["metrics"]["image_description_count"] == 1
    assert result["metrics"]["margin_count"] == 1
    assert result["metrics"]["marginal_note_count"] == 1
    assert result["metrics"]["footnote_block_count"] == 0
    assert result["metrics"]["footnote_definition_count"] == 1


def test_evaluate_scholarly_markdown_flags_anchor_and_block_errors():
    text = """{0}

<!-- page-header: legacy -->

<!-- ImageDescription: id="img1" anchors={0}-{2} -->
missing close

{2}
"""

    result = evaluate_scholarly_markdown_text(text)

    assert result["ok"] is False
    assert any(issue["code"] == "non_contiguous_page_anchors" for issue in result["errors"])
    assert any(issue["code"] == "unbalanced_comment_block" for issue in result["errors"])
    assert any(issue["code"] == "legacy_page_header_footer" for issue in result["warnings"])


def test_evaluate_scholarly_markdown_flags_legacy_new_output_syntax():
    text = """{0}

Body[^1] with legacy marker<sup>1)</sup>.

> **[Marginal-Left]** Side note

<!-- MarginalNote: id="m1" -->
> Side note
<!-- /MarginalNote -->

<!-- FootnoteBlock: id="fn1" anchors={0}-{1} -->
[^1]: Archive note

{1}
"""

    result = evaluate_scholarly_markdown_text(text)

    assert result["ok"] is False
    assert any(issue["code"] == "legacy_html_superscript_marker" for issue in result["errors"])
    assert any(issue["code"] == "legacy_markdown_footnote" for issue in result["errors"])
    assert any(issue["code"] == "legacy_margin_blockquote" for issue in result["errors"])
    assert any(issue["code"] == "legacy_marginal_note_comment" for issue in result["errors"])
    assert result["metrics"]["legacy_html_superscript_marker_count"] == 1


def test_evaluate_scholarly_markdown_can_run_compat_mode():
    text = """{0}

Body[^1] with legacy marker<sup>1)</sup>.

<!-- FootnoteBlock: id="fn1" anchors={0}-{1} -->
[^1]: Archive note

{1}
"""

    result = evaluate_scholarly_markdown_text(text, strict_new_output=False)

    assert result["ok"] is True
    assert result["metrics"]["legacy_html_superscript_marker_count"] == 1


def test_evaluate_scholarly_markdown_files_aggregates_cases(tmp_path):
    path = tmp_path / "sample.md"
    path.write_text("{0}\n\nhello\n\n{1}\n", encoding="utf-8")

    payload = evaluate_scholarly_markdown_files([path])

    assert payload["ok"] is True
    assert payload["case_count"] == 1
    assert payload["results"][0]["source_path"] == str(path)
