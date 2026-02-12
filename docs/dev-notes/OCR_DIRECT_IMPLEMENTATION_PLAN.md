# OCR Direct 模式完整实现方案

## 📋 目标

创建一个独立的 OCR Direct 转换模式,完全吸收现有成功的工程实践:

- ✅ 并发处理 (asyncio.Semaphore)
- ✅ 批处理与休息间隔
- ✅ API 密钥池管理
- ✅ 图像预处理
- ✅ 重试机制
- ✅ 所有输出格式 (HTML/Markdown/JSON/Chunk)
- ✅ 页码锚点系统
- ✅ 有序并发执行

---

## 🏗️ 架构设计

### 核心组件

```
OCR Direct Mode
├── Converter (ocr_direct_async.py)
│   ├── 并发控制 (asyncio.Semaphore)
│   ├── 批处理逻辑
│   ├── 图像预处理
│   └── API 调用管理
├── Service (services/ocr_chandra.py)
│   ├── API 通信
│   ├── 重试机制
│   └── 响应解析
├── Parser (builders/ocr_parser.py)
│   ├── JSON 解析
│   ├── Block 构建
│   └── 坐标转换
└── Renderer Integration
    ├── HTMLRenderer
    ├── MarkdownRenderer (with page anchors)
    ├── JSONRenderer
    └── ChunkRenderer
```

---

## 📦 实现文件清单

### 1. 核心转换器
**文件**: `marker/converters/ocr_direct_async.py`
- 异步并发处理
- 批处理与休息间隔
- 图像预处理管道
- 页码锚点集成

### 2. OCR 服务
**文件**: `marker/services/ocr_chandra.py`
- Chandra API 封装
- 重试机制 (指数退避)
- 响应格式处理

### 3. 输出解析器
**文件**: `marker/builders/ocr_parser.py`
- JSON 输出解析
- Block/Line/Span 构建
- 坐标转换 (bbox → PolygonBox)

### 4. 配置扩展
**文件**: `marker/config/parser.py` (修改)
- 添加 OCR Direct 配置项

### 5. UI 集成
**文件**: `marker/scripts/streamlit_app.py` (修改)
- 添加 OCR Direct 选项
- 配置界面

---

## 🔧 详细设计

### 设计 1: 核心转换器架构

参考: `marker/converters/vlm_direct_async.py`

**关键特性**:
1. **并发控制**: `asyncio.Semaphore(max_concurrent)`
2. **批处理**: 分批处理页面,批次间休息
3. **图像预处理**: resize → format conversion → base64
4. **API 密钥管理**: `APIKeyPool` 轮询分配
5. **重试机制**: 指数退避重试
6. **页码锚点**: `PageAnchorPlugin` 集成
7. **有序执行**: `OrderedConcurrentExecutor`

**核心方法**:
```python
class OcrDirectAsyncConverter(BaseConverter):
    def __init__(self, config):
        # 并发控制
        self.max_concurrent = config.ocr_concurrency
        self.batch_size = config.ocr_batch_size
        self.batch_rest_interval = config.ocr_batch_rest

        # API 管理
        self.api_key_pool = APIKeyPool(config.ocr_api_keys)

        # 服务
        self.ocr_service = OcrChandraService(config)

        # 页码锚点
        self.page_anchor_plugin = PageAnchorPlugin(config)
        self.printed_page_extractor = PrintedPageExtractor()

    async def __call__(self, filepath: str) -> Document:
        # 1. 加载图片
        pages_images = self._load_document(filepath)

        # 2. 批处理
        all_pages = []
        for batch_idx in range(0, len(pages_images), self.batch_size):
            batch = pages_images[batch_idx:batch_idx + self.batch_size]

            # 3. 并发处理批次
            batch_results = await self._process_batch_async(batch, batch_idx)
            all_pages.extend(batch_results)

            # 4. 批次间休息
            if batch_idx + self.batch_size < len(pages_images):
                await asyncio.sleep(self.batch_rest_interval)

        # 5. 构建 Document
        document = self._build_document(filepath, all_pages)

        # 6. 页码锚点处理
        document = self.page_anchor_plugin.process_pages(document)

        return document

    async def _process_batch_async(self, batch, batch_start_idx):
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async with aiohttp.ClientSession() as session:
            tasks = []
            for idx, img in enumerate(batch):
                page_num = batch_start_idx + idx
                task = self._convert_page_async(session, img, page_num, semaphore)
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

        return results

    async def _convert_page_async(self, session, img, page_num, semaphore):
        async with semaphore:
            # 1. 图像预处理
            processed_img = self._preprocess_image(img)
            img_base64 = self._img_to_base64(processed_img)

            # 2. 获取 API 密钥
            api_key = self.api_key_pool.get_key()

            # 3. 调用 OCR (带重试)
            for attempt in range(self.max_retries):
                try:
                    result = await self.ocr_service.process_page_async(
                        session, img_base64, api_key
                    )
                    return result
                except Exception as e:
                    if attempt < self.max_retries - 1:
                        wait_time = 2 * (attempt + 1)
                        await asyncio.sleep(wait_time)
                    else:
                        raise
```

---

### 设计 2: OCR 服务

参考: `marker/services/gemini.py`, `marker/services/claude.py`

**关键特性**:
1. **API 封装**: 统一的调用接口
2. **重试机制**: 指数退避
3. **响应解析**: JSON/HTML/Markdown
4. **错误处理**: 详细的错误信息

**核心方法**:
```python
class OcrChandraService:
    def __init__(self, config):
        self.endpoint = config.ocr_endpoint
        self.model = config.ocr_model
        self.output_format = config.ocr_output_format
        self.max_tokens = config.ocr_max_tokens
        self.temperature = config.ocr_temperature

    async def process_page_async(self, session, img_base64, api_key):
        """异步处理单页"""

        # 1. 构建 prompt
        prompt = self._build_prompt()

        # 2. 构建请求
        payload = {
            "model": self.model,
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
                            "text": prompt
                        }
                    ]
                }
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        }

        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # 3. 发送请求
        async with session.post(
            self.endpoint,
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=120)
        ) as response:
            response.raise_for_status()
            result = await response.json()

        # 4. 提取内容
        content = result["choices"][0]["message"]["content"]

        # 5. 解析响应
        return self._parse_response(content)

    def _build_prompt(self):
        """构建 OCR prompt"""
        if self.output_format == "json":
            return """Extract all text from this image and output as JSON with this structure:
{
  "blocks": [
    {
      "text": "extracted text",
      "bbox": [x1, y1, x2, y2],
      "type": "text|title|table|figure|equation|page_header|page_footer"
    }
  ]
}

Include bbox coordinates for every block.
Identify block types accurately."""

        elif self.output_format == "html":
            return """Extract all text and output as HTML with data-bbox attributes:
<div data-bbox="x1,y1,x2,y2" data-type="text">content</div>"""

        else:  # markdown
            return "Extract all text and output as clean Markdown."

    def _parse_response(self, content):
        """解析响应内容"""
        if self.output_format == "json":
            return json.loads(content)
        else:
            return content
```

---

### 设计 3: 输出解析器

参考: `marker/builders/document.py`, `marker/builders/layout.py`

**关键特性**:
1. **JSON 解析**: 提取 blocks 数组
2. **Block 构建**: 创建 Text/Table/Figure 等 Block
3. **坐标转换**: bbox → PolygonBox
4. **类型映射**: OCR type → BlockTypes

**核心方法**:
```python
class OcrParser:
    def __init__(self, config):
        self.config = config

    def parse_to_document(self, ocr_output, page_num, page_size):
        """将 OCR 输出解析为 Page"""

        if isinstance(ocr_output, dict):
            # JSON 格式
            return self._parse_json(ocr_output, page_num, page_size)
        else:
            # HTML/Markdown 格式
            return self._parse_text(ocr_output, page_num, page_size)

    def _parse_json(self, data, page_num, page_size):
        """解析 JSON 输出"""

        blocks = []

        for block_data in data.get("blocks", []):
            # 1. 提取数据
            text = block_data.get("text", "")
            bbox = block_data.get("bbox", [])
            block_type = block_data.get("type", "text")

            # 2. 创建 PolygonBox
            polygon = self._bbox_to_polygon(bbox, page_size)

            # 3. 创建 Block
            block = self._create_block(text, polygon, block_type, page_num)

            blocks.append(block)

        # 4. 创建 Page
        page = Page(
            page_id=page_num,
            polygon=PolygonBox.from_bbox([0, 0, page_size[0], page_size[1]]),
            structure=blocks
        )

        return page

    def _bbox_to_polygon(self, bbox, page_size):
        """bbox 转 PolygonBox"""
        if len(bbox) != 4:
            return PolygonBox.from_bbox([0, 0, 100, 100])

        x1, y1, x2, y2 = bbox
        return PolygonBox.from_bbox([x1, y1, x2, y2])

    def _create_block(self, text, polygon, block_type, page_num):
        """创建 Block 对象"""

        # 类型映射
        type_map = {
            "text": BlockTypes.Text,
            "title": BlockTypes.SectionHeader,
            "table": BlockTypes.Table,
            "figure": BlockTypes.Figure,
            "equation": BlockTypes.Equation,
            "page_header": BlockTypes.PageHeader,
            "page_footer": BlockTypes.PageFooter,
        }

        block_cls = type_map.get(block_type, BlockTypes.Text)

        # 创建 Block
        block = block_cls(
            polygon=polygon,
            structure=[
                Line(
                    polygon=polygon,
                    structure=[
                        Span(
                            text=text,
                            polygon=polygon
                        )
                    ]
                )
            ]
        )

        return block
```

---

## 📊 配置参数设计

参考: `marker/config/parser.py`

### 新增配置项

```python
# OCR Direct 模式配置
ocr_mode: str = "chandra"  # OCR 引擎: chandra, tesseract, etc.
ocr_endpoint: str = "http://localhost:1234/v1/chat/completions"
ocr_model: str = "chandra"
ocr_api_keys: List[str] = []  # 支持多个 API 密钥

# 输出格式
ocr_output_format: str = "json"  # json, html, markdown

# 并发控制
ocr_concurrency: int = 5  # 最大并发数
ocr_batch_size: int = 10  # 批次大小
ocr_batch_rest: float = 2.0  # 批次间休息时间(秒)

# 重试机制
ocr_max_retries: int = 3
ocr_retry_delay: float = 2.0

# API 参数
ocr_max_tokens: int = 4096
ocr_temperature: float = 0.1

# 图像预处理
ocr_resize_max: int = 2048  # 最大尺寸
ocr_image_format: str = "PNG"  # PNG, JPEG
ocr_image_quality: int = 95  # JPEG 质量

# 页码锚点
ocr_page_anchor_enabled: bool = True
ocr_page_anchor_format: str = "{n}"
```

---

## 🎨 Renderer 集成

### 1. Markdown Renderer

参考: `marker/renderers/markdown.py:80-106`

**集成点**: `convert_div` 方法

```python
def convert_div(self, document: Document, page: Page, page_id: int, printed_page_id: Optional[int] = None):
    # 1. 渲染页面内容
    page_html = page.render(document, self.config)

    # 2. 添加页码锚点
    if self.config.ocr_page_anchor_enabled:
        page_anchor = self.page_anchor_formatter.format(page_id, printed_page_id)
        page_tag = f"<!-- Page: {printed_page_id} -->\n" if printed_page_id else ""
        pagination_item = f"\n\n{page_anchor}\n{self.page_separator}\n{page_tag}\n"
    else:
        pagination_item = f"\n\n{self.page_separator}\n"

    # 3. 转换为 Markdown
    markdown = self.html_to_markdown(page_html)

    return pagination_item + markdown
```

### 2. JSON Renderer

参考: `marker/renderers/json.py`

**无需修改**: 自动支持,因为 OCR Direct 输出标准 Block 结构

### 3. Chunk Renderer

参考: `marker/renderers/chunk.py`

**无需修改**: 自动支持

---

## 🔄 图像预处理管道

参考: `marker/converters/vlm_direct_async.py:_resize_if_needed`, `_img_to_base64`

```python
def _preprocess_image(self, img: Image.Image) -> Image.Image:
    """图像预处理管道"""

    # 1. 调整大小
    img = self._resize_if_needed(img)

    # 2. 颜色空间转换
    if img.mode != "RGB":
        img = img.convert("RGB")

    return img

def _resize_if_needed(self, img: Image.Image) -> Image.Image:
    """调整图像大小"""
    max_size = self.config.ocr_resize_max

    if max(img.size) > max_size:
        ratio = max_size / max(img.size)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)

    return img

def _img_to_base64(self, img: Image.Image) -> str:
    """图像转 base64"""
    buffered = BytesIO()

    img_format = self.config.ocr_image_format
    if img_format == "JPEG":
        img.save(buffered, format="JPEG", quality=self.config.ocr_image_quality)
    else:
        img.save(buffered, format="PNG")

    return base64.b64encode(buffered.getvalue()).decode()
```

---

## 📝 页码锚点集成

参考: `marker/formatters.py`, `marker/converters/vlm_direct_async.py:444-460`

### 1. 页码提取

```python
# 在 _process_batch_async 后
printed_pages = self.printed_page_extractor.extract_batch(
    [page.render(document, self.config) for page in all_pages]
)
```

### 2. 页码锚点插入

```python
# 在 Markdown Renderer 中
document = self.page_anchor_plugin.process_pages(document)
```

---

## 🚀 实现优先级

### Phase 1: 核心功能 (必需)

1. ✅ `OcrChandraService` - API 调用封装
2. ✅ `OcrParser` - JSON 输出解析
3. ✅ `OcrDirectAsyncConverter` - 异步转换器
4. ✅ 配置参数扩展

### Phase 2: 工程实践 (重要)

1. ✅ 并发控制 (asyncio.Semaphore)
2. ✅ 批处理与休息间隔
3. ✅ API 密钥池管理
4. ✅ 重试机制
5. ✅ 图像预处理

### Phase 3: 输出集成 (重要)

1. ✅ Markdown Renderer 集成
2. ✅ 页码锚点系统
3. ✅ JSON/Chunk Renderer (自动支持)

### Phase 4: UI 集成 (可选)

1. ⚪ Streamlit UI 配置界面
2. ⚪ 配置验证与提示

---

## 📋 下一步行动

1. **实现 OcrChandraService** - API 封装
2. **实现 OcrParser** - 输出解析
3. **实现 OcrDirectAsyncConverter** - 核心转换器
4. **扩展配置参数** - config/parser.py
5. **测试集成** - 端到端测试
6. **UI 集成** - Streamlit 界面

---

## 🎯 成功标准

- ✅ 支持并发处理 (可配置并发数)
- ✅ 支持批处理 (可配置批次大小和休息间隔)
- ✅ 支持 API 密钥池 (多密钥轮询)
- ✅ 支持重试机制 (指数退避)
- ✅ 支持图像预处理 (resize, format conversion)
- ✅ 支持所有输出格式 (HTML, Markdown, JSON, Chunk)
- ✅ 支持页码锚点系统
- ✅ 代码质量与现有代码一致
- ✅ 完整的错误处理和日志

准备开始实现！
