# Chandra OCR Direct 重构计划

## 🎯 核心问题

**当前策略错误**：
1. ❌ 要求 Chandra 输出 JSON → Chandra 不擅长生成结构化 JSON
2. ❌ 使用自定义 prompt → 忽略了官方推荐的 `OCR_LAYOUT_PROMPT`
3. ❌ 解析器期望 JSON → 但 Chandra 原生输出 HTML

**正确策略**：
1. ✅ 使用官方 `OCR_LAYOUT_PROMPT`
2. ✅ Chandra 输出 HTML（带 `data-bbox` 和 `data-label`）
3. ✅ 使用 BeautifulSoup 解析 HTML
4. ✅ 转换坐标（0-1024 → 实际像素）
5. ✅ 转换为 Marker 的 Block 对象

---

## 📝 重构步骤

### 步骤 1: 更新 Prompt（`ocr_chandra.py`）

**文件**: `marker/services/ocr_chandra.py`

**修改**: `_build_prompt()` 方法

```python
def _build_prompt(self) -> str:
    """使用官方推荐的 OCR Layout Prompt"""
    return """OCR this image to HTML, arranged as layout blocks. Each layout block should be a div with the data-bbox attribute representing the bounding box of the block in [x0, y0, x1, y1] format. Bboxes are normalized 0-1024. The data-label attribute is the label for the block.

Use the following labels:
- Caption
- Footnote
- Equation-Block
- List-Group
- Page-Header
- Page-Footer
- Image
- Section-Header
- Table
- Text
- Complex-Block
- Code-Block
- Form
- Table-Of-Contents
- Figure

Only use these tags [math, br, i, b, u, del, sup, sub, table, tr, td, p, th, div, pre, h1, h2, h3, h4, h5, ul, ol, li, input, a, span, img, hr, tbody, small, caption, strong, thead, big, code], and these attributes [class, colspan, rowspan, display, checked, type, border, value, style, href, alt, align].

Guidelines:
* Inline math: Surround math with <math>...</math> tags. Math expressions should be rendered in KaTeX-compatible LaTeX. Use display for block math.
* Tables: Use colspan and rowspan attributes to match table structure.
* Formatting: Maintain consistent formatting with the image, including spacing, indentation, subscripts/superscripts, and special characters.
* Images: Include a description of any images in the alt attribute of an <img> tag. Do not fill out the src property.
* Forms: Mark checkboxes and radio buttons properly.
* Text: join lines together properly into paragraphs using <p>...</p> tags. Use <br> tags for line breaks within paragraphs, but only when absolutely necessary to maintain meaning.
* Use the simplest possible HTML structure that accurately represents the content of the block.
* Make sure the text is accurate and easy for a human to read and interpret. Reading order should be correct and natural."""
```

---

### 步骤 2: 更新响应解析（`ocr_chandra.py`）

**修改**: `_parse_response()` 方法

```python
def _parse_response(self, content: str) -> str:
    """
    Chandra 返回的是 HTML，直接返回
    不需要解析为 JSON
    """
    return content.strip()
```

---

### 步骤 3: 创建 HTML 解析器（`ocr_parser.py`）

**文件**: `marker/builders/ocr_parser.py`

**新增方法**: `parse_chandra_html_to_page()`

```python
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

    for div in top_level_divs:
        # 1. 提取 bbox
        bbox_str = div.get("data-bbox")
        if not bbox_str:
            logger.warning("Missing data-bbox attribute, skipping block")
            continue

        try:
            # 尝试解析 JSON 格式: "[x0, y0, x1, y1]"
            bbox = json.loads(bbox_str)
            if len(bbox) != 4:
                raise ValueError("Invalid bbox length")
        except Exception as e:
            logger.warning(f"Failed to parse bbox: {bbox_str}, error: {e}")
            continue

        # 2. 转换为实际像素坐标
        bbox_pixels = [
            max(0, int(bbox[0] * width_scaler)),
            max(0, int(bbox[1] * height_scaler)),
            min(int(bbox[2] * width_scaler), page_size[0]),
            min(int(bbox[3] * height_scaler), page_size[1])
        ]

        # 3. 提取标签
        label = div.get("data-label", "Text")

        # 4. 提取内容（HTML）
        content_html = str(div.decode_contents())

        # 5. 提取纯文本
        text = BeautifulSoup(content_html, "html.parser").get_text()
        text = text.strip()

        if not text:
            continue

        # 6. 映射 Chandra 标签到 Marker BlockTypes
        block_type = self._map_chandra_label_to_block_type(label)

        # 7. 创建 PolygonBox
        polygon = PolygonBox.from_bbox(bbox_pixels)

        # 8. 创建 Block
        block = self._create_block(text, polygon, block_type, page_id)
        blocks.append(block)

        logger.info(f"Parsed block: type={block_type}, label={label}, text_len={len(text)}")

    # 9. 创建 PageGroup
    page_polygon = PolygonBox.from_bbox([0, 0, page_size[0], page_size[1]])
    page = PageGroup(
        page_id=page_id,
        polygon=page_polygon,
        children=blocks
    )

    logger.info(f"Created PageGroup with {len(blocks)} blocks")
    return page

def _map_chandra_label_to_block_type(self, label: str) -> str:
    """
    映射 Chandra 标签到 Marker BlockTypes

    Chandra 标签:
    - Caption, Footnote, Equation-Block, List-Group
    - Page-Header, Page-Footer, Image, Section-Header
    - Table, Text, Complex-Block, Code-Block
    - Form, Table-Of-Contents, Figure
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
    return mapping.get(label, "text")
```

---

### 步骤 4: 更新 Converter（`ocr_direct_async.py`）

**文件**: `marker/converters/ocr_direct_async.py`

**修改**: 调用新的解析方法

```python
# 4. 解析输出
# Chandra 返回的是 HTML，使用专门的解析器
page = self.parser.parse_chandra_html_to_page(
    ocr_output,  # HTML 字符串
    page_num,
    img_size,
    bbox_scale=1024  # Chandra 默认归一化范围
)
```

---

### 步骤 5: 更新配置参数

**文件**: `marker/services/ocr_chandra.py`

**删除不需要的参数**:
- ❌ `ocr_output_format` - Chandra 只输出 HTML
- ❌ `ocr_max_tokens` - 使用官方推荐值 12384

**添加新参数**:
- ✅ `bbox_scale` - 坐标归一化范围（默认 1024）

```python
class OcrChandraService(BaseService):
    ocr_endpoint: Annotated[
        str, "OCR API endpoint"
    ] = "http://localhost:1234/v1/chat/completions"

    ocr_model: Annotated[
        str, "OCR model name"
    ] = "chandra"

    ocr_api_key: Annotated[
        Optional[str], "API key (optional)"
    ] = None

    bbox_scale: Annotated[
        int, "Bbox normalization scale"
    ] = 1024

    ocr_temperature: Annotated[
        float, "Temperature"
    ] = 0

    ocr_top_p: Annotated[
        float, "Top-p sampling"
    ] = 0.1

    ocr_timeout: Annotated[
        int, "API timeout (seconds)"
    ] = 120

    max_retries: Annotated[
        int, "Maximum retry attempts"
    ] = 3
```

---

### 步骤 6: 更新 API 请求参数

**文件**: `marker/services/ocr_chandra.py`

**修改**: `_build_request_payload()` 方法

```python
def _build_request_payload(self, img_base64: str) -> Dict[str, Any]:
    """构建 API 请求 payload（官方推荐参数）"""
    prompt = self._build_prompt()

    payload = {
        "model": self.ocr_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{img_base64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ],
        "max_tokens": 12384,  # 官方推荐值
        "temperature": self.ocr_temperature,
        "top_p": self.ocr_top_p
    }

    return payload
```

---

## 🔄 重构后的完整流程

```
1. PDF 页面 → 渲染为图像 (DPI 192+)
   ↓
2. 图像预处理 (最小尺寸 1536px, RGB, JPEG)
   ↓
3. 调用 Chandra OCR
   - Prompt: OCR_LAYOUT_PROMPT (官方)
   - 参数: max_tokens=12384, temperature=0, top_p=0.1
   ↓
4. Chandra 返回 HTML
   - 格式: <div data-bbox="[x0,y0,x1,y1]" data-label="Text">...</div>
   - 坐标: 归一化到 0-1024
   ↓
5. BeautifulSoup 解析 HTML
   - 提取所有顶层 <div> 元素
   - 读取 data-bbox 和 data-label 属性
   ↓
6. 转换坐标
   - 归一化坐标 (0-1024) → 实际像素坐标
   ↓
7. 创建 Marker Block 对象
   - 映射 Chandra 标签 → Marker BlockTypes
   - 创建 PolygonBox
   - 提取文本内容
   ↓
8. 创建 PageGroup
   - children = Block 列表
   ↓
9. 创建 Document
   - pages = PageGroup 列表
   ↓
10. MarkdownRenderer 渲染
    - Document → MarkdownOutput
    - 提取 markdown 字符串
    ↓
11. 保存 Markdown 文件
```

---

## ✅ 预期效果

### 修复前（当前）
- ❌ Chandra 返回不完美的 JSON
- ❌ 解析器无法处理
- ❌ page.children = None
- ❌ Markdown 文件为空

### 修复后
- ✅ Chandra 返回标准 HTML
- ✅ BeautifulSoup 正确解析
- ✅ page.children = [Block, Block, ...]
- ✅ Markdown 文件包含完整内容
- ✅ 保留坐标信息
- ✅ 保留布局标签（页眉、脚注、表格等）

---

## 📊 关键改进

1. **使用官方 Prompt** → Chandra 输出质量更好
2. **HTML 解析** → 比 JSON 解析更可靠
3. **坐标转换** → 保留精确的位置信息
4. **标签映射** → 保留文档结构（页眉、脚注、表格等）
5. **错误处理** → 更健壮的解析逻辑

---

## 🚀 下一步

1. 实现步骤 1-6 的代码修改
2. 测试单页 PDF 转换
3. 验证 Markdown 输出
4. 测试多页 PDF 批量处理
5. 集成页码锚点功能
6. 优化性能（并发、缓存）

---

## 📝 注意事项

1. **图像尺寸**: 推荐最小 1536px（官方建议）
2. **DPI**: 推荐 192+ DPI
3. **格式**: 使用 JPEG（减小 base64 大小）
4. **坐标**: 归一化范围固定为 1024
5. **标签**: 使用官方 15 种布局标签
6. **HTML 标签**: 只使用官方允许的标签和属性

---

**版本**: 1.0
**日期**: 2026-02-05
**状态**: 待实现
