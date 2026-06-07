import pytest

from aih_contexture.providers import raise_missing_format_dependency


@pytest.mark.parametrize(
    ("format_name", "packages"),
    [
        ("DOCX", ["mammoth", "weasyprint"]),
        ("XLSX", ["openpyxl", "weasyprint"]),
        ("PPTX", ["python-pptx", "weasyprint"]),
        ("EPUB", ["ebooklib", "weasyprint", "beautifulsoup4"]),
        ("HTML", ["weasyprint"]),
    ],
)
def test_raise_missing_format_dependency_message(format_name, packages):
    with pytest.raises(RuntimeError) as exc_info:
        raise_missing_format_dependency(format_name, packages, ModuleNotFoundError("missing"))

    message = str(exc_info.value)
    assert format_name in message
    assert 'aih-contexture[full]' in message
    for package in packages:
        assert package in message
