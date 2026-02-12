# Chandra OCR 模型集成技术文档

## 📋 文档概述

本文档用于指导开发人员通过 **LM Studio 的 OpenAI 兼容接口**调用 Chandra OCR 模型，并将输出结果解析为结构化的 Markdown 或 JSON 格式，用于 PDF 结构化提取系统。

---

## 🎯 核心信息

### 模型基本信息

- **模型名称**: Chandra OCR
- **模型类型**: 基于 Qwen3-VL 的专门 OCR 视觉模型
- **HuggingFace 地址**: `datalab-to/chandra`
- **主要功能**: 将文档图像转换为带坐标信息的结构化 HTML/Markdown/JSON
- **支持语言**: 40+ 种语言
- **特殊能力**: 表格识别、数学公式识别、手写识别、表单识别、版面分析

### 部署方式

- **推荐方式**: LM Studio（OpenAI 兼容接口）
- **API 端点**: `http://localhost:1234/v1`（LM Studio 默认）
- **认证**: 通常不需要 API Key，或使用 `"EMPTY"`

---

## 🔧 1. API 调用规范

### 1.1 请求格式

Chandra 使用标准的 OpenAI Chat Completions API 格式，支持视觉输入。

#### 请求端点
```
POST http://localhost:1234/v1/chat/completions
```

#### 请求头
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer EMPTY"
}
```

#### 请求体结构
```json
{
  "model": "chandra",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/png;base64,{BASE64_ENCODED_IMAGE}"
          }
        },
        {
          "type": "text",
          "text": "{PROMPT}"
        }
      ]
    }
  ],
  "max_tokens": 12384,
  "temperature": 0,
  "top_p": 0.1
}
```

### 1.2 关键参数说明

| 参数 | 说明 | 推荐值 |
|------|------|--------|
| `model` | 模型名称 | `"chandra"` |
| `max_tokens` | 最大输出令牌数 | `12384` |
| `temperature` | 采样温度（0=确定性） | `0` |
| `top_p` | 核采样参数 | `0.1` |
| `bbox_scale` | 坐标归一化范围（在 prompt 中） | `1024` |

---

## 📝 2. Prompt 规范

Chandra 官方提供两种标准 Prompt 模式：

### 2.1 模式 A: `ocr_layout`（推荐用于结构化提取）

这是**强烈推荐**的模式，提供完整的布局和坐标信息。

```
OCR this image to HTML, arranged as layout blocks. Each layout block should be a div with the data-bbox attribute representing the bounding box of the block in [x0, y0, x1, y1] format. Bboxes are normalized 0-1024. The data-label attribute is the label for the block.

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
* Make sure the text is accurate and easy for a human to read and interpret. Reading order should be correct and natural.
```

### 2.2 布局标签类型（15 种）

| 标签 | 说明 | 用途 |
|------|------|------|
| `Caption` | 标题/说明文字 | 图表标题、说明 |
| `Footnote` | 脚注 | 页面底部注释 |
| `Equation-Block` | 公式块 | 数学公式 |
| `List-Group` | 列表组 | 有序/无序列表 |
| `Page-Header` | 页眉 | 页面顶部信息 |
| `Page-Footer` | 页脚 | 页面底部信息 |
| `Image` | 图像 | 图片、图表 |
| `Section-Header` | 章节标题 | 文档结构标题 |
| `Table` | 表格 | 数据表格 |
| `Text` | 正文文本 | 主要内容 |
| `Complex-Block` | 复杂块 | 混合内容 |
| `Code-Block` | 代码块 | 程序代码 |
| `Form` | 表单 | 表单元素 |
| `Table-Of-Contents` | 目录 | 文档目录 |
| `Figure` | 图表 | 图表元素 |

---

## 📤 3. 输出格式解析

### 3.1 原始输出示例

模型返回的是带有 `data-bbox` 和 `data-label` 属性的 HTML：

```html
<div data-bbox="[347, 61, 594, 78]" data-label="Page-Header">Herder als Kants Zuhörer.</div>
<div data-bbox="[842, 62, 870, 78]" data-label="Page-Header">33</div>
<div data-bbox="[65, 91, 873, 390]" data-label="Text">
  <p>nachmals bezeichnete¹), die aber Kant an den Ton seiner Lieblingsdichter...</p>
</div>
<div data-bbox="[65, 394, 873, 795]" data-label="Text">
  <p>So kreuzten sich in der Seele des Jünglings Poesie und Philosophie...</p>
</div>
<div data-bbox="[123, 834, 370, 850]" data-label="Footnote">
  <p>¹) An Kant, WB. I, 2, 299.</p>
</div>
<div data-bbox="[50, 420, 500, 800]" data-label="Table">
  <table>
    <tr><th colspan="2">Header</th></tr>
    <tr><td>Cell 1</td><td>Cell 2</td></tr>
  </table>
</div>
<div data-bbox="[100, 200, 400, 350]" data-label="Equation-Block">
  <math display="block">E = mc^2</math>
</div>
```

### 3.2 坐标信息说明

#### 坐标格式
```
[x0, y0, x1, y1]
```
- `x0, y0`: 左上角坐标
- `x1, y1`: 右下角坐标
- **归一化范围**: `0-1024`（默认）

#### 坐标转换为实际像素

```python
def convert_bbox_to_pixels(bbox, image_width, image_height, bbox_scale=1024):
    """
    将归一化坐标转换为实际像素坐标
    
    Args:
        bbox: [x0, y0, x1, y1] 归一化坐标
        image_width: 图像实际宽度
        image_height: 图像实际高度
        bbox_scale: 归一化范围（默认 1024）
    
    Returns:
        [x0, y0, x1, y1] 实际像素坐标
    """
    width_scaler = image_width / bbox_scale
    height_scaler = image_height / bbox_scale
    
    return [
        max(0, int(bbox[0] * width_scaler)),
        max(0, int(bbox[1] * height_scaler)),
        min(int(bbox[2] * width_scaler), image_width),
        min(int(bbox[3] * height_scaler), image_height)
    ]
```

---

## 🔍 4. HTML 解析代码

### 4.1 解析为结构化 JSON

以下是官方的解析逻辑（来自 `chandra/output.py`）：

```python
import json
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import List

@dataclass
class LayoutBlock:
    """布局块数据结构"""
    bbox: List[int]      # 实际像素坐标 [x0, y0, x1, y1]
    label: str           # 块类型标签
    content: str         # HTML 内容

def parse_layout(html: str, image_width: int, image_height: int, bbox_scale=1024):
    """
    解析 HTML 为结构化的布局块列表
    
    Args:
        html: 模型输出的原始 HTML
        image_width: 图像实际宽度
        image_height: 图像实际高度
        bbox_scale: 归一化范围（默认 1024）
    
    Returns:
        List[LayoutBlock]: 布局块列表
    """
    soup = BeautifulSoup(html, "html.parser")
    top_level_divs = soup.find_all("div", recursive=False)
    
    width_scaler = image_width / bbox_scale
    height_scaler = image_height / bbox_scale
    
    layout_blocks = []
    
    for div in top_level_divs:
        # 提取 bbox 属性
        bbox = div.get("data-bbox")
        
        try:
            # 尝试解析 JSON 格式
            bbox = json.loads(bbox)
            assert len(bbox) == 4, "Invalid bbox length"
        except Exception:
            try:
                # 尝试解析空格分隔格式
                bbox = bbox.split(" ")
                assert len(bbox) == 4, "Invalid bbox length"
            except Exception:
                # 默认值
                bbox = [0, 0, 1, 1]
        
        bbox = list(map(int, bbox))
        
        # 转换为实际像素坐标
        bbox = [
            max(0, int(bbox[0] * width_scaler)),
            max(0, int(bbox[1] * height_scaler)),
            min(int(bbox[2] * width_scaler), image_width),
            min(int(bbox[3] * height_scaler), image_height),
        ]
        
        # 提取标签和内容
        label = div.get("data-label", "block")
        content = str(div.decode_contents())
        
        layout_blocks.append(
            LayoutBlock(bbox=bbox, label=label, content=content)
        )
    
    return layout_blocks
```

---

## 💻 5. 完整的 API 调用示例

### 5.1 使用 OpenAI Python SDK

```python
import base64
import io
from PIL import Image
from openai import OpenAI

# 初始化客户端（LM Studio）
client = OpenAI(
    api_key="EMPTY",
    base_url="http://localhost:1234/v1"
)

def image_to_base64(image: Image.Image) -> str:
    """将 PIL Image 转换为 base64"""
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

# OCR Layout Prompt（推荐）
OCR_LAYOUT_PROMPT = """OCR this image to HTML, arranged as layout blocks. Each layout block should be a div with the data-bbox attribute representing the bounding box of the block in [x0, y0, x1, y1] format. Bboxes are normalized 0-1024. The data-label attribute is the label for the block.

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

def call_chandra_ocr(image: Image.Image) -> str:
    """调用 Chandra OCR 模型"""
    image_b64 = image_to_base64(image)
    
    response = client.chat.completions.create(
        model="chandra",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_b64}"}
                    },
                    {
                        "type": "text",
                        "text": OCR_LAYOUT_PROMPT
                    }
                ]
            }
        ],
        max_tokens=12384,
        temperature=0,
        top_p=0.1
    )
    
    return response.choices[0].message.content

# 使用示例
image = Image.open("document_page.png")
html_output = call_chandra_ocr(image)
print(html_output)
```

---

## 🔄 6. 完整的处理流程

### 6.1 端到端处理示例

```python
from PIL import Image
from bs4 import BeautifulSoup
import json

def process_pdf_page(image: Image.Image) -> dict:
    """
    完整的 PDF 页面处理流程
    
    Args:
        image: PDF 页面的 PIL Image 对象
    
    Returns:
        {
            "blocks": 结构化块列表,
            "markdown": Markdown 文本,
            "html": 清理后的 HTML,
            "raw_html": 原始 HTML
        }
    """
    # 1. 调用 OCR 模型
    raw_html = call_chandra_ocr(image)
    
    # 2. 解析布局块
    blocks = parse_layout(raw_html, image.width, image.height)
    
    # 3. 过滤页眉页脚（可选）
    blocks = [b for b in blocks if b.label not in ["Page-Header", "Page-Footer"]]
    
    # 4. 重建 HTML（不含 data-bbox 和 data-label）
    clean_html = "".join([block.content for block in blocks])
    
    # 5. 转换为 Markdown（简化版）
    markdown = html_to_simple_markdown(clean_html)
    
    # 6. 转换为字典格式
    blocks_dict = [
        {
            "bbox": block.bbox,
            "label": block.label,
            "content": block.content
        }
        for block in blocks
    ]
    
    return {
        "blocks": blocks_dict,
        "markdown": markdown,
        "html": clean_html,
        "raw_html": raw_html
    }

def html_to_simple_markdown(html: str) -> str:
    """简化的 HTML 转 Markdown"""
    from markdownify import markdownify
    return markdownify(html, heading_style="ATX")
```

---

## 📦 7. 输出为 JSON 格式

### 7.1 标准 JSON 结构

```python
def convert_to_json(blocks: List[LayoutBlock], image_width: int, image_height: int) -> dict:
    """
    将解析结果转换为标准 JSON 格式
    
    Returns:
        {
            "page_info": {...},
            "blocks": [...]
        }
    """
    return {
        "page_info": {
            "width": image_width,
            "height": image_height,
            "total_blocks": len(blocks)
        },
        "blocks": [
            {
                "id": idx,
                "type": block.label,
                "bbox": {
                    "x0": block.bbox[0],
                    "y0": block.bbox[1],
                    "x1": block.bbox[2],
                    "y1": block.bbox[3]
                },
                "content": {
                    "html": block.content,
                    "text": BeautifulSoup(block.content, "html.parser").get_text()
                }
            }
            for idx, block in enumerate(blocks)
        ]
    }
```

### 7.2 JSON 输出示例

```json
{
  "page_info": {
    "width": 2048,
    "height": 2896,
    "total_blocks": 5
  },
  "blocks": [
    {
      "id": 0,
      "type": "Section-Header",
      "bbox": {
        "x0": 130,
        "y0": 182,
        "x1": 1188,
        "y1": 234
      },
      "content": {
        "html": "<h2>Introduction</h2>",
        "text": "Introduction"
      }
    },
    {
      "id": 1,
      "type": "Text",
      "bbox": {
        "x0": 130,
        "y0": 440,
        "x1": 1748,
        "y1": 1100
      },
      "content": {
        "html": "<p>This is the main text content...</p>",
        "text": "This is the main text content..."
      }
    }
  ]
}
```

---

## ⚠️ 8. 注意事项和最佳实践

### 8.1 图像预处理建议

```python
def preprocess_image(image: Image.Image, min_dim: int = 1536) -> Image.Image:
    """
    预处理图像以获得最佳 OCR 效果
    
    Args:
        image: 原始图像
        min_dim: 最小尺寸（短边）
    
    Returns:
        处理后的图像
    """
    # 确保最小尺寸
    width, height = image.size
    min_side = min(width, height)
    
    if min_side < min_dim:
        scale = min_dim / min_side
        new_width = int(width * scale)
        new_height = int(height * scale)
        image = image.resize((new_width, new_height), Image.LANCZOS)
    
    # 转换为 RGB（如果是 RGBA 或其他格式）
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    return image
```

### 8.2 错误处理

```python
def safe_call_chandra_ocr(image: Image.Image, max_retries: int = 3) -> str:
    """
    带重试机制的 OCR 调用
    
    Args:
        image: 输入图像
        max_retries: 最大重试次数
    
    Returns:
        HTML 输出
    """
    import time
    
    for attempt in range(max_retries):
        try:
            return call_chandra_ocr(image)
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 指数退避
            else:
                raise
```

### 8.3 批量处理 PDF

```python
import fitz  # PyMuPDF

def process_pdf_document(pdf_path: str, output_dir: str):
    """
    批量处理 PDF 文档的所有页面
    
    Args:
        pdf_path: PDF 文件路径
        output_dir: 输出目录
    """
    doc = fitz.open(pdf_path)
    results = []
    
    for page_num in range(len(doc)):
        print(f"Processing page {page_num + 1}/{len(doc)}...")
        
        # 渲染页面为图像
        page = doc[page_num]
        pix = page.get_pixmap(dpi=192)
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        # 预处理
        image = preprocess_image(image)
        
        # OCR 处理
        result = process_pdf_page(image)
        results.append(result)
        
        # 保存结果
        output_file = f"{output_dir}/page_{page_num + 1}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    
    return results
```

---

## 🎨 9. 特殊功能处理

### 9.1 表格提取

```python
def extract_tables(blocks: List[LayoutBlock]) -> List[dict]:
    """提取所有表格块"""
    tables = []
    for idx, block in enumerate(blocks):
        if block.label == "Table":
            tables.append({
                "id": idx,
                "bbox": block.bbox,
                "html": block.content
            })
    return tables
```

### 9.2 数学公式提取

```python
def extract_math_equations(blocks: List[LayoutBlock]) -> List[dict]:
    """提取所有数学公式"""
    equations = []
    for idx, block in enumerate(blocks):
        if block.label == "Equation-Block":
            soup = BeautifulSoup(block.content, "html.parser")
            math_tags = soup.find_all("math")
            for math_tag in math_tags:
                equations.append({
                    "id": idx,
                    "bbox": block.bbox,
                    "latex": math_tag.get_text(),
                    "display": math_tag.get("display") == "block"
                })
    return equations
```

### 9.3 图像区域提取

```python
def extract_image_regions(blocks: List[LayoutBlock], source_image: Image.Image) -> dict:
    """提取图像和图表区域"""
    images = {}
    for idx, block in enumerate(blocks):
        if block.label in ["Image", "Figure"]:
            try:
                cropped = source_image.crop(block.bbox)
                images[f"image_{idx}.png"] = cropped
            except ValueError:
                continue
    return images
```

---

## 📚 10. 依赖项

### 10.1 Python 依赖

```bash
pip install openai pillow beautifulsoup4 markdownify pymupdf
```

### 10.2 requirements.txt

```
openai>=1.0.0
pillow>=10.0.0
beautifulsoup4>=4.12.0
markdownify>=0.11.0
pymupdf>=1.23.0
```

---

## 📂 11. 关键代码文件引用

### 11.1 需要参考的官方代码文件

开发时建议参考以下官方代码文件：

1. **`chandra/prompts.py`** - Prompt 定义
   - 包含官方的 `OCR_LAYOUT_PROMPT` 和 `OCR_PROMPT`
   - 定义了允许的 HTML 标签和属性

2. **`chandra/output.py`** - 输出解析逻辑
   - `parse_layout()` - 解析 HTML 为布局块
   - `parse_html()` - 清理 HTML
   - `parse_markdown()` - 转换为 Markdown
   - `extract_images()` - 提取图像区域

3. **`chandra/model/vllm.py`** - API 调用逻辑
   - `generate_vllm()` - OpenAI 兼容接口调用
   - `image_to_base64()` - 图像转 base64

4. **`chandra/model/schema.py`** - 数据结构定义
   - `BatchInputItem` - 输入数据结构
   - `BatchOutputItem` - 输出数据结构
   - `GenerationResult` - 生成结果

5. **`chandra/settings.py`** - 配置参数
   - `BBOX_SCALE` - 坐标归一化范围（1024）
   - `MAX_OUTPUT_TOKENS` - 最大输出令牌（12384）
   - `IMAGE_DPI` - 图像 DPI（192）

---

## 🚀 12. 完整集成示例

### 12.1 完整的集成代码

```python
"""
Chandra OCR 集成示例
用于 PDF 结构化提取系统
"""

import base64
import io
import json
from dataclasses import dataclass
from typing import List
from PIL import Image
from openai import OpenAI
from bs4 import BeautifulSoup

# ============ 配置 ============
LM_STUDIO_BASE_URL = "http://localhost:1234/v1"
BBOX_SCALE = 1024

# ============ 初始化客户端 ============
client = OpenAI(api_key="EMPTY", base_url=LM_STUDIO_BASE_URL)

# ============ Prompt 定义 ============
OCR_LAYOUT_PROMPT = """OCR this image to HTML, arranged as layout blocks. Each layout block should be a div with the data-bbox attribute representing the bounding box of the block in [x0, y0, x1, y1] format. Bboxes are normalized 0-1024. The data-label attribute is the label for the block.

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
* Formatting: Maintain consistent formatting with the image, including spacing, indentation, subscripts/superscores, and special characters.
* Images: Include a description of any images in the alt attribute of an <img> tag. Do not fill out the src property.
* Forms: Mark checkboxes and radio buttons properly.
* Text: join lines together properly into paragraphs using <p>...</p> tags. Use <br> tags for line breaks within paragraphs, but only when absolutely necessary to maintain meaning.
* Use the simplest possible HTML structure that accurately represents the content of the block.
* Make sure the text is accurate and easy for a human to read and interpret. Reading order should be correct and natural."""

# ============ 数据结构 ============
@dataclass
class LayoutBlock:
    bbox: List[int]
    label: str
    content: str

# ============ 核心函数 ============
def image_to_base64(image: Image.Image) -> str:
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

def call_chandra_ocr(image: Image.Image) -> str:
    image_b64 = image_to_base64(image)
    response = client.chat.completions.create(
        model="chandra",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                {"type": "text", "text": OCR_LAYOUT_PROMPT}
            ]
        }],
        max_tokens=12384,
        temperature=0,
        top_p=0.1
    )
    return response.choices[0].message.content

def parse_layout(html: str, image_width: int, image_height: int) -> List[LayoutBlock]:
    soup = BeautifulSoup(html, "html.parser")
    divs = soup.find_all("div", recursive=False)
    
    width_scaler = image_width / BBOX_SCALE
    height_scaler = image_height / BBOX_SCALE
    blocks = []
    
    for div in divs:
        bbox = div.get("data-bbox")
        try:
            bbox = json.loads(bbox)
        except:
            bbox = [0, 0, 1, 1]
        
        bbox = [
            max(0, int(bbox[0] * width_scaler)),
            max(0, int(bbox[1] * height_scaler)),
            min(int(bbox[2] * width_scaler), image_width),
            min(int(bbox[3] * height_scaler), image_height)
        ]
        
        blocks.append(LayoutBlock(
            bbox=bbox,
            label=div.get("data-label", "block"),
            content=str(div.decode_contents())
        ))
    
    return blocks

def process_page(image: Image.Image) -> dict:
    # 1. OCR
    raw_html = call_chandra_ocr(image)
    
    # 2. 解析
    blocks = parse_layout(raw_html, image.width, image.height)
    
    # 3. 过滤页眉页脚
    blocks = [b for b in blocks if b.label not in ["Page-Header", "Page-Footer"]]
    
    # 4. 转换为 JSON
    return {
        "page_info": {"width": image.width, "height": image.height},
        "blocks": [
            {
                "id": i,
                "type": b.label,
                "bbox": {"x0": b.bbox[0], "y0": b.bbox[1], "x1": b.bbox[2], "y1": b.bbox[3]},
                "content": {"html": b.content, "text": BeautifulSoup(b.content, "html.parser").get_text()}
            }
            for i, b in enumerate(blocks)
        ]
    }

# ============ 使用示例 ============
if __name__ == "__main__":
    image = Image.open("page.png")
    result = process_page(image)
    print(json.dumps(result, ensure_ascii=False, indent=2))
```

---

## 💡 13. 常见问题和解决方案

### 13.1 坐标不准确

**问题**: 解析出的坐标与实际位置不符

**解决方案**:
- 确认 `bbox_scale` 参数为 1024
- 检查图像尺寸是否正确传递
- 验证坐标转换公式

### 13.2 表格识别不完整

**问题**: 复杂表格的 `colspan` 和 `rowspan` 不准确

**解决方案**:
- 提高图像分辨率（推荐 DPI 192+）
- 确保表格边界清晰
- 可能需要后处理修正

### 13.3 数学公式格式问题

**问题**: 公式中的 LaTeX 语法不正确

**解决方案**:
- 使用 KaTeX 或 MathJax 渲染前验证语法
- 对于复杂公式，可能需要人工校对

### 13.4 LM Studio 连接失败

**问题**: 无法连接到 LM Studio API

**解决方案**:
```python
# 检查 LM Studio 是否运行
import requests
try:
    response = requests.get("http://localhost:1234/v1/models")
    print("LM Studio is running:", response.json())
except:
    print("LM Studio is not running or not accessible")
```

---

## 📋 14. 总结

### 14.1 核心要点

1. **Prompt 使用**: 强烈推荐使用 `ocr_layout` prompt 获取完整的布局和坐标信息

2. **坐标处理**: 
   - 模型输出的坐标归一化到 0-1024
   - 需要根据实际图像尺寸转换为像素坐标

3. **输出格式**:
   - 原始输出: 带 `data-bbox` 和 `data-label` 的 HTML
   - 可转换为: JSON、Markdown、纯文本

4. **特殊功能**:
   - ✅ 表格识别（支持 colspan/rowspan）
   - ✅ 数学公式（KaTeX 兼容 LaTeX）
   - ✅ 版面分析（15 种布局标签）
   - ✅ 手写识别
   - ✅ 多语言支持（40+）

### 14.2 推荐工作流程

```
PDF 文件
  ↓
渲染为图像 (DPI 192+)
  ↓
预处理 (最小尺寸 1536px)
  ↓
调用 Chandra OCR (LM Studio)
  ↓
解析 HTML (BeautifulSoup)
  ↓
提取布局块 (bbox + label + content)
  ↓
转换坐标 (归一化 → 像素)
  ↓
输出 JSON/Markdown
```

### 14.3 性能优化建议

1. **批量处理**: 使用多线程/多进程处理多页 PDF
2. **缓存结果**: 避免重复处理相同页面
3. **图像优化**: 适当压缩图像以加快传输
4. **错误重试**: 实现指数退避重试机制

---

## 📚 15. 参考资源

### 15.1 官方资源

- **GitHub 仓库**: https://github.com/datalab-to/chandra
- **HuggingFace 模型**: https://huggingface.co/datalab-to/chandra
- **官方 API**: https://www.datalab.to/
- **在线演示**: https://www.datalab.to/playground

### 15.2 相关文档

- **Qwen3-VL**: https://github.com/QwenLM/Qwen3
- **OpenAI API 规范**: https://platform.openai.com/docs/api-reference
- **LM Studio**: https://lmstudio.ai/

### 15.3 技术支持

- **Discord 社区**: https://discord.gg/KuZwXNGnfH
- **GitHub Issues**: https://github.com/datalab-to/chandra/issues

---

## 📝 16. 附录：完整的 Prompt 模板

### 16.1 OCR Layout Prompt（完整版）

```python
OCR_LAYOUT_PROMPT = """OCR this image to HTML, arranged as layout blocks. Each layout block should be a div with the data-bbox attribute representing the bounding box of the block in [x0, y0, x1, y1] format. Bboxes are normalized 0-1024. The data-label attribute is the label for the block.

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

## 🎯 文档结束

**版本**: 1.0  
**更新日期**: 2026-02-05  
**适用模型**: Chandra OCR (datalab-to/chandra)  
**部署方式**: LM Studio (OpenAI 兼容接口)

如有问题，请参考官方文档或联系技术支持。

