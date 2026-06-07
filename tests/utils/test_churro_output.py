from aih_contexture.utils.churro_output import normalize_churro_xml_output, xml_to_json, xml_to_markdown


def test_churro_output_parses_official_historical_document_xml():
    xml = """```xml
<HistoricalDocument xmlns="http://example.com/historicaldocument">
  <Metadata>
    <Language>eng</Language>
    <Script>Latn</Script>
  </Metadata>
  <Page>
    <Header>
      <PageNumber>35</PageNumber>
      <Heading type="running_title"><Line>G. Gorham</Line></Heading>
    </Header>
    <Body>
      <Heading type="main"><Line>Introduction</Line></Heading>
      <Paragraph><Line>Body text with note¹.</Line></Paragraph>
      <MarginalNote placement="bottom_margin"><Line>1 Footnote body.</Line></MarginalNote>
      <MarginalNote placement="left_margin"><Line>Side note.</Line></MarginalNote>
      <List type="unordered"><Item><Line>List entry</Line></Item></List>
      <Formula notation="latex">E=mc^2</Formula>
    </Body>
    <Footer>
      <Heading type="running_title"><Line>Springer</Line></Heading>
    </Footer>
  </Page>
</HistoricalDocument>
```"""

    assert normalize_churro_xml_output(xml).startswith("<HistoricalDocument")

    data = xml_to_json(xml)
    page = data["content"][0]
    assert data["metadata"]["Language"] == "eng"
    assert page["page_number"] == "35"
    assert [element["type"] for element in page["elements"]] == [
        "page_number",
        "page_header",
        "page_footer",
        "heading",
        "paragraph",
        "footnote",
        "marginal_note",
        "list_item",
        "equation",
    ]
    assert page["elements"][5]["text"] == "1 Footnote body."

    markdown = xml_to_markdown(xml)
    assert "<!-- PageHeader: G. Gorham -->" in markdown
    assert "<!-- PageFooter: Springer -->" in markdown
    assert "# Introduction" in markdown
    assert "1 Footnote body." in markdown
    assert "<!-- Margin:left -->" in markdown
