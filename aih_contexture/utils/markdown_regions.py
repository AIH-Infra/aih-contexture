"""Protect explicit code, table and math regions during prose-only repairs."""
from __future__ import annotations

import hashlib
import re
from bisect import bisect_right


def markdown_lines(text: str, *, protect_indented: bool = False):
    """Yield original lines and whether a structural region owns their content."""
    fence = None
    table_depth = 0
    pre_depth = 0
    math = None
    indented = False
    previous_blank = True
    source_lines = str(text or '').splitlines(keepends=True)
    display_closers = [i for i, value in enumerate(source_lines)
                       if re.search(r'(?<![\\$])\$\$(?!\$)\s*$', value)]
    fence_boundaries = [i for i, value in enumerate(source_lines)
                        if re.match(r'^ {0,3}(?:`{3,}|~{3,})', value)]
    bracket_closers = [i for i, value in enumerate(source_lines)
                       if re.search(r'(?<!\\)\\\]', value)]
    for line_index, line in enumerate(source_lines):
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line.rstrip('\r\n'))
        if fence:
            protected = True
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
        elif marker:
            fence = marker[1]
            protected = True
        else:
            structural = re.sub(r'(?<!`)(`+)(?!`)[^\r\n]*?(?<!`)\1(?!`)', '', line)
            structural = re.sub(r'<!--.*?-->', '', structural)
            table_tags = re.findall(r'<\s*(/?)table\b[^>]*>', structural, re.I)
            pre_tags = re.findall(r'<\s*(/?)pre\b[^>]*>', structural, re.I)
            protected = bool(table_depth or pre_depth or table_tags or pre_tags or math)
            for closing in table_tags:
                table_depth = max(0, table_depth + (-1 if closing else 1))
            for closing in pre_tags:
                pre_depth = max(0, pre_depth + (-1 if closing else 1))
            if '$$' in structural and re.search(r'(?<!\\)\$\$', structural):
                protected = True
                # A closing delimiter may trail an equation, but an isolated
                # mid-prose OCR token (e.g. section signs read as $$) must never
                # open a display block that masks all following physical pages.
                if len(re.findall(r'(?<!\\)\$\$', structural)) % 2:
                    if math == 'dollar':
                        math = None
                    elif not math and structural.lstrip().startswith('$$'):
                        # An unmatched OCR chapter reference cannot claim the
                        # remainder of the document. A display close must end
                        # a later line; a second '$$10-12 cf.' is not a close.
                        closer = bisect_right(display_closers, line_index)
                        boundary = bisect_right(fence_boundaries, line_index)
                        if closer < len(display_closers):
                            if (boundary == len(fence_boundaries)
                                    or display_closers[closer] < fence_boundaries[boundary]):
                                math = 'dollar'
            bracket_open = re.search(r'(?<!\\)\\\[', structural)
            bracket_close = re.search(r'(?<!\\)\\\]', structural)
            if bracket_open or bracket_close:
                protected = True
                if bracket_open and not bracket_close and not math:
                    closer = bisect_right(bracket_closers, line_index)
                    boundary = bisect_right(fence_boundaries, line_index)
                    if closer < len(bracket_closers) and (boundary == len(fence_boundaries)
                            or bracket_closers[closer] < fence_boundaries[boundary]):
                        math = 'bracket'
                elif bracket_close and math == 'bracket':
                    math = None
            if '|' in structural and (structural.lstrip().startswith('|') or re.match(r'^\s*\S.*\|.*$', structural)):
                # Skipping prose edits on a pipe-bearing line is conservative;
                # it also supports tables without optional outer pipes.
                protected = True
            if protect_indented:
                if re.match(r'^(?: {4}|\t)', line) and (previous_blank or indented):
                    indented = True
                elif line.strip():
                    indented = False
                protected = protected or indented
        previous_blank = not line.strip()
        yield line, protected


def transform_prose_regions(text: str, transform):
    """Apply a transform outside structural blocks and inline code/math."""
    prefix = 'AIH_PROTECTED_' + hashlib.sha256(text.encode('utf-8')).hexdigest()[:16] + '_'
    while prefix in text:
        prefix += 'X'
    protected_inline = {}

    def prose(value):
        if not value:
            return value
        def hold(match):
            key = prefix + str(len(protected_inline)) + '_END'
            protected_inline[key] = match.group(0)
            return key
        masked = re.sub(r'(?<!`)(`+)(?!`)[\s\S]*?(?<!`)\1(?!`)|(?<![\\$])\$(?!\$)[^\n$]+(?<!\\)\$(?!\$)', hold, value)
        edge = re.match(r'^(\s*)([\s\S]*?)(\s*)$', masked)
        return edge[1] + transform(edge[2]) + edge[3]

    output = []
    buffered = []
    for line, protected in markdown_lines(text):
        if protected:
            output.append(prose(''.join(buffered)))
            buffered.clear()
            output.append(line)
        else:
            buffered.append(line)
    output.append(prose(''.join(buffered)))
    result = ''.join(output)
    for key, value in protected_inline.items():
        result = result.replace(key, value)
    return result
