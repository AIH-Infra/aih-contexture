"""High-level OCR interface -- the main public API."""

from __future__ import annotations

import logging
import os
import sys
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from PIL import Image

from ._dll import ScreenAIDll, find_screen_ai_dir
from ._protobuf import LineResult, parse_visual_annotation
from .models import BoundingBox, OcrBlock, OcrLine, OcrPage, OcrResult, OcrWord
from aih_contexture.backends.ocr.screenai.text_layer import UnicodeTextWriter
from aih_contexture.utils.pdf_text_layer import (
    COMPACT_PDF_SAVE_OPTIONS, remove_page_annotations, searchable_background,
)

log = logging.getLogger(__name__)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".gif"}

# ---------------------------------------------------------------------------
# Font fallback for invisible text overlay
# ---------------------------------------------------------------------------

# Character ranges that need a CJK-capable font for the invisible text layer.
_CJK_RANGES = [
    (0x3040, 0x309F),  # Hiragana
    (0x30A0, 0x30FF),  # Katakana
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0x3400, 0x4DBF),  # CJK Extension A
    (0xAC00, 0xD7AF),  # Hangul Syllables
    (0x3000, 0x303F),  # CJK Symbols and Punctuation
    (0xFF00, 0xFFEF),  # Halfwidth/Fullwidth forms
]


def _char_needs_cjk_font(ch: str) -> bool:
    cp = ord(ch)
    return any(start <= cp <= end for start, end in _CJK_RANGES)


def _text_needs_cjk_font(text: str) -> bool:
    return any(_char_needs_cjk_font(ch) for ch in text)


def _find_cjk_font() -> Path | None:
    """Locate a system font that can encode CJK characters.

    PyMuPDF's default Helvetica only covers Latin-1, so Chinese/Japanese/Korean
    text in the invisible overlay would otherwise be replaced by question marks.
    """
    candidates: list[Path] = []
    if sys.platform == "win32":
        system_root = Path(os.environ.get("SYSTEMROOT", r"C:\Windows"))
        candidates = [
            system_root / "Fonts" / "simhei.ttf",
            system_root / "Fonts" / "simsun.ttc",
            system_root / "Fonts" / "msyh.ttc",
            Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts" / "simhei.ttf",
        ]
    elif sys.platform == "darwin":
        candidates = [
            Path("/System/Library/Fonts/PingFang.ttc"),
            Path("/System/Library/Fonts/STHeiti Light.ttc"),
            Path("/Library/Fonts/Arial Unicode.ttf"),
        ]
    else:
        candidates = [
            Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
            Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ]

    for path in candidates:
        if path.exists():
            return path
    return None



class ScreenAI:
    """Direct interface to Chrome's screen-ai OCR.

    Loads the screen-ai shared library via ctypes -- no browser needed.

    >>> ai = ScreenAI()
    >>> result = ai.ocr("scan.pdf")
    >>> print(result.to_text())
    """

    def __init__(
        self,
        model_dir: Path | None = None,
        *,
        light_mode: bool = False,
    ):
        if model_dir is None:
            model_dir = find_screen_ai_dir()
        self._dll = ScreenAIDll(model_dir)
        if light_mode:
            self._dll.set_light_mode(True)
        if not self._dll.init_ocr():
            raise RuntimeError("Failed to initialize screen-ai OCR pipeline")
        self._max_dim = self._dll.get_max_image_dimension()
        log.info("OCR ready (max dimension: %d)", self._max_dim)

    # -- Public API ---------------------------------------------------------

    @property
    def version(self) -> tuple[int, int]:
        return self._dll.get_version()

    @property
    def max_image_dimension(self) -> int:
        return self._max_dim

    def ocr(
        self,
        file: str | Path,
        *,
        pages: Iterable[int] | None = None,
        remove_annotations: bool = True,
    ) -> OcrResult:
        """OCR a PDF or image file.

        Args:
            file: Path to a PDF or image.
            pages: For PDFs, 1-based page numbers to OCR.
                   ``None`` means all pages.  Ignored for images.

        Returns:
            Structured :class:`OcrResult`.
        """
        path = Path(file)
        if path.suffix.lower() == ".pdf":
            return self._ocr_pdf(path, pages=pages, remove_annotations=remove_annotations)
        return self._ocr_image_file(path)

    def ocr_pil_image(self, img: Image.Image) -> OcrPage:
        """OCR a single PIL Image.  Returns one :class:`OcrPage`."""
        lines, size = self._perform_ocr(img)
        return _lines_to_page(lines, page_number=1, img_size=size)

    def ocr_to_searchable_pdf(
        self,
        input_pdf: str | Path,
        output_pdf: str | Path,
        *,
        pages: Iterable[int] | None = None,
        remove_annotations: bool = True,
    ) -> OcrResult:
        """OCR a PDF and write a searchable copy with invisible text overlay.

        Builds a page background with a fresh searchable text layer.

        Args:
            input_pdf: Source (image-only) PDF.
            output_pdf: Destination path for the searchable PDF.
            pages: 1-based page numbers to OCR.  ``None`` = all.

        Returns:
            The :class:`OcrResult` that was overlaid.
        """
        try:
            import fitz  # PyMuPDF
        except ImportError as exc:
            raise ImportError(
                "PyMuPDF is required for PDF operations: pip install PyMuPDF"
            ) from exc

        with fitz.open(str(input_pdf)) as doc, fitz.open() as output_doc:
            writer = UnicodeTextWriter()
            page_set = set(pages) if pages is not None else None
            ocr_pages: list[OcrPage] = []

            for i in range(len(doc)):
                page_num = i + 1
                if page_set is not None and page_num not in page_set:
                    output_doc.insert_pdf(doc, from_page=i, to_page=i)
                    continue

                pg = doc[i]
                if remove_annotations:
                    remove_page_annotations(pg)
                if pg.rotation:
                    pg.remove_rotation()
                scale = min(1.0, self._max_dim / max(pg.rect.width, pg.rect.height))
                dpi = int(72 * scale * 2)
                pix = pg.get_pixmap(dpi=dpi)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                lines, ocr_size = self._perform_ocr(img)
                ocr_page = _lines_to_page(lines, page_number=page_num, img_size=ocr_size)
                ocr_pages.append(ocr_page)

                # Scale factor: OCR pixel coords -> PDF point coords
                sx = pg.rect.width / ocr_size[0]
                sy = pg.rect.height / ocr_size[1]

                target = output_doc.new_page(width=pg.rect.width, height=pg.rect.height)
                searchable_background(target, doc, i, dpi=dpi, remove_annotations=remove_annotations)
                _overlay_text(target, lines, sx, sy, writer=writer)

                log.info(
                    "Page %d: %d blocks, %d lines (overlaid)",
                    page_num,
                    len(ocr_page.blocks),
                    sum(len(b.lines) for b in ocr_page.blocks),
                )

            output_doc.subset_fonts()
            output_doc.save(str(output_pdf), **COMPACT_PDF_SAVE_OPTIONS)
        log.info("Searchable PDF -> %s", output_pdf)
        return OcrResult(pages=ocr_pages)

    # -- Internals ----------------------------------------------------------

    def _perform_ocr(
        self, img: Image.Image,
    ) -> tuple[list[LineResult], tuple[int, int]]:
        """Resize, convert to BGRA, call library, parse protobuf."""
        w, h = img.size
        if max(w, h) > self._max_dim:
            scale = self._max_dim / max(w, h)
            nw, nh = int(w * scale), int(h * scale)
            log.info("Resizing %dx%d -> %dx%d", w, h, nw, nh)
            img = img.resize((nw, nh), Image.LANCZOS)

        img = img.convert("RGBA")
        width, height = img.size

        raw = self._dll.perform_ocr(img.tobytes("raw", "BGRA"), width, height)
        if raw is None:
            return [], (width, height)
        return parse_visual_annotation(raw), (width, height)

    def _ocr_image_file(self, path: Path) -> OcrResult:
        img = Image.open(path)
        lines, size = self._perform_ocr(img)
        page = _lines_to_page(lines, page_number=1, img_size=size)
        return OcrResult(pages=[page])

    def _ocr_pdf(
        self, path: Path, *, pages: Iterable[int] | None = None, remove_annotations: bool = True,
    ) -> OcrResult:
        try:
            import fitz  # PyMuPDF
        except ImportError as exc:
            raise ImportError(
                "PyMuPDF is required for PDF OCR: pip install PyMuPDF"
            ) from exc

        doc = fitz.open(path)
        page_set = set(pages) if pages is not None else None
        ocr_pages: list[OcrPage] = []

        for i in range(len(doc)):
            page_num = i + 1
            if page_set is not None and page_num not in page_set:
                continue

            pg = doc[i]
            if remove_annotations:
                remove_page_annotations(pg)
            scale = min(1.0, self._max_dim / max(pg.rect.width, pg.rect.height))
            pix = pg.get_pixmap(dpi=int(72 * scale * 2))
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            lines, size = self._perform_ocr(img)
            ocr_page = _lines_to_page(lines, page_number=page_num, img_size=size)
            ocr_pages.append(ocr_page)
            log.info(
                "Page %d: %d blocks, %d lines", page_num,
                len(ocr_page.blocks),
                sum(len(b.lines) for b in ocr_page.blocks),
            )

        return OcrResult(pages=ocr_pages)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lines_to_page(
    lines: list[LineResult], page_number: int, img_size: tuple[int, int],
) -> OcrPage:
    blocks_map: dict[int, list[LineResult]] = defaultdict(list)
    for ln in lines:
        blocks_map[ln.block_id].append(ln)

    blocks: list[OcrBlock] = []
    for block_id in sorted(blocks_map):
        ocr_lines: list[OcrLine] = []
        for ln in blocks_map[block_id]:
            words = [
                OcrWord(
                    text=w.text,
                    confidence=w.confidence or None,
                    bounding_box=BoundingBox(x=w.x, y=w.y, width=w.width, height=w.height, angle=w.angle)
                    if w.width else None,
                )
                for w in ln.words
            ]
            ocr_lines.append(OcrLine(
                text=ln.text, words=words,
                bounding_box=BoundingBox(x=ln.x, y=ln.y, width=ln.width, height=ln.height, angle=ln.angle)
                if ln.width else None,
            ))
        blocks.append(OcrBlock(block_type="paragraph", lines=ocr_lines))

    return OcrPage(
        page_number=page_number, blocks=blocks,
        width=img_size[0], height=img_size[1],
    )


def _overlay_text(
    page,  # fitz.Page
    lines: list[LineResult],
    sx: float,
    sy: float,
    *, writer=None,
) -> None:
    """Insert invisible text onto a PyMuPDF page for each OCR'd word."""
    import fitz  # noqa: F811

    writer = writer or UnicodeTextWriter()
    for ln in lines:
        for w in ln.words:
            if not w.text or not w.width:
                continue
            # Convert OCR pixel coords to PDF points
            x0 = w.x * sx
            y0 = w.y * sy
            x1 = (w.x + w.width) * sx
            y1 = (w.y + w.height) * sy
            writer.insert_word(page, fitz.Rect(x0, y0, x1, y1), w.text)

def _insert_invisible_word(page, rect, text: str, cjk_font: Path | None = None) -> None:
    """Compatibility entry point; all scripts use the shared Unicode writer."""
    UnicodeTextWriter().insert_word(page, rect, text)
