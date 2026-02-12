# Chandra-OCR 最佳集成方案（基于官方特性）

## 🔍 关键发现

根据 Chandra 官方介绍：

> **Layout-aware output**: Every text block, table, and image comes with bounding box coordinates
> **Structured formats**: Output as Markdown, HTML, or JSON with full layout metadata

**重要结论**：Chandra 不仅是 OCR 工具，它本身就具备版面识别能力！

---

## 🎯 最佳方案：独立的 Chandra Direct 模式

### 为什么选择这个方案？

1. **Chandra 已经是完整的解决方案**
   - ✅ 版面识别（Layout-aware）
   - ✅ 文字识别（OCR）
   - ✅ 结构化输出（Markdown/HTML/JSON）
   - ✅ 坐标信息（Bounding boxes）

2. **不需要 Surya Layout**
   - Chandra 自己就能识别布局
   - 对于复杂/老旧文献，Chandra 比 Surya 更准确

3. **架构最简单**
   - 不需要 Pipeline 的复杂流程
   - 直接：图片 → Chandra → Markdown/JSON

---

## 📐 推荐架构

```
┌─────────────────────────────────────────────┐
│ 用户选择转换模式                              │
├─────────────────────────────────────────────┤
│                                             │
│ 1. Pipeline 模式（现有）                     │
│    ├─ Surya Layout + Surya OCR             │
│    ├─ VLM Layout + VLM OCR                 │
│    └─ YOLO Layout + Calamari OCR           │
│                                             │
│ 2. VLM Direct 模式（现有）                   │
│    ├─ Gemini Direct                        │
│    ├─ Claude Direct                        │
│    └─ Qwen Direct                          │
│                                             │
│ 3. Chandra Direct 模式（新增）← 推荐！        │
│    └─ Chandra (Layout + OCR 一体化)        │
│                                             │
└─────────────────────────────────────────────┘
```

### 定位对比

| 模式 | 适用场景 | 优势 |
|------|---------|------|
| **Pipeline** | 现代文档、标准排版 | 可定制、可后处理 |
| **VLM Direct** | 需要 LLM 理解的文档 | 智能分析、格式灵活 |
| **Chandra Direct** | 复杂/手写/老旧文献 | 专业 OCR、高准确度 |

---

## 🔧 实现方案

### 文件结构

```
marker/
├── converters/
│   └── chandra_direct.py          ← 新增（核心转换器）
├── services/
│   └── chandra.py                 ← 新增（API 调用）
├── builders/
│   └── chandra_parser.py          ← 新增（解析 Chandra 输出）
└── scripts/
    └── streamlit_app.py           ← 修改（添加 UI 选项）
```

### 核心代码结构

#### 1. Chandra Service

```python
# marker/services/chandra.py
"""
Chandra OCR Service

支持两种模式：
1. 本地 HuggingFace Transformers
2. vLLM 服务器（LM Studio）
"""

from typing import Dict, Any, Literal
from PIL import Image
import requests
import base64
from io import BytesIO


class ChandraService:
    """Chandra OCR 服务"""

    def __init__(
        self,
        mode: Literal["local", "server"] = "server",
        endpoint: str = None,
        api_key: str = None,
        output_format: Literal["markdown", "html", "json"] = "json"
    ):
        self.mode = mode
        self.endpoint = endpoint or "http://localhost:1234/v1/chat/completions"
        self.api_key = api_key
        self.output_format = output_format

    def process_page(
        self,
        image: Image.Image,
        **kwargs
    ) -> Dict[str, Any]:
        """
        处理单页图片

        Returns:
            {
                "content": "...",  # Markdown/HTML 内容
                "blocks": [...],   # 块信息（带坐标）
                "metadata": {...}  # 元数据
            }
        """
        if self.mode == "server":
            return self._process_via_server(image, **kwargs)
        else:
            return self._process_local(image, **kwargs)

    def _process_via_server(
        self,
        image: Image.Image,
        **kwargs
    ) -> Dict[str, Any]:
        """通过 vLLM 服务器处理（LM Studio）"""

        # 将图片转为 base64
        buffered = BytesIO()
        image.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode()

        # 构建请求
        payload = {
            "model": "chandra-ocr",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{img_base64}"
                            }
                        },
                        {
                            "type": "text",
                            "text": f"Extract all text and structure from this image. Output as {self.output_format} with bounding boxes."
                        }
                    ]
                }
            ],
            "max_tokens": 4096,
            "temperature": 0.1
        }

        headers = {
            "Content-Type": "application/json"
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # 调用 API
        response = requests.post(
            self.endpoint,
            json=payload,
            headers=headers
        )
        response.raise_for_status()

        result = response.json()
        content = result["choices"][0]["message"]["content"]

        # 解析输出
        return self._parse_output(content)

    def _process_local(
        self,
        image: Image.Image,
        **kwargs
    ) -> Dict[str, Any]:
        """本地 HuggingFace Transformers 处理"""
        # TODO: 实现本地推理
        raise NotImplementedError("Local mode not implemented yet")

    def _parse_output(self, content: str) -> Dict[str, Any]:
        """解析 Chandra 输出"""
        if self.output_format == "json":
            import json
            return json.loads(content)
        else:
            # Markdown/HTML 格式
            return {
                "content": content,
                "blocks": [],
                "metadata": {}
            }
```

---

#### 2. Chandra Parser

```python
# marker/builders/chandra_parser.py
"""
Chandra Output Parser

将 Chandra 的输出转换为 Marker 的 Document 结构
"""

from typing import Dict, Any, List
from marker.schema.document import Document
from marker.schema.groups.page import PageGroup
from marker.schema.blocks import Block
from marker.schema import BlockTypes
from marker.schema.polygon import PolygonBox
from bs4 import BeautifulSoup


class ChandraParser:
    """解析 Chandra 输出"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def parse_to_document(
        self,
        chandra_output: Dict[str, Any],
        page_num: int,
        page_size: tuple
    ) -> PageGroup:
        """
        将 Chandra 输出转换为 PageGroup

        Args:
            chandra_output: Chandra 的输出
            page_num: 页码
            page_size: 页面尺寸 (width, height)

        Returns:
            PageGroup 对象
        """

        # 根据输出格式选择解析方法
        if "blocks" in chandra_output:
            # JSON 格式（带坐标）
            return self._parse_json_format(chandra_output, page_num, page_size)
        elif "content" in chandra_output:
            # Markdown/HTML 格式
            return self._parse_text_format(chandra_output, page_num, page_size)
        else:
            raise ValueError("Unknown Chandra output format")

    def _parse_json_format(
        self,
        output: Dict[str, Any],
        page_num: int,
        page_size: tuple
    ) -> PageGroup:
        """解析 JSON 格式（带坐标）"""

        page = PageGroup(
            page_id=page_num,
            polygon=PolygonBox.from_bbox((0, 0, page_size[0], page_size[1])),
            children=[]
        )

        # 解析每个块
        for block_data in output.get("blocks", []):
            block = self._create_block_from_json(block_data, page_num)
            if block:
                page.add_child(block)

        return page

    def _create_block_from_json(
        self,
        block_data: Dict[str, Any],
        page_num: int
    ) -> Block:
        """从 JSON 数据创建 Block"""

        # 提取坐标
        bbox = block_data.get("bbox", [0, 0, 100, 100])
        polygon = PolygonBox.from_bbox(bbox)

        # 提取块类型
        block_type = self._map_chandra_type_to_marker(
            block_data.get("type", "text")
        )

        # 提取文本
        text = block_data.get("text", "")

        # 创建 Block
        block = Block(
            polygon=polygon,
            block_type=block_type,
            page_id=page_num,
            text_extraction_method="chandra"
        )

        # TODO: 创建 Line 和 Span 结构

        return block

    def _map_chandra_type_to_marker(self, chandra_type: str) -> BlockTypes:
        """映射 Chandra 的块类型到 Marker 的 BlockTypes"""
        mapping = {
            "text": BlockTypes.Text,
            "title": BlockTypes.SectionHeader,
            "table": BlockTypes.Table,
            "figure": BlockTypes.Figure,
            "equation": BlockTypes.Equation,
            "form": BlockTypes.Form,
            # ... 更多映射
        }
        return mapping.get(chandra_type, BlockTypes.Text)

    def _parse_text_format(
        self,
        output: Dict[str, Any],
        page_num: int,
        page_size: tuple
    ) -> PageGroup:
        """解析 Markdown/HTML 格式"""

        content = output.get("content", "")

        # 如果是 HTML，解析标签
        if "<" in content and ">" in content:
            return self._parse_html(content, page_num, page_size)
        else:
            # Markdown 格式，简单处理
            return self._parse_markdown(content, page_num, page_size)

    def _parse_html(
        self,
        html_content: str,
        page_num: int,
        page_size: tuple
    ) -> PageGroup:
        """解析 HTML 内容"""

        soup = BeautifulSoup(html_content, 'html.parser')

        page = PageGroup(
            page_id=page_num,
            polygon=PolygonBox.from_bbox((0, 0, page_size[0], page_size[1])),
            children=[]
        )

        # 解析 HTML 标签
        for element in soup.find_all(['div', 'p', 'h1', 'h2', 'h3', 'table']):
            block = self._create_block_from_html(element, page_num)
            if block:
                page.add_child(block)

        return page

    def _create_block_from_html(
        self,
        element,
        page_num: int
    ) -> Block:
        """从 HTML 元素创建 Block"""

        # 提取 data-bbox 属性
        bbox_str = element.get('data-bbox', '[0,0,100,100]')
        bbox = eval(bbox_str)  # 注意：生产环境应该用 json.loads
        polygon = PolygonBox.from_bbox(bbox)

        # 提取 data-label 属性
        label = element.get('data-label', 'Text')
        block_type = self._map_chandra_type_to_marker(label.lower())

        # 提取文本
        text = element.get_text()

        # 创建 Block
        block = Block(
            polygon=polygon,
            block_type=block_type,
            page_id=page_num,
            text_extraction_method="chandra"
        )

        return block
```

---

---

#### 3. Chandra Direct Converter

```python
# marker/converters/chandra_direct.py
"""
Chandra Direct Converter

直接使用 Chandra 处理整个文档
"""

from typing import List
from pathlib import Path
from PIL import Image
import fitz  # PyMuPDF

from marker.converters import BaseConverter
from marker.schema.document import Document
from marker.services.chandra import ChandraService
from marker.builders.chandra_parser import ChandraParser


class ChandraDirectConverter(BaseConverter):
    """
    Chandra Direct 转换器

    特点：
    - 不需要 Layout Backend
    - 不需要 OCR Backend
    - Chandra 一步完成版面识别和文字识别
    """

    def __init__(self, config):
        super().__init__(config)

        # 初始化 Chandra 服务
        self.chandra_service = ChandraService(
            mode=config.get("chandra_mode", "server"),
            endpoint=config.get("chandra_endpoint"),
            api_key=config.get("chandra_api_key"),
            output_format=config.get("chandra_output_format", "json")
        )

        # 初始化解析器
        self.parser = ChandraParser(config)

    def __call__(self, filepath: str) -> Document:
        """
        转换文档

        流程：
        1. 加载 PDF/图片
        2. 对每页调用 Chandra
        3. 解析输出
        4. 构建 Document
        """

        # 1. 加载文档
        pages_images = self._load_document(filepath)

        # 2. 创建 Document
        document = Document(
            filepath=filepath,
            pages=[]
        )

        # 3. 处理每一页
        for page_num, page_image in enumerate(pages_images):
            print(f"Processing page {page_num + 1}/{len(pages_images)}...")

            # 调用 Chandra
            chandra_output = self.chandra_service.process_page(page_image)

            # 解析输出
            page_group = self.parser.parse_to_document(
                chandra_output,
                page_num=page_num,
                page_size=page_image.size
            )

            document.pages.append(page_group)

        return document

    def _load_document(self, filepath: str) -> List[Image.Image]:
        """加载文档为图片列表"""

        filepath = Path(filepath)

        if filepath.suffix.lower() == '.pdf':
            return self._load_pdf(filepath)
        else:
            # 单张图片
            return [Image.open(filepath)]

    def _load_pdf(self, pdf_path: Path) -> List[Image.Image]:
        """加载 PDF 为图片列表"""

        doc = fitz.open(pdf_path)
        images = []

        for page_num in range(len(doc)):
            page = doc[page_num]

            # 渲染为图片（高分辨率）
            mat = fitz.Matrix(2.0, 2.0)  # 2x zoom
            pix = page.get_pixmap(matrix=mat)

            # 转为 PIL Image
            img = Image.frombytes(
                "RGB",
                [pix.width, pix.height],
                pix.samples
            )
            images.append(img)

        doc.close()
        return images
```

---

#### 4. Streamlit UI 集成

```python
# marker/scripts/streamlit_app.py（修改部分）

# 在转换模式选择部分添加
conversion_mode = st.radio(
    "选择转换模式",
    options=["pipeline", "vlm_direct", "chandra_direct"],  # 新增
    format_func=lambda x: {
        "pipeline": "🔄 Pipeline (传统模式)",
        "vlm_direct": "🤖 VLM Direct (视觉语言模型)",
        "chandra_direct": "📚 Chandra Direct (专业 OCR)"  # 新增
    }[x],
    index=0
)

# ... 现有的 pipeline 和 vlm_direct 配置 ...

# 🆕 Chandra Direct 配置
if conversion_mode == "chandra_direct":
    st.markdown("### 📚 Chandra Direct 配置")

    st.info("""
    **Chandra 专门处理**：
    - ✅ 手写文档（医生笔记、表单、作业）
    - ✅ 复杂表格（合并单元格、财务报表）
    - ✅ 数学公式（LaTeX 格式）
    - ✅ 表单（复选框、单选按钮）
    - ✅ 复杂布局（多栏、报纸、教科书）
    """)

    # Chandra 模式选择
    chandra_mode = st.radio(
        "运行模式",
        options=["server", "local"],
        format_func=lambda x: {
            "server": "🌐 服务器模式（LM Studio / vLLM）",
            "local": "💻 本地模式（HuggingFace Transformers）"
        }[x],
        index=0,
        help="服务器模式性能更高（50-100 tokens/s）"
    )

    if chandra_mode == "server":
        # 服务器配置
        chandra_endpoint = st.text_input(
            "API Endpoint",
            value="http://localhost:1234/v1/chat/completions",
            help="LM Studio 或 vLLM 服务器地址"
        )

        chandra_api_key = st.text_input(
            "API Key（可选）",
            type="password",
            help="如果服务器需要认证"
        )
    else:
        # 本地模式配置
        st.warning("本地模式需要安装 transformers 和足够的 GPU 内存")

    # 输出格式
    chandra_output_format = st.selectbox(
        "输出格式",
        options=["json", "markdown", "html"],
        format_func=lambda x: {
            "json": "JSON（带坐标，推荐）",
            "markdown": "Markdown（纯文本）",
            "html": "HTML（带格式）"
        }[x],
        index=0,
        help="JSON 格式包含完整的布局元数据"
    )

    # 高级选项
    with st.expander("⚙️ 高级选项", expanded=False):
        chandra_max_tokens = st.number_input(
            "最大 Tokens",
            min_value=1024,
            max_value=8192,
            value=4096,
            step=512
        )

        chandra_temperature = st.slider(
            "Temperature",
            min_value=0.0,
            max_value=1.0,
            value=0.1,
            step=0.1,
            help="较低的值产生更确定的输出"
        )

    # 更新 config_params
    config_params.update({
        "chandra_mode": chandra_mode,
        "chandra_endpoint": chandra_endpoint if chandra_mode == "server" else None,
        "chandra_api_key": chandra_api_key if chandra_mode == "server" else None,
        "chandra_output_format": chandra_output_format,
        "chandra_max_tokens": chandra_max_tokens,
        "chandra_temperature": chandra_temperature,
    })
```

---

## 🎨 使用流程

### 场景 1: 手写文档

**配置**：
1. 选择 "📚 Chandra Direct"
2. 运行模式：服务器模式
3. 输出格式：JSON（带坐标）

**效果**：
- ✅ 准确识别手写文字
- ✅ 保留布局结构
- ✅ 输出坐标信息

---

### 场景 2: 复杂表格

**配置**：
1. 选择 "📚 Chandra Direct"
2. 输出格式：HTML（保留表格结构）

**效果**：
- ✅ 识别合并单元格
- ✅ 保留表格格式
- ✅ 输出为 HTML 表格

---

### 场景 3: 数学公式

**配置**：
1. 选择 "📚 Chandra Direct"
2. 输出格式：Markdown（LaTeX 公式）

**效果**：
- ✅ 公式转为 LaTeX
- ✅ 行内和块级公式都支持
- ✅ 可直接在 Markdown 中渲染

---

## 📊 与其他模式对比

| 特性 | Pipeline | VLM Direct | Chandra Direct |
|------|---------|-----------|----------------|
| **版面识别** | Surya/VLM/YOLO | VLM | Chandra |
| **文字识别** | Surya/VLM/Calamari | VLM | Chandra |
| **手写识别** | ⚠️ 一般 | ⚠️ 一般 | ✅ 优秀 |
| **表格识别** | ✅ 好 | ✅ 好 | ✅ 优秀 |
| **数学公式** | ⚠️ 需要 LLM | ✅ 好 | ✅ 优秀 |
| **复杂布局** | ✅ 好 | ✅ 好 | ✅ 优秀 |
| **坐标信息** | ✅ 有 | ❌ 无 | ✅ 有 |
| **后处理** | ✅ 可用 Processors | ❌ 不可用 | ⚠️ 可选 |
| **本地部署** | ✅ 是 | ⚠️ 部分 | ✅ 是 |
| **速度** | 快 | 中等 | 快（50-100 t/s）|

---

## ✅ 实现优先级

### Phase 1: 核心功能（必需）

1. ✅ `ChandraService` - API 调用
2. ✅ `ChandraDirectConverter` - 转换器
3. ✅ `ChandraParser` - 输出解析
4. ✅ Streamlit UI - 配置界面

### Phase 2: 格式支持（重要）

1. ✅ JSON 格式解析（带坐标）
2. ✅ HTML 格式解析（带标签）
3. ✅ Markdown 格式解析

### Phase 3: 高级功能（可选）

1. ⚪ 本地 HuggingFace 模式
2. ⚪ 批量处理优化
3. ⚪ 与 Processors 集成
4. ⚪ 缓存机制

---

## 🚀 下一步行动

1. **确认方案**：你同意这个方案吗？
2. **测试 API**：
   - 在 LM Studio 中部署 Chandra
   - 测试 API 调用
   - 查看实际输出格式
3. **开始实现**：从 `ChandraService` 开始

**需要你提供**：
- LM Studio 中 Chandra 的实际 API 响应格式
- 一个测试图片的完整输出示例

准备好后我就开始实现！
