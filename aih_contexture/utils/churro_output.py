"""
Churro Output Parser

解析 Churro XML 输出并转换为多种格式：
- XML (原始格式，用于归档)
- JSON (用于机器学习分析)
- Markdown (用于阅读，无元数据)
- HTML (用于浏览器查看)
"""

import json
import html
import re
from typing import List, Dict, Any, Optional
from lxml import etree
from bs4 import BeautifulSoup

from aih_contexture.logger import get_logger

logger = get_logger()


_OUTER_FENCE_RE = re.compile(r"^(?:```|~~~)[^\n]*\n(?P<body>.*)\n(?:```|~~~)\s*$", re.DOTALL)
_FOOTNOTE_START_RE = re.compile(
    r"^\s*(?:<sup>\s*)?([0-9]{1,4}|[ivxlcdm]{1,12}|[⁰¹²³⁴⁵⁶⁷⁸⁹]+)(?:\s*</sup>)?[.)]?\s+",
    re.IGNORECASE,
)
_INLINE_EMPHASIS_MARKER_RE = re.compile(r"^\s*([0-9]{1,4}|[ivxlcdm]{1,12}|[⁰¹²³⁴⁵⁶⁷⁸⁹]+)\s*$", re.IGNORECASE)
_HTML_SUP_MARKER_RE = re.compile(r"<sup>\s*([^<]+?)\s*</sup>", re.IGNORECASE)
_FOOTNOTE_MARKER_BODY_RE = re.compile(
    r"^\s*([0-9]{1,4}|[ivxlcdm]{1,12}|[⁰¹²³⁴⁵⁶⁷⁸⁹]+)[.)]?\s+(.+?)\s*$",
    re.IGNORECASE | re.DOTALL,
)
_VISUAL_SUPERSCRIPT_TAGS = {"Above", "Superscript", "Addition"}


def normalize_churro_xml_output(text: str) -> str:
    """Return the XML document from a Churro response, stripping wrappers/fences."""
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""

    match = _OUTER_FENCE_RE.match(cleaned)
    if match:
        cleaned = match.group("body").strip()

    for tag in ("HistoricalDocument", "Page", "output"):
        start = re.search(rf"<{tag}\b[^>]*>", cleaned, flags=re.IGNORECASE)
        end = re.search(rf"</{tag}>", cleaned, flags=re.IGNORECASE)
        if start and end and end.end() > start.start():
            cleaned = cleaned[start.start():end.end()].strip()
            break

    if cleaned.startswith("<output"):
        try:
            root = etree.fromstring(cleaned.encode())
            inner = "".join(
                etree.tostring(child, encoding="unicode") for child in root
            ).strip()
            if inner:
                return inner
        except etree.XMLSyntaxError:
            pass
    return cleaned


def _local_tag(elem: etree._Element) -> str:
    return etree.QName(elem).localname if isinstance(elem.tag, str) else ""


def _children(elem: etree._Element, tag: str | None = None) -> list[etree._Element]:
    items = [child for child in elem if isinstance(child.tag, str)]
    if tag is None:
        return items
    return [child for child in items if _local_tag(child) == tag]


def _first_child(elem: etree._Element, tag: str) -> etree._Element | None:
    for child in _children(elem):
        if _local_tag(child) == tag:
            return child
    return None


def _text(elem: etree._Element) -> str:
    return " ".join(part.strip() for part in elem.itertext() if part and part.strip()).strip()


def _inline_text(elem: etree._Element, *, preserve_emphasis_markers: bool = False) -> str:
    parts: list[str] = []
    if elem.text:
        parts.append(elem.text)
    for child in _children(elem):
        child_tag = _local_tag(child)
        child_text = _text(child)
        marker_match = _INLINE_EMPHASIS_MARKER_RE.match(child_text)
        if (
            preserve_emphasis_markers
            and (
                child_tag in _VISUAL_SUPERSCRIPT_TAGS
                or (
                    child_tag == "Emphasis"
                    and str(child.get("type") or "").strip().lower() == "other"
                )
            )
            and marker_match
        ):
            marker = marker_match.group(1).translate(str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789"))
            parts.append(f"<sup>{html.escape(marker, quote=False)}</sup>")
        else:
            parts.append(_inline_text(child, preserve_emphasis_markers=preserve_emphasis_markers))
        if child.tail:
            parts.append(child.tail)
    return _normalize_inline_text("".join(parts))


def _normalize_inline_text(text: str) -> str:
    text = re.sub(r"[ \t\r\f\v]+", " ", text or "")
    text = re.sub(r"\s*\n\s*", " ", text)
    text = re.sub(r"\s+(<sup>)", r"\1", text)
    text = re.sub(r"(</sup>)\s+([,.;:!?，。；：！？、)\]\}])", r"\1\2", text)
    return text.strip()


def _line_text(elem: etree._Element, *, preserve_emphasis_markers: bool = False) -> str:
    lines = [_inline_text(line, preserve_emphasis_markers=preserve_emphasis_markers) for line in _children(elem, "Line")]
    lines = [line for line in lines if line]
    if lines:
        return "\n".join(lines)
    return _inline_text(elem, preserve_emphasis_markers=preserve_emphasis_markers)


def _join_lines(elem: etree._Element, *, preserve_emphasis_markers: bool = False) -> str:
    return " ".join(line for line in _line_text(elem, preserve_emphasis_markers=preserve_emphasis_markers).splitlines() if line.strip()).strip()


def _looks_like_footnote(text: str) -> bool:
    return _FOOTNOTE_START_RE.match(text or "") is not None


def _inline_marks_from_text(text: str) -> list[dict[str, Any]]:
    marks: list[dict[str, Any]] = []
    for match in _HTML_SUP_MARKER_RE.finditer(text or ""):
        marker = html.unescape(match.group(1)).strip()
        if not marker:
            continue
        marks.append(
            {
                "kind": "superscript",
                "text": marker,
                "visual_role": "superscript",
                "marker": marker,
                "marker_normalized": marker.lower(),
                "source": "churro_visual_superscript",
            }
        )
    return marks


def _markdown_footnote_text(text: str) -> str:
    match = _FOOTNOTE_MARKER_BODY_RE.match(text or "")
    if not match:
        return text
    marker = match.group(1).translate(str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789"))
    body = match.group(2).strip()
    return f"<sup>{html.escape(marker, quote=False)}</sup> {body}"


def _heading_level(value: str | None) -> int:
    normalized = str(value or "").strip().lower()
    if normalized == "main":
        return 1
    if normalized == "sub":
        return 2
    return 2


def parse_xml(xml_str: str) -> etree._Element:
    """
    解析 XML 字符串为 lxml Element

    Args:
        xml_str: XML 字符串

    Returns:
        lxml Element 对象
    """
    xml_str = normalize_churro_xml_output(xml_str)
    try:
        return etree.fromstring(xml_str.encode())
    except etree.XMLSyntaxError as e:
        logger.error(f"XML parsing error: {e}")
        # 尝试容错解析
        parser = etree.XMLParser(recover=True)
        return etree.fromstring(xml_str.encode(), parser)


def xml_to_json(xml_str: str) -> Dict[str, Any]:
    """
    将 XML 转换为 JSON 格式（结构化提取）

    Args:
        xml_str: XML 字符串

    Returns:
        JSON 字典
    """
    root = parse_xml(xml_str)
    result = {"metadata": {}, "content": []}

    metadata_elem = next((elem for elem in root.iter() if _local_tag(elem) == "Metadata"), None)
    if metadata_elem is not None:
        for child in _children(metadata_elem):
            child_text = _text(child)
            if child_text:
                result["metadata"][_local_tag(child)] = child_text

    page_elems = [root] if _local_tag(root) == "Page" else [elem for elem in root.iter() if _local_tag(elem) == "Page"]
    for page_elem in page_elems:
        page_data = {"type": "page", "elements": []}

        for region_tag in ("Header", "Footer"):
            region = _first_child(page_elem, region_tag)
            if region is None:
                continue
            region_texts: list[str] = []
            for child in _children(region):
                child_tag = _local_tag(child)
                child_text = _join_lines(child)
                if not child_text:
                    continue
                if child_tag in {"PageNumber", "FolioNumber"}:
                    page_data.setdefault("page_number", child_text)
                    page_data["elements"].append({
                        "type": "page_number",
                        "text": child_text,
                        "region": region_tag.lower(),
                        "raw_tag": child_tag,
                    })
                else:
                    region_texts.append(child_text)
            if region_texts:
                page_data["elements"].append({
                    "type": "page_header" if region_tag == "Header" else "page_footer",
                    "text": " ".join(region_texts),
                    "region": region_tag.lower(),
                })

        body_elem = _first_child(page_elem, "Body")
        if body_elem is not None:
            for child in _children(body_elem):
                page_data["elements"].extend(_body_element_to_json(child))

        result["content"].append(page_data)

    return result


def _body_element_to_json(elem: etree._Element) -> list[dict[str, Any]]:
    tag = _local_tag(elem)
    preserve_inline_markers = tag in {"Paragraph", "BlockQuotation", "DateLine"}
    text = _join_lines(elem, preserve_emphasis_markers=preserve_inline_markers)
    if not text and tag not in {"Table", "Figure", "Gap", "Seal", "Stamp", "Watermark", "MusicalNotation"}:
        return []

    if tag == "Paragraph":
        block = {"type": "paragraph", "text": text}
        inline_marks = _inline_marks_from_text(text)
        if inline_marks:
            block["inline_marks"] = inline_marks
        return [block]
    if tag == "BlockQuotation":
        block = {"type": "blockquote", "text": text, "quotation_type": elem.get("type", "")}
        inline_marks = _inline_marks_from_text(text)
        if inline_marks:
            block["inline_marks"] = inline_marks
        return [block]
    if tag == "MarginalNote":
        placement = elem.get("placement", "")
        text = _join_lines(elem)
        block_type = "footnote" if placement == "bottom_margin" and _looks_like_footnote(text) else "marginal_note"
        return [{"type": block_type, "placement": placement, "text": text}]
    if tag == "Heading":
        heading_type = elem.get("type", "")
        return [{
            "type": "heading",
            "text": text,
            "heading_type": heading_type,
            "heading_level": _heading_level(heading_type),
        }]
    if tag == "DateLine":
        block = {"type": "paragraph", "text": text, "raw_tag": tag}
        inline_marks = _inline_marks_from_text(text)
        if inline_marks:
            block["inline_marks"] = inline_marks
        return [block]
    if tag in {"DatedEntry", "RecordEntry"}:
        blocks: list[dict[str, Any]] = []
        for child in _children(elem):
            blocks.extend(_body_element_to_json(child))
        if not blocks and text:
            blocks.append({"type": "paragraph", "text": text, "raw_tag": tag})
        return blocks
    if tag == "List":
        return [
            {"type": "list_item", "text": _join_lines(item), "list_type": elem.get("type", "")}
            for item in _children(elem, "Item")
            if _join_lines(item)
        ]
    if tag == "Table":
        return [{"type": "table", "text": _table_to_html(elem)}]
    if tag == "Formula":
        return [{"type": "equation", "text": text}]
    if tag == "InterlinearNote":
        return [{"type": "inline_annotation", "text": text}]
    if tag == "Figure":
        blocks = []
        caption = _first_child(elem, "Caption")
        if caption is not None and _join_lines(caption):
            blocks.append({"type": "caption", "text": _join_lines(caption)})
        description = _first_child(elem, "Description")
        figure_text = _text(description) if description is not None else ""
        blocks.append({"type": "figure", "text": figure_text})
        return blocks
    if tag in {"Seal", "Stamp", "Watermark", "MusicalNotation", "Gap"}:
        description = elem.get("description") or elem.get("reason") or tag
        return [{"type": "complex_region", "text": description, "raw_tag": tag}]
    return [{"type": "complex_region", "text": text, "raw_tag": tag}] if text else []


def _table_to_html(table: etree._Element) -> str:
    rows = []
    for row in _children(table, "TableRow"):
        cells = []
        for cell in _children(row, "TableCell"):
            attrs = []
            for key in ("colspan", "rowspan"):
                value = cell.get(key)
                if value and value != "1":
                    attrs.append(f'{key}="{value}"')
            cell_tag = "th" if cell.get("role") == "header" else "td"
            attr_text = f" {' '.join(attrs)}" if attrs else ""
            cells.append(f"<{cell_tag}{attr_text}>{_join_lines(cell)}</{cell_tag}>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return "<table>\n" + "\n".join(rows) + "\n</table>"


def xml_to_markdown(xml_str: str) -> str:
    """
    将 Churro XML 转换为 Markdown

    Args:
        xml_str: Churro XML 字符串

    Returns:
        Markdown 字符串
    """
    data = xml_to_json(xml_str)
    parts = []
    for page in data.get("content", []):
        if not isinstance(page, dict):
            continue
        for element in page.get("elements", []):
            if not isinstance(element, dict):
                continue
            block_type = str(element.get("type") or "")
            text = str(element.get("text") or "").strip()
            if not text and block_type not in {"figure"}:
                continue
            if block_type == "page_number":
                continue
            if block_type == "page_header":
                parts.append(f"<!-- PageHeader: {text} -->")
            elif block_type == "page_footer":
                parts.append(f"<!-- PageFooter: {text} -->")
            elif block_type == "heading":
                level = int(element.get("heading_level") or 2)
                parts.append(f"{'#' * max(1, min(6, level))} {text}")
            elif block_type == "blockquote":
                parts.append("\n".join(f"> {line}" for line in text.splitlines()))
            elif block_type == "marginal_note":
                side = {"left_margin": "left", "right_margin": "right"}.get(str(element.get("placement") or ""))
                if side:
                    parts.append(f"<!-- Margin:{side} -->\n> {text}\n<!-- /Margin -->")
                else:
                    parts.append(text)
            elif block_type == "footnote":
                parts.append(_markdown_footnote_text(text))
            elif block_type == "list_item":
                parts.append(f"- {text}")
            elif block_type == "equation":
                parts.append(f"$$\n{text}\n$$")
            elif block_type == "caption":
                parts.append(f"*{text}*")
            elif block_type == "figure":
                parts.append(f"![{text or 'Image'}]()")
            else:
                parts.append(text)
    return "\n\n".join(parts)


def xml_to_html(xml_str: str) -> str:
    """
    将 XML 转换为 HTML 格式（通过 Markdown）

    Args:
        xml_str: XML 字符串

    Returns:
        HTML 字符串
    """
    # 先转为 Markdown
    markdown = xml_to_markdown(xml_str)

    # 使用简单的 Markdown 到 HTML 转换
    import re
    html = markdown

    # 标题
    html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)

    # 引用块
    lines = html.split('\n')
    in_blockquote = False
    result_lines = []
    for line in lines:
        if line.startswith('>'):
            if not in_blockquote:
                result_lines.append('<blockquote>')
                in_blockquote = True
            result_lines.append(f'<p>{line[1:].strip()}</p>')
        else:
            if in_blockquote:
                result_lines.append('</blockquote>')
                in_blockquote = False
            if line.strip():
                result_lines.append(f'<p>{line}</p>')
            else:
                result_lines.append('<br>')

    if in_blockquote:
        result_lines.append('</blockquote>')

    return '\n'.join(result_lines)


def extract_page_number(xml_str: str) -> Optional[str]:
    """
    从 Churro XML 中提取印刷页码

    Args:
        xml_str: XML 字符串

    Returns:
        页码字符串或 None
    """
    try:
        root = parse_xml(xml_str)

        def get_local_tag(elem: etree._Element) -> str:
            return etree.QName(elem).localname if elem.tag else ""

        # 查找 PageNumber 元素
        for elem in root.iter():
            if get_local_tag(elem) == "PageNumber":
                page_num = "".join(elem.itertext()).strip()
                if page_num:
                    return page_num

        return None
    except Exception as e:
        logger.warning(f"Failed to extract page number: {e}")
        return None


def parse_xml_pages(xml_pages: List[str]) -> List[Dict[str, Any]]:
    """
    批量解析 XML 页面

    Args:
        xml_pages: XML 字符串列表

    Returns:
        解析结果列表
    """
    results = []
    for i, xml_str in enumerate(xml_pages):
        try:
            result = {
                "page_num": i,
                "xml": xml_str,
                "json": xml_to_json(xml_str),
                "markdown": xml_to_markdown(xml_str),
                "html": xml_to_html(xml_str)
            }
            results.append(result)
        except Exception as e:
            logger.error(f"Failed to parse page {i}: {e}")
            results.append({
                "page_num": i,
                "xml": xml_str,
                "json": {},
                "markdown": "",
                "html": "",
                "error": str(e)
            })
    return results
