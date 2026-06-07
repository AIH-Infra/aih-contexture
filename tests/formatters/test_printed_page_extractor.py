from aih_contexture.formatters import PrintedPageExtractor


def test_printed_page_extractor_rejects_roman_looking_words():
    extractor = PrintedPageExtractor(patterns=[r"\b([IVXLCDMivxlcdm]{1,6})\b"])

    content, page = extractor.extract("Simply put, where did he get such an idea?")

    assert content == "Simply put, where did he get such an idea?"
    assert page is None


def test_printed_page_extractor_accepts_valid_roman_page_numbers():
    extractor = PrintedPageExtractor(patterns=[r"^([IVXLCDMivxlcdm]{1,6})$"])

    _, page = extractor.extract("xii")

    assert page == "xii"
