"""Preserve prose literals without changing valid Markdown structures."""
from __future__ import annotations

import html
import re

_HTML_TAGS = ('a abbr b bdi bdo blockquote br caption cite code col colgroup dd del '
              'details div dl dt em figcaption figure h1 h2 h3 h4 h5 h6 hr i img '
              'ins kbd li mark math ol p pre q rp rt ruby s samp section small '
              'span strong sub summary sup table tbody td tfoot th thead tr u ul var').split()
_ANGLE = re.compile(
    r'<!--[\s\S]*?-->|</?(?:' + '|'.join(_HTML_TAGS) + r')(?=[\s/>])[^>]*>'
    r'|<(?:https?://|mailto:)[^\s<>]+>|<[\w.+-]+@[\w.-]+\.[\w-]+>'
    r'|<[^<>\n]*>|<', re.I)
_VALID = re.compile(
    r'^(?:<!--[\s\S]*?-->|</?(?:' + '|'.join(_HTML_TAGS) + r')(?=[\s/>])[^>]*>'
    r'|<(?:https?://|mailto:)[^\s<>]+>|<[\w.+-]+@[\w.-]+\.[\w-]+>)$', re.I)


def escape_literal_angles(text: str) -> str:
    """Escape editorial/unclosed angle text, retaining known structural HTML."""
    return _ANGLE.sub(lambda m: m[0] if _VALID.fullmatch(m[0]) else html.escape(m[0], quote=False), text)


def escape_unpaired_prose_math(text: str) -> str:
    """A typed prose block cannot open a display region in another block.

    Preserve paired displays and inline code. A multiline display closes at
    the end of a line; another chapter reference beginning $$ is not a close.
    Source text and Equation blocks are kept separately by the caller.
    """
    lines = text.splitlines(keepends=True)
    fence = None
    display = None
    for i, line in enumerate(lines):
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line.rstrip('\r\n'))
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
            continue
        if marker:
            fence = marker[1]
            continue
        if display is not None:
            if i == display:
                display = None
            continue
        # Code spans own their contents, including literal dollar signs.
        pieces = re.split(r'(`+[^\r\n]*?`+)', line)
        for part_index in range(0, len(pieces), 2):
            value = pieces[part_index]
            opening = re.search(r'(?<!\\)\\\[', value)
            if opening and not re.search(r'(?<!\\)\\\]', value[opening.end():]):
                bracket_close = any(re.search(r'(?<!\\)\\\]', following)
                                    for following in lines[i+1:])
                if not bracket_close:
                    value = re.sub(r'(?<!\\)\\\[', '&#92;[', value)
                    pieces[part_index] = value
            tokens = list(re.finditer(r'(?<![\\$])\$\$(?!\$)', value))
            if len(tokens) % 2 == 0:
                continue
            token = tokens[-1]
            closing = None
            if value[:token.start()].strip() == '':
                for j in range(i + 1, len(lines)):
                    candidate = lines[j].rstrip('\r\n')
                    if re.match(r'^ {0,3}(?:`{3,}|~{3,})', candidate):
                        break
                    if re.search(r'(?<![\\$])\$\$(?!\$)\s*$', candidate):
                        closing = j
                        break
            if closing is not None:
                display = closing
            else:
                pieces[part_index] = value[:token.start()] + '&#36;&#36;' + value[token.end():]
        lines[i] = ''.join(pieces)
    return ''.join(lines)
