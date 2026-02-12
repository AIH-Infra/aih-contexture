"""
将此方法添加到 marker/builders/ocr_parser.py 的 OcrParser 类中
位置：在 parse_json_to_page() 方法之前（约 line 117）
"""

def parse_chandra_html_to_page(
    self,
    html: str,
    page_id: int,
    page_size: Tuple[int, int],
    bbox_scale: int = 1024
) -> PageGroup:
    """
    解析 Chandra 输出的 HTML 为 PageGroup

    Args:
        html: Chandra 返回的 HTML（带 data-bbox 和 data-label）
        page_id: 页面 ID
        page_size: (width, height) 页面尺寸
        bbox_scale: 坐标归一化范围（默认 1024）

    Returns:
        PageGroup 对象
    """
    from bs4 import BeautifulSoup
    import json

    soup = BeautifulSoup(html, "html.parser")
    top_level_divs = soup.find_all("div", recursive=False)

    width_scaler = page_size[0] / bbox_scale
    height_scaler = page_size[1] / bbox_scale

    blocks = []

    for idx, div in enumerate(top_level_divs):
        try:
            # 1. 提取 bbox
            bbox_str = div.get("data-bbox")
            if not bbox_str:
                logger.warning(f"Block {idx}: Missing data-bbox, skipping")
                continue

            # 2. 解析 bbox
            try:
                bbox = json.loads(bbox_str)
                if not isinstance(bbox, list) or len(bbox) != 4:
                    raise ValueError(f"Invalid bbox format: {bbox}")
            except Exception as e:
                logger.warning(f"Block {idx}: Failed to parse bbox '{bbox_str}': {e}")
                continue

            # 3. 转换为实际像素坐标
            bbox_pixels = [
                max(0, int(bbox[0] * width_scaler)),
                max(0, int(bbox[1] * height_scaler)),
                min(int(bbox[2] * width_scaler), page_size[0]),
                min(int(bbox[3] * height_scaler), page_size[1])
            ]

            # 4. 提取标签
            label = div.get("data-label", "Text")

            # 5. 提取内容
            content_html = str(div.decode_contents())
            text = BeautifulSoup(content_html, "html.parser").get_text()
            text = text.strip()

            if not text:
                logger.warning(f"Block {idx}: Empty text, skipping")
                continue

            # 6. 映射标签
            block_type = self._map_chandra_label(label)

            # 7. 创建 PolygonBox
            polygon = PolygonBox.from_bbox(bbox_pixels)

            # 8. 创建 Block
            block = self._create_block(text, polygon, block_type, page_id)
            blocks.append(block)

            logger.info(f"Block {idx}: type={block_type}, label={label}, text_len={len(text)}")

        except Exception as e:
            logger.error(f"Block {idx}: Failed to parse: {e}")
            continue

    # 9. 创建 PageGroup
    page_polygon = PolygonBox.from_bbox([0, 0, page_size[0], page_size[1]])
    page = PageGroup(
        page_id=page_id,
        polygon=page_polygon,
        children=blocks
    )

    logger.info(f"Page {page_id}: Created PageGroup with {len(blocks)} blocks")
    return page

def _map_chandra_label(self, label: str) -> str:
    """
    映射 Chandra 标签到 Marker BlockTypes

    Chandra 标签 (15种):
    Caption, Footnote, Equation-Block, List-Group,
    Page-Header, Page-Footer, Image, Section-Header,
    Table, Text, Complex-Block, Code-Block,
    Form, Table-Of-Contents, Figure
    """
    mapping = {
        "Caption": "caption",
        "Footnote": "footnote",
        "Equation-Block": "equation",
        "List-Group": "list_group",
        "Page-Header": "page_header",
        "Page-Footer": "page_footer",
        "Image": "picture",
        "Section-Header": "section_header",
        "Table": "table",
        "Text": "text",
        "Complex-Block": "text",
        "Code-Block": "code",
        "Form": "form",
        "Table-Of-Contents": "toc",
        "Figure": "figure"
    }
    result = mapping.get(label, "text")
    if label not in mapping:
        logger.warning(f"Unknown Chandra label: {label}, using 'text'")
    return result
