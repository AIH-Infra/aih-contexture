"""Wire-format protobuf decoder for VisualAnnotation.

Decodes the binary protobuf returned by PerformOCR without needing
compiled .proto files.  Field numbers match Chromium's
``chrome_screen_ai.VisualAnnotation`` message definition.
"""

from __future__ import annotations

import struct


# ---------------------------------------------------------------------------
# Generic wire-format helpers
# ---------------------------------------------------------------------------


def _decode_varint(data: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        b = data[pos]; pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7


def _decode_raw(data: bytes) -> list[tuple[int, int, object]]:
    pos = 0
    items: list[tuple[int, int, object]] = []
    while pos < len(data):
        try:
            tag, pos = _decode_varint(data, pos)
        except (IndexError, ValueError):
            break
        fn, wt = tag >> 3, tag & 7
        if wt == 0:
            val, pos = _decode_varint(data, pos)
        elif wt == 1:
            val = struct.unpack("<d", data[pos:pos + 8])[0]; pos += 8
        elif wt == 2:
            length, pos = _decode_varint(data, pos)
            val = data[pos:pos + length]; pos += length
        elif wt == 5:
            val = struct.unpack("<f", data[pos:pos + 4])[0]; pos += 4
        else:
            break
        items.append((fn, wt, val))
    return items


# ---------------------------------------------------------------------------
# Intermediate result types (internal to the package)
# ---------------------------------------------------------------------------


class LineResult:
    """One line from the VisualAnnotation protobuf."""
    __slots__ = (
        "text", "language", "block_id", "paragraph_id", "confidence",
        "x", "y", "width", "height", "angle", "direction", "content_type", "words",
    )

    def __init__(self):
        self.text = self.language = ""
        self.block_id = self.paragraph_id = 0
        self.confidence = 0.0
        self.x = self.y = self.width = self.height = 0
        self.angle = 0.0
        self.direction = self.content_type = 0
        self.words: list[WordResult] = []


class WordResult:
    __slots__ = ("text", "language", "confidence", "x", "y", "width", "height", "angle")

    def __init__(self):
        self.text = self.language = ""
        self.confidence = 0.0
        self.x = self.y = self.width = self.height = 0
        self.angle = 0.0


# ---------------------------------------------------------------------------
# Parsers for individual protobuf sub-messages
# ---------------------------------------------------------------------------


def _parse_rect(data: bytes) -> tuple[int, int, int, int, float]:
    x = y = w = h = 0
    angle = 0.0
    for fn, wt, val in _decode_raw(data):
        if fn == 1 and wt == 0: x = val
        elif fn == 2 and wt == 0: y = val
        elif fn == 3 and wt == 0: w = val
        elif fn == 4 and wt == 0: h = val
        elif fn == 5 and wt == 5: angle = val  # clockwise degrees
    return x, y, w, h, angle


def _parse_word(data: bytes) -> WordResult:
    w = WordResult()
    for fn, wt, val in _decode_raw(data):
        if fn == 2 and wt == 2: w.x, w.y, w.width, w.height, w.angle = _parse_rect(val)
        elif fn == 3 and wt == 2: w.text = val.decode("utf-8", errors="replace")
        elif fn == 5 and wt == 2: w.language = val.decode("utf-8", errors="replace")
        elif fn == 15 and wt == 5: w.confidence = val
    return w


def _parse_line(data: bytes) -> LineResult:
    ln = LineResult()
    for fn, wt, val in _decode_raw(data):
        if fn == 1 and wt == 2: ln.words.append(_parse_word(val))
        elif fn == 2 and wt == 2: ln.x, ln.y, ln.width, ln.height, ln.angle = _parse_rect(val)
        elif fn == 3 and wt == 2: ln.text = val.decode("utf-8", errors="replace")
        elif fn == 4 and wt == 2: ln.language = val.decode("utf-8", errors="replace")
        elif fn == 5 and wt == 0: ln.block_id = val
        elif fn == 7 and wt == 0: ln.direction = val
        elif fn == 8 and wt == 0: ln.content_type = val
        elif fn == 10 and wt == 5: ln.confidence = val
        elif fn == 11 and wt == 0: ln.paragraph_id = val
    return ln


def parse_visual_annotation(data: bytes) -> list[LineResult]:
    """Parse a serialised chrome_screen_ai.VisualAnnotation protobuf."""
    return [_parse_line(val) for fn, wt, val in _decode_raw(data) if fn == 2 and wt == 2]
