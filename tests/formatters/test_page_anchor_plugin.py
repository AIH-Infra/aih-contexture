from aih_contexture.formatters import PageAnchorPlugin, join_markdown_pages


def test_page_anchor_plugin_inserts_separator_after_before_anchor():
    plugin = PageAnchorPlugin(page_separator="---")

    rendered = plugin.wrap_page_content(3, "Body")

    assert rendered == "{3}\n\n---\n\nBody"


def test_page_anchor_plugin_inserts_separator_after_final_position_anchor():
    plugin = PageAnchorPlugin(position="after", page_separator="---")

    rendered = plugin.wrap_page_content(3, "Body")

    assert rendered == "Body\n\n{3}\n\n---"


def test_join_markdown_pages_does_not_duplicate_separator_after_page_anchor():
    plugin = PageAnchorPlugin(page_separator="---")
    pages = [
        plugin.wrap_page_content(12, "Page 12"),
        plugin.wrap_page_content(13, "Page 13"),
    ]

    rendered = join_markdown_pages(pages, page_anchors_enabled=True)

    assert rendered == "{12}\n\n---\n\nPage 12\n\n{13}\n\n---\n\nPage 13"
    assert "---\n\n{13}\n\n---" not in rendered


def test_join_markdown_pages_keeps_separator_when_page_anchors_are_disabled():
    rendered = join_markdown_pages(["Page 1", "Page 2"], page_anchors_enabled=False)

    assert rendered == "Page 1\n\n---\n\nPage 2"
