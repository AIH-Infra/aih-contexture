from importlib import import_module

import filetype
import filetype.match as file_match
from filetype.types import archive, document, IMAGE

_PROVIDER_SPECS = {
    "pdf": ("aih_contexture.providers.pdf", "PdfProvider"),
    "image": ("aih_contexture.providers.image", "ImageProvider"),
    "doc": ("aih_contexture.providers.document", "DocumentProvider"),
    "xls": ("aih_contexture.providers.spreadsheet", "SpreadSheetProvider"),
    "ppt": ("aih_contexture.providers.powerpoint", "PowerPointProvider"),
    "epub": ("aih_contexture.providers.epub", "EpubProvider"),
    "html": ("aih_contexture.providers.html", "HTMLProvider"),
}

DOCTYPE_MATCHERS = {
    "image": IMAGE,
    "pdf": [
        archive.Pdf,
    ],
    "epub": [
        archive.Epub,
    ],
    "doc": [document.Docx],
    "xls": [document.Xlsx],
    "ppt": [document.Pptx],
}


def _load_provider(doctype: str):
    module_name, class_name = _PROVIDER_SPECS[doctype]
    module = import_module(module_name)
    return getattr(module, class_name)


def load_matchers(doctype: str):
    return [cls() for cls in DOCTYPE_MATCHERS[doctype]]


def load_extensions(doctype: str):
    return [cls.EXTENSION for cls in DOCTYPE_MATCHERS[doctype]]


def _looks_like_html(filepath: str) -> bool:
    try:
        from bs4 import BeautifulSoup

        with open(filepath, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")
            return bool(soup.find())
    except Exception:
        return False


def provider_from_ext(filepath: str):
    ext = filepath.rsplit(".", 1)[-1].strip().lower()
    if not ext:
        return _load_provider("pdf")

    if ext in load_extensions("image"):
        return _load_provider("image")
    if ext in load_extensions("pdf"):
        return _load_provider("pdf")
    if ext in load_extensions("doc"):
        return _load_provider("doc")
    if ext in load_extensions("xls"):
        return _load_provider("xls")
    if ext in load_extensions("ppt"):
        return _load_provider("ppt")
    if ext in load_extensions("epub"):
        return _load_provider("epub")
    if ext in ["html"]:
        return _load_provider("html")

    return _load_provider("pdf")


def provider_from_filepath(filepath: str):
    if filetype.image_match(filepath) is not None:
        return _load_provider("image")
    if file_match(filepath, load_matchers("pdf")) is not None:
        return _load_provider("pdf")
    if file_match(filepath, load_matchers("epub")) is not None:
        return _load_provider("epub")
    if file_match(filepath, load_matchers("doc")) is not None:
        return _load_provider("doc")
    if file_match(filepath, load_matchers("xls")) is not None:
        return _load_provider("xls")
    if file_match(filepath, load_matchers("ppt")) is not None:
        return _load_provider("ppt")
    if _looks_like_html(filepath):
        return _load_provider("html")

    # Fallback if we incorrectly detect the file type
    return provider_from_ext(filepath)
