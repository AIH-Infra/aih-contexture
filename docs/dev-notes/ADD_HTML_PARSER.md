# Chandra HTML 解析器 - 完整代码

## 添加到 marker/builders/ocr_parser.py

在 line 116 之后（`return block` 之后），添加以下两个方法：

```python
    def parse_chandra_html_to_page(
        self,
        html: str,
        page_id: int,
        page_size: Tuple[int, int],
        bbox_scale: int = 1024
    ) -> PageGroup:
        """解析 Chandra HTML 为 PageGroup"""
        from bs4 import BeautifulSoup
        import json

        soup = BeautifulSoup(html, "html.parser")
        divs = soup.find_all("div", recursive=False)

        width_scaler = page_size[0] / bbox_scale
        height_scaler = page_size[1] / bbox_scale
        blocks = []

        for idx, div in enumerate(divs):
            try:
                bbox_str = div.get("data-bbox")
                if not bbox_str:
                    continue

                bbox = json.loads(bbox_str)
                if len(bbox) != 4:
                    continue

                bbox_pixels = [
                    max(0, int(bbox[0] * width_scaler)),
                    max(0, int(bbox[1] * height_scaler)),
                    min(int(bbox[2] * width_scaler), page_size[0]),
                    min(int(bbox[3] * height_scaler), page_size[1])
                ]

                label = div.get("data-label", "Text")
                text = BeautifulSoup(str(div.decode_contents()), "html.parser").get_text().strip()

                if not text:
                    continue

                block_type = self._map_chandra_label(label)
                polygon = PolygonBox.from_bbox(bbox_pixels)
                block = self._create_block(text, polygon, block_type, page_id)
                blocks.append(block)

                logger.info(f"Block {idx}: {block_type}, {len(text)} chars")
            except Exception as e:
                logger.error(f"Block {idx} failed: {e}")
                continue

        page_polygon = PolygonBox.from_bbox([0, 0, page_size[0], page_size[1]])
        page = PageGroup(page_id=page_id, polygon=page_polygon, children=blocks)
        logger.info(f"Page {page_id}: {len(blocks)} blocks")
        return page

    def _map_chandra_label(self, label: str) -> str:
        """映射 Chandra 标签"""
        mapping = {
            "Caption": "caption", "Footnote": "footnote",
            "Equation-Block": "equation", "List-Group": "list_group",
            "Page-Header": "page_header", "Page-Footer": "page_footer",
            "Image": "picture", "Section-Header": "section_header",
            "Table": "table", "Text": "text",
            "Complex-Block": "text", "Code-Block": "code",
            "Form": "form", "Table-Of-Contents": "toc",
            "Figure": "figure"
        }
        return mapping.get(label, "text")
```

## 需要添加的导入

在文件顶部添加：
```python
from bs4 import BeautifulSoup
import json
```

## 测试

完成后运行：
```bash
streamlit run marker/scripts/streamlit_app.py
```
