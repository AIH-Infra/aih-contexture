# 經緯 · Contexture 完整技术文档

> **将PDF转化为结构化知识，以页码锚点守护学术伦理**
> ——面向下一代的人文学科材料基础设施

---

## 目录

1. [项目概述](#1-项目概述)
2. [核心架构](#2-核心架构)
3. [三种转换模式](#3-三种转换模式)
4. [版面识别后端](#4-版面识别后端)
5. [OCR后端](#5-ocr后端)
6. [页码锚点系统](#6-页码锚点系统)
7. [处理器配置](#7-处理器配置)
8. [配置管理系统](#8-配置管理系统)
9. [API与命令行](#9-api与命令行)
10. [开发指南](#10-开发指南)

---

## 1. 项目概述

### 1.1 设计理念

Contexture（經緯）是一个面向人文学科的文献结构化提取平台，核心目标是：

1. **结构化提取**：将PDF文档转化为可机器处理的Markdown/JSON格式
2. **页码锚点**：保留原始页码信息，确保学术引用的可追溯性
3. **灵活架构**：支持从简单的文本提取到复杂的OCR识别多种场景

### 1.2 典型使用场景

| 场景 | 推荐模式 | 配置要点 |
|------|----------|----------|
| 现代出版物（已有文本层） | Pipeline + 禁用OCR | 快速提取结构，无需OCR |
| 扫描件/图片PDF | Pipeline + Surya OCR | 本地OCR，保护隐私 |
| 历史文献/古籍 | VLM特化 + Chandra | 专业OCR模型，高准确率 |
| 批量处理/云端部署 | VLM泛化 + GPT-4V | 异步并发，速度快 |

### 1.3 项目结构

```
Contexture/
├── aih_contexture/
│   ├── converters/          # 转换器（核心处理逻辑）
│   │   ├── pdf.py           # Pipeline模式转换器
│   │   ├── vlm_direct_async.py  # VLM泛化模式转换器
│   │   └── ocr_direct_async.py  # VLM特化模式转换器
│   ├── builders/            # 构建器（文档结构构建）
│   ├── processors/          # 处理器（后处理逻辑）
│   ├── renderers/           # 渲染器（输出格式）
│   ├── services/            # 外部服务（API调用）
│   ├── schema/              # 数据模型
│   ├── scripts/             # 脚本入口
│   │   └── streamlit_app.py # Web UI
│   └── utils/               # 工具函数
├── configs/                 # 配置文件存储
└── assets/                  # 静态资源
```

---

## 2. 核心架构

### 2.1 处理流程总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        输入: PDF文件                              │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      模式选择 (conversion_mode)                   │
├─────────────────┬─────────────────────┬─────────────────────────┤
│    Pipeline     │    VLM 泛化         │      VLM 特化            │
│   (pipeline)    │  (vlm_generalized)  │   (vlm_specialized)     │
└────────┬────────┴──────────┬──────────┴────────────┬────────────┘
         │                   │                       │
         ▼                   ▼                       ▼
┌────────────────┐  ┌────────────────┐     ┌────────────────┐
│ 版面识别       │  │ 页面渲染为图像  │     │ 页面渲染为图像  │
│ (Layout)       │  │                │     │                │
├────────────────┤  ├────────────────┤     ├────────────────┤
│ OCR识别        │  │ VLM API调用    │     │ 专用OCR API    │
│ (可选)         │  │ (GPT-4V等)     │     │ (Chandra等)    │
├────────────────┤  ├────────────────┤     ├────────────────┤
│ 结构化处理     │  │ Markdown解析   │     │ 结构化输出     │
│ (Processors)   │  │                │     │                │
└────────┬───────┘  └────────┬───────┘     └────────┬───────┘
         │                   │                       │
         ▼                   ▼                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    输出: Markdown / JSON / HTML                   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 代码入口点

**Web UI 入口** (`streamlit_app.py`):
```python
# 第866行: 模式选择
conversion_mode = st.radio(
    "选择转换模式",
    options=["pipeline", "vlm_generalized", "vlm_specialized"],
    ...
)
```

**模式分发逻辑** (`build_config_dict` 函数, 第278行):
```python
def build_config_dict(config_params: dict) -> dict:
    conversion_mode = config_params.get("conversion_mode", "pipeline")

    if conversion_mode == "vlm_specialized":
        # VLM特化模式: 使用 OcrDirectAsyncConverter
        return {...}

    # Pipeline 和 VLM泛化模式: 使用 PdfConverter
    return {...}
```

---

## 3. 三种转换模式

### 3.1 Pipeline 模式 (默认)

**适用场景**: 现代出版物、需要精细控制的场景

**处理流程**:
```
PDF → 版面识别 → [OCR识别] → 结构化处理 → 渲染输出
```

**关键配置项**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `layout_backend` | str | "surya" | 版面识别后端 |
| `ocr_backend` | str | "none" | OCR后端（none=禁用） |
| `force_ocr` | bool | False | 强制OCR |
| `use_llm` | bool | False | 启用LLM增强 |

**代码实现** (`converters/pdf.py`):
```python
class PdfConverter(BaseConverter):
    """Pipeline模式的核心转换器"""

    def __call__(self, filepath: str) -> RenderedDocument:
        # 1. 加载文档
        provider = self.resolve_provider(filepath)

        # 2. 版面识别
        layout_builder = self.resolve_builder("layout")
        layout_builder(provider)

        # 3. OCR识别（如果启用）
        if self.config.ocr_backend != "none":
            ocr_builder = self.resolve_builder("ocr")
            ocr_builder(provider)

        # 4. 运行处理器链
        for processor in self.processors:
            processor(provider)

        # 5. 渲染输出
        return self.renderer(provider)
```

### 3.2 VLM 泛化模式

**适用场景**: 批量处理、云端部署、需要快速结果的场景

**处理流程**:
```
PDF → 页面渲染为图像 → VLM API 调用 → Markdown 解析 → 输出
```

**核心特点**:
- 使用通用 VLM（如 GPT-4V、Gemini、Claude）直接识别页面
- 支持多 API Key 轮询，提高并发能力
- 输出格式固定为 Markdown

**支持的 API 提供商**:

| 提供商 | 配置键前缀 | 说明 |
|--------|-----------|------|
| OpenAI 兼容 | `vlm_direct_*` | 支持任何 OpenAI 兼容 API |
| Google Gemini | `vlm_gemini_*` | Gemini 原生 API |
| Anthropic Claude | `vlm_anthropic_*` | Claude 原生 API |

**关键配置项**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `vlm_api_provider` | str | "openai_compatible" | API 提供商类型 |
| `vlm_direct_base_url` | str | - | API 端点 URL |
| `vlm_direct_model` | str | - | 模型名称 |
| `vlm_direct_api_key` | str | - | API Key（支持多个） |
| `vlm_direct_max_concurrent` | int | 5 | 页面并发数 |
| `vlm_concurrency_mode` | str | "serial_file" | 并发模式 |

**并发模式说明**:

| 模式 | 适用场景 | 说明 |
|------|----------|------|
| `serial_file` | 多页 PDF | 逐个文件处理，文件内页面并行 |
| `batch_single_page` | 扫描图片 | 多个单页文件同时处理 |

### 3.3 VLM 特化模式

**适用场景**: 历史文献、古籍、手写文档等需要专业 OCR 的场景

**处理流程**:
```
PDF → 页面渲染为图像 → 专用 OCR API → 结构化输出
```

**核心特点**:
- 使用专门训练的 OCR 模型（如 Chandra）
- 支持本地部署（LM Studio）
- 输出格式支持 Markdown、JSON、HTML

**关键配置项**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `ocr_endpoint` | str | "http://localhost:1234/v1" | OCR API 端点 |
| `ocr_model` | str | "chandra-ocr@f16" | OCR 模型名称 |
| `ocr_api_key` | str | "" | API Key（可选） |
| `ocr_image_format` | str | "jpeg" | 图像格式 |
| `ocr_resize_max` | int | 2048 | 最大图像尺寸 |
| `ocr_image_quality` | int | 60 | JPEG 压缩质量 |

---

## 4. 版面识别后端

版面识别是 Pipeline 模式的核心组件，用于检测文档结构（文本块、图片、表格等）。

### 4.1 后端对比

| 后端 | 特点 | 适用场景 | 依赖 |
|------|------|----------|------|
| **Surya** | 内置深度学习模型，开箱即用 | 通用文档（推荐） | 无需额外配置 |
| **VLM** | 使用视觉语言模型 | 复杂版面、需要语义理解 | 需要 API |
| **YOLO** | DocLayout-YOLO 模型 | 高精度需求 | 需要 Docker |

### 4.2 Surya 后端（默认）

**配置项**: 无需额外配置，开箱即用

**代码位置**: `builders/layout.py`

```python
# Surya 版面识别流程
class LayoutBuilder:
    def __call__(self, provider):
        # 使用 Surya 模型检测版面元素
        layout_results = self.surya_model.detect(provider.pages)
        for page, result in zip(provider.pages, layout_results):
            page.layout = result
```

### 4.3 VLM 后端

使用视觉语言模型进行版面识别，适合复杂版面。

**配置项**:

| 参数 | 说明 |
|------|------|
| `vlm_layout_provider` | API 提供商 |
| `vlm_layout_base_url` | API 端点 |
| `vlm_layout_model` | 模型名称 |
| `vlm_layout_api_key` | API Key |

### 4.4 YOLO 后端

使用 DocLayout-YOLO 模型，需要 Docker 服务。

**配置项**:

| 参数 | 说明 |
|------|------|
| `yolo_service_url` | YOLO 服务地址 |
| `yolo_confidence` | 置信度阈值 |

---

## 5. OCR后端

OCR 后端用于从图像中提取文本，仅在 Pipeline 模式下使用。

### 5.1 后端对比

| 后端 | 特点 | 适用场景 |
|------|------|----------|
| **none** | 禁用 OCR，使用 PDF 内嵌文本 | 现代出版物（推荐） |
| **surya** | 内置 OCR 模型 | 扫描件、图片 PDF |
| **calamari** | 高精度 OCR | 历史文献 |
| **vlm** | 使用 VLM 进行 OCR | 复杂文档 |

### 5.2 禁用 OCR（默认）

现代出版物通常已有高质量文本层，无需 OCR。

```python
# 配置示例
config = {
    "ocr_backend": "none",
    "force_ocr": False
}
```

### 5.3 Surya OCR

本地 OCR，保护隐私。

```python
config = {
    "ocr_backend": "surya",
    "force_ocr": True  # 强制使用 OCR
}
```

---

## 6. 页码锚点系统

页码锚点是 Contexture 的核心特性，用于保留原始页码信息，确保学术引用的可追溯性。

### 6.1 设计理念

在人文学科研究中，准确的页码引用至关重要。页码锚点系统在输出的 Markdown 中插入页码标记，格式为 `{n}`（n 为页码）。

### 6.2 配置项

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enable_page_anchors` | bool | True | 启用页码锚点 |
| `page_anchor_position` | str | "before" | 锚点位置 |

**锚点位置选项**:
- `before`: 页面内容之前（推荐）
- `after`: 页面内容之后

### 6.3 输出示例

```markdown
{1}

# 第一章 绪论

这是第一页的内容...

{2}

## 1.1 研究背景

这是第二页的内容...
```

---

## 7. 处理器配置

处理器是 Pipeline 模式的后处理组件，用于优化输出格式。

### 7.1 文本处理器

| 处理器 | 默认 | 说明 |
|--------|------|------|
| Markdown 噪音清理 | ✅ | 清理 OCR 识别出的特殊符号 |
| 行合并 | ✅ | 合并同一段落的多行文本 |
| 引用块检测 | ✅ | 检测缩进的引用块 |

### 7.2 结构处理器

| 处理器 | 默认 | 说明 |
|--------|------|------|
| 章节标题检测 | ✅ | 识别章节标题层级 |
| 脚注处理 | ✅ | 处理页面脚注 |
| 目录生成 | ❌ | 自动生成文档目录 |

### 7.3 表格处理器

| 处理器 | 默认 | 说明 |
|--------|------|------|
| 表格检测 | ✅ | 检测并提取表格 |
| 表格合并 | ❌ | 合并跨页表格 |

---

## 8. 配置管理系统

配置管理系统支持保存、加载、导出和导入配置。

### 8.1 配置文件结构

配置文件存储在 `configs/` 目录，格式为 JSON。

```json
{
  "meta": {
    "version": "1.0.0",
    "name": "配置名称",
    "description": "配置描述",
    "created_at": "2026-02-09T10:30:00",
    "updated_at": "2026-02-09T10:30:00"
  },
  "global": {
    "conversion_mode": "pipeline",
    "enable_page_anchors": true
  },
  "pipeline": { ... },
  "vlm_generalized": { ... },
  "vlm_specialized": { ... }
}
```

### 8.2 API Key 处理

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `exclude` | 不保存 API Key | 公开分享 |
| `placeholder` | 保存为占位符 | 团队分享 |
| `include` | 保存实际值 | 个人备份 |

### 8.3 ConfigManager 类

**代码位置**: `utils/config_manager.py`

```python
from aih_contexture.utils.config_manager import ConfigManager

manager = ConfigManager()

# 列出所有配置
configs = manager.list_configs()

# 保存配置
manager.save_config("my_config", config_data)

# 加载配置
config = manager.load_config("my_config")
```

---

## 9. API与命令行

### 9.1 Web UI

启动 Web UI：

```bash
streamlit run aih_contexture/scripts/streamlit_app.py
```

### 9.2 命令行接口

```bash
# 单文件转换
python convert_single.py input.pdf -o output/

# 批量转换
python convert.py input_dir/ -o output_dir/
```

---

## 10. 开发指南

### 10.1 环境配置

```bash
# 安装依赖
pip install -r requirements.txt

# 运行测试
pytest tests/
```

### 10.2 添加新处理器

```python
# processors/my_processor.py
from aih_contexture.processors.base import BaseProcessor

class MyProcessor(BaseProcessor):
    def __call__(self, document):
        for page in document.pages:
            # 处理逻辑
            pass
        return document
```

### 10.3 核心类关系

```
BaseConverter
├── PdfConverter (Pipeline 模式)
├── VlmDirectAsyncConverter (VLM 泛化模式)
└── OcrDirectAsyncConverter (VLM 特化模式)

BaseBuilder
├── LayoutBuilder
├── OcrBuilder
└── StructureBuilder

BaseProcessor
├── TextProcessor
├── TableProcessor
└── ...
```

### 10.4 UI 状态管理

Streamlit 使用 `session_state` 管理组件状态：

```python
# 初始化状态
if "conversion_mode" not in st.session_state:
    st.session_state.conversion_mode = "pipeline"

# 读取状态
mode = st.session_state.conversion_mode
```

---

## 附录

### A. 快速参考

| 场景 | 模式 | 配置 |
|------|------|------|
| 现代出版物 | Pipeline | Surya + 禁用OCR |
| 扫描件 | Pipeline | Surya + Surya OCR |
| 历史文献 | VLM特化 | Chandra |
| 批量处理 | VLM泛化 | GPT-4V/Gemini |

### B. 关键文件索引

| 文件 | 用途 |
|------|------|
| `scripts/streamlit_app.py` | Web UI 入口 |
| `converters/pdf.py` | Pipeline 转换器 |
| `converters/vlm_direct_async.py` | VLM泛化转换器 |
| `converters/ocr_direct_async.py` | VLM特化转换器 |
| `utils/config_manager.py` | 配置管理 |

---

> **文档版本**: 1.0.0
> **最后更新**: 2026-02-09
> **项目主页**: Contexture / 經緯
