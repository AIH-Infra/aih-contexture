from aih_contexture.builders.document import DocumentBuilder


class _Page:
    text_extraction_method = "pdftext"


class _Document:
    def __init__(self):
        self.pages = [_Page()]


def test_document_builder_skips_line_builder_when_ocr_backend_owns_lines():
    document = _Document()
    calls = []
    builder = DocumentBuilder({"ocr_line_source": "tesseract"})
    builder.build_document = lambda _provider: document

    def layout_builder(doc, provider):
        calls.append("layout")

    def line_builder(doc, provider):
        calls.append("line")

    def ocr_builder(doc, provider):
        calls.append("ocr")

    result = builder(object(), layout_builder, line_builder, ocr_builder)

    assert result is document
    assert calls == ["layout", "ocr"]
    assert document.pages[0].text_extraction_method == "surya"
