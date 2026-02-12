# 📚 Marker LLM 辅助功能完整指南

## 🎯 概述

Marker 的 LLM 辅助功能使用大语言模型（如 Gemini）来提升 PDF 文档转换的质量。LLM 在 OCR 和版面识别完成后，对特定类型的内容块进行后处理和优化。

## 🔧 工作原理

### 处理流程

```
PDF 输入
  ↓
版面识别 (Layout Detection)
  ↓
OCR 文本提取
  ↓
文档结构构建
  ↓
【LLM 辅助处理】← 在这个阶段发挥作用
  ├─ 表格优化
  ├─ 图片描述
  ├─ 公式修正
  ├─ 手写识别
  ├─ 复杂区域处理
  └─ 其他优化
  ↓
最终输出 (Markdown/HTML/JSON)
```

### 关键特点

1. **后处理阶段**：LLM 不参与 OCR，而是优化已识别的内容
2. **选择性处理**：只处理特定类型的块（表格、图片、公式等）
3. **并发执行**：使用线程池并发处理多个块，提高效率
4. **可选功能**：默认关闭，需要手动启用

## 📋 LLM 处理器列表

### 1. **LLMTableProcessor** - 表格优化
- **文件**: `marker/processors/llm/llm_table.py`
- **作用**: 修正表格 HTML 结构，确保列对齐正确
- **处理对象**: `BlockTypes.Table`, `BlockTypes.TableOfContents`
- **工作方式**:
  - 提取表格图像
  - 将现有 HTML 和图像发送给 LLM
  - LLM 对比图像和 HTML，修正错误
  - 更新表格 HTML
- **配置参数**:
  - `max_rows_per_batch`: 60（每批最多处理行数）
  - `max_table_rows`: 175（最大表格行数）
  - `max_table_iterations`: 2（最大重写迭代次数）

**示例提示词**:
```
You are a text correction expert specializing in accurately reproducing text from images.
You will receive an image and an html representation of the table in the image.
Your task is to correct any errors in the html representation...
```

### 2. **LLMTableMergeProcessor** - 表格合并
- **文件**: `marker/processors/llm/llm_table_merge.py`
- **作用**: 合并跨页的表格
- **处理对象**: 分散在多页的表格块
- **工作方式**: 识别并合并属于同一表格的多个块

### 3. **LLMImageDescriptionProcessor** - 图片描述生成
- **文件**: `marker/processors/llm/llm_image_description.py`
- **作用**: 为图片和图表生成文字描述
- **处理对象**: `BlockTypes.Picture`, `BlockTypes.Figure`
- **工作方式**:
  - 提取图片
  - 提取图片中的文本
  - LLM 生成详细描述
  - 替换或补充原有内容

**示例提示词**:
```
You are a document analysis expert who specializes in creating text descriptions for images.
You will receive an image of a picture or figure. Your job will be to create a short description...
```

### 4. **LLMEquationProcessor** - 公式修正
- **文件**: `marker/processors/llm/llm_equation.py`
- **作用**: 修正数学公式的 LaTeX 表示
- **处理对象**: `BlockTypes.Equation`
- **工作方式**: 对比图像和 LaTeX，修正错误

### 5. **LLMHandwritingProcessor** - 手写识别
- **文件**: `marker/processors/llm/llm_handwriting.py`
- **作用**: 识别和转录手写文本
- **处理对象**: 手写文本块
- **工作方式**: 使用 LLM 的视觉能力识别手写内容

### 6. **LLMFormProcessor** - 表单处理
- **文件**: `marker/processors/llm/llm_form.py`
- **作用**: 识别和结构化表单内容
- **处理对象**: 表单块
- **工作方式**: 提取表单字段和值

### 7. **LLMComplexRegionProcessor** - 复杂区域处理
- **文件**: `marker/processors/llm/llm_complex.py`
- **作用**: 处理复杂布局区域
- **处理对象**: 复杂布局块
- **工作方式**: 使用 LLM 理解和重构复杂内容

### 8. **LLMMathBlockProcessor** - 数学块处理
- **文件**: `marker/processors/llm/llm_mathblock.py`
- **作用**: 处理数学公式块
- **处理对象**: 数学块
- **工作方式**: 优化数学内容的表示

### 9. **LLMSectionHeaderProcessor** - 章节标题优化
- **文件**: `marker/processors/llm/llm_sectionheader.py`
- **作用**: 优化章节标题识别
- **处理对象**: 章节标题块
- **工作方式**: 改进标题层级和格式

### 10. **LLMPageCorrectionProcessor** - 页面修正
- **文件**: `marker/processors/llm/llm_page_correction.py`
- **作用**: 整体页面内容修正
- **处理对象**: 整页内容
- **工作方式**: 全局优化页面结构

## 🚀 如何启用 LLM 辅助

### 在 Streamlit GUI 中

1. **选择 OCR 后端**（Surya 或其他）
2. **勾选"🧠 启用 LLM 增强"**
3. **配置 LLM 服务**（在高级选项中）:
   - Gemini API Key
   - Gemini Model（可选）

### 在代码中

```python
from marker.converters.pdf import PdfConverter
from marker.scripts.common import load_models

# 加载模型
artifacts = load_models()

# 配置
config = {
    "use_llm": True,  # 启用 LLM
    "gemini_api_key": "your-api-key",  # Gemini API 密钥
    "gemini_model": "gemini-1.5-flash",  # 可选，默认模型
}

# 创建转换器
converter = PdfConverter(
    config=config,
    artifact_dict=artifacts
)

# 处理文档
document = converter.build_document("input.pdf")
```

## 🔑 支持的 LLM 服务

### 1. **Google Gemini**（默认）
- **类**: `GoogleGeminiService`
- **文件**: `marker/services/gemini.py`
- **配置**:
  ```python
  {
      "gemini_api_key": "your-key",
      "gemini_model": "gemini-1.5-flash"  # 或 gemini-1.5-pro
  }
  ```

### 2. **Claude**
- **类**: `ClaudeService`
- **文件**: `marker/services/claude.py`
- **配置**:
  ```python
  {
      "llm_service": "marker.services.claude.ClaudeService",
      "claude_api_key": "your-key",
      "claude_model": "claude-3-5-sonnet-20241022"
  }
  ```

### 3. **Ollama**（本地）
- **类**: `OllamaService`
- **文件**: `marker/services/ollama.py`
- **配置**:
  ```python
  {
      "llm_service": "marker.services.ollama.OllamaService",
      "ollama_base_url": "http://localhost:11434",
      "ollama_model": "llama3.2-vision"
  }
  ```

### 4. **Google Vertex AI**
- **类**: `GoogleVertexService`
- **文件**: `marker/services/vertex.py`
- **配置**:
  ```python
  {
      "llm_service": "marker.services.vertex.GoogleVertexService",
      "vertex_project_id": "your-project-id",
      "vertex_location": "us-central1"
  }
  ```

### 5. **Azure OpenAI**
- **类**: `AzureOpenAIService`
- **文件**: `marker/services/azure_openai.py`
- **配置**:
  ```python
  {
      "llm_service": "marker.services.azure_openai.AzureOpenAIService",
      "azure_endpoint": "https://your-resource.openai.azure.com",
      "azure_api_key": "your-key",
      "deployment_name": "gpt-4o",
      "azure_api_version": "2024-02-15-preview"
  }
  ```

## ⚙️ 高级配置

### 并发控制

```python
config = {
    "use_llm": True,
    "max_concurrency": 3,  # 最大并发请求数
}
```

### 图像扩展比例

```python
config = {
    "image_expansion_ratio": 0.01,  # 裁剪图像时的扩展比例
}
```

### 禁用进度条

```python
config = {
    "disable_tqdm": True,  # 禁用 tqdm 进度条
}
```

## 📊 性能影响

### 处理时间

- **不启用 LLM**: 1-2 分钟/页（取决于 OCR 后端）
- **启用 LLM**: 3-5 分钟/页（额外增加 2-3 分钟）

### API 成本（Gemini）

- **Gemini 1.5 Flash**: ~$0.01-0.02/页
- **Gemini 1.5 Pro**: ~$0.05-0.10/页

### 质量提升

- **表格准确率**: +15-25%
- **公式准确率**: +20-30%
- **图片描述**: 从无到有
- **整体可读性**: 显著提升

## 🎯 使用建议

### 何时启用 LLM

✅ **推荐启用**:
- 包含复杂表格的文档
- 包含大量公式的学术论文
- 包含图表需要描述的报告
- 手写内容较多的文档
- 对质量要求极高的场景

❌ **不推荐启用**:
- 纯文本文档
- 简单布局文档
- 对成本敏感的场景
- 需要快速处理的场景
- 批量处理大量文档

### 最佳实践

1. **先测试不启用 LLM**: 看基础 OCR 效果
2. **对比启用 LLM 后的效果**: 评估是否值得
3. **选择合适的 LLM 服务**:
   - Gemini Flash: 速度快，成本低
   - Gemini Pro: 质量高，成本高
   - Ollama: 本地运行，免费但需要 GPU
4. **调整并发数**: 根据 API 限制和成本控制

## 🔍 调试和日志

### 查看 LLM 处理日志

```python
from marker.logger import get_logger
logger = get_logger()
logger.setLevel("DEBUG")
```

### 常见日志信息

```
[LLMTableProcessor] Processing 5 tables
[LLMImageDescriptionProcessor] Generating descriptions for 3 images
[LLMEquationProcessor] Correcting 10 equations
```

## 📝 总结

LLM 辅助功能是 Marker 的高级特性，通过后处理优化提升文档转换质量。它：

1. **不替代 OCR**: 在 OCR 之后工作
2. **选择性处理**: 只处理特定类型的内容
3. **可配置**: 支持多种 LLM 服务
4. **有成本**: 需要 API 调用费用
5. **显著提升质量**: 特别是表格、公式、图片描述

根据你的需求和预算，合理选择是否启用 LLM 辅助功能。
