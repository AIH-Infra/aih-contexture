# VLM多格式输出功能 - 更新说明

## 🎉 新功能

VLM模式现在支持与流水线模式相同的多格式输出能力!

### 支持的输出格式

- ✅ **Markdown** (默认,向后兼容)
- ✅ **HTML** (网页展示)
- ✅ **JSON** (结构化数据)
- ✅ **Chunks** (RAG应用)
- ✅ **元数据支持**

## 快速开始

### 默认Markdown输出

```python
from marker.converters.vlm_direct_async import VlmDirectAsyncConverter

converter = VlmDirectAsyncConverter({"vlm_direct_api_key": "sk-..."})
markdown = converter("doc.pdf")  # 返回 str
```

### HTML输出

```python
config = {
    "vlm_direct_api_key": "sk-...",
    "renderer": "marker.renderers.html.HTMLRenderer"
}
converter = VlmDirectAsyncConverter(config)
html_output = converter("doc.pdf")  # 返回 HTMLOutput
```

### JSON输出

```python
config = {
    "vlm_direct_api_key": "sk-...",
    "renderer": "marker.renderers.json.JSONRenderer"
}
converter = VlmDirectAsyncConverter(config)
json_output = converter("doc.pdf")  # 返回 JSONOutput
```

### Chunks输出 (RAG)

```python
config = {
    "vlm_direct_api_key": "sk-...",
    "renderer": "marker.renderers.chunk.ChunkRenderer"
}
converter = VlmDirectAsyncConverter(config)
chunks_output = converter("doc.pdf")  # 返回 ChunkOutput
```

## 核心改进

### 1. 新增MarkdownDocumentBuilder

将VLM生成的Markdown解析成Document对象,使其可以使用渲染器系统。

**文件:** [marker/builders/markdown.py](marker/builders/markdown.py)

### 2. 增强VlmDirectAsyncConverter

添加可选的渲染器支持,保持向后兼容。

**新增配置:**
- `renderer`: 渲染器类路径
- `use_markdown_builder`: 是否构建Document对象

### 3. 架构统一

```
VLM模式:
输入 → VLM API → Markdown → MarkdownDocumentBuilder → Document → 渲染器 → 多格式输出

流水线模式:
输入 → Layout → OCR → Document → 渲染器 → 多格式输出
```

## 文档

- 📖 [完整使用指南](VLM_MULTI_FORMAT_GUIDE.md)
- 📋 [快速参考](VLM_MULTI_FORMAT_QUICKREF.md)
- 📝 [实施说明](VLM_UNIFIED_IMPLEMENTATION.md)

## 示例

- 🧪 [完整测试](test_vlm_renderer.py)
- 💡 [简单示例](example_vlm_formats.py)

## 运行测试

```bash
export OPENAI_API_KEY="sk-..."
python test_vlm_renderer.py
```

## 对比

| 特性 | VLM模式 | 流水线模式 |
|------|---------|------------|
| 速度 | ⚡ 快 | 🐢 慢 |
| 渲染器支持 | ✅ | ✅ |
| 输出格式 | Markdown, HTML, JSON, Chunks | 全部 + OCR JSON |
| 布局精度 | 虚拟 | 真实 |
| 图像提取 | ❌ | ✅ |

## 推荐场景

- **快速转换** → VLM + Markdown
- **网页展示** → VLM + HTML
- **RAG应用** → VLM + Chunks
- **复杂文档** → 流水线模式

## 向后兼容

✅ 完全向后兼容!默认行为不变,仍然返回Markdown字符串。

## 更新日期

2026-01-28
