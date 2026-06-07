from aih_contexture.renderers.markdown import MarkdownFormatter


def test_markdown_formatter_normalizes_legacy_footnote_superscripts():
    text = "Body<sup>12)</sup> and roman<sup>iv)</sup> and star<sup>*)</sup>."

    formatted = MarkdownFormatter().format(text)

    assert formatted == "Body<sup>12</sup> and roman<sup>iv</sup> and star<sup>*</sup>."


def test_markdown_formatter_repairs_escaped_superscript_prefix():
    text = "<sup>&</sup>lt;sup>26</sup> Alexander, on Mixture."

    formatted = MarkdownFormatter().format(text)

    assert formatted == "<sup>26</sup> Alexander, on Mixture."


def test_markdown_formatter_does_not_turn_emphasis_into_lists():
    formatter = MarkdownFormatter()

    assert formatter.format("**Abstract** text") == "**Abstract** text"
    assert formatter.format("*Abstract* text") == "*Abstract* text"
    assert formatter.format("*item") == "* item"


def test_markdown_formatter_repairs_old_emphasis_list_drift():
    text = "* *Abstract** The pantheon."

    formatted = MarkdownFormatter().format(text)

    assert formatted == "**Abstract** The pantheon."
