from aih_contexture.providers.registry import provider_from_ext


def test_provider_from_ext_uses_lazy_import_for_pdf():
    provider_cls = provider_from_ext("sample.pdf")

    assert provider_cls.__name__ == "PdfProvider"
    assert provider_cls.__module__ == "aih_contexture.providers.pdf"


def test_provider_from_ext_uses_lazy_import_for_html():
    provider_cls = provider_from_ext("sample.html")

    assert provider_cls.__name__ == "HTMLProvider"
    assert provider_cls.__module__ == "aih_contexture.providers.html"
