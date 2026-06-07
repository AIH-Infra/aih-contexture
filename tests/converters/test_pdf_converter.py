import io

import pytest
from aih_contexture.converters.pdf import PdfConverter
from aih_contexture.renderers.markdown import MarkdownOutput


def test_pdf_converter_tracks_academic_annotation_processors_disabled_by_default(model_dict):
    converter = PdfConverter(artifact_dict=model_dict, config={})
    summary = converter.get_processor_debug_summary()

    assert "marginal_annotation" in summary["disabled_labels"]
    assert "inline_annotation" in summary["disabled_labels"]
    assert "marginal_annotation" not in summary["execution_order"]
    assert "inline_annotation" not in summary["execution_order"]


def test_pdf_converter_enables_academic_annotation_processors_when_configured(model_dict):
    converter = PdfConverter(
        artifact_dict=model_dict,
        config={
            "enable_marginal_detection": True,
            "enable_inline_detection": True,
        },
    )
    summary = converter.get_processor_debug_summary()

    assert "marginal_annotation" in summary["enabled_labels"]
    assert "inline_annotation" in summary["enabled_labels"]
    assert "marginal_annotation" in summary["execution_order"]
    assert "inline_annotation" in summary["execution_order"]
    assert summary["execution_order"].index("marginal_annotation") < summary["execution_order"].index("section_header")
    assert summary["execution_order"].index("inline_annotation") < summary["execution_order"].index("section_header")


@pytest.mark.output_format("markdown")
@pytest.mark.config({"page_range": [0, 1, 2, 3, 7], "disable_ocr": True})
def test_pdf_converter(pdf_converter: PdfConverter, temp_doc):
    markdown_output: MarkdownOutput = pdf_converter(temp_doc.name)
    markdown = markdown_output.markdown

    # Basic assertions
    assert len(markdown) > 0
    assert "# Subspace Adversarial Training" in markdown

    # Some assertions for line joining across pages
    assert (
        "AT solutions. However, these methods highly rely on specifically" in markdown
    )  # pgs: 1-2
    assert (
        "(with adversarial perturbations), which harms natural accuracy, " in markdown
    )  # pgs: 3-4

    # Some assertions for line joining across columns
    assert "remain similar across a wide range of choices." in markdown  # pg: 2
    assert "a new scheme for designing more robust and efficient" in markdown  # pg: 8


@pytest.mark.filename("manual.epub")
@pytest.mark.config({"page_range": [0]})
def test_epub_converter(pdf_converter: PdfConverter, temp_doc):
    markdown_output: MarkdownOutput = pdf_converter(temp_doc.name)
    markdown = markdown_output.markdown

    # Basic assertions
    assert "Simple Sabotage Field Manual" in markdown


@pytest.mark.filename("single_sheet.xlsx")
@pytest.mark.config({"page_range": [0]})
def test_xlsx_converter(pdf_converter: PdfConverter, temp_doc):
    markdown_output: MarkdownOutput = pdf_converter(temp_doc.name)
    markdown = markdown_output.markdown

    # Basic assertions
    assert "four" in markdown


@pytest.mark.filename("china.html")
@pytest.mark.config({"page_range": [10]})
def test_html_converter(pdf_converter: PdfConverter, temp_doc):
    markdown_output: MarkdownOutput = pdf_converter(temp_doc.name)
    markdown = markdown_output.markdown

    # Basic assertions
    assert "Republic of China" in markdown


@pytest.mark.filename("gatsby.docx")
@pytest.mark.config({"page_range": [0]})
def test_docx_converter(pdf_converter: PdfConverter, temp_doc):
    markdown_output: MarkdownOutput = pdf_converter(temp_doc.name)
    markdown = markdown_output.markdown

    # Basic assertions
    assert "The Decline of the American Dream in the 1920s" in markdown


@pytest.mark.filename("lambda.pptx")
@pytest.mark.config({"page_range": [0]})
def test_pptx_converter(pdf_converter: PdfConverter, temp_doc):
    markdown_output: MarkdownOutput = pdf_converter(temp_doc.name)
    markdown = markdown_output.markdown

    # Basic assertions
    assert "Adam Doupé" in markdown


@pytest.mark.output_format("markdown")
@pytest.mark.config({"page_range": [0, 1, 2, 3, 7], "disable_ocr": True})
def test_pdf_converter_bytes(pdf_converter: PdfConverter, temp_doc):
    with open(temp_doc.name, "rb") as f:
        data = f.read()

    input_bytes = io.BytesIO(data)
    markdown_output: MarkdownOutput = pdf_converter(input_bytes)
    markdown = markdown_output.markdown

    # Basic assertions
    assert len(markdown) > 0
    assert "# Subspace Adversarial Training" in markdown

    # Some assertions for line joining across pages
    assert (
        "AT solutions. However, these methods highly rely on specifically" in markdown
    )  # pgs: 1-2
    assert (
        "(with adversarial perturbations), which harms natural accuracy, " in markdown
    )  # pgs: 3-4

    # Some assertions for line joining across columns
    assert "remain similar across a wide range of choices." in markdown  # pg: 2
    assert "a new scheme for designing more robust and efficient" in markdown  # pg: 8
