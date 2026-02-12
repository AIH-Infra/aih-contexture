# VLM多格式输出 - 快速参考

## 一句话总结

VLM模式现在支持输出Markdown、HTML、JSON、Chunks等多种格式,与流水线模式架构对齐!

## 快速开始

### 1. 默认Markdown (向后兼容)

```python
from marker.converters.vlm_direct_async import VlmDirectAsyncConverter

converter = VlmDirectAsyncConverter({"vlm_direct_api_key": "sk-..."})
markdown = converter("doc.pdf")  # 返回 str
```

### 2. Markdown + 元数据

```python
config = {"vlm_direct_api_key": "sk-...", "renderer": "marker.renderers.markdown.MarkdownRenderer"}
converter = VlmDirectAsyncConverter(config)
output = converter("doc.pdf")  # 返回 MarkdownOutput
print(output.markdown, output.metadata)
```

### 3. HTML输出

```python
config = {"vlm_direct_api_key": "sk-...", "renderer": "marker.renderers.html.HTMLRenderer"}
converter = VlmDirectAsyncConverter(config)
output = converter("doc.pdf")  # 返回 HTMLOutput
print(output.html)
```

### 4. JSON输出 (结构化)

```python
config = {"vlm_direct_api_key": "sk-...", "renderer": "marker.renderers.json.JSONRenderer"}
converter = VlmDirectAsyncConverter(config)
output = converter("doc.pdf")  # 返回 JSONOutput
print(output.children)  # Block列表
```

### 5. Chunks输出 (RAG)

```python
config = {"vlm_direct_api_key": "sk-...", "renderer": "marker.renderers.chunk.ChunkRenderer"}
converter = VlmDirectAsyncConverter(config)
output = converter("doc.pdf")  # 返回 ChunkOutput
print(output.blocks)  # 扁平化Block列表
```

## 渲染器对照表

| 渲染器 | 返回类型 | 用途 | 特点 |
|--------|----------|------|------|
| 无 (默认) | `str` | 简单转换 | 纯Markdown字符串 |
| `MarkdownRenderer` | `MarkdownOutput` | Markdown + 元数据 | 包含统计信息 |
| `HTMLRenderer` | `HTMLOutput` | 网页展示 | 完整HTML文档 |
| `JSONRenderer` | `JSONOutput` | 程序化处理 | 层级结构 |
| `ChunkRenderer` | `ChunkOutput` | RAG/向量库 | 扁平化结构 |

## 保存输出

```python
from marker.output import save_output

# 自动根据类型保存 (.md, .html, .json + _meta.json)
save_output(output, "output_dir", "filename")
```

## 核心文件

- [marker/builders/markdown.py](marker/builders/markdown.py) - MarkdownDocumentBuilder
- [marker/converters/vlm_direct_async.py](marker/converters/vlm_direct_async.py) - 增强的VLM转换器
- [test_vlm_renderer.py](test_vlm_renderer.py) - 测试脚本
- [VLM_MULTI_FORMAT_GUIDE.md](VLM_MULTI_FORMAT_GUIDE.md) - 完整文档

## 测试

```bash
export OPENAI_API_KEY="sk-..."
python test_vlm_renderer.py
```

## 架构

```
VLM API → Markdown → MarkdownDocumentBuilder → Document → 渲染器 → 多格式输出
```

## 对比

| 特性 | VLM模式 | 流水线模式 |
|------|---------|------------|
| 速度 | 快 | 慢 |
| 布局精度 | 低 (虚拟) | 高 (真实) |
| 渲染器支持 | ✅ | ✅ |
| 输出格式 | Markdown, HTML, JSON, Chunks | 全部 + OCR JSON |
| 图像提取 | ❌ | ✅ |

## 推荐

- **快速转换** → VLM + Markdown
- **网页展示** → VLM + HTML
- **RAG应用** → VLM + Chunks
- **复杂文档** → 流水线模式
