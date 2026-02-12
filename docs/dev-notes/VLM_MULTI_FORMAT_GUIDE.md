# VLM模式多格式输出指南

## 概述

VLM模式现在支持与流水线模式相同的多格式输出能力!通过新增的`MarkdownDocumentBuilder`和渲染器支持,VLM模式可以输出:

- **Markdown** (默认,向后兼容)
- **HTML** (网页格式)
- **JSON** (结构化数据)
- **Chunks** (分块格式,适合RAG)
- **OCR JSON** (字符级数据)

## 架构设计

### 新架构流程

```
输入文件 → VLM API → Markdown字符串 → MarkdownDocumentBuilder → Document对象 → 渲染器 → 多格式输出
                                    ↓
                              (可选,向后兼容)
                            直接返回Markdown字符串
```

### 核心组件

1. **MarkdownDocumentBuilder** ([marker/builders/markdown.py](marker/builders/markdown.py))
   - 将Markdown字符串解析成Document对象
   - 支持页面分隔符识别
   - 支持页码锚点提取
   - 创建轻量级Block结构

2. **VlmDirectAsyncConverter** (增强版)
   - 新增`renderer`参数: 指定渲染器类路径
   - 新增`use_markdown_builder`参数: 是否构建Document对象
   - 保持向后兼容: 默认返回Markdown字符串

## 使用方法

### 方式1: 默认Markdown输出 (向后兼容)

```python
from marker.converters.vlm_direct_async import VlmDirectAsyncConverter

config = {
    "vlm_direct_base_url": "https://api.openai.com/v1",
    "vlm_direct_model": "gpt-4o",
    "vlm_direct_api_key": "sk-...",
}

converter = VlmDirectAsyncConverter(config)
markdown_string = converter("document.pdf")  # 返回 str

# 保存
with open("output.md", "w") as f:
    f.write(markdown_string)
```

**特点:**
- 返回类型: `str`
- 无元数据
- 最简单,最快速
- 完全向后兼容

---

### 方式2: Markdown + 元数据

```python
from marker.converters.vlm_direct_async import VlmDirectAsyncConverter
from marker.output import save_output

config = {
    "vlm_direct_base_url": "https://api.openai.com/v1",
    "vlm_direct_model": "gpt-4o",
    "vlm_direct_api_key": "sk-...",
    "renderer": "marker.renderers.markdown.MarkdownRenderer",  # 指定渲染器
}

converter = VlmDirectAsyncConverter(config)
output = converter("document.pdf")  # 返回 MarkdownOutput 对象

# 访问内容
print(output.markdown)      # Markdown文本
print(output.metadata)      # 元数据 (页数, 统计等)
print(output.images)        # 提取的图像 (VLM模式为空)

# 保存 (自动保存 .md 和 _meta.json)
save_output(output, "output_dir", "document")
```

**特点:**
- 返回类型: `MarkdownOutput`
- 包含元数据
- 可使用`save_output()`统一保存

---

### 方式3: HTML输出

```python
config = {
    "vlm_direct_base_url": "https://api.openai.com/v1",
    "vlm_direct_model": "gpt-4o",
    "vlm_direct_api_key": "sk-...",
    "renderer": "marker.renderers.html.HTMLRenderer",  # HTML渲染器
}

converter = VlmDirectAsyncConverter(config)
output = converter("document.pdf")  # 返回 HTMLOutput 对象

# 访问内容
print(output.html)          # HTML文本
print(output.metadata)      # 元数据
print(output.images)        # 提取的图像

# 保存 (自动保存 .html 和 _meta.json)
save_output(output, "output_dir", "document")
```

**特点:**
- 返回类型: `HTMLOutput`
- 完整的HTML文档
- 支持分页显示
- 支持Block ID标注

---

### 方式4: JSON输出 (结构化)

```python
config = {
    "vlm_direct_base_url": "https://api.openai.com/v1",
    "vlm_direct_model": "gpt-4o",
    "vlm_direct_api_key": "sk-...",
    "renderer": "marker.renderers.json.JSONRenderer",  # JSON渲染器
}

converter = VlmDirectAsyncConverter(config)
output = converter("document.pdf")  # 返回 JSONOutput 对象

# 访问内容
print(output.block_type)    # "Document"
print(output.children)      # 子Block列表 (层级结构)
print(output.metadata)      # 元数据

# 遍历Block
for block in output.children:
    print(f"Block ID: {block.id}")
    print(f"Block Type: {block.block_type}")
    print(f"HTML: {block.html}")
    print(f"BBox: {block.bbox}")
    print(f"Polygon: {block.polygon}")

# 保存 (自动保存 .json 和 _meta.json)
save_output(output, "output_dir", "document")
```

**特点:**
- 返回类型: `JSONOutput`
- 层级结构 (Document → Page → Block)
- 包含边界框和多边形
- 适合程序化处理

---

### 方式5: Chunks输出 (适合RAG)

```python
config = {
    "vlm_direct_base_url": "https://api.openai.com/v1",
    "vlm_direct_model": "gpt-4o",
    "vlm_direct_api_key": "sk-...",
    "renderer": "marker.renderers.chunk.ChunkRenderer",  # Chunk渲染器
}

converter = VlmDirectAsyncConverter(config)
output = converter("document.pdf")  # 返回 ChunkOutput 对象

# 访问内容
print(output.blocks)        # 扁平化的Block列表
print(output.page_info)     # 页面几何信息
print(output.metadata)      # 元数据

# 遍历Chunk
for block in output.blocks:
    print(f"Block ID: {block.id}")
    print(f"Page: {block.page}")
    print(f"HTML: {block.html}")
    print(f"Section: {block.section_hierarchy}")

# 保存 (自动保存 .json 和 _meta.json)
save_output(output, "output_dir", "document")
```

**特点:**
- 返回类型: `ChunkOutput`
- 扁平化结构 (无嵌套)
- 每个Block包含页码
- 适合RAG/向量数据库

---

## 配置参数

### VLM基础配置

```python
config = {
    # API配置
    "vlm_direct_base_url": "https://api.openai.com/v1",
    "vlm_direct_model": "gpt-4o",
    "vlm_direct_api_key": "sk-...",

    # 并发配置
    "vlm_direct_max_concurrent": 5,  # 并发数

    # 图像配置
    "vlm_direct_image_format": "jpeg",  # jpeg, png, webp
    "vlm_direct_max_image_dimension": 2048,
    "vlm_direct_jpeg_quality": 90,
    "vlm_direct_dpi": 144,

    # 提示词配置
    "vlm_direct_prompt": "Convert to Markdown...",

    # 页面分隔符
    "vlm_direct_page_separator": "\\n\\n---\\n\\n",

    # 页码锚点
    "vlm_direct_enable_page_anchors": True,
    "vlm_direct_page_anchor_template": "{n}",
    "vlm_direct_page_anchor_wrapper": "{{{}}}",
    "vlm_direct_page_anchor_position": "before",  # before, after, both
    "vlm_direct_extract_printed_pages": True,
}
```

### 渲染器配置

```python
config = {
    # ... VLM基础配置 ...

    # 渲染器选择 (可选)
    "renderer": "marker.renderers.markdown.MarkdownRenderer",
    # 或
    # "renderer": "marker.renderers.html.HTMLRenderer",
    # "renderer": "marker.renderers.json.JSONRenderer",
    # "renderer": "marker.renderers.chunk.ChunkRenderer",

    # 是否构建Document对象 (可选,指定renderer时自动启用)
    "use_markdown_builder": False,
}
```

## 对比: VLM模式 vs 流水线模式

| 特性 | VLM模式 | 流水线模式 |
|------|---------|------------|
| **输入处理** | 图像 → VLM API | PDF → Layout → OCR → 结构化 |
| **Document构建** | Markdown → 轻量级Document | 完整的Document对象 |
| **Block结构** | 简化 (每页一个Text block) | 完整 (Text, Table, Figure等) |
| **布局信息** | 无 (虚拟边界框) | 完整 (真实坐标) |
| **OCR数据** | 无 | 完整 (字符级) |
| **渲染器支持** | ✅ 支持 (新增) | ✅ 支持 |
| **输出格式** | Markdown, HTML, JSON, Chunks | Markdown, HTML, JSON, Chunks, OCR JSON |
| **元数据** | 基础 | 丰富 |
| **图像提取** | 不支持 | 支持 |
| **速度** | 快 (并发VLM调用) | 慢 (多阶段处理) |
| **准确性** | 依赖VLM | 依赖Layout+OCR |
| **适用场景** | 快速转换, 简单文档 | 复杂文档, 需要精确布局 |

## 实现细节

### MarkdownDocumentBuilder

**功能:**
1. 分割页面 (通过分隔符或页码锚点)
2. 为每页创建PageGroup
3. 为每页创建Text block
4. 构建Document对象

**限制:**
- 每页只有一个Text block (简化结构)
- 无真实布局信息 (使用虚拟边界框)
- 无图像提取
- 无OCR数据

**代码位置:** [marker/builders/markdown.py](marker/builders/markdown.py)

### VlmDirectAsyncConverter增强

**新增功能:**
1. `renderer`参数: 指定渲染器类路径
2. `use_markdown_builder`参数: 是否构建Document
3. 自动解析渲染器依赖
4. 向后兼容: 默认返回字符串

**代码位置:** [marker/converters/vlm_direct_async.py](marker/converters/vlm_direct_async.py)

## 测试

运行测试脚本:

```bash
# 设置API密钥
export OPENAI_API_KEY="sk-..."

# 准备测试文件
cp your_document.pdf test.pdf

# 运行测试
python test_vlm_renderer.py
```

测试脚本会生成:
- `output_markdown.md` - 纯Markdown
- `output_markdown_renderer.md` + `_meta.json` - Markdown + 元数据
- `output_html.html` + `_meta.json` - HTML
- `output_json.json` + `_meta.json` - 结构化JSON
- `output_chunks.json` + `_meta.json` - 分块JSON

## 最佳实践

### 1. 选择合适的输出格式

- **纯Markdown**: 简单文档, 只需文本
- **Markdown + 元数据**: 需要统计信息
- **HTML**: 网页展示, 需要样式
- **JSON**: 程序化处理, 需要结构
- **Chunks**: RAG应用, 向量数据库

### 2. 性能优化

```python
config = {
    # 增加并发数 (根据API限制)
    "vlm_direct_max_concurrent": 10,

    # 降低图像质量 (加快上传)
    "vlm_direct_jpeg_quality": 85,
    "vlm_direct_max_image_dimension": 1536,

    # 使用更快的模型
    "vlm_direct_model": "gpt-4o-mini",
}
```

### 3. 成本优化

```python
config = {
    # 使用更便宜的模型
    "vlm_direct_model": "gpt-4o-mini",

    # 降低图像分辨率
    "vlm_direct_dpi": 96,
    "vlm_direct_max_image_dimension": 1024,

    # 减少token输出
    "vlm_direct_max_tokens": 4096,
}
```

### 4. 准确性优化

```python
config = {
    # 使用最强模型
    "vlm_direct_model": "gpt-4o",

    # 提高图像质量
    "vlm_direct_dpi": 200,
    "vlm_direct_max_image_dimension": 2048,
    "vlm_direct_jpeg_quality": 95,

    # 自定义提示词
    "vlm_direct_prompt": """详细的提示词...""",
}
```

## 常见问题

### Q1: 为什么VLM模式的JSON输出比流水线模式简单?

**A:** VLM模式生成的Document是轻量级的,每页只有一个Text block,没有详细的布局信息。流水线模式有完整的Layout和OCR数据,因此JSON更详细。

### Q2: 可以让VLM直接返回JSON吗?

**A:** 不推荐。VLM生成JSON容易出现语法错误,而生成Markdown更可靠。当前方案是VLM生成Markdown,然后本地解析成JSON,更稳定。

### Q3: VLM模式支持图像提取吗?

**A:** 目前不支持。VLM模式返回的是纯文本,没有图像提取功能。如需图像提取,请使用流水线模式。

### Q4: 如何统一VLM和流水线模式的输出?

**A:** 使用相同的渲染器即可:

```python
# VLM模式
vlm_config = {"renderer": "marker.renderers.json.JSONRenderer"}
vlm_converter = VlmDirectAsyncConverter(vlm_config)
vlm_output = vlm_converter("doc.pdf")

# 流水线模式
pdf_config = {"renderer": "marker.renderers.json.JSONRenderer"}
pdf_converter = PdfConverter(renderer="marker.renderers.json.JSONRenderer", config=pdf_config)
pdf_output = pdf_converter("doc.pdf")

# 两者都返回 JSONOutput 对象,可以用相同方式处理
save_output(vlm_output, ".", "vlm_doc")
save_output(pdf_output, ".", "pdf_doc")
```

### Q5: 性能如何?

**A:** VLM模式的性能瓶颈在VLM API调用,Document构建和渲染非常快(<1秒)。总体性能主要取决于:
- VLM API响应时间
- 并发数设置
- 文档页数

## 总结

通过新增的`MarkdownDocumentBuilder`和渲染器支持,VLM模式现在可以:

✅ 输出多种格式 (Markdown, HTML, JSON, Chunks)
✅ 包含元数据
✅ 使用统一的`save_output()`保存
✅ 与流水线模式架构对齐
✅ 保持向后兼容

**推荐使用场景:**
- 快速文档转换 → VLM模式 + Markdown
- 网页展示 → VLM模式 + HTML
- RAG应用 → VLM模式 + Chunks
- 复杂文档 + 精确布局 → 流水线模式

**下一步:**
- 增强MarkdownDocumentBuilder,支持更多Block类型识别
- 添加图像提取支持
- 优化Markdown解析准确性
