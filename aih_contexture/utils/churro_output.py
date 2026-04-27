"""
Churro Output Parser

解析 Churro XML 输出并转换为多种格式：
- XML (原始格式，用于归档)
- JSON (用于机器学习分析)
- Markdown (用于阅读，无元数据)
- HTML (用于浏览器查看)
"""

import json
from typing import List, Dict, Any, Optional
from lxml import etree
from bs4 import BeautifulSoup

from aih_contexture.logger import get_logger

logger = get_logger()


def parse_xml(xml_str: str) -> etree._Element:
    """
    解析 XML 字符串为 lxml Element

    Args:
        xml_str: XML 字符串

    Returns:
        lxml Element 对象
    """
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

    def get_local_tag(elem: etree._Element) -> str:
        return etree.QName(elem).localname if elem.tag else ""

    result = {
        "metadata": {},
        "content": []
    }

    # 提取元数据
    for metadata_elem in root.findall(".//*"):
        tag = get_local_tag(metadata_elem)
        if tag == "Metadata":
            for child in metadata_elem:
                child_tag = get_local_tag(child)
                child_text = "".join(child.itertext()).strip()
                if child_text:
                    result["metadata"][child_tag] = child_text
            break

    # 提取内容块
    for page_elem in root.findall(".//*"):
        if get_local_tag(page_elem) == "Page":
            page_data = {"type": "page", "elements": []}

            # 提取页码
            for header_elem in page_elem.findall(".//*"):
                if get_local_tag(header_elem) == "PageNumber":
                    page_num = "".join(header_elem.itertext()).strip()
                    if page_num:
                        page_data["page_number"] = page_num
                    break

            # 提取 Body 内容
            for body_elem in page_elem.findall(".//*"):
                if get_local_tag(body_elem) == "Body":
                    for child in body_elem:
                        child_tag = get_local_tag(child)

                        if child_tag == "Paragraph":
                            lines = []
                            for line in child:
                                if get_local_tag(line) == "Line":
                                    lines.append("".join(line.itertext()).strip())
                            if lines:
                                page_data["elements"].append({
                                    "type": "paragraph",
                                    "text": " ".join(lines)
                                })

                        elif child_tag == "BlockQuotation":
                            lines = []
                            for line in child:
                                if get_local_tag(line) == "Line":
                                    lines.append("".join(line.itertext()).strip())
                            if lines:
                                page_data["elements"].append({
                                    "type": "blockquote",
                                    "text": " ".join(lines)
                                })

                        elif child_tag == "MarginalNote":
                            lines = []
                            for line in child:
                                if get_local_tag(line) == "Line":
                                    lines.append("".join(line.itertext()).strip())
                            if lines:
                                page_data["elements"].append({
                                    "type": "marginal_note",
                                    "placement": child.get("placement", ""),
                                    "text": " ".join(lines)
                                })

                        elif child_tag == "Heading":
                            text = "".join(child.itertext()).strip()
                            if text:
                                page_data["elements"].append({
                                    "type": "heading",
                                    "text": text,
                                    "heading_type": child.get("type", "")
                                })

            result["content"].append(page_data)

    return result


def xml_to_markdown(xml_str: str) -> str:
    """
    将 Churro XML 转换为 Markdown

    Args:
        xml_str: Churro XML 字符串

    Returns:
        Markdown 字符串
    """
    root = parse_xml(xml_str)
    parts = []

    def get_local_tag(elem: etree._Element) -> str:
        """获取不带命名空间的标签名"""
        return etree.QName(elem).localname if elem.tag else ""

    def extract_text(elem: etree._Element):
        tag = get_local_tag(elem)

        # Page > Body - 提取主体内容
        if tag == "Body":
            for child in elem:
                extract_text(child)
            return

        # Paragraph - 段落（包含多个 Line）
        if tag == "Paragraph":
            lines = []
            for child in elem:
                if get_local_tag(child) == "Line":
                    line_text = "".join(child.itertext()).strip()
                    if line_text:
                        lines.append(line_text)
            if lines:
                parts.append(" ".join(lines))
            return

        # BlockQuotation - 引用
        if tag == "BlockQuotation":
            lines = []
            for child in elem:
                if get_local_tag(child) == "Line":
                    line_text = "".join(child.itertext()).strip()
                    if line_text:
                        lines.append(f"> {line_text}")
            if lines:
                parts.extend(lines)
            return

        # MarginalNote - 边注（格式对齐 vlm_json_output: > **[Marginal-Left/Right]** 内容）
        if tag == "MarginalNote":
            placement = elem.get("placement", "")
            placement_map = {
                "left_margin": "Marginal-Left",
                "right_margin": "Marginal-Right",
                "top_margin": "Marginal-Top",
                "bottom_margin": "Marginal-Bottom"
            }
            placement_text = placement_map.get(placement, placement)

            lines = []
            for child in elem:
                if get_local_tag(child) == "Line":
                    line_text = "".join(child.itertext()).strip()
                    if line_text:
                        lines.append(line_text)
            if lines:
                content = " ".join(lines)
                parts.append(f"> **[{placement_text}]** {content}")
            return

        # Heading - 标题
        if tag == "Heading":
            text = "".join(elem.itertext()).strip()
            if text:
                parts.append(f"## {text}")
            return

        # 递归处理子元素
        for child in elem:
            extract_text(child)

    extract_text(root)
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
