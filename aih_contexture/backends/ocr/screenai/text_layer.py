"""Unicode text overlay shared by the ScreenAI adapters."""

from functools import lru_cache
from pathlib import Path
import os
import sys
import unicodedata
from uuid import uuid4

import pymupdf as fitz


@lru_cache(maxsize=1)
def _fonts():
    if sys.platform == 'win32':
        root = Path(os.environ.get('SYSTEMROOT', r'C:\Windows')) / 'Fonts'
        paths = [root / name for name in ('segoeui.ttf', 'arial.ttf', 'tahoma.ttf', 'simhei.ttf', 'simsun.ttc', 'msyh.ttc')]
    elif sys.platform == 'darwin':
        root = Path('/System/Library/Fonts')
        paths = [root / name for name in ('Supplemental/Arial Unicode.ttf', 'GeezaPro.ttc', 'Hebrew.ttc', 'Thonburi.ttc')]
    else:
        root = Path('/usr/share/fonts')
        paths = [root / name for name in (
            'truetype/dejavu/DejaVuSans.ttf', 'truetype/noto/NotoSans-Regular.ttf',
            'truetype/noto/NotoSansArabic-Regular.ttf', 'truetype/noto/NotoSansHebrew-Regular.ttf',
            'truetype/noto/NotoSansThai-Regular.ttf', 'truetype/thai/Loma.ttf', 'truetype/tlwg/Loma.ttf',
        )]
    font_dir = os.environ.get('CONTEXTURE_SCREENAI_FONT_DIR')
    if font_dir:
        folder = Path(font_dir).expanduser()
        if not folder.is_dir():
            raise FileNotFoundError(f'ScreenAI font directory does not exist: {folder}')
        paths.extend(path for path in sorted(folder.iterdir())
                     if path.suffix.lower() in {'.ttf', '.otf', '.ttc'})
    return ['helv', 'cjk', *(path for path in paths if path.is_file())]


@lru_cache(maxsize=None)
def _load_font(source):
    return fitz.Font(fontfile=str(source)) if isinstance(source, Path) else fitz.Font(source)


@lru_cache(maxsize=4096)
def _font_for(text: str):
    for source in _fonts():
        font = _load_font(source)
        if all(font.has_glyph(ord(char), fallback=False) for char in text):
            return font
    missing = ' '.join(f'U+{ord(char):04X}' for char in dict.fromkeys(text))
    raise ValueError(f'ScreenAI 文字层缺少支持这些字符的字体：{missing}')


class UnicodeTextWriter:
    """Embed full fonts under fresh names and map used glyphs to source Unicode."""

    def __init__(self):
        self.salt = uuid4().hex
        self.fonts = {}
        self.cmaps = set()

    def insert_word(self, page, rect, text: str) -> None:
        if not text or rect.is_empty or rect.width <= 0 or rect.height <= 0:
            return
        # ScreenAI can return Arabic presentation forms; store logical characters.
        text = ''.join(unicodedata.normalize('NFKC', char) if 0xFB50 <= ord(char) <= 0xFDFF or 0xFE70 <= ord(char) <= 0xFEFF else char for char in text)
        directions = [unicodedata.bidirectional(char) for char in text]
        if any(direction in ('R', 'AL') for direction in directions) and any(direction in ('L', 'EN', 'AN') for direction in directions):
            # Keep numeric / Latin runs increasing in x inside an RTL word.
            # Separate text operations also keep both PDF engines from reversing
            # the digits a second time when reconstructing logical text.
            runs = []
            direction = next(item for item in directions if item in ('R', 'AL', 'L'))
            paragraph_rtl = True
            for char, bidi in zip(text, directions):
                kind = 'rtl' if bidi in ('R', 'AL') or (bidi == 'NSM' and direction in ('R', 'AL')) else 'ltr' if bidi in ('L', 'EN', 'AN') else 'neutral'
                if runs and runs[-1][0] == kind:
                    runs[-1] = (kind, runs[-1][1] + char)
                else:
                    runs.append((kind, char))
                if bidi in ('R', 'AL', 'L', 'EN', 'AN'):
                    direction = bidi
            widths = [_font_for(run).text_length(run, 1) for _, run in runs]
            scale = rect.width / sum(widths)
            cursor = rect.x1 if paragraph_rtl else rect.x0
            for (_, run), width in zip(runs, widths):
                width *= scale
                left = cursor - width if paragraph_rtl else cursor
                self.insert_word(page, fitz.Rect(left, rect.y0, left + width, rect.y1), run)
                cursor += -width if paragraph_rtl else width
            return
        font = _font_for(text)
        key = id(font)
        if key not in self.fonts:
            self.fonts[key] = (f'CW{self.salt}{len(self.fonts)}', {})
        alias, mapping = self.fonts[key]
        font_xref = page.insert_font(fontname=alias, fontbuffer=font.buffer)
        changed = font_xref not in self.cmaps
        for char in text:
            glyph = font.has_glyph(ord(char), fallback=False)
            previous = mapping.get(glyph)
            if previous is not None and previous != char:
                raise ValueError('ScreenAI 字体将不同字符映射到同一字形，无法无损生成文字层。')
            if previous is None:
                mapping[glyph] = char
                changed = True
        visual = text
        if any(unicodedata.bidirectional(char) in ('R', 'AL') for char in text):
            visual = fitz.TextWriter(page.rect).clean_rtl(text)[::-1]
        size = max(1.0, rect.height * .8)
        width = font.text_length(visual, size)
        point = fitz.Point(rect.x0, rect.y1 - size * .1)
        page.insert_text(point, visual, fontsize=size, fontname=alias, render_mode=3,
                         morph=(point, fitz.Matrix(rect.width / max(width, .01), 1)))
        if not changed:
            return
        # System fonts may reverse-map Arabic glyphs to presentation forms or
        # map ordinary spaces to NBSP. Use the actual recognized code points.
        kind, reference = page.parent.xref_get_key(font_xref, 'ToUnicode')
        if kind != 'xref':
            raise ValueError('ScreenAI 嵌入字体缺少 ToUnicode 映射。')
        pairs = [f'<{glyph:04x}> <{char.encode("utf-16-be").hex()}>' for glyph, char in mapping.items()]
        chunks = ['\n'.join([f'{len(pairs[i:i+100])} beginbfchar', *pairs[i:i+100], 'endbfchar']) for i in range(0, len(pairs), 100)]
        cmap = ('/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n'
                '/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n'
                '/CMapName /Adobe-Identity-UCS def /CMapType 2 def\n'
                '1 begincodespacerange <0000> <ffff> endcodespacerange\n' + '\n'.join(chunks) +
                '\nendcmap CMapName currentdict /CMap defineresource pop end end')
        page.parent.update_stream(int(reference.split()[0]), cmap.encode('ascii'))
        self.cmaps.add(font_xref)
