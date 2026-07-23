"""locro -- Python wrapper for Chrome's screen-ai OCR."""

from ._download import download_component
from .models import BoundingBox, OcrBlock, OcrLine, OcrPage, OcrResult, OcrWord
from .ocr import ScreenAI

__all__ = [
    "BoundingBox",
    "OcrBlock",
    "OcrLine",
    "OcrPage",
    "OcrResult",
    "OcrWord",
    "ScreenAI",
    "download_component",
]
